"""Flight-data provider seam.

A `FlightProvider` returns a spread of `FlightCandidate`s for one air leg so the
journey builder can pick the best one per persona (fastest, cheapest, restful…).

Three implementations sit behind one interface:
  * `SerpApiFlightProvider`  — real Google Flights times/stops/price (needs key).
  * `GeneratorFlightProvider` — deterministic synthetic spread (no key, always on).

Deep links are layered separately (see links.py): Travelpayouts when configured,
Kayak otherwise. Swapping providers requires no change to the builder or the UI.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.core.config import Settings
from app.services.booking import _city_to_iata


@dataclass
class FlightCandidate:
    depart_time: str | None  # ISO-8601 local, e.g. "2026-08-10T11:00"
    arrive_time: str | None
    duration_minutes: int | None
    stops: int
    price: int | None
    carrier: str
    data_source: str  # "serpapi" | "generator"


def _is_long_haul(origin: str, destination: str) -> bool:
    """Rough heuristic: intercontinental/long legs vs short regional hops.

    Used only to make the generator's synthetic durations feel realistic; the
    real provider supplies true durations.
    """
    long_haul_hubs = {
        "SFO", "LAX", "JFK", "ORD", "BOS", "SEA", "MIA", "DFW", "IAH", "DEN",
        "ATL", "YYZ", "YVR", "SYD", "MEL", "AKL", "NRT", "KIX", "ICN", "HKG",
        "SIN", "BKK", "DPS", "DXB", "DOH", "GRU", "EZE", "SCL",
    }
    o = _city_to_iata(origin).upper()[:3]
    d = _city_to_iata(destination).upper()[:3]
    return o in long_haul_hubs or d in long_haul_hubs


class GeneratorFlightProvider:
    """Deterministic synthetic flight spread — the always-available fallback.

    Produces a realistic time-of-day / price / stops spread so personas have
    something meaningful to optimize against, even with zero API keys.
    """

    data_source = "generator"

    def search(
        self, origin: str, destination: str, depart: date, adults: int, base_price: int
    ) -> list[FlightCandidate]:
        long_haul = _is_long_haul(origin, destination)
        nonstop = 600 if long_haul else 95          # minutes
        carrier = "Multiple carriers"
        # (depart_hour, stops, price_multiplier) — a deliberate spread so personas
        # land on genuinely different flights: a cheap overnight, an early connection,
        # then morning / midday / evening nonstops.
        spread = [
            (22, 2 if long_haul else 1, 0.80),   # overnight budget
            (7, 1, 0.92),                         # early connection
            (10, 0, 1.05),                        # morning nonstop  → fastest
            (13, 0, 1.10),                        # midday nonstop   → balanced
            (18, 0, 1.20),                        # evening nonstop  → rest
        ]
        candidates: list[FlightCandidate] = []
        for hour, stops, mult in spread:
            duration = int(nonstop * (1.0 + 0.4 * stops))
            dep = datetime(depart.year, depart.month, depart.day, hour, 0)
            arr = dep + timedelta(minutes=duration)
            candidates.append(
                FlightCandidate(
                    depart_time=dep.strftime("%Y-%m-%dT%H:%M"),
                    arrive_time=arr.strftime("%Y-%m-%dT%H:%M"),
                    duration_minutes=duration,
                    stops=stops,
                    price=max(60, int(base_price * mult)),
                    carrier=carrier,
                    data_source=self.data_source,
                )
            )
        return candidates


class SerpApiFlightProvider:
    """Real flight spread via SerpApi's Google Flights engine.

    Cached per (origin, dest, date, adults) and hard-capped per process run so the
    free tier (100 searches/mo) is never exceeded. Any failure (no key, over cap,
    network/parse error) raises, and the builder falls back to the generator.
    """

    data_source = "serpapi"
    _cache: dict[str, list[FlightCandidate]] = {}
    _call_count = 0
    _lock = threading.Lock()

    def __init__(self, settings: Settings):
        self.settings = settings

    @classmethod
    def _cache_key(cls, origin: str, destination: str, depart: date, adults: int) -> str:
        return f"{_city_to_iata(origin)}|{_city_to_iata(destination)}|{depart.isoformat()}|{adults}"

    def search(
        self, origin: str, destination: str, depart: date, adults: int, base_price: int
    ) -> list[FlightCandidate]:
        if not self.settings.serpapi_api_key:
            raise RuntimeError("SerpApi key not configured")

        key = self._cache_key(origin, destination, depart, adults)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            if SerpApiFlightProvider._call_count >= self.settings.serpapi_monthly_cap:
                raise RuntimeError("SerpApi monthly cap reached; using generator fallback")
            SerpApiFlightProvider._call_count += 1

        candidates = self._fetch(origin, destination, depart, adults)
        if not candidates:
            raise RuntimeError("SerpApi returned no flights")
        with self._lock:
            self._cache[key] = candidates
        return candidates

    def _fetch(self, origin: str, destination: str, depart: date, adults: int) -> list[FlightCandidate]:
        import httpx  # lazy: only needed when a key is configured

        params = {
            "engine": "google_flights",
            "departure_id": _city_to_iata(origin).upper()[:3],
            "arrival_id": _city_to_iata(destination).upper()[:3],
            "outbound_date": depart.isoformat(),
            "type": "2",  # one-way; the builder composes legs itself
            "adults": str(max(1, adults)),
            "currency": "USD",
            "api_key": self.settings.serpapi_api_key,
        }
        response = httpx.get("https://serpapi.com/search.json", params=params, timeout=20.0)
        response.raise_for_status()
        body = response.json()
        raw = (body.get("best_flights") or []) + (body.get("other_flights") or [])
        candidates: list[FlightCandidate] = []
        for entry in raw[:8]:
            legs = entry.get("flights") or []
            if not legs:
                continue
            depart_time = legs[0].get("departure_airport", {}).get("time")
            arrive_time = legs[-1].get("arrival_airport", {}).get("time")
            carrier = legs[0].get("airline") or "Multiple carriers"
            candidates.append(
                FlightCandidate(
                    depart_time=_to_iso(depart_time),
                    arrive_time=_to_iso(arrive_time),
                    duration_minutes=entry.get("total_duration"),
                    stops=max(0, len(legs) - 1),
                    price=entry.get("price"),
                    carrier=carrier,
                    data_source=self.data_source,
                )
            )
        return candidates


def _to_iso(value: str | None) -> str | None:
    """SerpApi returns 'YYYY-MM-DD HH:MM' — normalize to ISO 'YYYY-MM-DDTHH:MM'."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M").strftime("%Y-%m-%dT%H:%M")
    except (ValueError, TypeError):
        return value


def get_flight_candidates(
    settings: Settings, origin: str, destination: str, depart: date, adults: int, base_price: int
) -> tuple[list[FlightCandidate], str]:
    """Return (candidates, data_source), trying SerpApi first then the generator.

    Never raises — the generator is guaranteed to return a usable spread.
    """
    if settings.serpapi_enabled:
        try:
            candidates = SerpApiFlightProvider(settings).search(origin, destination, depart, adults, base_price)
            if candidates:
                return candidates, "serpapi"
        except Exception as exc:  # noqa: BLE001 — provider failure must degrade gracefully
            print(
                "trip_architect.travel "
                + json.dumps({"message": "serpapi_fallback", "detail": str(exc)[:200]}),
                flush=True,
            )
    return GeneratorFlightProvider().search(origin, destination, depart, adults, base_price), "generator"
