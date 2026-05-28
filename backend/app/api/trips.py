from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    AgentRun,
    ConfirmedBooking,
    FlightOption,
    HotelOption,
    Itinerary,
    ItineraryDay,
    SavedTrip,
    TravelerProfile,
    TripOption,
    TripRequest,
    User,
)
from app.schemas.trip import BookingSelectionRequest, DashboardResponse, SaveTripRequest, TripCreateRequest, TripRead
from app.services.agent_planner import TripPlanner

router = APIRouter(prefix="/trips", tags=["trips"])


def _trip_query():
    return (
        select(TripRequest)
        .options(
            joinedload(TripRequest.options).joinedload(TripOption.itinerary).joinedload(Itinerary.days),
            joinedload(TripRequest.itineraries).joinedload(Itinerary.days),
            joinedload(TripRequest.flight_options),
            joinedload(TripRequest.hotel_options),
            joinedload(TripRequest.confirmed_bookings),
            joinedload(TripRequest.agent_runs),
            joinedload(TripRequest.saved_trip),
        )
        .order_by(TripRequest.created_at.desc())
    )


def _get_trip_or_404(db: Session, user_id: str, trip_id: str) -> TripRequest:
    statement = _trip_query().where(TripRequest.id == trip_id, TripRequest.user_id == user_id)
    trip = db.scalars(statement).unique().first()
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
    return trip


def _serialize_trip(trip: TripRequest) -> TripRead:
    return TripRead.model_validate(trip)


def _materialize_trip_request(
    db: Session,
    current_user: User,
    payload: TripCreateRequest,
    profile: TravelerProfile | None,
) -> TripRequest:
    effective_budget = payload.budget_range or (profile.budget_preference if profile else None)
    effective_pace = payload.pace_preference or (profile.pace_preference if profile else None)
    enriched_style = payload.trip_style.strip()
    if profile and profile.interests:
        interests = ", ".join(profile.interests)
        enriched_style = f"{enriched_style} Traveler profile interests: {interests}."

    trip = TripRequest(
        user_id=current_user.id,
        origin=payload.origin.strip(),
        start_date=payload.start_date,
        end_date=payload.end_date,
        destination_candidates=payload.destination_candidates,
        trip_style=enriched_style,
        budget_range=effective_budget,
        traveler_count=payload.traveler_count,
        pace_preference=effective_pace,
        status="planning",
    )
    db.add(trip)
    db.flush()

    effective_payload = TripCreateRequest(
        origin=trip.origin,
        start_date=trip.start_date,
        end_date=trip.end_date,
        destination_candidates=trip.destination_candidates,
        trip_style=trip.trip_style,
        budget_range=trip.budget_range,
        traveler_count=trip.traveler_count,
        pace_preference=trip.pace_preference,
    )
    planner = TripPlanner(get_settings())
    planning = planner.generate_trip_options(effective_payload)
    trip.planning_mode = planning.mode
    trip.status = "planned"

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
    db.add(
        AgentRun(
            trip_request_id=trip.id,
            kind="options",
            mode=planning.mode,
            summary=planning.planning_summary,
            input_payload={
                **payload.model_dump(mode="json"),
                "traveler_profile": {
                    "home_airport": profile.home_airport if profile else None,
                    "budget_preference": profile.budget_preference if profile else None,
                    "pace_preference": profile.pace_preference if profile else None,
                    "interests": profile.interests if profile else [],
                },
            },
            output_payload={"options_count": len(planning.options)},
            steps=planning.steps,
            sources=planning.sources,
        )
    )
    return trip


def _update_confirmed_booking_count(trip: TripRequest) -> None:
    if trip.saved_trip is not None:
        trip.saved_trip.confirmed_booking_count = sum(
            1 for booking in trip.confirmed_bookings if booking.selection_state == "confirmed"
        )


@router.get("", response_model=DashboardResponse)
def list_trips(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DashboardResponse:
    trips = db.scalars(_trip_query().where(TripRequest.user_id == current_user.id)).unique().all()
    saved = [trip for trip in trips if trip.saved_trip is not None]
    return DashboardResponse(recent_trips=[_serialize_trip(trip) for trip in trips], saved_trips=[_serialize_trip(trip) for trip in saved])


@router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def create_trip(
    payload: TripCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TripRead:
    trip = _materialize_trip_request(db, current_user, payload, current_user.profile)
    db.commit()
    trip = _get_trip_or_404(db, current_user.id, trip.id)
    return _serialize_trip(trip)


@router.get("/{trip_id}", response_model=TripRead)
def get_trip(
    trip_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TripRead:
    return _serialize_trip(_get_trip_or_404(db, current_user.id, trip_id))


@router.post("/{trip_id}/select-option/{option_id}", response_model=TripRead)
def select_trip_option(
    trip_id: str,
    option_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TripRead:
    trip = _get_trip_or_404(db, current_user.id, trip_id)
    selected_option = next((option for option in trip.options if option.id == option_id), None)
    if not selected_option:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip option not found.")

    for option in trip.options:
        option.is_selected = option.id == option_id
    trip.selected_option_id = option_id
    trip.status = "selected"

    existing_itinerary = next((itinerary for itinerary in trip.itineraries if itinerary.trip_option_id == option_id), None)
    if not existing_itinerary:
        effective_payload = TripCreateRequest(
            origin=trip.origin,
            start_date=trip.start_date,
            end_date=trip.end_date,
            destination_candidates=trip.destination_candidates,
            trip_style=trip.trip_style,
            budget_range=trip.budget_range,
            traveler_count=trip.traveler_count,
            pace_preference=trip.pace_preference,
        )
        planner = TripPlanner(get_settings())
        itinerary_artifacts = planner.generate_itinerary(
            effective_payload,
            {
                "name": selected_option.name,
                "destination_order": selected_option.destination_order,
                "days_by_stop": selected_option.days_by_stop,
                "pace_label": selected_option.pace_label,
                "estimated_total_min": selected_option.estimated_total_min,
            },
        )
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
        db.add(
            AgentRun(
                trip_request_id=trip.id,
                kind="itinerary",
                mode=itinerary_artifacts.mode,
                summary=itinerary_artifacts.summary,
                input_payload={"selected_option_id": selected_option.id},
                output_payload={"itinerary_title": itinerary_artifacts.itinerary["title"]},
                steps=itinerary_artifacts.steps,
                sources=itinerary_artifacts.sources,
            )
        )
    db.commit()
    return _serialize_trip(_get_trip_or_404(db, current_user.id, trip_id))


@router.post("/{trip_id}/save", response_model=TripRead)
def save_trip(
    trip_id: str,
    payload: SaveTripRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TripRead:
    trip = _get_trip_or_404(db, current_user.id, trip_id)
    if trip.saved_trip:
        trip.saved_trip.label = payload.label
        trip.saved_trip.notes = payload.notes
    else:
        trip.saved_trip = SavedTrip(
            user_id=current_user.id,
            trip_request_id=trip.id,
            label=payload.label,
            notes=payload.notes,
            confirmed_booking_count=0,
        )
    trip.status = "saved"
    _update_confirmed_booking_count(trip)
    db.commit()
    return _serialize_trip(_get_trip_or_404(db, current_user.id, trip_id))


@router.post("/{trip_id}/duplicate", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def duplicate_trip(
    trip_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TripRead:
    trip = _get_trip_or_404(db, current_user.id, trip_id)
    payload = TripCreateRequest(
        origin=trip.origin,
        start_date=trip.start_date,
        end_date=trip.end_date,
        destination_candidates=trip.destination_candidates,
        trip_style=trip.trip_style.split(" Traveler profile interests:")[0],
        budget_range=trip.budget_range,
        traveler_count=trip.traveler_count,
        pace_preference=trip.pace_preference,
    )
    duplicate = _materialize_trip_request(db, current_user, payload, current_user.profile)
    db.commit()
    return _serialize_trip(_get_trip_or_404(db, current_user.id, duplicate.id))


@router.post("/{trip_id}/booking-selection", response_model=TripRead)
def update_booking_selection(
    trip_id: str,
    payload: BookingSelectionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TripRead:
    trip = _get_trip_or_404(db, current_user.id, trip_id)
    if payload.booking_type == "flight":
        option = next((item for item in trip.flight_options if item.id == payload.option_id), None)
        provider = option.source_name if option else None
        label = option.route_summary if option else None
        booking_url = option.booking_url if option else None
    else:
        option = next((item for item in trip.hotel_options if item.id == payload.option_id), None)
        provider = option.source_name if option else None
        label = option.name if option else None
        booking_url = option.booking_url if option else None

    if option is None or provider is None or label is None or booking_url is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking option not found.")

    existing = next(
        (
            booking
            for booking in trip.confirmed_bookings
            if booking.booking_type == payload.booking_type and booking.source_option_id == payload.option_id
        ),
        None,
    )

    if payload.selection_state == "none":
        if existing is not None:
            trip.confirmed_bookings.remove(existing)
            db.delete(existing)
    else:
        if trip.saved_trip is None:
            trip.saved_trip = SavedTrip(
                user_id=current_user.id,
                trip_request_id=trip.id,
                label=f"{trip.destination_candidates[0]} trip",
                notes="Auto-created when the traveler saved a booking option.",
                confirmed_booking_count=0,
            )
            db.flush()
        if existing is None:
            trip.confirmed_bookings.append(
                ConfirmedBooking(
                    trip_request_id=trip.id,
                    booking_type=payload.booking_type,
                    source_option_id=payload.option_id,
                    provider_name=provider,
                    label=label,
                    booking_url=booking_url,
                    selection_state=payload.selection_state,
                )
            )
        else:
            existing.provider_name = provider
            existing.label = label
            existing.booking_url = booking_url
            existing.selection_state = payload.selection_state

    trip.status = "saved" if trip.saved_trip is not None else trip.status
    _update_confirmed_booking_count(trip)
    db.commit()
    return _serialize_trip(_get_trip_or_404(db, current_user.id, trip_id))
