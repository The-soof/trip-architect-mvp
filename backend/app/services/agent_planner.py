from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from itertools import combinations
import json
import os
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.schemas.trip import TripCreateRequest
from app.services.booking import build_booking_link, build_google_flights_link

CITY_TRAITS: dict[str, dict[str, Any]] = {
    "barcelona": {
        "vibe": ["food", "nightlife", "beach", "design"],
        "neighborhoods": ["Eixample", "El Born", "Barceloneta"],
        "highlights": ["tapas crawl", "beach afternoon", "late-night cocktail scene"],
    },
    "mykonos": {
        "vibe": ["nightlife", "water", "luxury", "relaxation"],
        "neighborhoods": ["Mykonos Town", "Ornos", "Platis Gialos"],
        "highlights": ["beach club day", "sunset dinner", "boat outing"],
    },
    "split": {
        "vibe": ["water", "history", "food", "island hopping"],
        "neighborhoods": ["Old Town", "Veli Varos", "Bacvice"],
        "highlights": ["old town wander", "harbor lunch", "island day trip"],
    },
    "budapest": {
        "vibe": ["nightlife", "culture", "value", "thermal baths"],
        "neighborhoods": ["District V", "Jewish Quarter", "Buda Castle"],
        "highlights": ["ruin bars", "thermal bath afternoon", "Danube dinner cruise"],
    },
}

ACTIVITY_BLOCKS = {
    "food": (
        "slow breakfast at a neighborhood cafe and a market stop",
        "reserve a signature lunch and leave time for browsing local food shops",
        "anchor the night around a memorable dinner and nearby wine or cocktail bar",
    ),
    "nightlife": (
        "keep the morning light with coffee and a scenic walk",
        "plan a flexible afternoon so energy is saved for later",
        "build the evening around the strongest nightlife pocket in the city",
    ),
    "water": (
        "start near the waterfront before crowds build",
        "use the afternoon for a swim, beach block, or harbor activity",
        "wind down with sunset views and seafood or open-air drinks",
    ),
    "culture": (
        "start with a landmark or museum while attention is fresh",
        "layer in a design-forward or historical neighborhood walk",
        "end with live music, architecture views, or a cultural dinner spot",
    ),
    "relaxation": (
        "keep the morning slow and unstructured",
        "add spa, beach, or lounge time instead of stacking logistics",
        "choose a low-friction evening close to where you stay",
    ),
}


class ResearchSource(BaseModel):
    title: str
    url: str
    category: str
    evidence_type: str = Field(description="One of researched_fact, inferred_recommendation, estimated_price")


class DeepOptionPayload(BaseModel):
    name: str
    summary: str
    rationale: str
    tradeoffs: list[str]
    destination_order: list[str]
    days_by_stop: list[dict[str, int | str]]
    pace_label: str
    estimated_total_min: int
    estimated_total_max: int
    budget_confidence: str
    fit_score: float


class DeepTripOptionsPayload(BaseModel):
    planning_summary: str
    options: list[DeepOptionPayload]
    sources: list[ResearchSource]


class DeepItineraryDayPayload(BaseModel):
    day_number: int
    city: str
    theme: str
    morning: str
    afternoon: str
    evening: str
    logistics_note: str
    flexibility_note: str


class DeepItineraryPayload(BaseModel):
    title: str
    overview: str
    logistics: str
    neighborhood_guidance: list[dict[str, str]]
    days: list[DeepItineraryDayPayload]
    sources: list[ResearchSource]


@dataclass
class PlanningArtifacts:
    mode: str
    planning_summary: str
    options: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    steps: list[dict[str, Any]]


@dataclass
class ItineraryArtifacts:
    mode: str
    summary: str
    itinerary: dict[str, Any]
    flights: list[dict[str, Any]]
    hotels: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    steps: list[dict[str, Any]]


def _trip_length(payload: TripCreateRequest) -> int:
    return (payload.end_date - payload.start_date).days


def _normalized_traits(city: str) -> dict[str, Any]:
    return CITY_TRAITS.get(
        city.lower(),
        {
            "vibe": ["food", "culture", "relaxation"],
            "neighborhoods": [f"Central {city}", f"Old Town {city}", f"Waterfront {city}"],
            "highlights": [f"signature walk through {city}", f"food crawl in {city}", f"evening views in {city}"],
        },
    )


def _style_keywords(trip_style: str) -> set[str]:
    lowered = trip_style.lower()
    return {key for key in ACTIVITY_BLOCKS if key in lowered}


def _budget_multiplier(budget_range: str | None) -> float:
    if not budget_range:
        return 1.0
    lowered = budget_range.lower()
    if "budget" in lowered:
        return 0.78
    if "luxury" in lowered:
        return 1.5
    if "mid" in lowered:
        return 1.0
    return 1.0


def _pace_label(stop_count: int, trip_days: int, preference: str | None) -> str:
    if preference:
        return preference.capitalize()
    if stop_count >= 3 and trip_days <= 8:
        return "Fast-paced"
    if stop_count == 1:
        return "Slow"
    return "Balanced"


def _allocate_days(total_days: int, stops: list[str]) -> list[dict[str, int | str]]:
    stop_count = len(stops)
    base = max(2, total_days // stop_count)
    remainder = total_days - (base * stop_count)
    current_day = 1
    allocations: list[dict[str, int | str]] = []
    for index, stop in enumerate(stops):
        nights = base + (1 if index < remainder else 0)
        end_day = current_day + nights - 1
        allocations.append(
            {
                "city": stop,
                "nights": nights,
                "start_day": current_day,
                "end_day": end_day,
            }
        )
        current_day = end_day + 1
    return allocations


def _normalize_days_by_stop(
    raw_days_by_stop: list[dict[str, Any]],
    destination_order: list[str],
    total_days: int,
) -> list[dict[str, int | str]]:
    if not raw_days_by_stop or not destination_order:
        return _allocate_days(total_days, destination_order)

    nights_by_city: dict[str, int] = {}
    for stop in raw_days_by_stop:
        if not isinstance(stop, dict):
            continue
        if {"city", "nights"}.issubset(stop):
            city = str(stop["city"]).strip()
            nights = int(stop["nights"])
        elif len(stop) == 1:
            city, nights_value = next(iter(stop.items()))
            city = str(city).strip()
            nights = int(nights_value)
        else:
            continue

        if city and nights > 0:
            nights_by_city[city] = nights

    if any(city not in nights_by_city for city in destination_order):
        return _allocate_days(total_days, destination_order)

    total_nights = sum(nights_by_city[city] for city in destination_order)
    if total_nights <= 0:
        return _allocate_days(total_days, destination_order)

    if total_nights != total_days:
        last_city = destination_order[-1]
        adjusted_last_nights = nights_by_city[last_city] + (total_days - total_nights)
        if adjusted_last_nights <= 0:
            return _allocate_days(total_days, destination_order)
        nights_by_city[last_city] = adjusted_last_nights

    current_day = 1
    normalized: list[dict[str, int | str]] = []
    for city in destination_order:
        nights = nights_by_city[city]
        end_day = current_day + nights - 1
        normalized.append(
            {
                "city": city,
                "nights": nights,
                "start_day": current_day,
                "end_day": end_day,
            }
        )
        current_day = end_day + 1
    return normalized


def _fit_score(destinations: list[str], trip_style: str) -> float:
    keywords = _style_keywords(trip_style)
    if not keywords:
        return 8.4
    matches = 0
    for city in destinations:
        traits = set(_normalized_traits(city)["vibe"])
        matches += len(keywords.intersection(traits))
    return round(min(9.8, 7.2 + (matches / max(1, len(destinations))) * 0.75), 1)


def _estimate_costs(payload: TripCreateRequest, stops: list[str]) -> tuple[int, int]:
    trip_days = _trip_length(payload)
    multiplier = _budget_multiplier(payload.budget_range)
    daily_base = 210 * multiplier
    lodging = trip_days * daily_base * max(1, payload.traveler_count * 0.85)
    flights = (420 + len(stops) * 130) * payload.traveler_count
    local = trip_days * 70 * payload.traveler_count
    activities = trip_days * 55 * payload.traveler_count * multiplier
    total = lodging + flights + local + activities
    return int(total * 0.88), int(total * 1.14)


def _make_tradeoffs(stops: list[str], trip_days: int) -> list[str]:
    notes = []
    if len(stops) >= 3:
        notes.append("Higher city variety, but more transit overhead between stops.")
    if trip_days <= 7:
        notes.append("Limited slack time if flights or ferries shift.")
    if len(stops) == 1:
        notes.append("Relaxed pacing, but less destination variety.")
    if not notes:
        notes.append("Balanced route with room for both anchor plans and flexible recovery time.")
    return notes


def _make_option_name(stops: list[str]) -> str:
    return " + ".join(stops)


def _planning_sources(destinations: list[str], mode: str) -> list[dict[str, str]]:
    sources = [
        {
            "title": "Trip request constraints",
            "url": "app://trip-request",
            "category": "traveler_input",
            "evidence_type": "researched_fact",
        }
    ]
    for city in destinations:
        sources.append(
            {
                "title": f"{city} destination profile",
                "url": f"app://destination-profile/{city.lower()}",
                "category": "destination_profile",
                "evidence_type": "inferred_recommendation" if mode == "mock" else "researched_fact",
            }
        )
    sources.append(
        {
            "title": "Budget estimator",
            "url": "app://pricing-estimator",
            "category": "pricing",
            "evidence_type": "estimated_price",
        }
    )
    return sources


def _configure_model_provider_env(settings: Settings) -> None:
    if settings.google_api_key:
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key
    if settings.tavily_api_key:
        os.environ["TAVILY_API_KEY"] = settings.tavily_api_key


def _build_tavily_tool():
    from langchain_tavily import TavilySearch

    return TavilySearch(
        max_results=5,
        include_answer=True,
        include_raw_content=True,
    )


def _message_text_from_result(result: dict[str, Any]) -> str:
    messages = result.get("messages", [])
    if not messages:
        raise ValueError("Deepagents returned no messages.")

    final_message = messages[-1]
    content = getattr(final_message, "content", final_message.get("content", ""))
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        if text_parts:
            return "\n".join(text_parts)
    raise ValueError("Deepagents returned no text content.")


def _extract_json_payload(raw_text: str) -> dict[str, Any]:
    trimmed = raw_text.strip()
    if trimmed.startswith("```"):
        trimmed = trimmed.split("\n", 1)[1]
        if trimmed.endswith("```"):
            trimmed = trimmed.rsplit("\n", 1)[0]

    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Deepagents response did not include a JSON object.")
    return json.loads(trimmed[start : end + 1])


class TripPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate_trip_options(self, payload: TripCreateRequest) -> PlanningArtifacts:
        if self.settings.enable_real_agent and self.settings.tavily_api_key and self.settings.google_api_key:
            try:
                return self._generate_with_deepagents(payload)
            except Exception:
                pass
        return self._generate_mock_options(payload)

    def generate_itinerary(self, payload: TripCreateRequest, selected_option: dict[str, Any]) -> ItineraryArtifacts:
        if self.settings.enable_real_agent and self.settings.tavily_api_key and self.settings.google_api_key:
            try:
                return self._generate_deep_itinerary(payload, selected_option)
            except Exception:
                pass
        return self._generate_mock_itinerary(payload, selected_option)

    def _generate_mock_options(self, payload: TripCreateRequest) -> PlanningArtifacts:
        trip_days = _trip_length(payload)
        candidates = payload.destination_candidates[:4]
        combos: list[list[str]] = []
        if len(candidates) == 1:
            combos.append(candidates)
        else:
            for size in range(min(3, len(candidates)), 0, -1):
                for combo in combinations(candidates, size):
                    combos.append(list(combo))
        unique: list[list[str]] = []
        seen = set()
        for combo in combos:
            key = tuple(combo)
            if key not in seen:
                unique.append(combo)
                seen.add(key)
            if len(unique) == 4:
                break

        options = []
        for rank, stops in enumerate(unique, start=1):
            allocations = _allocate_days(trip_days, stops)
            fit_score = _fit_score(stops, payload.trip_style)
            cost_min, cost_max = _estimate_costs(payload, stops)
            highlight_bits = []
            for city in stops:
                traits = _normalized_traits(city)
                highlight_bits.append(traits["highlights"][0])
            options.append(
                {
                    "name": _make_option_name(stops),
                    "summary": (
                        f"A { _pace_label(len(stops), trip_days, payload.pace_preference).lower() } route through "
                        f"{', '.join(stops)} built around {', '.join(highlight_bits[:2])}."
                    ),
                    "rationale": (
                        f"This option leans into the user's request for {payload.trip_style.strip()} by pairing "
                        f"{', '.join(stops[:2])} and keeping enough time in each stop to avoid a tab-heavy trip."
                    ),
                    "tradeoffs": _make_tradeoffs(stops, trip_days),
                    "destination_order": stops,
                    "days_by_stop": allocations,
                    "pace_label": _pace_label(len(stops), trip_days, payload.pace_preference),
                    "estimated_total_min": cost_min,
                    "estimated_total_max": cost_max,
                    "budget_confidence": "medium",
                    "fit_score": round(fit_score - (rank - 1) * 0.2, 1),
                }
            )

        steps = [
            {"agent": "intake-agent", "status": "completed", "detail": "Normalized traveler constraints and timing window."},
            {"agent": "routing-agent", "status": "completed", "detail": "Compared destination combinations and pacing tradeoffs."},
            {"agent": "budget-agent", "status": "completed", "detail": "Estimated flight, lodging, food, and local transit ranges."},
            {"agent": "planner-agent", "status": "completed", "detail": "Ranked options by fit, pacing, and estimated spend."},
        ]
        return PlanningArtifacts(
            mode="mock",
            planning_summary=f"Generated {len(options)} trip options with structured routing and budget estimates.",
            options=options,
            sources=_planning_sources(candidates, "mock"),
            steps=steps,
        )

    def _generate_mock_itinerary(self, payload: TripCreateRequest, selected_option: dict[str, Any]) -> ItineraryArtifacts:
        allocations = selected_option["days_by_stop"]
        keywords = _style_keywords(payload.trip_style) or {"food", "culture", "relaxation"}
        day_rows = []
        neighborhoods = []
        current_date = payload.start_date
        for stop in allocations:
            city = str(stop["city"])
            traits = _normalized_traits(city)
            neighborhoods.append(
                {
                    "city": city,
                    "recommended_area": traits["neighborhoods"][0],
                    "why": f"Strong base for {', '.join(traits['vibe'][:2])} with walkable access to core experiences.",
                }
            )
            for _ in range(int(stop["nights"])):
                lead_theme = next(iter(keywords))
                blocks = ACTIVITY_BLOCKS.get(lead_theme, ACTIVITY_BLOCKS["culture"])
                day_number = len(day_rows) + 1
                day_rows.append(
                    {
                        "day_number": day_number,
                        "city": city,
                        "theme": f"{city} with a {lead_theme}-first rhythm",
                        "morning": f"{blocks[0]} in {traits['neighborhoods'][0]}.",
                        "afternoon": f"{blocks[1]}; keep one anchor around {traits['highlights'][0]}.",
                        "evening": f"{blocks[2]} and orient around {traits['neighborhoods'][1]}.",
                        "logistics_note": (
                            f"{city} segment for {current_date.isoformat()}. Keep transit blocks under two commitments today."
                        ),
                        "flexibility_note": "Reserve one flexible hour for weather, jet lag, or spontaneous finds.",
                    }
                )
                current_date = current_date + timedelta(days=1)

        first_stop = allocations[0]["city"]
        summary = f"Built a {selected_option['pace_label'].lower()} itinerary across {len(allocations)} stops."
        itinerary = {
            "title": f"{selected_option['name']} itinerary",
            "overview": (
                f"This itinerary turns the selected route into day-by-day structure with room for "
                f"{payload.trip_style.strip()} while keeping transfer days realistic."
            ),
            "logistics": (
                f"Plan major transfers between {', '.join(selected_option['destination_order'])} in the middle of the day, "
                "and avoid stacking reservations immediately after arrivals."
            ),
            "neighborhood_guidance": neighborhoods,
            "days": day_rows,
        }
        flights = [
            {
                "carrier": "Best Balance Route",
                "route_summary": f"{payload.origin} → {first_stop} → {allocations[-1]['city']} → {payload.origin}",
                "price": max(420, int(selected_option["estimated_total_min"] * 0.23)),
                "stops": max(0, len(allocations) - 1),
                "comfort_label": "Best overall fit",
                "source_name": "Google Flights",
                "booking_url": build_google_flights_link(
                    payload.origin,
                    str(first_stop),
                    payload.start_date.isoformat(),
                    payload.end_date.isoformat(),
                ),
                "match_reason": "Best balance of routing simplicity, pace, and estimated total spend.",
            },
            {
                "carrier": "Low Friction Schedule",
                "route_summary": f"{payload.origin} → {first_stop} round-trip with internal hop coverage",
                "price": max(390, int(selected_option["estimated_total_min"] * 0.2)),
                "stops": 1,
                "comfort_label": "Simplest logistics",
                "source_name": "Google Flights",
                "booking_url": build_google_flights_link(
                    payload.origin,
                    str(first_stop),
                    payload.start_date.isoformat(),
                    payload.end_date.isoformat(),
                ),
                "match_reason": "Reduces transfer complexity and protects the trip if schedules shift.",
            },
        ]
        hotels = []
        for stop in allocations:
            traits = _normalized_traits(str(stop["city"]))
            hotels.append(
                {
                    "city": str(stop["city"]),
                    "name": f"{stop['city']} Base Camp",
                    "neighborhood": traits["neighborhoods"][0],
                    "nightly_rate": max(135, int(selected_option["estimated_total_min"] / max(1, _trip_length(payload)) * 0.42)),
                    "rating": 4.4,
                    "style_label": f"{selected_option['pace_label']} boutique stay",
                    "source_name": "Booking.com",
                    "booking_url": build_booking_link(
                        str(stop["city"]),
                        payload.start_date.isoformat(),
                        payload.end_date.isoformat(),
                    ),
                    "match_reason": f"Strong access to {traits['neighborhoods'][0]} and the itinerary's main activity zones.",
                }
            )
        steps = [
            {"agent": "research-agent", "status": "completed", "detail": "Mapped destination themes and neighborhood fit."},
            {"agent": "itinerary-agent", "status": "completed", "detail": "Drafted daily morning, afternoon, and evening structure."},
            {"agent": "booking-discovery-agent", "status": "completed", "detail": "Prepared flight and hotel link-out options aligned to the route."},
        ]
        return ItineraryArtifacts(
            mode="mock",
            summary=summary,
            itinerary=itinerary,
            flights=flights,
            hotels=hotels,
            sources=_planning_sources(selected_option["destination_order"], "mock"),
            steps=steps,
        )

    def _generate_with_deepagents(self, payload: TripCreateRequest) -> PlanningArtifacts:
        from deepagents import create_deep_agent
        from langgraph.checkpoint.memory import MemorySaver
        _configure_model_provider_env(self.settings)
        tavily_search_tool = _build_tavily_tool()

        research_subagent = {
            "name": "research-agent",
            "description": "Researches destination fit, seasonality, and activity signals for the requested trip.",
            "system_prompt": "Research the requested destinations and return concise evidence for trip planning.",
            "tools": [tavily_search_tool],
        }
        routing_subagent = {
            "name": "routing-agent",
            "description": "Recommends feasible destination combinations and sequencing.",
            "system_prompt": "Optimize route feasibility, pacing, and variety without suggesting impossible routing.",
            "tools": [tavily_search_tool],
        }
        agent = create_deep_agent(
            model=self.settings.llm_model,
            tools=[tavily_search_tool],
            subagents=[research_subagent, routing_subagent],
            checkpointer=MemorySaver(),
            name="trip-architect-planner",
        )
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Generate 3-5 trip options for this request and return only valid JSON. "
                            "The JSON object must contain: planning_summary (string), options (array), sources (array). "
                            "Each option must include name, summary, rationale, tradeoffs, destination_order, days_by_stop, "
                            "pace_label, estimated_total_min, estimated_total_max, budget_confidence, and fit_score. "
                            "Each days_by_stop item must be an object with city, nights, start_day, and end_day. "
                            "Each source must include title, url, category, and evidence_type. "
                            f"Origin: {payload.origin}. Dates: {payload.start_date} to {payload.end_date}. "
                            f"Candidates: {', '.join(payload.destination_candidates)}. "
                            f"Trip style: {payload.trip_style}. Budget: {payload.budget_range or 'not specified'}. "
                            f"Travelers: {payload.traveler_count}. Pace: {payload.pace_preference or 'not specified'}."
                        ),
                    }
                ]
            },
            config={"configurable": {"thread_id": f"trip-options-{payload.origin}-{payload.start_date}"}},
        )
        structured = DeepTripOptionsPayload.model_validate(_extract_json_payload(_message_text_from_result(result)))
        trip_days = _trip_length(payload)
        normalized_options = []
        for option in structured.options:
            normalized_option = option.model_dump()
            normalized_option["days_by_stop"] = _normalize_days_by_stop(
                normalized_option["days_by_stop"],
                normalized_option["destination_order"],
                trip_days,
            )
            normalized_options.append(normalized_option)
        return PlanningArtifacts(
            mode="deepagents",
            planning_summary=structured.planning_summary,
            options=normalized_options,
            sources=[source.model_dump() for source in structured.sources],
            steps=[
                {"agent": "intake-agent", "status": "completed", "detail": "Delegated trip planning to deepagents workflow."},
                {"agent": "research-agent", "status": "completed", "detail": "Gathered Tavily-backed destination context."},
                {"agent": "routing-agent", "status": "completed", "detail": "Returned structured routing recommendations."},
            ],
        )

    def _generate_deep_itinerary(self, payload: TripCreateRequest, selected_option: dict[str, Any]) -> ItineraryArtifacts:
        from deepagents import create_deep_agent
        from langgraph.checkpoint.memory import MemorySaver
        _configure_model_provider_env(self.settings)
        tavily_search_tool = _build_tavily_tool()

        itinerary_subagent = {
            "name": "itinerary-agent",
            "description": "Builds a day-by-day travel itinerary with logistics and neighborhood guidance.",
            "system_prompt": "Return a realistic itinerary with daily structure and room for recovery time.",
            "tools": [tavily_search_tool],
        }
        agent = create_deep_agent(
            model=self.settings.llm_model,
            tools=[tavily_search_tool],
            subagents=[itinerary_subagent],
            checkpointer=MemorySaver(),
            name="trip-architect-itinerary",
        )
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Build a personalized itinerary for this selected trip option and return only valid JSON. "
                            "The JSON object must contain title, overview, logistics, neighborhood_guidance, days, and sources. "
                            "Each day must include day_number, city, theme, morning, afternoon, evening, logistics_note, and flexibility_note. "
                            "Each neighborhood guidance item must include city, recommended_area, and why. "
                            "Each source must include title, url, category, and evidence_type. "
                            f"Trip style: {payload.trip_style}. Route: {selected_option['destination_order']}. "
                            f"Day allocation: {selected_option['days_by_stop']}."
                        ),
                    }
                ]
            },
            config={"configurable": {"thread_id": f"trip-itinerary-{payload.origin}-{payload.start_date}"}},
        )
        structured = DeepItineraryPayload.model_validate(_extract_json_payload(_message_text_from_result(result)))
        mock_result = self._generate_mock_itinerary(payload, selected_option)
        return ItineraryArtifacts(
            mode="deepagents",
            summary="Generated itinerary with Tavily-backed research and structured deepagents output.",
            itinerary={
                "title": structured.title,
                "overview": structured.overview,
                "logistics": structured.logistics,
                "neighborhood_guidance": structured.neighborhood_guidance,
                "days": [day.model_dump() for day in structured.days],
            },
            flights=mock_result.flights,
            hotels=mock_result.hotels,
            sources=[source.model_dump() for source in structured.sources],
            steps=[
                {"agent": "research-agent", "status": "completed", "detail": "Pulled destination context with Tavily."},
                {"agent": "itinerary-agent", "status": "completed", "detail": "Returned structured itinerary output."},
                {"agent": "booking-discovery-agent", "status": "completed", "detail": "Composed booking link-out recommendations."},
            ],
        )
