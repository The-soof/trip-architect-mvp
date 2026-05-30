from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import AgentRun, FlightOption, HotelOption, Itinerary, ItineraryDay, TripOption, TripRequest
from app.schemas.trip import TripCreateRequest
from app.services.agent_planner import TripPlanner
from app.services.job_runner import submit_background_job


def _bounded_text(value: object, max_length: int, default: str = "") -> str:
    text = " ".join(str(value or default).split())
    if not text:
        text = default
    return text[:max_length]


def _bounded_confidence(value: object) -> str:
    text = _bounded_text(value, 32, "medium")
    lowered = text.lower()
    for label in ("low", "medium", "high"):
        if label in lowered:
            return label
    return text


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


def recover_interrupted_trip_jobs() -> None:
    db = SessionLocal()
    try:
        trips = db.scalars(
            _trip_query().where(TripRequest.status.in_(["planning", "itinerary_planning", "selected"]))
        ).unique().all()
        recovered = 0
        for trip in trips:
            options_run = _latest_agent_run(trip, "options")
            if trip.status == "planning" and options_run is not None and options_run.status == "running" and not trip.options:
                submit_background_job(_run_trip_options_generation, trip.id)
                recovered += 1
                continue

            itinerary_run = _latest_agent_run(trip, "itinerary")
            if (
                trip.selected_option_id
                and itinerary_run is not None
                and itinerary_run.status == "running"
                and not any(option.itinerary is not None for option in trip.options if option.id == trip.selected_option_id)
            ):
                submit_background_job(_run_itinerary_generation, trip.id, trip.selected_option_id)
                recovered += 1

        if recovered:
            print(
                "trip_architect.jobs "
                + json.dumps(
                    {
                        "message": "recovered_interrupted_jobs",
                        "count": recovered,
                    }
                ),
                flush=True,
            )
    finally:
        db.close()


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
                    name=_bounded_text(option["name"], 160, "Trip option"),
                    summary=option["summary"],
                    rationale=option["rationale"],
                    tradeoffs=option["tradeoffs"],
                    destination_order=option["destination_order"],
                    days_by_stop=option["days_by_stop"],
                    pace_label=_bounded_text(option["pace_label"], 40, "Balanced"),
                    estimated_total_min=option["estimated_total_min"],
                    estimated_total_max=option["estimated_total_max"],
                    budget_confidence=_bounded_confidence(option["budget_confidence"]),
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
            title=_bounded_text(itinerary_artifacts.itinerary["title"], 200, "Trip itinerary"),
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
                    city=_bounded_text(day["city"], 120, "Destination"),
                    theme=_bounded_text(day["theme"], 160, "Day plan"),
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
            db.add(
                FlightOption(
                    trip_request_id=trip.id,
                    trip_option_id=selected_option.id,
                    carrier=_bounded_text(flight["carrier"], 120, "Flight option"),
                    route_summary=_bounded_text(flight["route_summary"], 200, "Route"),
                    price=flight["price"],
                    stops=flight["stops"],
                    comfort_label=_bounded_text(flight["comfort_label"], 40, "Best fit"),
                    source_name=_bounded_text(flight["source_name"], 60, "Flight source"),
                    booking_url=flight["booking_url"],
                    match_reason=flight["match_reason"],
                )
            )
        for hotel in itinerary_artifacts.hotels:
            db.add(
                HotelOption(
                    trip_request_id=trip.id,
                    trip_option_id=selected_option.id,
                    city=_bounded_text(hotel["city"], 120, "Destination"),
                    name=_bounded_text(hotel["name"], 160, "Hotel option"),
                    neighborhood=_bounded_text(hotel["neighborhood"], 160, "Central"),
                    nightly_rate=hotel["nightly_rate"],
                    rating=hotel["rating"],
                    style_label=_bounded_text(hotel["style_label"], 80, "Recommended stay"),
                    source_name=_bounded_text(hotel["source_name"], 60, "Hotel source"),
                    booking_url=hotel["booking_url"],
                    match_reason=hotel["match_reason"],
                    address=_bounded_text(hotel.get("address"), 255) or None,
                    latitude=hotel.get("latitude"),
                    longitude=hotel.get("longitude"),
                    maps_url=hotel.get("maps_url"),
                )
            )

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
