from __future__ import annotations

from datetime import date
from typing import Any

from app.core.config import Settings
from app.schemas.trip import TripCreateRequest
from app.services import agent_planner
from app.services.agent_planner import PlanningArtifacts, TripPlanner

ALLOWED_EVIDENCE_TYPES = {"researched_fact", "inferred_recommendation", "estimated_price"}


def make_trip_request(
    *,
    origin: str = "New York",
    destinations: list[str] | None = None,
    trip_style: str = "Fun summer trip with good food, nightlife, water, and some relaxation.",
    budget_range: str | None = "Mid-range",
    pace_preference: str | None = "Balanced",
) -> TripCreateRequest:
    return TripCreateRequest(
        origin=origin,
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 20),
        destination_candidates=destinations or ["Mykonos", "Barcelona", "Split", "Budapest"],
        trip_style=trip_style,
        budget_range=budget_range,
        traveler_count=2,
        pace_preference=pace_preference,
    )


def assert_score(name: str, score: int, possible: int, minimum_ratio: float = 0.9) -> None:
    required = int(possible * minimum_ratio)
    assert score >= required, f"{name} scored {score}/{possible}, below required {required}/{possible}"


def option_quality_score(payload: TripCreateRequest, artifacts: PlanningArtifacts) -> tuple[int, int]:
    possible = 0
    score = 0
    allowed_destinations = set(payload.destination_candidates)
    trip_days = (payload.end_date - payload.start_date).days

    checks: list[bool] = [
        artifacts.mode in {"mock", "gemini"},
        bool(artifacts.planning_summary),
        1 <= len(artifacts.options) <= 6,
        bool(artifacts.steps),
        bool(artifacts.sources),
    ]

    for option in artifacts.options:
        stops = option["destination_order"]
        days_by_stop = option["days_by_stop"]
        checks.extend(
            [
                bool(option["name"]),
                bool(option["summary"]),
                bool(option["rationale"]),
                bool(option["tradeoffs"]),
                set(stops).issubset(allowed_destinations),
                [stop["city"] for stop in days_by_stop] == stops,
                sum(int(stop["nights"]) for stop in days_by_stop) == trip_days,
                days_by_stop[0]["start_day"] == 1,
                days_by_stop[-1]["end_day"] == trip_days,
                option["estimated_total_min"] > 0,
                option["estimated_total_max"] >= option["estimated_total_min"],
                option["budget_confidence"],
                0 <= option["fit_score"] <= 10,
            ]
        )

    for source in artifacts.sources:
        checks.extend(
            [
                bool(source["title"]),
                bool(source["url"]),
                source["evidence_type"] in ALLOWED_EVIDENCE_TYPES,
            ]
        )

    possible += len(checks)
    score += sum(1 for check in checks if check)
    return score, possible


def itinerary_quality_score(payload: TripCreateRequest, planning: PlanningArtifacts) -> tuple[int, int]:
    selected_option = planning.options[0]
    itinerary = TripPlanner(Settings(app_env="test", enable_real_agent=False)).generate_itinerary(
        payload,
        selected_option,
    )
    trip_days = (payload.end_date - payload.start_date).days
    checks: list[bool] = [
        itinerary.mode == "mock",
        bool(itinerary.summary),
        bool(itinerary.itinerary["title"]),
        bool(itinerary.itinerary["overview"]),
        bool(itinerary.itinerary["logistics"]),
        len(itinerary.itinerary["days"]) == trip_days,
        len(itinerary.hotels) == len(selected_option["destination_order"]),
        len(itinerary.flights) >= 1,
        bool(itinerary.sources),
        bool(itinerary.steps),
    ]

    for day_number, day in enumerate(itinerary.itinerary["days"], start=1):
        checks.extend(
            [
                day["day_number"] == day_number,
                day["city"] in selected_option["destination_order"],
                bool(day["theme"]),
                bool(day["morning"]),
                bool(day["afternoon"]),
                bool(day["evening"]),
                bool(day["logistics_note"]),
                bool(day["flexibility_note"]),
            ]
        )

    for flight in itinerary.flights:
        checks.extend(
            [
                flight["price"] > 0,
                flight["booking_url"].startswith("https://"),
                bool(flight["match_reason"]),
                bool(flight["source_name"]),
            ]
        )

    for hotel in itinerary.hotels:
        checks.extend(
            [
                hotel["city"] in selected_option["destination_order"],
                hotel["nightly_rate"] > 0,
                0 <= hotel["rating"] <= 5,
                hotel["booking_url"].startswith("https://"),
                bool(hotel["match_reason"]),
            ]
        )

    return sum(1 for check in checks if check), len(checks)


def test_agent_eval_trip_options_quality_across_core_personas() -> None:
    planner = TripPlanner(Settings(app_env="test", enable_real_agent=False))
    scenarios = [
        make_trip_request(),
        make_trip_request(
            origin="SFO",
            destinations=["Barcelona"],
            trip_style="Food, culture, walkable neighborhoods, and relaxed evenings.",
            pace_preference="Slow",
        ),
        make_trip_request(
            origin="Chicago",
            destinations=["Tokyo", "Kyoto", "Osaka"],
            trip_style="A culture-heavy trip with food markets, temples, design, and low-stress train logistics.",
            budget_range="Luxury",
            pace_preference="Balanced",
        ),
    ]

    for scenario in scenarios:
        artifacts = planner.generate_trip_options(scenario)
        score, possible = option_quality_score(scenario, artifacts)
        assert_score(f"trip option eval for {scenario.destination_candidates}", score, possible)


def test_agent_eval_itinerary_and_inventory_quality() -> None:
    payload = make_trip_request()
    planning = TripPlanner(Settings(app_env="test", enable_real_agent=False)).generate_trip_options(payload)

    score, possible = itinerary_quality_score(payload, planning)

    assert_score("itinerary and booking discovery eval", score, possible)


def test_gemini_option_generation_normalizes_structured_output(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_generate_structured(settings, prompt, schema, temperature=0.2):
        captured["prompt"] = prompt
        captured["schema"] = schema
        captured["temperature"] = temperature
        return schema.model_validate(
            {
                "planning_summary": "Compact Barcelona shortlist.",
                "brief_summary": "Food and culture focus in Barcelona with a relaxed pace.",
                "options": [
                    {
                        "name": "Old City Food Base",
                        "summary": "Stay central and walk between food markets and relaxed evening neighborhoods.",
                        "rationale": "Fits food, culture, walkability, and a short schedule.",
                        "tradeoffs": ["Less beach time, more old-city density."],
                        "destination_order": ["Barcelona"],
                        "days_by_stop": [{"city": "Barcelona", "nights": 10, "start_day": 1, "end_day": 10}],
                        "pace_label": "Relaxed",
                        "budget_confidence": "medium",
                        "return_city": "SFO",
                        "fit_score": 9.2,
                    }
                ],
            }
        )

    monkeypatch.setattr(agent_planner, "_generate_structured_with_gemini", fake_generate_structured)

    payload = make_trip_request(
        origin="SFO",
        destinations=["Barcelona"],
        trip_style="Food, culture, walkable neighborhoods, and relaxed evenings.",
        pace_preference="Relaxed",
    )
    artifacts = TripPlanner(
        Settings(
            app_env="test",
            enable_real_agent=True,
            gemini_api_key="test-key",
        )
    ).generate_trip_options(payload)

    user_prompt = captured["prompt"].lower()
    assert "return only valid json" in user_prompt
    assert "candidate destinations: barcelona" in user_prompt
    assert artifacts.mode == "gemini"
    assert artifacts.options[0]["days_by_stop"][0]["end_day"] == 10
    assert artifacts.options[0]["estimated_total_max"] >= artifacts.options[0]["estimated_total_min"]
    assert artifacts.sources[0]["evidence_type"] == "researched_fact"
