"""Assemble persona-tailored, multi-modal travel journeys for a selected route.

The builder is mode-agnostic: a journey is an ordered list of segments, and each
segment names its own transport mode + deep link. Flights come from the provider
seam (SerpApi → generator); ground/sea legs are inferred from geography and
deep-link out to the relevant search. Personas differ mainly by which flight in
the spread they pick (latest vs cheapest vs fewest-stops) and, for "scenic", by
favoring routes that already include a ferry or train.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.schemas.trip import TripCreateRequest
from app.services.booking import IATA_CODES
from app.services.travel.links import (
    car_rental_link,
    ferry_link,
    flight_link,
    train_link,
    transfer_link,
)
from app.services.travel.providers import FlightCandidate, get_flight_candidates

# True islands — these genuinely require a ferry or a flight to reach.
ISLAND_PLACES = {
    "mykonos", "santorini", "ios", "naxos", "paros", "milos", "crete", "heraklion",
    "rhodes", "corfu", "kos", "zakynthos", "kefalonia", "hydra", "capri", "ibiza",
    "mallorca", "menorca", "sicily", "palermo", "hvar",
}
# Coastal ports that an island can reach by ferry (islands + mainland ferry hubs).
FERRY_PLACES = ISLAND_PLACES | {
    "split", "dubrovnik", "zadar", "kotor", "venice", "naples", "bari",
    "athens", "piraeus", "barcelona", "valencia",
}
# Fallback gateway airports for islands with no commercial airport of their own.
# Used only when no airport-served stop already on the route can serve as the gateway.
GATEWAY_AIRPORTS = {
    "ios": "Athens",
    "hydra": "Athens",
    "milos": "Athens",
    "hvar": "Split",
    "capri": "Naples",
}


def _has_airport(city: str) -> bool:
    """True when the city has a known commercial airport (an IATA code we map)."""
    return city.lower().strip() in IATA_CODES


def _needs_gateway(city: str) -> bool:
    """An airport-less island can only be entered/exited via a ferry to a gateway airport."""
    cl = city.lower().strip()
    return cl in ISLAND_PLACES and not _has_airport(city)


def _gateway_for(island: str, route_cities: list[str]) -> str | None:
    """Pick a ferry-connected airport city to reach/leave an airport-less island.

    Prefers an airport-served stop already on the trip (so the traveler ferries to a
    place they're visiting anyway); otherwise falls back to a known regional gateway.
    """
    il = island.lower().strip()
    for city in route_cities:
        cl = city.lower().strip()
        if cl != il and _has_airport(city) and cl in FERRY_PLACES and il in FERRY_PLACES:
            return city
    return GATEWAY_AIRPORTS.get(il)
# City → country for same-country rail inference.
CITY_COUNTRY = {
    "barcelona": "ES", "madrid": "ES", "seville": "ES", "valencia": "ES", "malaga": "ES",
    "bilbao": "ES", "granada": "ES", "san sebastian": "ES",
    "rome": "IT", "florence": "IT", "milan": "IT", "venice": "IT", "naples": "IT",
    "bologna": "IT", "turin": "IT",
    "paris": "FR", "lyon": "FR", "nice": "FR", "marseille": "FR", "bordeaux": "FR",
    "lisbon": "PT", "porto": "PT", "faro": "PT",
    "berlin": "DE", "munich": "DE", "frankfurt": "DE", "hamburg": "DE", "cologne": "DE",
    "amsterdam": "NL", "rotterdam": "NL",
    "tokyo": "JP", "osaka": "JP", "kyoto": "JP", "hiroshima": "JP",
    "london": "GB", "edinburgh": "GB", "manchester": "GB",
    "athens": "GR", "thessaloniki": "GR",
}

# Estimated price / duration (minutes) for non-flight legs (generator-side).
GROUND_DEFAULTS = {
    "ferry": {"price": 48, "duration": 150, "provider": "Ferry operators"},
    "train": {"price": 62, "duration": 195, "provider": "Rail / coach"},
    "car": {"price": 58, "duration": 120, "provider": "Car rental"},
    "transfer": {"price": 35, "duration": 35, "provider": "Taxi / rideshare"},
}

PERSONAS = {
    "balanced": {
        "title": "The Balanced Route",
        "summary": "A sensible middle ground — reasonable timing, at most one stop, fair price.",
        "base_fit": 8.0,
        "tags": ["Well-rounded"],
    },
    "fastest": {
        "title": "The Speed Run",
        "summary": "Shortest door-to-door time. Prioritizes nonstops and the fewest connections.",
        "base_fit": 7.9,
        "tags": ["Fewest stops", "Shortest total time"],
    },
    "rest": {
        "title": "Easy Does It",
        "summary": "Built around rest — civilised departure times, no red-eyes, nonstop where possible.",
        "base_fit": 7.8,
        "tags": ["No red-eyes", "Relaxed timing"],
    },
    "budget": {
        "title": "The Smart Saver",
        "summary": "The lowest total fare on this route, even if it means an earlier start or a connection.",
        "base_fit": 7.6,
        "tags": ["Lowest fares"],
    },
}
PERSONA_ORDER = ["balanced", "fastest", "rest", "budget"]


def _inter_stop_mode(a: str, b: str) -> str:
    a_l, b_l = a.lower().strip(), b.lower().strip()
    # An island endpoint can only be reached by ferry (if the other side is a port) or by air.
    if a_l in ISLAND_PLACES or b_l in ISLAND_PLACES:
        return "ferry" if (a_l in FERRY_PLACES and b_l in FERRY_PLACES) else "flight"
    # Mainland-to-mainland: prefer rail within the same country, else fly.
    ca, cb = CITY_COUNTRY.get(a_l), CITY_COUNTRY.get(b_l)
    if ca and cb and ca == cb:
        return "train"
    return "flight"


def _hour_of(depart_time: str | None) -> int:
    if not depart_time:
        return 12
    try:
        return datetime.fromisoformat(depart_time).hour
    except (ValueError, TypeError):
        return 12


def _pick_candidate(candidates: list[FlightCandidate], persona: str) -> FlightCandidate:
    if not candidates:
        raise ValueError("no candidates to pick from")

    def price(c: FlightCandidate) -> int:
        return c.price if c.price is not None else 10_000

    def duration(c: FlightCandidate) -> int:
        return c.duration_minutes if c.duration_minutes is not None else 10_000

    if persona == "fastest":
        # Fewest stops, shortest air time, arrive soonest (earliest departure).
        return min(candidates, key=lambda c: (c.stops, duration(c), _hour_of(c.depart_time)))
    if persona == "budget":
        return min(candidates, key=lambda c: (price(c), c.stops, duration(c)))
    if persona == "rest":
        # Latest civilised nonstop — no red-eyes, no early alarms.
        def rest_score(c: FlightCandidate) -> float:
            hour = _hour_of(c.depart_time)
            red_eye = 500 if (hour < 7 or hour >= 21) else 0
            return red_eye + c.stops * 120 - hour  # prefer later within the allowed window
        return min(candidates, key=rest_score)
    # balanced — the nonstop closest to midday at a fair price.
    return min(candidates, key=lambda c: (c.stops, abs(_hour_of(c.depart_time) - 13), price(c)))


class _Leg:
    __slots__ = ("mode", "frm", "to", "day", "kind", "base_price", "provider", "note")

    def __init__(
        self,
        mode: str,
        frm: str,
        to: str,
        day: date,
        kind: str,
        base_price: int,
        provider: str | None = None,
        note: str | None = None,
    ):
        self.mode = mode
        self.frm = frm
        self.to = to
        self.day = day
        self.kind = kind
        self.base_price = base_price
        # Optional overrides supplied by the Gemini route planner (Approach B).
        self.provider = provider
        self.note = note


def _stop_dates(payload: TripCreateRequest, stops: list[dict[str, Any]]) -> tuple[list[date], list[date]]:
    """Return (arrival_date_per_stop, departure_date_per_stop)."""
    arrivals: list[date] = []
    departures: list[date] = []
    cumulative = 0
    for stop in stops:
        arrivals.append(payload.start_date + timedelta(days=cumulative))
        cumulative += max(1, int(stop.get("nights", 1)))
        leave = payload.start_date + timedelta(days=cumulative)
        departures.append(min(leave, payload.end_date))
    return arrivals, departures


def _build_legs(payload: TripCreateRequest, selected_option: dict[str, Any]) -> list[_Leg]:
    stops = selected_option.get("days_by_stop") or []
    cities = [str(stop["city"]).strip() for stop in stops if stop.get("city")]
    if not cities:
        cities = [str(c).strip() for c in selected_option.get("destination_order", []) if str(c).strip()]
        stops = [{"city": c, "nights": 2} for c in cities]
    if not cities:
        return []

    _, departures = _stop_dates(payload, stops)

    return_city = (selected_option.get("return_city") or "").strip()
    one_way = return_city.lower() == "none"
    if return_city and not one_way and return_city.lower() != payload.origin.strip().lower():
        return_target = return_city
    else:
        return_target = payload.origin.strip()

    total_min = int(selected_option.get("estimated_total_min", 2400))
    # Number of air legs drives the per-leg flight budget.
    inter_modes = [_inter_stop_mode(cities[i], cities[i + 1]) for i in range(len(cities) - 1)]
    n_air = 1 + sum(1 for m in inter_modes if m == "flight") + (0 if one_way else 1)
    base_air = max(150, int(total_min * 0.24 / max(1, n_air)))

    origin = payload.origin.strip()
    ferry_price = GROUND_DEFAULTS["ferry"]["price"]
    legs: list[_Leg] = []

    # Outbound: if the first stop is an airport-less island, fly to a gateway airport
    # and ferry across; otherwise fly straight in.
    first = cities[0]
    outbound_gateway = _gateway_for(first, cities) if _needs_gateway(first) else None
    if outbound_gateway:
        legs.append(_Leg("flight", origin, outbound_gateway, payload.start_date, "outbound_gateway", base_air))
        legs.append(_Leg("ferry", outbound_gateway, first, payload.start_date, "outbound_transfer", ferry_price))
    else:
        legs.append(_Leg("flight", origin, first, payload.start_date, "outbound", base_air))

    for i, mode in enumerate(inter_modes):
        leg_price = int(base_air * 0.6) if mode == "flight" else GROUND_DEFAULTS[mode]["price"]
        legs.append(_Leg(mode, cities[i], cities[i + 1], departures[i], "inter", leg_price))

    # Return: if the last stop is an airport-less island, ferry to a gateway airport
    # first, then fly home; otherwise fly straight out.
    if not one_way:
        last = cities[-1]
        return_gateway = _gateway_for(last, cities) if _needs_gateway(last) else None
        if return_gateway:
            legs.append(_Leg("ferry", last, return_gateway, payload.end_date, "return_transfer", ferry_price))
            legs.append(_Leg("flight", return_gateway, return_target, payload.end_date, "return", base_air))
        else:
            legs.append(_Leg("flight", last, return_target, payload.end_date, "return", base_air))
    return legs


# --------------------------------------------------------------------------- #
# Approach B: Gemini-generated route topology.
#
# Gemini decides the door-to-door leg structure (modes, gateways, transfers)
# using its global geographic knowledge — no hand-maintained island/airport
# tables. Flight legs still flow through the provider seam for real SerpApi
# times/prices, and personas still pick from the candidate spread. Any failure
# (no key, bad JSON, no flights) falls back to the deterministic _build_legs.
# --------------------------------------------------------------------------- #

_MODE_ALIASES = {
    "flight": "flight", "fly": "flight", "plane": "flight", "air": "flight", "airplane": "flight",
    "ferry": "ferry", "boat": "ferry", "sea": "ferry", "catamaran": "ferry", "hydrofoil": "ferry",
    "train": "train", "rail": "train", "highspeed": "train", "high-speed": "train",
    "car": "car", "drive": "car", "rental": "car", "self-drive": "car", "road": "car",
    "transfer": "transfer", "taxi": "transfer", "shuttle": "transfer", "bus": "transfer",
    "coach": "transfer", "metro": "transfer", "rideshare": "transfer", "private": "transfer",
}


class GeminiTravelLegPayload(BaseModel):
    mode: str = Field(description="One of: flight, ferry, train, car, transfer.")
    from_place: str = Field(description="Departure place name (city; for flights you may append an airport code in parentheses).")
    to_place: str = Field(description="Arrival place name, same convention as from_place.")
    note: str = Field(default="", description="Optional short rider, under 12 words (e.g. 'Gateway ferry to the nearest airport').")
    provider_hint: str = Field(default="", description="Optional typical operator/carrier (e.g. 'SeaJets ferry', 'Trenitalia', 'Multiple airlines').")


class GeminiJourneyPlanPayload(BaseModel):
    legs: list[GeminiTravelLegPayload] = Field(default_factory=list)


def _normalize_mode(raw: str) -> str:
    key = re.sub(r"[^a-z-]", "", (raw or "").lower())
    return _MODE_ALIASES.get(key, "flight" if "flight" in key else "transfer")


def _clean_place(place: str) -> str:
    """Strip parenthetical airport codes etc. so IATA lookup uses the plain city name."""
    return re.sub(r"\s*\(.*?\)\s*", " ", place or "").strip() or place.strip()


def _gemini_journey_prompt(
    payload: TripCreateRequest,
    cities: list[str],
    stops: list[dict[str, Any]],
    return_target: str,
    one_way: bool,
) -> str:
    stop_lines = ", ".join(
        f"{c} ({int(s.get('nights', 1))} nights)" for c, s in zip(cities, stops, strict=False)
    )
    ending = "a one-way trip ending at the final stop (no journey home)" if one_way else f"returning to {return_target}"
    return (
        "You are Trip Architect's travel-logistics planner. Return ONLY valid JSON. "
        "Produce the realistic, ordered, door-to-door sequence of travel legs for this trip, "
        "from the origin through every stop IN THE GIVEN ORDER, then "
        f"{ending}. Do not skip, add, or reorder stops.\n"
        "Rules:\n"
        "- Pick the right mode for each hop: 'flight' for long or no-rail intercity hops; 'ferry' between islands or coastal ports; "
        "'train' for shorter same-country mainland hops; 'car' for short scenic drives.\n"
        "- CRITICAL: never put a flight departing from or arriving at a place with no commercial airport (e.g. small Greek isles like Ios, Hydra). "
        "Instead, route via the nearest gateway: ferry/train/drive to a city that HAS an airport, then fly.\n"
        "- Include short local 'transfer' legs where natural (airport/port to accommodation).\n"
        "- Use real place names. For flight legs you may append the airport code in parentheses.\n"
        f"Origin: {payload.origin}. Stops in order: {stop_lines}. "
        f"Dates: {payload.start_date} to {payload.end_date}. Travelers: {payload.traveler_count}."
    )


def _build_legs_with_gemini(
    settings: Settings, payload: TripCreateRequest, selected_option: dict[str, Any]
) -> list[_Leg]:
    stops = selected_option.get("days_by_stop") or []
    cities = [str(stop["city"]).strip() for stop in stops if stop.get("city")]
    if not cities:
        cities = [str(c).strip() for c in selected_option.get("destination_order", []) if str(c).strip()]
        stops = [{"city": c, "nights": 2} for c in cities]
    if not cities:
        raise ValueError("no cities to plan")

    _, departures = _stop_dates(payload, stops)
    return_city = (selected_option.get("return_city") or "").strip()
    one_way = return_city.lower() == "none"
    if return_city and not one_way and return_city.lower() != payload.origin.strip().lower():
        return_target = return_city
    else:
        return_target = payload.origin.strip()

    # Lazy import avoids a circular dependency (agent_planner imports this module).
    from app.services.agent_planner import _generate_structured_with_gemini

    prompt = _gemini_journey_prompt(payload, cities, stops, return_target, one_way)
    plan = _generate_structured_with_gemini(
        settings, prompt, GeminiJourneyPlanPayload, temperature=0.2, thinking_budget=1024
    )
    raw_legs = [leg for leg in plan.legs if leg.from_place.strip() and leg.to_place.strip()]
    if not any(_normalize_mode(leg.mode) == "flight" for leg in raw_legs):
        raise ValueError("Gemini plan contained no flights")

    total_min = int(selected_option.get("estimated_total_min", 2400))
    n_air = sum(1 for leg in raw_legs if _normalize_mode(leg.mode) == "flight")
    base_air = max(150, int(total_min * 0.24 / max(1, n_air)))

    cities_lower = [c.lower() for c in cities]

    def stop_index(place: str) -> int | None:
        pl = _clean_place(place).lower()
        for i, c in enumerate(cities_lower):
            if c and (c in pl or pl in c):
                return i
        return None

    legs: list[_Leg] = []
    reached = -1  # highest stop index reached; -1 = still at origin
    for gleg in raw_legs:
        mode = _normalize_mode(gleg.mode)
        frm, to = _clean_place(gleg.from_place), _clean_place(gleg.to_place)
        # Phase-based date: outbound legs depart on day 1, return legs on the last day,
        # inter-stop legs on the day you leave the originating stop. Only flights/ferries
        # actually consume the date, and those land in the correct phase.
        if reached < 0:
            day, kind = payload.start_date, "outbound"
        elif reached >= len(cities) - 1:
            day, kind = payload.end_date, "return"
        else:
            day, kind = departures[min(reached, len(departures) - 1)], "inter"

        price = base_air if mode == "flight" else GROUND_DEFAULTS.get(mode, GROUND_DEFAULTS["transfer"])["price"]
        legs.append(_Leg(mode, frm, to, day, kind, price, provider=gleg.provider_hint or None, note=gleg.note or None))

        to_idx = stop_index(gleg.to_place)
        if to_idx is not None and to_idx > reached:
            reached = to_idx
    return legs


def _segment(order: int, mode: str, frm: str, to: str, **kw: Any) -> dict[str, Any]:
    return {
        "order_index": order,
        "mode": mode,
        "from_label": frm[:120],
        "to_label": to[:120],
        "depart_time": kw.get("depart_time"),
        "arrive_time": kw.get("arrive_time"),
        "provider": (kw.get("provider") or "")[:120],
        "price_estimate": kw.get("price_estimate"),
        "deep_link": kw.get("deep_link") or "",
        "note": kw.get("note") or "",
        "data_source": kw.get("data_source") or "generator",
    }


def _assemble_segments(
    settings: Settings,
    payload: TripCreateRequest,
    legs: list[_Leg],
    candidates_by_leg: dict[int, list[FlightCandidate]],
    persona: str,
    *,
    auto_transfers: bool = True,
) -> list[dict[str, Any]]:
    """Render a leg plan into persona-specific segments.

    `auto_transfers=True` (deterministic builder) inserts arrival transfers itself.
    `auto_transfers=False` (Gemini builder) renders exactly the legs Gemini produced,
    since it already includes its own transfer legs.
    """
    segments: list[dict[str, Any]] = []
    order = 0
    for leg_index, leg in enumerate(legs):
        if leg.mode == "flight":
            cand = _pick_candidate(candidates_by_leg[leg_index], persona)
            # Journeys are composed of one-way legs, so each flight link is one-way.
            deep = flight_link(
                settings, leg.frm, leg.to, leg.day, None, payload.traveler_count
            )
            note = "Nonstop" if cand.stops == 0 else f"{cand.stops} stop{'s' if cand.stops > 1 else ''}"
            segments.append(
                _segment(
                    order, "flight", leg.frm, leg.to,
                    depart_time=cand.depart_time, arrive_time=cand.arrive_time,
                    provider=cand.carrier, price_estimate=cand.price,
                    deep_link=deep, note=note, data_source=cand.data_source,
                )
            )
            order += 1
            # Arrival transfer into a base city (not after the flight home).
            if auto_transfers and leg.kind in ("outbound", "inter"):
                segments.append(_arrival_transfer(order, leg.to))
                order += 1
        else:
            defaults = GROUND_DEFAULTS.get(leg.mode, GROUND_DEFAULTS["transfer"])
            deep = _ground_link(leg)
            if leg.note:
                note = leg.note
            elif leg.kind == "outbound_transfer":
                note = f"Ferry from {leg.frm} (gateway airport) to {leg.to}"
            elif leg.kind == "return_transfer":
                note = f"Ferry to {leg.to} to connect with the flight home"
            else:
                note = {
                    "ferry": "Island/coastal ferry crossing",
                    "train": "Direct regional rail",
                    "car": "Self-drive leg",
                    "transfer": "Local transfer",
                }.get(leg.mode, "")
            segments.append(
                _segment(
                    order, leg.mode, leg.frm, leg.to,
                    provider=leg.provider or defaults["provider"], price_estimate=leg.base_price,
                    deep_link=deep, note=note, data_source="generator",
                )
            )
            order += 1
            # Add a port→accommodation transfer only when arriving somewhere to stay.
            # A return-gateway ferry heads to the airport, so it gets no transfer.
            if auto_transfers and leg.mode in ("ferry", "train") and leg.kind != "return_transfer":
                segments.append(_arrival_transfer(order, leg.to))
                order += 1
    return segments


def _arrival_transfer(order: int, city: str) -> dict[str, Any]:
    defaults = GROUND_DEFAULTS["transfer"]
    return _segment(
        order, "transfer", f"{city} arrival point", f"{city} accommodation",
        provider=defaults["provider"], price_estimate=defaults["price"],
        deep_link=transfer_link(f"{city} airport", f"{city} city center"),
        note="Arrival → accommodation", data_source="generator",
    )


def _ground_link(leg: _Leg) -> str:
    if leg.mode == "ferry":
        return ferry_link(leg.frm, leg.to, leg.day)
    if leg.mode == "train":
        return train_link(leg.frm, leg.to, leg.day)
    if leg.mode == "car":
        return car_rental_link(leg.frm, leg.day)
    return transfer_link(leg.frm, leg.to)


def _signature(segments: list[dict[str, Any]]) -> tuple:
    return tuple((s["mode"], s["from_label"], s["to_label"], s["depart_time"], s["price_estimate"]) for s in segments)


def _recommended_key(payload: TripCreateRequest, emitted: list[str]) -> str:
    hints = " ".join(
        filter(None, [payload.pace_preference, payload.budget_range, payload.trip_style])
    ).lower()
    if any(word in hints for word in ("budget", "cheap", "affordable", "save", "shoestring")):
        choice = "budget"
    elif any(word in hints for word in ("relax", "slow", "rest", "recover", "unwind", "leisure", "calm")):
        choice = "rest"
    elif any(word in hints for word in ("fast", "packed", "efficient", "quick", "maximize", "see it all")):
        choice = "fastest"
    else:
        choice = "balanced"
    return choice if choice in emitted else emitted[0]


def build_travel_journeys(
    settings: Settings,
    payload: TripCreateRequest,
    selected_option: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return a list of persona journey dicts ready to persist as TravelJourney rows."""
    # Approach B: let Gemini plan the route topology when the live agent is on; fall back
    # to the deterministic geography builder (Approach A) when it's off or anything fails.
    legs: list[_Leg] = []
    auto_transfers = True
    if settings.enable_real_agent and settings.gemini_api_key:
        try:
            legs = _build_legs_with_gemini(settings, payload, selected_option)
            auto_transfers = False
        except Exception as exc:  # noqa: BLE001 — degrade gracefully to the deterministic builder
            print(
                "trip_architect.travel "
                + json.dumps({"message": "gemini_route_fallback", "detail": str(exc)[:200]}),
                flush=True,
            )
            legs = []
    if not legs:
        legs = _build_legs(payload, selected_option)
        auto_transfers = True
    if not legs:
        return []

    # Fetch the flight spread once per air leg; personas pick from the same pool.
    candidates_by_leg: dict[int, list[FlightCandidate]] = {}
    for index, leg in enumerate(legs):
        if leg.mode == "flight":
            candidates, _source = get_flight_candidates(
                settings, leg.frm, leg.to, leg.day, payload.traveler_count, leg.base_price
            )
            candidates_by_leg[index] = candidates

    journeys: list[dict[str, Any]] = []
    seen_signatures: dict[tuple, dict[str, Any]] = {}
    for persona in PERSONA_ORDER:
        segments = _assemble_segments(
            settings, payload, legs, candidates_by_leg, persona, auto_transfers=auto_transfers
        )
        signature = _signature(segments)
        meta = PERSONAS[persona]
        if signature in seen_signatures:
            # Identical plan to an earlier persona — merge this persona's tags instead of duplicating.
            kept = seen_signatures[signature]
            for tag in meta["tags"]:
                if tag not in kept["tags"]:
                    kept["tags"].append(tag)
            continue

        total_price = sum(s["price_estimate"] or 0 for s in segments)
        total_duration = sum(_segment_duration(s) for s in segments) or None
        journey = {
            "persona_key": persona,
            "title": meta["title"],
            "summary": meta["summary"],
            "is_recommended": False,
            "total_price_min": int(total_price * 0.92),
            "total_price_max": int(total_price * 1.12),
            "total_duration_minutes": total_duration,
            "fit_score": meta["base_fit"],
            "tags": list(meta["tags"]),
            "sort_order": 0,
            "segments": segments,
        }
        journeys.append(journey)
        seen_signatures[signature] = journey

    if not journeys:
        return []

    emitted = [j["persona_key"] for j in journeys]
    rec_key = _recommended_key(payload, emitted)
    for journey in journeys:
        if journey["persona_key"] == rec_key:
            journey["is_recommended"] = True
            journey["fit_score"] = round(min(10.0, journey["fit_score"] + 0.8), 1)
            if "Recommended for you" not in journey["tags"]:
                journey["tags"].insert(0, "Recommended for you")

    journeys.sort(key=lambda j: (not j["is_recommended"], -j["fit_score"]))
    for order, journey in enumerate(journeys):
        journey["sort_order"] = order
    return journeys


def _segment_duration(segment: dict[str, Any]) -> int:
    if segment["depart_time"] and segment["arrive_time"]:
        try:
            delta = datetime.fromisoformat(segment["arrive_time"]) - datetime.fromisoformat(segment["depart_time"])
            return max(0, int(delta.total_seconds() // 60))
        except (ValueError, TypeError):
            pass
    return GROUND_DEFAULTS.get(segment["mode"], {}).get("duration", 0)
