from __future__ import annotations

from urllib.parse import quote_plus


def build_google_flights_link(origin: str, first_stop: str, start_date: str, end_date: str) -> str:
    query = f"flights from {origin} to {first_stop} {start_date} return {end_date}"
    return f"https://www.google.com/travel/flights?q={quote_plus(query)}"


def build_booking_link(city: str, start_date: str, end_date: str) -> str:
    return (
        "https://www.booking.com/searchresults.html?"
        f"ss={quote_plus(city)}&checkin={quote_plus(start_date)}&checkout={quote_plus(end_date)}"
    )

