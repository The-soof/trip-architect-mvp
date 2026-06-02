from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


def _uuid() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped[TravelerProfile | None] = relationship(back_populates="user", uselist=False)
    trip_requests: Mapped[list[TripRequest]] = relationship(back_populates="user", cascade="all, delete-orphan")
    saved_trips: Mapped[list[SavedTrip]] = relationship(back_populates="user", cascade="all, delete-orphan")


class TravelerProfile(Base):
    __tablename__ = "traveler_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    home_airport: Mapped[str | None] = mapped_column(String(12), nullable=True)
    budget_preference: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pace_preference: Mapped[str | None] = mapped_column(String(40), nullable=True)
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)

    user: Mapped[User] = relationship(back_populates="profile")


class TripRequest(Base):
    __tablename__ = "trip_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    origin: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date())
    end_date: Mapped[date] = mapped_column(Date())
    destination_candidates: Mapped[list[str]] = mapped_column(JSON)
    trip_style: Mapped[str] = mapped_column(Text())
    brief_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    budget_range: Mapped[str | None] = mapped_column(String(80), nullable=True)
    traveler_count: Mapped[int] = mapped_column(Integer, default=1)
    pace_preference: Mapped[str | None] = mapped_column(String(40), nullable=True)
    planning_mode: Mapped[str] = mapped_column(String(32), default="mock")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    selected_option_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    flight_selection_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_flight_option_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="trip_requests")
    options: Mapped[list[TripOption]] = relationship(back_populates="trip_request", cascade="all, delete-orphan")
    itineraries: Mapped[list[Itinerary]] = relationship(back_populates="trip_request", cascade="all, delete-orphan")
    flight_options: Mapped[list[FlightOption]] = relationship(back_populates="trip_request", cascade="all, delete-orphan")
    hotel_options: Mapped[list[HotelOption]] = relationship(back_populates="trip_request", cascade="all, delete-orphan")
    agent_runs: Mapped[list[AgentRun]] = relationship(back_populates="trip_request", cascade="all, delete-orphan")
    saved_trip: Mapped[SavedTrip | None] = relationship(back_populates="trip_request", uselist=False)
    confirmed_bookings: Mapped[list[ConfirmedBooking]] = relationship(
        back_populates="trip_request", cascade="all, delete-orphan"
    )


class TripOption(Base):
    __tablename__ = "trip_options"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_request_id: Mapped[str] = mapped_column(ForeignKey("trip_requests.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text())
    rationale: Mapped[str] = mapped_column(Text())
    tradeoffs: Mapped[list[str]] = mapped_column(JSON, default=list)
    destination_order: Mapped[list[str]] = mapped_column(JSON, default=list)
    days_by_stop: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    pace_label: Mapped[str] = mapped_column(String(40))
    estimated_total_min: Mapped[int] = mapped_column(Integer)
    estimated_total_max: Mapped[int] = mapped_column(Integer)
    budget_confidence: Mapped[str] = mapped_column(String(32), default="medium")
    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trip_request: Mapped[TripRequest] = relationship(back_populates="options")
    itinerary: Mapped[Itinerary | None] = relationship(back_populates="trip_option", uselist=False)

    @property
    def cost_breakdown(self) -> dict[str, dict[str, int] | str]:
        flights = {"min": int(self.estimated_total_min * 0.24), "max": int(self.estimated_total_max * 0.24)}
        lodging = {"min": int(self.estimated_total_min * 0.4), "max": int(self.estimated_total_max * 0.4)}
        local_transport = {"min": int(self.estimated_total_min * 0.12), "max": int(self.estimated_total_max * 0.12)}
        food_and_activities = {
            "min": self.estimated_total_min - flights["min"] - lodging["min"] - local_transport["min"],
            "max": self.estimated_total_max - flights["max"] - lodging["max"] - local_transport["max"],
        }
        return {
            "flights": flights,
            "lodging": lodging,
            "local_transport": local_transport,
            "food_and_activities": food_and_activities,
            "confidence": self.budget_confidence,
        }

    @property
    def price_assumptions(self) -> list[str]:
        stop_count = max(1, len(self.destination_order))
        return [
            "Flight pricing is modeled as an estimate, not a live fare hold.",
            f"Lodging assumes {self.pace_label.lower()} pacing across {stop_count} stops.",
            "Food and activity budgets scale with the requested budget tier and traveler count.",
        ]

    @property
    def warning_flags(self) -> list[str]:
        warnings: list[str] = []
        total_nights = sum(int(stop.get("nights", 0)) for stop in self.days_by_stop)
        if len(self.destination_order) >= 3 and total_nights <= 8:
            warnings.append("This route is ambitious for the available dates.")
        if any(int(stop.get("nights", 0)) < 2 for stop in self.days_by_stop):
            warnings.append("At least one stop is very short and may feel rushed.")
        return warnings


class Itinerary(Base):
    __tablename__ = "itineraries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_request_id: Mapped[str] = mapped_column(ForeignKey("trip_requests.id"), index=True)
    trip_option_id: Mapped[str] = mapped_column(ForeignKey("trip_options.id"), index=True, unique=True)
    title: Mapped[str] = mapped_column(String(200))
    overview: Mapped[str] = mapped_column(Text())
    logistics: Mapped[str] = mapped_column(Text())
    neighborhood_guidance: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trip_request: Mapped[TripRequest] = relationship(back_populates="itineraries")
    trip_option: Mapped[TripOption] = relationship(back_populates="itinerary")
    days: Mapped[list[ItineraryDay]] = relationship(back_populates="itinerary", cascade="all, delete-orphan")


class ItineraryDay(Base):
    __tablename__ = "itinerary_days"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    itinerary_id: Mapped[str] = mapped_column(ForeignKey("itineraries.id"), index=True)
    day_number: Mapped[int] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(String(120))
    theme: Mapped[str] = mapped_column(String(160))
    morning: Mapped[str] = mapped_column(Text())
    afternoon: Mapped[str] = mapped_column(Text())
    evening: Mapped[str] = mapped_column(Text())
    logistics_note: Mapped[str] = mapped_column(Text())
    flexibility_note: Mapped[str] = mapped_column(Text())

    itinerary: Mapped[Itinerary] = relationship(back_populates="days")


class FlightOption(Base):
    __tablename__ = "flight_options"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_request_id: Mapped[str] = mapped_column(ForeignKey("trip_requests.id"), index=True)
    trip_option_id: Mapped[str] = mapped_column(ForeignKey("trip_options.id"), index=True)
    carrier: Mapped[str] = mapped_column(String(120))
    route_summary: Mapped[str] = mapped_column(String(200))
    price: Mapped[int] = mapped_column(Integer)
    stops: Mapped[int] = mapped_column(Integer, default=1)
    comfort_label: Mapped[str] = mapped_column(String(40))
    source_name: Mapped[str] = mapped_column(String(60), default="Kayak")
    booking_url: Mapped[str] = mapped_column(Text())
    match_reason: Mapped[str] = mapped_column(Text(), default="")

    trip_request: Mapped[TripRequest] = relationship(back_populates="flight_options")


class HotelOption(Base):
    __tablename__ = "hotel_options"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_request_id: Mapped[str] = mapped_column(ForeignKey("trip_requests.id"), index=True)
    trip_option_id: Mapped[str] = mapped_column(ForeignKey("trip_options.id"), index=True)
    city: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(160))
    neighborhood: Mapped[str] = mapped_column(String(160))
    nightly_rate: Mapped[int] = mapped_column(Integer)
    rating: Mapped[float] = mapped_column(Float)
    style_label: Mapped[str] = mapped_column(String(80))
    source_name: Mapped[str] = mapped_column(String(60), default="Booking.com")
    booking_url: Mapped[str] = mapped_column(Text())
    match_reason: Mapped[str] = mapped_column(Text(), default="")
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    maps_url: Mapped[str | None] = mapped_column(Text(), nullable=True)

    trip_request: Mapped[TripRequest] = relationship(back_populates="hotel_options")


class SavedTrip(Base):
    __tablename__ = "saved_trips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    trip_request_id: Mapped[str] = mapped_column(ForeignKey("trip_requests.id"), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    confirmed_booking_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="saved_trips")
    trip_request: Mapped[TripRequest] = relationship(back_populates="saved_trip")


class ConfirmedBooking(Base):
    __tablename__ = "confirmed_bookings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_request_id: Mapped[str] = mapped_column(ForeignKey("trip_requests.id"), index=True)
    booking_type: Mapped[str] = mapped_column(String(20))
    source_option_id: Mapped[str] = mapped_column(String(36), index=True)
    provider_name: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(200))
    booking_url: Mapped[str] = mapped_column(Text())
    selection_state: Mapped[str] = mapped_column(String(20), default="saved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    trip_request: Mapped[TripRequest] = relationship(back_populates="confirmed_bookings")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_request_id: Mapped[str] = mapped_column(ForeignKey("trip_requests.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="completed")
    summary: Mapped[str] = mapped_column(Text())
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    trip_request: Mapped[TripRequest] = relationship(back_populates="agent_runs")
