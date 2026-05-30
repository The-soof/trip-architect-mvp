from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from itertools import combinations
import json
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.schemas.trip import TripCreateRequest
from app.services.booking import build_booking_link, build_kayak_flights_link
from app.services.google_places import PlaceLookupResult, search_places

StructuredPayloadT = TypeVar("StructuredPayloadT", bound=BaseModel)

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
    title: str = "Agent research note"
    url: str = "app://agent-research"
    category: str = "agent_research"
    evidence_type: str = Field(default="researched_fact", description="One of researched_fact, inferred_recommendation, estimated_price")


class GeminiDayStopPayload(BaseModel):
    city: str
    nights: int
    start_day: int
    end_day: int


class GeminiOptionSeed(BaseModel):
    name: str
    summary: str
    rationale: str
    tradeoffs: list[str] = Field(default_factory=list)
    destination_order: list[str] = Field(default_factory=list)
    days_by_stop: list[GeminiDayStopPayload] = Field(default_factory=list)
    pace_label: str
    budget_confidence: str = "medium"
    fit_score: float


class GeminiTripOptionsPayload(BaseModel):
    planning_summary: str
    options: list[GeminiOptionSeed] = Field(default_factory=list)


class PlaceQueryCandidate(BaseModel):
    city: str
    category: str
    query: str
    reason: str


class PlacesResearchPlanPayload(BaseModel):
    overview: str
    venue_queries: list[PlaceQueryCandidate] = Field(default_factory=list)
    hotel_queries: list[PlaceQueryCandidate] = Field(default_factory=list)


class DeepItineraryDayPayload(BaseModel):
    day_number: int
    city: str
    theme: str
    morning: str
    afternoon: str
    evening: str
    logistics_note: str
    flexibility_note: str


class NeighborhoodGuidancePayload(BaseModel):
    city: str
    recommended_area: str
    why: str


class DeepItineraryPayload(BaseModel):
    title: str
    overview: str
    logistics: str
    neighborhood_guidance: list[NeighborhoodGuidancePayload] = Field(default_factory=list)
    days: list[DeepItineraryDayPayload] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)


@dataclass
class PlanningArtifacts:
    mode: str
    planning_summary: str
    options: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    fallback_reason: str | None = None


@dataclass
class ItineraryArtifacts:
    mode: str
    summary: str
    itinerary: dict[str, Any]
    flights: list[dict[str, Any]]
    hotels: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    fallback_reason: str | None = None


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
    stop_count = max(1, len(stops))
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
        },
        {
            "title": "Gemini route synthesis",
            "url": "app://gemini/route-synthesis",
            "category": "model_reasoning",
            "evidence_type": "inferred_recommendation",
        },
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


def _log_agent_event(flow: str, message: str, **metadata: Any) -> None:
    payload = {"flow": flow, "message": message, **metadata}
    print(f"trip_architect.planner {json.dumps(payload, default=str)}", flush=True)


def _is_bad_request_error(exc: Exception) -> bool:
    class_name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    return (
        "badrequest" in class_name
        or "invalidargument" in class_name
        or "400" in message
        or "bad request" in message
        or "invalid_argument" in message
        or "response schema" in message
    )


def _fallback_reason_from_exception(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()
    if _is_bad_request_error(exc):
        return (
            "The live Gemini structured response failed at the API boundary, so Trip Architect switched to the "
            "deterministic fallback planner."
        )
    if "resource_exhausted" in lowered or "429" in lowered or "quota" in lowered or "credit" in lowered:
        return "The live Gemini, Tavily, or Google Places pipeline is currently unavailable, so Trip Architect switched to the deterministic fallback planner."
    if "api key" in lowered or "permission" in lowered or "auth" in lowered or "forbidden" in lowered or "unauthorized" in lowered:
        return "The live Gemini, Tavily, or Google Places credentials were rejected, so Trip Architect switched to the deterministic fallback planner."
    if "timeout" in lowered or "timed out" in lowered:
        return "The live itinerary pipeline exceeded the time budget before finishing. Trip Architect switched to the deterministic fallback planner."
    return f"Live planning was unavailable ({message[:160]}), so Trip Architect switched to the deterministic fallback planner."


def _message_text_from_response(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return text
    raise ValueError("Gemini response did not include text content.")


def _generate_structured_with_gemini(
    settings: Settings,
    prompt: str,
    schema: type[StructuredPayloadT],
    *,
    temperature: float = 0.2,
) -> StructuredPayloadT:
    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config={
            "temperature": temperature,
            "response_mime_type": "application/json",
            "response_schema": schema,
        },
    )
    return schema.model_validate_json(_message_text_from_response(response))


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source in sources:
        key = (str(source.get("title", "")), str(source.get("url", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _build_tavily_queries(payload: TripCreateRequest, selected_option: dict[str, Any], max_queries: int) -> list[str]:
    route = ", ".join(selected_option["destination_order"])
    month_hint = payload.start_date.strftime("%B %Y")
    query_pool = [
        f"{route} {month_hint} seasonal events festivals travel calendar",
        f"{route} neighborhood guide travel blog best areas food nightlife culture",
        f"{route} opening hours closures reservation alerts local guide",
        f"{route} airport transfer logistics ferry train travel tips",
    ]
    return query_pool[:max_queries]


def _simplify_tavily_result(query: str, result: dict[str, Any]) -> dict[str, Any]:
    items = []
    for row in result.get("results", [])[:3]:
        items.append(
            {
                "title": row.get("title") or "Travel research result",
                "url": row.get("url") or "about:blank",
                "content": " ".join(str(row.get("content", "")).split())[:320],
            }
        )
    return {"query": query, "results": items}


async def _run_tavily_searches(settings: Settings, queries: list[str]) -> list[dict[str, Any]]:
    from tavily import TavilyClient

    client = TavilyClient(api_key=settings.tavily_api_key)
    tasks = [
        asyncio.to_thread(
            client.search,
            query=query,
            max_results=3 if settings.fast_mvp_mode else 5,
            topic="general",
            include_raw_content=False,
        )
        for query in queries
    ]
    results = await asyncio.gather(*tasks)
    return [_simplify_tavily_result(query, result) for query, result in zip(queries, results, strict=False)]


async def _resolve_places(
    settings: Settings,
    venue_queries: list[PlaceQueryCandidate],
    hotel_queries: list[PlaceQueryCandidate],
) -> tuple[list[PlaceLookupResult], list[PlaceLookupResult]]:
    venue_tasks = [
        asyncio.to_thread(
            search_places,
            api_key=settings.google_places_api_key or "",
            query=candidate.query,
            city=candidate.city,
            category=candidate.category,
            reason=candidate.reason,
            max_results=1,
        )
        for candidate in venue_queries
    ]
    hotel_tasks = [
        asyncio.to_thread(
            search_places,
            api_key=settings.google_places_api_key or "",
            query=candidate.query,
            city=candidate.city,
            category="hotel",
            reason=candidate.reason,
            max_results=1,
        )
        for candidate in hotel_queries
    ]
    venue_results, hotel_results = await asyncio.gather(
        asyncio.gather(*venue_tasks),
        asyncio.gather(*hotel_tasks),
    )
    return list(venue_results), list(hotel_results)


def _place_sources(results: list[PlaceLookupResult]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for result in results:
        if not result.place or not result.place.get("maps_url"):
            continue
        sources.append(
            {
                "title": result.place["name"],
                "url": result.place["maps_url"],
                "category": f"google_places_{result.category}",
                "evidence_type": "researched_fact",
            }
        )
    return sources


def _tavily_sources(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for result in results:
        for item in result["results"]:
            sources.append(
                {
                    "title": item["title"],
                    "url": item["url"],
                    "category": "tavily_research",
                    "evidence_type": "researched_fact",
                }
            )
    return sources


def _build_hotel_options(
    payload: TripCreateRequest,
    selected_option: dict[str, Any],
    hotel_places: list[PlaceLookupResult],
) -> list[dict[str, Any]]:
    hotels_by_city = {result.city.lower(): result for result in hotel_places if result.place}
    hotels: list[dict[str, Any]] = []
    for stop_index, stop in enumerate(selected_option["days_by_stop"]):
        city = str(stop["city"])
        nights = int(stop.get("nights", 3))
        traits = _normalized_traits(city)
        checkin_date = (payload.start_date + timedelta(days=int(stop["start_day"]) - 1)).isoformat()
        checkout_date = (payload.start_date + timedelta(days=int(stop["end_day"]))).isoformat()
        place_result = hotels_by_city.get(city.lower())
        place = place_result.place if place_result else None
        base_rate = max(135, int(selected_option["estimated_total_min"] / max(1, _trip_length(payload)) * 0.42))
        rate_multiplier = [1.0, 0.86, 1.12][stop_index % 3]
        nightly_rate = max(110, int(base_rate * rate_multiplier * (1.0 + nights * 0.02)))
        hotels.append(
            {
                "city": city,
                "name": place["name"] if place else f"{city} Base Camp",
                "neighborhood": traits["neighborhoods"][0],
                "nightly_rate": nightly_rate,
                "rating": float(place.get("rating") or 4.3) if place else 4.3,
                "style_label": f"{selected_option['pace_label']} stay",
                "source_name": "Booking.com",
                "booking_url": build_booking_link(city, checkin_date, checkout_date),
                "match_reason": place_result.reason if place_result else f"Strong access to {traits['neighborhoods'][0]} and the itinerary's main activity zones.",
                "address": place.get("address") if place else None,
                "latitude": place.get("latitude") if place else None,
                "longitude": place.get("longitude") if place else None,
                "maps_url": place.get("maps_url") if place else None,
            }
        )
    return hotels


def _build_flight_options(payload: TripCreateRequest, selected_option: dict[str, Any]) -> list[dict[str, Any]]:
    allocations = selected_option["days_by_stop"]
    first_stop = str(allocations[0]["city"])
    last_stop = str(allocations[-1]["city"])
    return [
        {
            "carrier": "Open-jaw balance",
            "route_summary": f"{payload.origin} → {first_stop} / {last_stop} → {payload.origin}",
            "price": max(420, int(selected_option["estimated_total_min"] * 0.23)),
            "stops": max(0, len(allocations) - 1),
            "comfort_label": "Best overall fit",
            "source_name": "Kayak",
            "booking_url": build_kayak_flights_link(
                payload.origin,
                first_stop,
                payload.start_date.isoformat(),
                payload.end_date.isoformat(),
                adults=payload.traveler_count,
            ),
            "match_reason": "Keeps the route aligned with the chosen stop order and avoids unnecessary backtracking.",
        },
        {
            "carrier": "Simplest timing",
            "route_summary": f"{payload.origin} → {first_stop} round-trip with regional transfers in between",
            "price": max(390, int(selected_option["estimated_total_min"] * 0.2)),
            "stops": 1,
            "comfort_label": "Lowest friction",
            "source_name": "Kayak",
            "booking_url": build_kayak_flights_link(
                payload.origin,
                first_stop,
                payload.start_date.isoformat(),
                payload.end_date.isoformat(),
                adults=payload.traveler_count,
            ),
            "match_reason": "Useful if the traveler prefers one primary arrival airport and simpler ticket management.",
        },
    ]


class TripPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate_trip_options(self, payload: TripCreateRequest) -> PlanningArtifacts:
        if self.settings.enable_real_agent and self.settings.gemini_api_key:
            try:
                return self._generate_with_gemini_options(payload)
            except Exception as exc:
                return self._generate_mock_options(payload, fallback_reason=_fallback_reason_from_exception(exc))
        return self._generate_mock_options(payload)

    def generate_itinerary(self, payload: TripCreateRequest, selected_option: dict[str, Any]) -> ItineraryArtifacts:
        if (
            self.settings.enable_real_agent
            and self.settings.gemini_api_key
            and self.settings.tavily_api_key
            and self.settings.google_places_api_key
        ):
            try:
                return self._generate_with_research_pipeline(payload, selected_option)
            except Exception as exc:
                return self._generate_mock_itinerary(payload, selected_option, fallback_reason=_fallback_reason_from_exception(exc))
        return self._generate_mock_itinerary(payload, selected_option)

    def _generate_mock_options(
        self,
        payload: TripCreateRequest,
        fallback_reason: str | None = None,
    ) -> PlanningArtifacts:
        trip_days = _trip_length(payload)
        candidates = payload.destination_candidates[:6]
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
            if len(unique) == 6:
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
                        f"A {_pace_label(len(stops), trip_days, payload.pace_preference).lower()} route through "
                        f"{', '.join(stops)} built around {', '.join(highlight_bits[:2])}."
                    ),
                    "rationale": (
                        f"This option leans into the request for {payload.trip_style.strip()} by pairing "
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
        if fallback_reason:
            steps.append({"agent": "fallback-guard", "status": "warning", "detail": fallback_reason})
        return PlanningArtifacts(
            mode="mock",
            planning_summary=(
                f"Generated {len(options)} trip options with structured routing and budget estimates."
                if not fallback_reason
                else f"Generated {len(options)} trip options with the deterministic fallback planner after the live path failed."
            ),
            options=options,
            sources=_planning_sources(candidates, "mock"),
            steps=steps,
            fallback_reason=fallback_reason,
        )

    def _generate_mock_itinerary(
        self,
        payload: TripCreateRequest,
        selected_option: dict[str, Any],
        fallback_reason: str | None = None,
    ) -> ItineraryArtifacts:
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
        flights = _build_flight_options(payload, selected_option)
        hotels = _build_hotel_options(payload, selected_option, [])
        steps = [
            {"agent": "research-agent", "status": "completed", "detail": "Mapped destination themes and neighborhood fit."},
            {"agent": "itinerary-agent", "status": "completed", "detail": "Drafted daily morning, afternoon, and evening structure."},
            {"agent": "booking-discovery-agent", "status": "completed", "detail": "Prepared flight and hotel link-out options aligned to the route."},
        ]
        if fallback_reason:
            steps.append({"agent": "fallback-guard", "status": "warning", "detail": fallback_reason})
        return ItineraryArtifacts(
            mode="mock",
            summary=summary if not fallback_reason else "Built the itinerary with the deterministic fallback planner after the live path failed.",
            itinerary=itinerary,
            flights=flights,
            hotels=hotels,
            sources=_planning_sources(selected_option["destination_order"], "mock"),
            steps=steps,
            fallback_reason=fallback_reason,
        )

    def _generate_with_gemini_options(self, payload: TripCreateRequest) -> PlanningArtifacts:
        trip_days = _trip_length(payload)
        prompt = (
            "You are Trip Architect's trip-options planner. Return only valid JSON. "
            "Generate 4 to 6 realistic route options using only the user's trip brief, not web search. "
            "Each option must include: name, summary, rationale, tradeoffs, destination_order, days_by_stop, pace_label, budget_confidence, fit_score. "
            "Keep destination_order limited to the provided candidates and make days_by_stop feasible for the exact trip length. "
            "Be decisive, concrete, and avoid duplicate route orders. "
            f"Origin: {payload.origin}. Dates: {payload.start_date} to {payload.end_date} ({trip_days} nights). "
            f"Candidate destinations: {', '.join(payload.destination_candidates)}. "
            f"Trip style: {payload.trip_style}. Budget: {payload.budget_range or 'not specified'}. "
            f"Travelers: {payload.traveler_count}. Pace preference: {payload.pace_preference or 'not specified'}."
        )
        structured = _generate_structured_with_gemini(self.settings, prompt, GeminiTripOptionsPayload, temperature=0.25)
        if not structured.options:
            raise ValueError("Gemini returned no trip options.")

        normalized_options = []
        seen_routes: set[tuple[str, ...]] = set()
        for rank, option in enumerate(structured.options, start=1):
            candidate = option.model_dump()
            route = tuple(candidate["destination_order"])
            if not route or route in seen_routes:
                continue
            seen_routes.add(route)
            candidate["days_by_stop"] = _normalize_days_by_stop(candidate["days_by_stop"], candidate["destination_order"], trip_days)
            candidate["tradeoffs"] = candidate["tradeoffs"] or _make_tradeoffs(candidate["destination_order"], trip_days)
            cost_min, cost_max = _estimate_costs(payload, candidate["destination_order"])
            candidate["estimated_total_min"] = cost_min
            candidate["estimated_total_max"] = cost_max
            candidate["pace_label"] = _pace_label(len(candidate["destination_order"]), trip_days, candidate["pace_label"] or payload.pace_preference)
            candidate["budget_confidence"] = (candidate.get("budget_confidence") or "medium").lower()[:32]
            candidate["fit_score"] = round(max(0.0, min(10.0, float(candidate["fit_score"]) - (rank - 1) * 0.05)), 1)
            normalized_options.append(candidate)
            if len(normalized_options) == 6:
                break

        if not normalized_options:
            raise ValueError("Gemini returned only invalid or duplicate route options.")

        return PlanningArtifacts(
            mode="gemini",
            planning_summary=structured.planning_summary,
            options=normalized_options,
            sources=_planning_sources(payload.destination_candidates[:6], "gemini"),
            steps=[
                {"agent": "intake-agent", "status": "completed", "detail": "Normalized dates, budget, and route constraints for Gemini."},
                {"agent": "gemini-planner", "status": "completed", "detail": "Generated structured trip options with Gemini 2.5 Flash."},
                {"agent": "budget-agent", "status": "completed", "detail": "Applied local cost and pacing estimates for each returned route."},
            ],
        )

    def _build_places_research_plan(
        self,
        payload: TripCreateRequest,
        selected_option: dict[str, Any],
        tavily_results: list[dict[str, Any]],
    ) -> PlacesResearchPlanPayload:
        prompt = (
            "You are preparing Google Places lookups for a travel itinerary. Return only valid JSON. "
            "Create up to 3 venue queries per city for morning, afternoon, and evening experiences, plus 1 hotel query per city. "
            "Every query must be concise and suitable for Google Places text search. "
            "Prefer concrete venue names when the research clearly names them; otherwise use neighborhood-aware search phrases. "
            f"Trip style: {payload.trip_style}. Route: {selected_option['destination_order']}. "
            f"Tavily layer 1 research: {json.dumps(tavily_results, ensure_ascii=True)}"
        )
        return _generate_structured_with_gemini(self.settings, prompt, PlacesResearchPlanPayload, temperature=0.15)

    def _build_itinerary_prompt(
        self,
        payload: TripCreateRequest,
        selected_option: dict[str, Any],
        tavily_results: list[dict[str, Any]],
        venue_places: list[PlaceLookupResult],
        hotel_places: list[PlaceLookupResult],
    ) -> str:
        simplified_places = [
            {
                "city": result.city,
                "category": result.category,
                "reason": result.reason,
                "place": result.place,
            }
            for result in venue_places + hotel_places
            if result.place
        ]
        return (
            "You are Trip Architect's itinerary synthesizer. Return only valid JSON. "
            "Use Layer 1 Tavily research plus Layer 2 Google Places facts to produce a useful, travelable day-by-day itinerary. "
            "Only mention specific named venues when they appear in the Google Places layer. "
            "Preserve slack on arrival and transfer days, and surface timing cautions when opening-hours context suggests them. "
            f"Trip style: {payload.trip_style}. Route: {selected_option['destination_order']}. "
            f"Day allocation: {selected_option['days_by_stop']}. "
            f"Layer 1 Tavily research: {json.dumps(tavily_results, ensure_ascii=True)}. "
            f"Layer 2 Google Places research: {json.dumps(simplified_places, ensure_ascii=True)}."
        )

    def _generate_with_research_pipeline(self, payload: TripCreateRequest, selected_option: dict[str, Any]) -> ItineraryArtifacts:
        max_queries = self.settings.fast_mvp_search_limit if self.settings.fast_mvp_mode else 4
        tavily_queries = _build_tavily_queries(payload, selected_option, max_queries)
        _log_agent_event("itinerary", "research_started", tavily_queries=tavily_queries)
        tavily_results = asyncio.run(_run_tavily_searches(self.settings, tavily_queries))
        research_plan = self._build_places_research_plan(payload, selected_option, tavily_results)
        venue_places, hotel_places = asyncio.run(
            _resolve_places(
                self.settings,
                research_plan.venue_queries,
                research_plan.hotel_queries,
            )
        )
        prompt = self._build_itinerary_prompt(payload, selected_option, tavily_results, venue_places, hotel_places)
        structured = _generate_structured_with_gemini(self.settings, prompt, DeepItineraryPayload, temperature=0.2)
        hotels = _build_hotel_options(payload, selected_option, hotel_places)
        flights = _build_flight_options(payload, selected_option)
        sources = _dedupe_sources(
            [source.model_dump() for source in structured.sources] + _tavily_sources(tavily_results) + _place_sources(venue_places + hotel_places)
        )
        return ItineraryArtifacts(
            mode="hybrid_research",
            summary="Generated itinerary with Tavily seasonal research, Google Places enrichment, and Gemini structured synthesis.",
            itinerary={
                "title": structured.title,
                "overview": structured.overview,
                "logistics": structured.logistics,
                "neighborhood_guidance": [item.model_dump() for item in structured.neighborhood_guidance],
                "days": [day.model_dump() for day in structured.days],
            },
            flights=flights,
            hotels=hotels,
            sources=sources,
            steps=[
                {"agent": "research-agent", "status": "completed", "detail": "Gathered seasonal events, travel blogs, opening alerts, and local guide context with Tavily."},
                {"agent": "places-agent", "status": "completed", "detail": "Resolved venue and stay candidates into ratings, coordinates, hours, and addresses with Google Places."},
                {"agent": "gemini-itinerary-agent", "status": "completed", "detail": "Synthesized the final day-by-day itinerary from both research layers."},
                {"agent": "booking-discovery-agent", "status": "completed", "detail": "Prepared Booking.com and Kayak deeplinks for stays and flights."},
            ],
        )
