"""Deep-link builders for each transport mode.

These are intentionally best-effort search deep links (not booking holds). The
deep-link system is slated for a dedicated overhaul, so the contract here is
simple: given a leg, return a URL that drops the traveler onto a relevant search
on a reputable provider. Swap the bodies later without touching the builder.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import quote_plus

from app.core.config import Settings
from app.services.booking import _city_to_iata, build_kayak_flights_link


def flight_link(
    settings: Settings,
    origin: str,
    destination: str,
    depart: date,
    return_date: date | None,
    adults: int,
) -> str:
    """Affiliate Travelpayouts link when configured, else a Kayak search deep link."""
    if settings.travelpayouts_enabled:
        origin_code = _city_to_iata(origin).upper()[:3]
        dest_code = _city_to_iata(destination).upper()[:3]
        # Travelpayouts / Aviasales search path: ORIGINddmmDESTINATIONddmm + passengers.
        depart_segment = depart.strftime("%d%m")
        path = f"{origin_code}{depart_segment}{dest_code}"
        if return_date is not None:
            path += return_date.strftime("%d%m")
        path += str(max(1, adults))
        return (
            f"https://www.aviasales.com/search/{path}"
            f"?marker={quote_plus(settings.travelpayouts_marker or '')}"
        )
    return build_kayak_flights_link(
        origin,
        destination,
        depart.isoformat(),
        return_date.isoformat() if return_date else "",
        adults=adults,
    )


def ferry_link(origin: str, destination: str, depart: date) -> str:
    """Ferryhopper search deep link (covers Greek isles, Adriatic, Baltic, etc.)."""
    return (
        "https://www.ferryhopper.com/en/ferry-routes"
        f"/{quote_plus(origin.strip())}/{quote_plus(destination.strip())}"
        f"?date={depart.isoformat()}"
    )


def train_link(origin: str, destination: str, depart: date) -> str:
    """Omio rail/coach search deep link."""
    query = f"train from {origin} to {destination} {depart.isoformat()}"
    return f"https://www.omio.com/search-frontend/results?q={quote_plus(query)}"


def car_rental_link(city: str, pickup: date, dropoff: date | None = None) -> str:
    """Kayak car-rental search deep link for a city + date window."""
    code = _city_to_iata(city)
    drop = (dropoff or pickup).isoformat()
    return f"https://www.kayak.com/cars/{quote_plus(str(code))}/{pickup.isoformat()}/{drop}"


def transfer_link(origin: str, destination: str) -> str:
    """Google Maps directions link for a short ground transfer (airport → hotel, port → town)."""
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={quote_plus(origin.strip())}&destination={quote_plus(destination.strip())}"
        "&travelmode=driving"
    )
