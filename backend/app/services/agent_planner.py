from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from itertools import combinations
import json
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.schemas.trip import TripCreateRequest
from app.services.booking import build_booking_link, build_google_flights_link

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


def _build_chat_model(settings: Settings):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0,
        max_tokens=2200,
        timeout=90,
    )


def _build_tavily_tool(settings: Settings):
    from langchain.tools import tool
    from tavily import TavilyClient

    tavily_client = TavilyClient(api_key=settings.tavily_api_key)
    search_count = 0

    @tool("internet_search")
    def internet_search(
        query: str,
        max_results: int = 5,
        topic: Literal["general", "news", "finance"] = "general",
        include_raw_content: bool = False,
    ) -> dict[str, Any]:
        """Run a Tavily web search for current travel facts, logistics, prices, and destination research."""
        nonlocal search_count
        capped_results = min(max_results, 3 if settings.fast_mvp_mode else 5)
        if settings.fast_mvp_mode and search_count >= settings.fast_mvp_search_limit:
            _log_agent_event(
                "tool",
                "internet_search_skipped",
                query=query,
                reason="fast_mvp_search_budget_exhausted",
                budget=settings.fast_mvp_search_limit,
            )
            return {
                "results": [],
                "answer": "",
                "query": query,
                "budget_exhausted": True,
            }
        search_count += 1
        _log_agent_event(
            "tool",
            "internet_search_started",
            query=query,
            max_results=capped_results,
            topic=topic,
            include_raw_content=include_raw_content,
            search_count=search_count,
        )
        result = tavily_client.search(
            query=query,
            max_results=capped_results,
            topic=topic,
            include_raw_content=include_raw_content,
        )
        _log_agent_event(
            "tool",
            "internet_search_completed",
            query=query,
            results_count=len(result.get("results", [])),
            search_count=search_count,
        )
        return result

    return internet_search


def _structured_response_from_result(result: dict[str, Any], schema: type[StructuredPayloadT]) -> StructuredPayloadT:
    structured_response = result.get("structured_response")
    if structured_response is not None:
        return schema.model_validate(structured_response)
    return schema.model_validate(_extract_json_payload(_message_text_from_result(result)))


def _log_agent_event(flow: str, message: str, **metadata: Any) -> None:
    payload = {"flow": flow, "message": message, **metadata}
    print(f"trip_architect.deepagent {json.dumps(payload, default=str)}", flush=True)


def _summarize_text(value: Any, limit: int = 260) -> str:
    if isinstance(value, str):
        text = value
    elif isinstance(value, list):
        text = " ".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in value)
    else:
        text = str(value)
    text = " ".join(text.split())
    return text[:limit]


def _log_agent_state(flow: str, step_index: int, state: dict[str, Any]) -> None:
    if state.get("structured_response") is not None:
        _log_agent_event(flow, "structured_response_ready", step_index=step_index)

    messages = state.get("messages", [])
    if not messages:
        _log_agent_event(flow, "state_update", step_index=step_index, keys=sorted(state.keys()))
        return

    latest_message = messages[-1]
    tool_calls = getattr(latest_message, "tool_calls", None) or []
    if tool_calls:
        _log_agent_event(
            flow,
            "tool_calls_requested",
            step_index=step_index,
            tools=[
                {
                    "name": call.get("name"),
                    "args": call.get("args"),
                }
                for call in tool_calls
            ],
        )
        return

    message_type = latest_message.__class__.__name__
    tool_name = getattr(latest_message, "name", None)
    content = getattr(latest_message, "content", "")
    _log_agent_event(
        flow,
        "message_update",
        step_index=step_index,
        message_type=message_type,
        tool_name=tool_name,
        content_preview=_summarize_text(content),
    )


def _run_deepagent_with_observability(agent: Any, payload: dict[str, Any], flow: str, max_steps: int = 24) -> dict[str, Any]:
    _log_agent_event(
        flow,
        "started",
        note="Using default Deep Agents harness tools plus Trip Architect custom tools.",
    )
    final_state: dict[str, Any] | None = None
    for step_index, state in enumerate(
        agent.stream(payload, stream_mode="values", config={"recursion_limit": max_steps + 4}),
        start=1,
    ):
        final_state = state
        _log_agent_state(flow, step_index, state)
        if step_index >= max_steps and state.get("structured_response") is None:
            raise TimeoutError(f"Deepagents exceeded the {max_steps}-step execution budget for {flow}.")
    if final_state is None:
        raise ValueError("Deepagents returned no state updates.")
    _log_agent_event(flow, "completed", total_messages=len(final_state.get("messages", [])))
    return final_state


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


def _fallback_reason_from_exception(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()
    if "resource_exhausted" in lowered or "429" in lowered or "quota" in lowered or "credit" in lowered:
        return "The live DeepSeek-compatible endpoint is currently unavailable, so Trip Architect switched to the structured fallback planner."
    if "api key" in lowered or "permission" in lowered or "auth" in lowered:
        return "The live DeepSeek-compatible endpoint rejected the credentials, so Trip Architect switched to the structured fallback planner."
    return f"Live agent planning was unavailable ({message[:160]}), so Trip Architect switched to the structured fallback planner."


class TripPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate_trip_options(self, payload: TripCreateRequest) -> PlanningArtifacts:
        if (
            self.settings.enable_real_agent
            and self.settings.tavily_api_key
            and self.settings.openai_api_key
            and self.settings.openai_base_url
        ):
            try:
                return self._generate_with_deepagents(payload)
            except Exception as exc:
                return self._generate_mock_options(payload, fallback_reason=_fallback_reason_from_exception(exc))
        return self._generate_mock_options(payload)

    def generate_itinerary(self, payload: TripCreateRequest, selected_option: dict[str, Any]) -> ItineraryArtifacts:
        if (
            self.settings.enable_real_agent
            and self.settings.tavily_api_key
            and self.settings.openai_api_key
            and self.settings.openai_base_url
        ):
            try:
                return self._generate_deep_itinerary(payload, selected_option)
            except Exception as exc:
                return self._generate_mock_itinerary(payload, selected_option, fallback_reason=_fallback_reason_from_exception(exc))
        return self._generate_mock_itinerary(payload, selected_option)

    def _generate_mock_options(
        self,
        payload: TripCreateRequest,
        fallback_reason: str | None = None,
    ) -> PlanningArtifacts:
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
        if fallback_reason:
            steps.append({"agent": "fallback-guard", "status": "warning", "detail": fallback_reason})
        return PlanningArtifacts(
            mode="mock",
            planning_summary=(
                f"Generated {len(options)} trip options with structured routing and budget estimates."
                if not fallback_reason
                else f"Generated {len(options)} trip options with the structured fallback planner after the live agent path failed."
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
        if fallback_reason:
            steps.append({"agent": "fallback-guard", "status": "warning", "detail": fallback_reason})
        return ItineraryArtifacts(
            mode="mock",
            summary=summary if not fallback_reason else "Built the itinerary with the structured fallback planner after the live agent path failed.",
            itinerary=itinerary,
            flights=flights,
            hotels=hotels,
            sources=_planning_sources(selected_option["destination_order"], "mock"),
            steps=steps,
            fallback_reason=fallback_reason,
        )

    def _generate_with_deepagents(self, payload: TripCreateRequest) -> PlanningArtifacts:
        from deepagents import create_deep_agent

        tavily_search_tool = _build_tavily_tool(self.settings)
        chat_model = _build_chat_model(self.settings)
        max_searches = self.settings.fast_mvp_search_limit if self.settings.fast_mvp_mode else 6
        max_steps = 8 if self.settings.fast_mvp_mode else 24
        direct_search_guidance = (
            "Temporary fast MVP mode is active. Do not use the built-in task tool. Use internet_search directly, stop after the minimum evidence needed, and finish quickly."
            if self.settings.fast_mvp_mode
            else (
                "This is a narrow request; do not delegate to the built-in task tool. Use internet_search directly and finish quickly."
                if len(payload.destination_candidates) <= 2
                else "Use the built-in task tool only for genuinely independent research branches; otherwise use internet_search directly."
            )
        )

        agent = create_deep_agent(
            model=chat_model,
            tools=[tavily_search_tool],
            name="trip-architect-planner",
            system_prompt=(
                "You are Trip Architect's trip-options agent. Build polished, realistic travel options from the exact form input. "
                "Use Tavily to research the candidate destinations, seasonality, travel friction, neighborhoods, food/culture fit, "
                "and any timing or budget signals that materially affect the recommendation. Work freely with your tools, but finish "
                "with only the structured response requested by the schema. Make 3 to 5 distinct options unless the user's candidates "
                "make fewer options more honest. Every option must be feasible for the dates, traveler count, budget, origin, and pace. "
                "Use real source URLs when Tavily provides them, and keep estimates transparent rather than overconfident. "
                f"Keep the run compact: prefer 2-3 targeted searches, never exceed {max_searches} internet searches, avoid broad research loops, and complete the final JSON promptly. "
                f"{direct_search_guidance}"
            ),
            response_format=DeepTripOptionsPayload,
        )
        result = _run_deepagent_with_observability(
            agent,
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
                            f"Temporary fast MVP mode is active. Use at most {max_searches} internet searches total and do not call the task tool. "
                            f"{direct_search_guidance} "
                            f"Origin: {payload.origin}. Dates: {payload.start_date} to {payload.end_date}. "
                            f"Candidates: {', '.join(payload.destination_candidates)}. "
                            f"Trip style: {payload.trip_style}. Budget: {payload.budget_range or 'not specified'}. "
                            f"Travelers: {payload.traveler_count}. Pace: {payload.pace_preference or 'not specified'}."
                        ),
                    }
                ]
            },
            "trip_options",
            max_steps=max_steps,
        )
        structured = _structured_response_from_result(result, DeepTripOptionsPayload)
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

        tavily_search_tool = _build_tavily_tool(self.settings)
        chat_model = _build_chat_model(self.settings)
        max_searches = self.settings.fast_mvp_search_limit if self.settings.fast_mvp_mode else 6
        max_steps = 10 if self.settings.fast_mvp_mode else 24
        direct_search_guidance = (
            "Temporary fast MVP mode is active. Do not use the built-in task tool. Use internet_search directly, keep research narrow, and finish quickly."
            if self.settings.fast_mvp_mode
            else (
                "Do not delegate to the built-in task tool for this itinerary. Use internet_search directly and finish quickly."
                if len(selected_option.get("destination_order", [])) <= 2
                else "Use the built-in task tool only for independent multi-stop research branches; otherwise use internet_search directly."
            )
        )

        agent = create_deep_agent(
            model=chat_model,
            tools=[tavily_search_tool],
            name="trip-architect-itinerary",
            system_prompt=(
                "You are Trip Architect's itinerary agent. Turn the selected trip option and original form input into a useful, "
                "travelable day-by-day plan. Use Tavily to research current neighborhoods, restaurants or activity clusters, opening/logistics "
                "signals, transfer friction, and practical booking context. Work freely with your tools, then finish with only the structured "
                "response requested by the schema. Keep each day specific, realistic, and paced for humans. Preserve slack around arrivals, "
                "do not invent fake hotel names as sources, and cite real source URLs when Tavily provides them. "
                f"Keep the run compact: prefer 2-3 targeted searches, never exceed {max_searches} internet searches, avoid broad research loops, and complete the final JSON promptly. "
                f"{direct_search_guidance}"
            ),
            response_format=DeepItineraryPayload,
        )
        result = _run_deepagent_with_observability(
            agent,
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
                            f"Temporary fast MVP mode is active. Use at most {max_searches} internet searches total and do not call the task tool. "
                            f"{direct_search_guidance} "
                            f"Trip style: {payload.trip_style}. Route: {selected_option['destination_order']}. "
                            f"Day allocation: {selected_option['days_by_stop']}."
                        ),
                    }
                ]
            },
            "itinerary",
            max_steps=max_steps,
        )
        structured = _structured_response_from_result(result, DeepItineraryPayload)
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
