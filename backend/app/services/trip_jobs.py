from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import AgentRun, FlightOption, HotelOption, Itinerary, ItineraryDay, TripOption, TripRequest
from app.schemas.trip import TripCreateRequest
from app.services.agent_planner import TripPlanner
from app.services.job_runner import submit_background_job


def _trip_query():
    return (
        select(TripRequest)
        .options(
            joinedload(TripRequest.options).joinedload(TripOption.itinerary).joinedload(Itinerary.days),
            joinedload(TripRequest.itineraries).joinedload(Itinerary.days),
            joinedload(TripRequest.flight_options),
            joinedload(TripRequest.hotel_options),
            joinedload(TripRequest.agent_runs),
            joinedload(TripRequest.saved_trip),
        )
        .order_by(TripRequest.created_at.desc())
    )


def _trip_payload_from_trip(trip: TripRequest) -> TripCreateRequest:
    return TripCreateRequest(
        origin=trip.origin,
        start_date=trip.start_date,
        end_date=trip.end_date,
        destination_candidates=trip.destination_candidates,
        trip_style=trip.trip_style,
        budget_range=trip.budget_range,
        traveler_count=trip.traveler_count,
        pace_preference=trip.pace_preference,
    )


def _latest_agent_run(trip: TripRequest, kind: str) -> AgentRun | None:
    runs = [run for run in trip.agent_runs if run.kind == kind]
    if not runs:
        return None
    runs.sort(key=lambda run: run.created_at or 0)
    return runs[-1]


def _serialize_failure(exc: Exception) -> tuple[str, list[dict[str, str]]]:
    detail = str(exc).strip() or exc.__class__.__name__
    summary = "Agent execution failed before the trip workspace could be completed."
    steps = [
        {
            "agent": "orchestrator",
            "status": "failed",
            "detail": detail[:300],
        }
    ]
    return summary, steps


def schedule_trip_options_generation(trip_id: str) -> None:
    submit_background_job(_run_trip_options_generation, trip_id)


def schedule_itinerary_generation(trip_id: str, option_id: str) -> None:
    submit_background_job(_run_itinerary_generation, trip_id, option_id)


def _run_trip_options_generation(trip_id: str) -> None:
    db = SessionLocal()
    try:
        trip = db.scalars(_trip_query().where(TripRequest.id == trip_id)).unique().first()
        if not trip:
            return

        planner = TripPlanner(get_settings())
        planning = planner.generate_trip_options(_trip_payload_from_trip(trip))
        run = _latest_agent_run(trip, "options")

        for option in planning.options:
            db.add(
                TripOption(
                    trip_request_id=trip.id,
                    name=option["name"],
                    summary=option["summary"],
                    rationale=option["rationale"],
                    tradeoffs=option["tradeoffs"],
                    destination_order=option["destination_order"],
                    days_by_stop=option["days_by_stop"],
                    pace_label=option["pace_label"],
                    estimated_total_min=option["estimated_total_min"],
                    estimated_total_max=option["estimated_total_max"],
                    budget_confidence=option["budget_confidence"],
                    fit_score=option["fit_score"],
                )
            )

        trip.planning_mode = planning.mode
        trip.status = "planned"

        if run is not None:
            run.mode = planning.mode
            run.status = "completed"
            run.summary = planning.planning_summary
            run.steps = planning.steps
            run.sources = planning.sources
            run.output_payload = {"options_count": len(planning.options)}
            if planning.fallback_reason:
                run.output_payload["fallback_reason"] = planning.fallback_reason

        db.commit()
    except Exception as exc:
        db.rollback()
        trip = db.scalars(_trip_query().where(TripRequest.id == trip_id)).unique().first()
        if trip is None:
            db.close()
            return
        run = _latest_agent_run(trip, "options")
        summary, steps = _serialize_failure(exc)
        trip.status = "failed"
        if run is not None:
            run.status = "failed"
            run.summary = summary
            run.steps = steps
            run.output_payload = {"error": str(exc)[:300]}
        db.commit()
    finally:
        db.close()


def _run_itinerary_generation(trip_id: str, option_id: str) -> None:
    db = SessionLocal()
    try:
        trip = db.scalars(_trip_query().where(TripRequest.id == trip_id)).unique().first()
        if not trip:
            return

        selected_option = next((option for option in trip.options if option.id == option_id), None)
        if selected_option is None:
            return

        planner = TripPlanner(get_settings())
        itinerary_artifacts = planner.generate_itinerary(
            _trip_payload_from_trip(trip),
            {
                "name": selected_option.name,
                "destination_order": selected_option.destination_order,
                "days_by_stop": selected_option.days_by_stop,
                "pace_label": selected_option.pace_label,
                "estimated_total_min": selected_option.estimated_total_min,
            },
        )
        run = _latest_agent_run(trip, "itinerary")

        itinerary = Itinerary(
            trip_request_id=trip.id,
            trip_option_id=selected_option.id,
            title=itinerary_artifacts.itinerary["title"],
            overview=itinerary_artifacts.itinerary["overview"],
            logistics=itinerary_artifacts.itinerary["logistics"],
            neighborhood_guidance=itinerary_artifacts.itinerary["neighborhood_guidance"],
        )
        db.add(itinerary)
        db.flush()

        for day in itinerary_artifacts.itinerary["days"]:
            db.add(
                ItineraryDay(
                    itinerary_id=itinerary.id,
                    day_number=day["day_number"],
                    city=day["city"],
                    theme=day["theme"],
                    morning=day["morning"],
                    afternoon=day["afternoon"],
                    evening=day["evening"],
                    logistics_note=day["logistics_note"],
                    flexibility_note=day["flexibility_note"],
                )
            )

        db.query(FlightOption).filter(FlightOption.trip_option_id == selected_option.id).delete()
        db.query(HotelOption).filter(HotelOption.trip_option_id == selected_option.id).delete()

        for flight in itinerary_artifacts.flights:
            db.add(FlightOption(trip_request_id=trip.id, trip_option_id=selected_option.id, **flight))
        for hotel in itinerary_artifacts.hotels:
            db.add(HotelOption(trip_request_id=trip.id, trip_option_id=selected_option.id, **hotel))

        trip.status = "saved" if trip.saved_trip is not None else "selected"

        if run is not None:
            run.mode = itinerary_artifacts.mode
            run.status = "completed"
            run.summary = itinerary_artifacts.summary
            run.steps = itinerary_artifacts.steps
            run.sources = itinerary_artifacts.sources
            run.output_payload = {"itinerary_title": itinerary_artifacts.itinerary["title"]}
            if itinerary_artifacts.fallback_reason:
                run.output_payload["fallback_reason"] = itinerary_artifacts.fallback_reason

        db.commit()
    except Exception as exc:
        db.rollback()
        trip = db.scalars(_trip_query().where(TripRequest.id == trip_id)).unique().first()
        if trip is None:
            db.close()
            return
        run = _latest_agent_run(trip, "itinerary")
        summary, steps = _serialize_failure(exc)
        trip.status = "failed"
        if run is not None:
            run.status = "failed"
            run.summary = summary
            run.steps = steps
            run.output_payload = {"error": str(exc)[:300]}
        db.commit()
    finally:
        db.close()
