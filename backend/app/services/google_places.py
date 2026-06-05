from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELD_MASK = ",".join(
    [
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.currentOpeningHours",
        "places.googleMapsUri",
        "places.businessStatus",
    ]
)


@dataclass
class PlaceLookupResult:
    query: str
    city: str
    category: str
    reason: str
    place: dict[str, Any] | None


def search_places(
    *,
    api_key: str,
    query: str,
    city: str,
    category: str,
    reason: str,
    max_results: int = 1,
    region_code: str = "US",
    language_code: str = "en",
    timeout: float = 12.0,
) -> PlaceLookupResult:
    payload = {
        "textQuery": f"{query} in {city}" if city.lower() not in query.lower() else query,
        "pageSize": max(1, min(max_results, 3)),
        "languageCode": language_code,
        "regionCode": region_code,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": PLACES_FIELD_MASK,
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(PLACES_TEXT_SEARCH_URL, json=payload, headers=headers)
        response.raise_for_status()
    body = response.json()
    places = body.get("places", [])
    normalized = [_normalize_place(place) for place in places]
    operational = [
        p for p in normalized
        if p.get("business_status") not in ("CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY")
    ]
    return PlaceLookupResult(
        query=query,
        city=city,
        category=category,
        reason=reason,
        place=operational[0] if operational else None,
    )


def _normalize_place(place: dict[str, Any]) -> dict[str, Any]:
    display_name = place.get("displayName", {})
    location = place.get("location", {})
    opening_hours = place.get("currentOpeningHours", {})
    weekday_descriptions = opening_hours.get("weekdayDescriptions", [])
    return {
        "name": display_name.get("text") or "Unknown place",
        "address": place.get("formattedAddress"),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "rating": place.get("rating"),
        "user_rating_count": place.get("userRatingCount"),
        "maps_url": place.get("googleMapsUri"),
        "business_status": place.get("businessStatus"),
        "opening_hours_summary": "; ".join(weekday_descriptions[:2]) if weekday_descriptions else None,
    }
