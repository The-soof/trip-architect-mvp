from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TripCreateRequest(BaseModel):
    origin: str = Field(min_length=2, max_length=120)
    start_date: date
    end_date: date
    destination_candidates: list[str] = Field(min_length=1, max_length=6)
    trip_style: str = Field(min_length=12, max_length=1000)
    budget_range: str | None = Field(default=None, max_length=80)
    traveler_count: int = Field(default=1, ge=1, le=12)
    pace_preference: str | None = Field(default=None, max_length=40)

    @field_validator("destination_candidates")
    @classmethod
    def normalize_destinations(cls, value: list[str]) -> list[str]:
        cleaned = []
        for item in value:
            normalized = item.strip()
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
        if not cleaned:
            raise ValueError("At least one destination is required.")
        return cleaned

    @field_validator("end_date")
    @classmethod
    def validate_dates(cls, value: date, info) -> date:
        start_date = info.data.get("start_date")
        if start_date and value <= start_date:
            raise ValueError("End date must be after start date.")
        return value


class SaveTripRequest(BaseModel):
    label: str = Field(min_length=2, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)


class BookingSelectionRequest(BaseModel):
    booking_type: str = Field(pattern="^(flight|hotel)$")
    option_id: str = Field(min_length=8, max_length=64)
    selection_state: str = Field(pattern="^(saved|confirmed|none)$")


class CostBand(BaseModel):
    min: int
    max: int


class CostBreakdownRead(BaseModel):
    flights: CostBand
    lodging: CostBand
    local_transport: CostBand
    food_and_activities: CostBand
    confidence: str


class DayStop(BaseModel):
    city: str
    nights: int
    start_day: int
    end_day: int


class TripOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    summary: str
    rationale: str
    tradeoffs: list[str]
    destination_order: list[str]
    days_by_stop: list[DayStop]
    pace_label: str
    estimated_total_min: int
    estimated_total_max: int
    budget_confidence: str
    fit_score: float
    cost_breakdown: CostBreakdownRead
    price_assumptions: list[str]
    warning_flags: list[str]
    is_selected: bool
    created_at: datetime


class ItineraryDayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    day_number: int
    city: str
    theme: str
    morning: str
    afternoon: str
    evening: str
    logistics_note: str
    flexibility_note: str


class ItineraryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    overview: str
    logistics: str
    neighborhood_guidance: list[dict]
    created_at: datetime
    days: list[ItineraryDayRead]


class FlightOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    carrier: str
    route_summary: str
    price: int
    stops: int
    comfort_label: str
    source_name: str
    booking_url: str
    match_reason: str


class HotelOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    city: str
    name: str
    neighborhood: str
    nightly_rate: int
    rating: float
    style_label: str
    source_name: str
    booking_url: str
    match_reason: str


class ConfirmedBookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    booking_type: str
    source_option_id: str
    provider_name: str
    label: str
    booking_url: str
    selection_state: str
    created_at: datetime
    updated_at: datetime


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    mode: str
    status: str
    summary: str
    input_payload: dict
    output_payload: dict
    steps: list[dict]
    sources: list[dict]
    created_at: datetime
    updated_at: datetime


class SavedTripRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    notes: str | None
    confirmed_booking_count: int
    created_at: datetime
    updated_at: datetime


class TripRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    origin: str
    start_date: date
    end_date: date
    destination_candidates: list[str]
    trip_style: str
    budget_range: str | None
    traveler_count: int
    pace_preference: str | None
    planning_mode: str
    status: str
    selected_option_id: str | None
    created_at: datetime
    updated_at: datetime
    options: list[TripOptionRead]
    itineraries: list[ItineraryRead]
    flight_options: list[FlightOptionRead]
    hotel_options: list[HotelOptionRead]
    confirmed_bookings: list[ConfirmedBookingRead]
    agent_runs: list[AgentRunRead]
    saved_trip: SavedTripRead | None


class DashboardResponse(BaseModel):
    recent_trips: list[TripRead]
    saved_trips: list[TripRead]
