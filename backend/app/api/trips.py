from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import (
    AgentRun,
    ConfirmedBooking,
    Itinerary,
    SavedTrip,
    TravelerProfile,
    TripOption,
    TripRequest,
    User,
)
from app.schemas.trip import BookingSelectionRequest, DashboardResponse, RegenerateRequest, SaveTripRequest, TripCreateRequest, TripRead
from app.services.trip_jobs import schedule_itinerary_generation, schedule_trip_options_generation

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


def _raise_flight_lock_error() -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A flight has already been saved for this trip. Flight selection is now permanent, so routes and flight choices can no longer be changed.",
    )


def _raise_trip_lock_error() -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A trip option has already been confirmed for this trip. Once selected, the route cannot be changed or regenerated.",
    )


def _prepare_trip_request(
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
    agent_run = AgentRun(
        trip_request_id=trip.id,
        kind="options",
        mode="pending",
        status="running",
        summary="Planning trip options in the background.",
        input_payload={
            **payload.model_dump(mode="json"),
            "traveler_profile": {
                "home_airport": profile.home_airport if profile else None,
                "budget_preference": profile.budget_preference if profile else None,
                "pace_preference": profile.pace_preference if profile else None,
                "interests": profile.interests if profile else [],
            },
        },
        output_payload={"options_count": 0},
        steps=[
            {"agent": "intake-agent", "status": "running", "detail": "Normalizing traveler constraints and timing window."},
            {"agent": "routing-agent", "status": "pending", "detail": "Waiting to compare destination combinations and pacing tradeoffs."},
            {"agent": "budget-agent", "status": "pending", "detail": "Waiting to estimate flight, lodging, and activity ranges."},
            {"agent": "planner-agent", "status": "pending", "detail": "Waiting to rank the best-fit route options."},
        ],
        sources=[],
    )
    db.add(agent_run)
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


@router.post("", response_model=TripRead, status_code=status.HTTP_202_ACCEPTED)
def create_trip(
    payload: TripCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TripRead:
    trip = _prepare_trip_request(db, current_user, payload, current_user.profile)
    db.commit()
    response_trip = _get_trip_or_404(db, current_user.id, trip.id)
    schedule_trip_options_generation(trip.id)
    return _serialize_trip(response_trip)


@router.get("/{trip_id}", response_model=TripRead)
def get_trip(
    trip_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TripRead:
    return _serialize_trip(_get_trip_or_404(db, current_user.id, trip_id))


@router.post("/{trip_id}/regenerate", response_model=TripRead, status_code=status.HTTP_202_ACCEPTED)
def regenerate_trip(
    trip_id: str,
    payload: RegenerateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TripRead:
    """Wipe existing options + itinerary for a trip and reschedule the planning job.

    An optional feedback string is appended to the trip_style so the planner
    can take the user's adjustment note into account on the next run.
    """
    trip = _get_trip_or_404(db, current_user.id, trip_id)
    if trip.selected_option_id is not None:
        _raise_trip_lock_error()
    if trip.flight_selection_locked:
        _raise_flight_lock_error()

    # Block regeneration while a run is already in progress
    running_run = next(
        (run for run in trip.agent_runs if run.status == "running" and run.kind == "options"),
        None,
    )
    if running_run:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A planning run is already in progress. Please wait for it to finish before regenerating.",
        )

    # Append feedback to trip_style if provided
    feedback = payload.feedback.strip()
    if feedback:
        separator = " " if not trip.trip_style.endswith(".") else " "
        trip.trip_style = f"{trip.trip_style}{separator}Regeneration note: {feedback}"

    # Clear options, itineraries, and flight/hotel options so the new run starts clean
    for option in list(trip.options):
        db.delete(option)
    for itinerary in list(trip.itineraries):
        db.delete(itinerary)
    for flight in list(trip.flight_options):
        db.delete(flight)
    for hotel in list(trip.hotel_options):
        db.delete(hotel)

    trip.selected_option_id = None
    trip.status = "planning"
    trip.planning_mode = "pending"

    agent_run = AgentRun(
        trip_request_id=trip.id,
        kind="options",
        mode="pending",
        status="running",
        summary="Regenerating trip options with updated preferences.",
        input_payload={"feedback": feedback, "trip_style": trip.trip_style},
        output_payload={"options_count": 0},
        steps=[
            {"agent": "intake-agent", "status": "running", "detail": "Re-normalizing traveler constraints with updated feedback."},
            {"agent": "routing-agent", "status": "pending", "detail": "Waiting to rebuild destination combinations."},
            {"agent": "planner-agent", "status": "pending", "detail": "Waiting to rank the refreshed options."},
        ],
        sources=[],
    )
    db.add(agent_run)
    db.commit()

    response_trip = _get_trip_or_404(db, current_user.id, trip_id)
    schedule_trip_options_generation(trip.id)
    return _serialize_trip(response_trip)


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
    if trip.selected_option_id is not None and trip.selected_option_id != option_id:
        _raise_trip_lock_error()
    if trip.flight_selection_locked and trip.selected_option_id != option_id:
        _raise_flight_lock_error()

    for option in trip.options:
        option.is_selected = option.id == option_id
    trip.selected_option_id = option_id

    existing_itinerary = next((itinerary for itinerary in trip.itineraries if itinerary.trip_option_id == option_id), None)
    running_itinerary_run = next(
        (
            run
            for run in reversed(trip.agent_runs)
            if run.kind == "itinerary"
            and run.status == "running"
            and run.input_payload.get("selected_option_id") == selected_option.id
        ),
        None,
    )
    if not existing_itinerary:
        trip.status = "building_itinerary"
        if running_itinerary_run is None:
            itinerary_run = AgentRun(
                trip_request_id=trip.id,
                kind="itinerary",
                mode="pending",
                status="running",
                summary="Building the detailed itinerary in the background.",
                input_payload={"selected_option_id": selected_option.id},
                output_payload={},
                steps=[
                    {"agent": "research-agent", "status": "running", "detail": "Gathering destination context, neighborhood fit, and logistics notes."},
                    {"agent": "itinerary-agent", "status": "pending", "detail": "Waiting to build the day-by-day morning, afternoon, and evening structure."},
                    {"agent": "booking-discovery-agent", "status": "pending", "detail": "Waiting to align flight and hotel discovery with the selected route."},
                ],
                sources=[],
            )
            db.add(itinerary_run)
    else:
        trip.status = "saved" if trip.saved_trip is not None else "selected"
    db.commit()
    response_trip = _get_trip_or_404(db, current_user.id, trip_id)
    if not existing_itinerary and running_itinerary_run is None:
        schedule_itinerary_generation(trip.id, option_id)
    return _serialize_trip(response_trip)


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


@router.post("/{trip_id}/duplicate", response_model=TripRead, status_code=status.HTTP_202_ACCEPTED)
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
    duplicate = _prepare_trip_request(db, current_user, payload, current_user.profile)
    db.commit()
    response_trip = _get_trip_or_404(db, current_user.id, duplicate.id)
    schedule_trip_options_generation(duplicate.id)
    return _serialize_trip(response_trip)


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

    if payload.booking_type == "flight" and trip.flight_selection_locked:
        if trip.locked_flight_option_id != payload.option_id or payload.selection_state == "none":
            _raise_flight_lock_error()

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

        if payload.booking_type == "flight" and payload.selection_state in {"saved", "confirmed"}:
            trip.flight_selection_locked = True
            trip.locked_flight_option_id = payload.option_id

    trip.status = "saved" if trip.saved_trip is not None else trip.status
    _update_confirmed_booking_count(trip)
    db.commit()
    return _serialize_trip(_get_trip_or_404(db, current_user.id, trip_id))
