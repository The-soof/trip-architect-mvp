from __future__ import annotations

import re
from urllib.parse import quote_plus

# IATA city/airport codes for common Trip Architect destinations.
# These are the most-used codes for each city — major international airports.
# When a city is not in this table we fall back to the city name directly (Kayak
# also accepts plain city names in the path and will resolve them).
IATA_CODES: dict[str, str] = {
    # Europe — primary destinations
    "barcelona": "BCN",
    "mykonos": "JMK",
    "split": "SPU",
    "budapest": "BUD",
    "lisbon": "LIS",
    "porto": "OPO",
    "rome": "FCO",
    "amsterdam": "AMS",
    "paris": "CDG",
    "london": "LHR",
    "berlin": "BER",
    "madrid": "MAD",
    "athens": "ATH",
    "dubrovnik": "DBV",
    "florence": "FLR",
    "milan": "MXP",
    "prague": "PRG",
    "vienna": "VIE",
    "copenhagen": "CPH",
    "stockholm": "ARN",
    "oslo": "OSL",
    "istanbul": "IST",
    "tel aviv": "TLV",
    "zurich": "ZRH",
    "frankfurt": "FRA",
    "munich": "MUC",
    "brussels": "BRU",
    "edinburgh": "EDI",
    "santorini": "JTR",
    "rhodes": "RHO",
    "corfu": "CFU",
    "naples": "NAP",
    "palermo": "PMO",
    "seville": "SVQ",
    "málaga": "AGP",
    "malaga": "AGP",
    "valencia": "VLC",
    "nice": "NCE",
    "marseille": "MRS",
    "bordeaux": "BOD",
    "lyon": "LYS",
    "stockholm": "ARN",
    "reykjavik": "KEF",
    "dubrovnik": "DBV",
    "zagreb": "ZAG",
    "Ljubljana": "LJU",
    "ljubljana": "LJU",
    "sofia": "SOF",
    "bucharest": "OTP",
    "warsaw": "WAW",
    "krakow": "KRK",
    "riga": "RIX",
    "tallinn": "TLL",
    "vilnius": "VNO",
    "thessaloniki": "SKG",
    "heraklion": "HER",
    "crete": "HER",
    "cyprus": "LCA",
    "limassol": "LCA",
    # Asia Pacific
    "tokyo": "NRT",
    "osaka": "KIX",
    "bangkok": "BKK",
    "bali": "DPS",
    "singapore": "SIN",
    "hong kong": "HKG",
    "seoul": "ICN",
    "taipei": "TPE",
    "sydney": "SYD",
    "melbourne": "MEL",
    "auckland": "AKL",
    "dubai": "DXB",
    "abu dhabi": "AUH",
    "doha": "DOH",
    # Americas
    "new york": "JFK",
    "new york city": "JFK",
    "nyc": "JFK",
    "los angeles": "LAX",
    "san francisco": "SFO",
    "chicago": "ORD",
    "miami": "MIA",
    "boston": "BOS",
    "seattle": "SEA",
    "denver": "DEN",
    "atlanta": "ATL",
    "dallas": "DFW",
    "houston": "IAH",
    "washington": "DCA",
    "toronto": "YYZ",
    "montreal": "YUL",
    "vancouver": "YVR",
    "mexico city": "MEX",
    "cancun": "CUN",
    "bogota": "BOG",
    "lima": "LIM",
    "sao paulo": "GRU",
    "rio de janeiro": "GIG",
    "buenos aires": "EZE",
    "santiago": "SCL",
}


def resolve_iata_code(city: str) -> str | None:
    """Return a confident IATA airport code for a city, or None if unknown.

    Handles three input shapes that real planners (and Gemini) produce:
      * an explicit code in parentheses, e.g. "New York (JFK)" -> "JFK"
      * a known city name, e.g. "Madrid" -> "MAD"
      * a city with a trailing descriptor, e.g. "New York City" -> "JFK"
    Returns None when no airport can be matched, so callers can avoid querying a
    flight API with a bogus code.
    """
    raw = (city or "").strip()
    if not raw:
        return None
    # An explicit 3-letter airport code in parentheses always wins.
    match = re.search(r"\(([A-Za-z]{3})\)", raw)
    if match:
        return match.group(1).upper()
    key = re.sub(r"\s+", " ", raw.lower()).strip()
    if key in IATA_CODES:
        return IATA_CODES[key]
    # Retry after dropping a trailing descriptor like "city" (but only as a
    # fallback, so "Mexico City" -> MEX still matches exactly first).
    stripped = re.sub(r"\s+", " ", re.sub(r"\bcity\b", "", key)).strip()
    if stripped and stripped in IATA_CODES:
        return IATA_CODES[stripped]
    return None


def _city_to_iata(city: str) -> str:
    """Return the IATA code for a city, or the raw city name as fallback.

    Kayak accepts plain city names in the path (e.g. /flights/NYC-Barcelona/...)
    so the fallback is safe even without a known code.
    """
    return resolve_iata_code(city) or city.strip()


def build_kayak_flights_link(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str,
    adults: int = 1,
) -> str:
    """Build a Kayak deep-link flight search URL.

    Example output:
    https://www.kayak.com/flights/SFO-BCN/2025-08-10/2025-08-20/2adults
    """
    origin_code = _city_to_iata(origin)
    dest_code = _city_to_iata(destination)
    adults_segment = f"/{adults}adults" if adults > 1 else ""
    if not return_date:
        return f"https://www.kayak.com/flights/{origin_code}-{dest_code}/{depart_date}{adults_segment}"
    return (
        f"https://www.kayak.com/flights/{origin_code}-{dest_code}"
        f"/{depart_date}/{return_date}{adults_segment}"
    )


def build_google_flights_link(origin: str, first_stop: str, start_date: str, end_date: str) -> str:
    """Google Flights fallback — uses ?q= search query (no structured deep-link available without tfs encoding)."""
    query = f"flights from {origin} to {first_stop} {start_date} return {end_date}"
    return f"https://www.google.com/travel/flights?q={quote_plus(query)}"


def build_booking_link(city: str, start_date: str, end_date: str) -> str:
    return (
        "https://www.booking.com/searchresults.html?"
        f"ss={quote_plus(city)}&checkin={quote_plus(start_date)}&checkout={quote_plus(end_date)}"
    )
