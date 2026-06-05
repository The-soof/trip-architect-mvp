import time

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.services.agent_planner import PlanningArtifacts, _normalize_days_by_stop


def register_user(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "alex@example.com",
            "full_name": "Alex Rivera",
            "password": "supersecure123",
        },
    )
    assert response.status_code == 201
    return response.json()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def trip_payload() -> dict:
    return {
        "origin": "New York",
        "start_date": "2026-08-10",
        "end_date": "2026-08-20",
        "destination_candidates": ["Mykonos", "Barcelona", "Split", "Budapest"],
        "trip_style": "Fun summer trip with good food, nightlife, water, and some relaxation.",
        "budget_range": "Mid-range",
        "traveler_count": 2,
        "pace_preference": "Balanced",
    }


def wait_for_trip(
    client: TestClient,
    token: str,
    trip_id: str,
    predicate,
    *,
    attempts: int = 40,
    delay: float = 0.05,
) -> dict:
    last_trip = {}
    for _ in range(attempts):
        response = client.get(f"/api/trips/{trip_id}", headers=auth_headers(token))
        assert response.status_code == 200
        last_trip = response.json()
        if predicate(last_trip):
            return last_trip
        time.sleep(delay)
    raise AssertionError(f"Timed out waiting for trip state. Last trip: {last_trip}")


def test_register_and_me(client: TestClient) -> None:
    payload = register_user(client)
    me = client.get("/api/auth/me", headers=auth_headers(payload["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "alex@example.com"


def test_login_rejects_wrong_password(client: TestClient) -> None:
    register_user(client)
    response = client.post(
        "/api/auth/login",
        json={"email": "alex@example.com", "password": "wrongwrong"},
    )
    assert response.status_code == 401


def test_trip_planning_flow(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    response = client.post("/api/trips", headers=auth_headers(token), json=trip_payload())
    assert response.status_code == 202

    trip = response.json()
    assert trip["status"] == "planning"
    trip = wait_for_trip(client, token, trip["id"], lambda payload: payload["status"] == "planned" and len(payload["options"]) >= 3)
    assert trip["agent_runs"][0]["kind"] == "options"


def test_select_option_generates_itinerary_and_inventory(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    trip = client.post("/api/trips", headers=auth_headers(token), json=trip_payload()).json()
    trip = wait_for_trip(client, token, trip["id"], lambda payload: len(payload["options"]) >= 3)
    selected_option_id = trip["options"][0]["id"]

    response = client.post(
        f"/api/trips/{trip['id']}/select-option/{selected_option_id}",
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    updated = wait_for_trip(
        client,
        token,
        trip["id"],
        lambda payload: payload["selected_option_id"] == selected_option_id and len(payload["itineraries"]) == 1,
    )
    assert updated["selected_option_id"] == selected_option_id
    assert len(updated["itineraries"][0]["days"]) == 10
    assert len(updated["flight_options"]) >= 1
    assert len(updated["hotel_options"]) >= 1


def test_selected_trip_blocks_regeneration_and_route_changes(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    trip = client.post("/api/trips", headers=auth_headers(token), json=trip_payload()).json()
    trip = wait_for_trip(client, token, trip["id"], lambda payload: len(payload["options"]) >= 2)
    selected_option_id = trip["options"][0]["id"]
    alternate_option_id = trip["options"][1]["id"]

    select_response = client.post(
        f"/api/trips/{trip['id']}/select-option/{selected_option_id}",
        headers=auth_headers(token),
    )
    assert select_response.status_code == 200

    selected_trip = wait_for_trip(
        client,
        token,
        trip["id"],
        lambda payload: payload["selected_option_id"] == selected_option_id,
    )
    assert selected_trip["selected_option_id"] == selected_option_id

    regenerate_response = client.post(
        f"/api/trips/{trip['id']}/regenerate",
        headers=auth_headers(token),
        json={"feedback": "Try fewer stops."},
    )
    assert regenerate_response.status_code == 409
    assert "cannot be changed or regenerated" in regenerate_response.json()["detail"]

    reselection_response = client.post(
        f"/api/trips/{trip['id']}/select-option/{alternate_option_id}",
        headers=auth_headers(token),
    )
    assert reselection_response.status_code == 409
    assert "cannot be changed" in reselection_response.json()["detail"]


def test_save_trip(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    trip = client.post("/api/trips", headers=auth_headers(token), json=trip_payload()).json()
    trip = wait_for_trip(client, token, trip["id"], lambda payload: len(payload["options"]) >= 3)
    response = client.post(
        f"/api/trips/{trip['id']}/save",
        headers=auth_headers(token),
        json={"label": "Europe Summer Shortlist", "notes": "Option A feels strongest."},
    )
    assert response.status_code == 200
    saved = response.json()
    assert saved["status"] == "saved"
    assert saved["saved_trip"]["label"] == "Europe Summer Shortlist"


def test_dashboard_lists_recent_and_saved(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    trip = client.post("/api/trips", headers=auth_headers(token), json=trip_payload()).json()
    trip = wait_for_trip(client, token, trip["id"], lambda payload: len(payload["options"]) >= 3)
    client.post(
        f"/api/trips/{trip['id']}/save",
        headers=auth_headers(token),
        json={"label": "Keep", "notes": None},
    )
    dashboard = client.get("/api/trips", headers=auth_headers(token))
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert len(payload["recent_trips"]) == 1
    assert len(payload["saved_trips"]) == 1


def test_profile_defaults_are_applied_to_new_trip(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    profile_response = client.put(
        "/api/profile/me",
        headers=auth_headers(token),
        json={
            "home_airport": "sfo",
            "budget_preference": "Luxury",
            "pace_preference": "Slow",
            "interests": ["Food", "Design"],
        },
    )
    assert profile_response.status_code == 200

    payload = trip_payload()
    payload["origin"] = "San Francisco"
    payload["budget_range"] = None
    payload["pace_preference"] = None

    trip_response = client.post("/api/trips", headers=auth_headers(token), json=payload)
    assert trip_response.status_code == 202
    trip = wait_for_trip(client, token, trip_response.json()["id"], lambda payload: len(payload["options"]) >= 3)
    assert trip["budget_range"] == "Luxury"
    assert trip["pace_preference"] == "Slow"
    assert "Traveler profile interests: Food, Design." in trip["trip_style"]


def test_duplicate_trip_creates_fresh_plan(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    original = client.post("/api/trips", headers=auth_headers(token), json=trip_payload()).json()
    original = wait_for_trip(client, token, original["id"], lambda payload: len(payload["options"]) >= 3)

    duplicate_response = client.post(
        f"/api/trips/{original['id']}/duplicate",
        headers=auth_headers(token),
    )
    assert duplicate_response.status_code == 202
    duplicate = wait_for_trip(client, token, duplicate_response.json()["id"], lambda payload: len(payload["options"]) >= 3)
    assert duplicate["id"] != original["id"]
    assert duplicate["destination_candidates"] == original["destination_candidates"]
    assert duplicate["trip_style"] == original["trip_style"]
    assert len(duplicate["options"]) >= 3


def test_booking_selection_persists_and_counts_confirmed(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    trip = client.post("/api/trips", headers=auth_headers(token), json=trip_payload()).json()
    trip = wait_for_trip(client, token, trip["id"], lambda payload: len(payload["options"]) >= 3)
    selected_option_id = trip["options"][0]["id"]
    client.post(
        f"/api/trips/{trip['id']}/select-option/{selected_option_id}",
        headers=auth_headers(token),
    )
    selected_trip = wait_for_trip(
        client,
        token,
        trip["id"],
        lambda payload: payload["selected_option_id"] == selected_option_id and len(payload["flight_options"]) >= 1 and len(payload["hotel_options"]) >= 1,
    )

    flight_id = selected_trip["flight_options"][0]["id"]
    hotel_id = selected_trip["hotel_options"][0]["id"]

    saved_response = client.post(
        f"/api/trips/{trip['id']}/booking-selection",
        headers=auth_headers(token),
        json={
            "booking_type": "flight",
            "option_id": flight_id,
            "selection_state": "saved",
        },
    )
    assert saved_response.status_code == 200
    saved_trip = saved_response.json()
    assert len(saved_trip["confirmed_bookings"]) == 1
    assert saved_trip["confirmed_bookings"][0]["selection_state"] == "saved"
    assert saved_trip["saved_trip"] is not None

    confirmed_response = client.post(
        f"/api/trips/{trip['id']}/booking-selection",
        headers=auth_headers(token),
        json={
            "booking_type": "hotel",
            "option_id": hotel_id,
            "selection_state": "confirmed",
        },
    )
    assert confirmed_response.status_code == 200
    confirmed_trip = confirmed_response.json()
    assert len(confirmed_trip["confirmed_bookings"]) == 2
    assert confirmed_trip["saved_trip"]["confirmed_booking_count"] == 1

    clear_response = client.post(
        f"/api/trips/{trip['id']}/booking-selection",
        headers=auth_headers(token),
        json={
            "booking_type": "hotel",
            "option_id": hotel_id,
            "selection_state": "none",
        },
    )
    assert clear_response.status_code == 200
    cleared_trip = clear_response.json()
    assert len(cleared_trip["confirmed_bookings"]) == 1
    assert cleared_trip["saved_trip"]["confirmed_booking_count"] == 0


def test_saved_flight_locks_future_flight_changes(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    trip = client.post("/api/trips", headers=auth_headers(token), json=trip_payload()).json()
    trip = wait_for_trip(client, token, trip["id"], lambda payload: len(payload["options"]) >= 2)
    selected_option_id = trip["options"][0]["id"]

    client.post(
        f"/api/trips/{trip['id']}/select-option/{selected_option_id}",
        headers=auth_headers(token),
    )
    selected_trip = wait_for_trip(
        client,
        token,
        trip["id"],
        lambda payload: payload["selected_option_id"] == selected_option_id and len(payload["flight_options"]) >= 1,
    )
    flight_id = selected_trip["flight_options"][0]["id"]

    save_flight = client.post(
        f"/api/trips/{trip['id']}/booking-selection",
        headers=auth_headers(token),
        json={
            "booking_type": "flight",
            "option_id": flight_id,
            "selection_state": "saved",
        },
    )
    assert save_flight.status_code == 200
    locked_trip = save_flight.json()
    assert locked_trip["flight_selection_locked"] is True
    assert locked_trip["locked_flight_option_id"] == flight_id

    clear_flight_response = client.post(
        f"/api/trips/{trip['id']}/booking-selection",
        headers=auth_headers(token),
        json={
            "booking_type": "flight",
            "option_id": flight_id,
            "selection_state": "none",
        },
    )
    assert clear_flight_response.status_code == 409


def test_travel_journeys_generated_and_selection_locks_route(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    trip = client.post("/api/trips", headers=auth_headers(token), json=trip_payload()).json()
    trip = wait_for_trip(client, token, trip["id"], lambda payload: len(payload["options"]) >= 2)
    selected_option_id = trip["options"][0]["id"]

    client.post(
        f"/api/trips/{trip['id']}/select-option/{selected_option_id}",
        headers=auth_headers(token),
    )
    selected_trip = wait_for_trip(
        client,
        token,
        trip["id"],
        lambda payload: payload["selected_option_id"] == selected_option_id
        and len(payload["travel_journeys"]) >= 2,
    )

    journeys = sorted(selected_trip["travel_journeys"], key=lambda j: j["sort_order"])
    # Multiple distinct personas, exactly one recommended, each a multi-step journey.
    assert len({j["persona_key"] for j in journeys}) == len(journeys)
    assert sum(1 for j in journeys if j["is_recommended"]) == 1
    assert journeys[0]["is_recommended"] is True
    first = journeys[0]
    assert len(first["segments"]) >= 1
    assert all(seg["deep_link"] for seg in first["segments"])
    assert {seg["mode"] for seg in first["segments"]} <= {"flight", "ferry", "train", "car", "transfer"}

    # Selecting a whole journey locks the route.
    journey_id = first["id"]
    select = client.post(
        f"/api/trips/{trip['id']}/booking-selection",
        headers=auth_headers(token),
        json={"booking_type": "journey", "option_id": journey_id, "selection_state": "confirmed"},
    )
    assert select.status_code == 200
    locked = select.json()
    assert locked["selected_journey_id"] == journey_id
    assert locked["flight_selection_locked"] is True

    # A different journey can no longer be selected, and the locked one can't be cleared.
    other_id = journeys[1]["id"]
    switch = client.post(
        f"/api/trips/{trip['id']}/booking-selection",
        headers=auth_headers(token),
        json={"booking_type": "journey", "option_id": other_id, "selection_state": "confirmed"},
    )
    assert switch.status_code == 409
    clear = client.post(
        f"/api/trips/{trip['id']}/booking-selection",
        headers=auth_headers(token),
        json={"booking_type": "journey", "option_id": journey_id, "selection_state": "none"},
    )
    assert clear.status_code == 409


def test_airport_less_island_return_routes_through_gateway() -> None:
    from datetime import date

    from app.core.config import get_settings
    from app.schemas.trip import TripCreateRequest
    from app.services.travel import build_travel_journeys

    payload = TripCreateRequest(
        origin="SFO",
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 20),
        destination_candidates=["Mykonos", "Ios"],
        trip_style="Relaxed island hopping with rest and food.",
        budget_range="mid",
        traveler_count=2,
        pace_preference="relaxed",
    )
    option = {
        "destination_order": ["Mykonos", "Ios"],
        "days_by_stop": [{"city": "Mykonos", "nights": 5}, {"city": "Ios", "nights": 5}],
        "pace_label": "Relaxed",
        "estimated_total_min": 4200,
        "return_city": "SFO",
    }
    journeys, notices = build_travel_journeys(get_settings(), payload, option)
    assert journeys
    # With no flight-search key configured in tests, a fallback notice explains the estimates.
    assert any("estimate" in n.lower() for n in notices)
    segments = journeys[0]["segments"]

    # Ios has no airport: the trip must ferry back to the Mykonos gateway, not fly from Ios.
    flights = [s for s in segments if s["mode"] == "flight"]
    assert flights[-1]["from_label"] == "Mykonos"
    assert all(s["from_label"] != "Ios" for s in flights)
    assert any(
        s["mode"] == "ferry" and s["from_label"] == "Ios" and s["to_label"] == "Mykonos"
        for s in segments
    )


def test_iata_resolution_handles_descriptors_and_codes() -> None:
    from app.services.booking import resolve_iata_code
    from app.services.travel.providers import _is_long_haul

    # "New York City" must resolve (regression: it used to fall through to the
    # generator with a bogus code, producing impossible short-haul transatlantics).
    assert resolve_iata_code("New York City") == "JFK"
    assert resolve_iata_code("New York (JFK)") == "JFK"  # explicit code wins
    assert resolve_iata_code("Mexico City") == "MEX"  # exact match not broken by 'city' strip
    assert resolve_iata_code("Madrid") == "MAD"
    assert resolve_iata_code("Ios") is None  # genuinely airport-less -> caller falls back

    assert _is_long_haul("New York City", "Madrid") is True
    assert _is_long_haul("Barcelona", "Madrid") is False


def test_gemini_route_plan_normalizes_legs(monkeypatch) -> None:
    from datetime import date

    from app.core.config import Settings
    from app.schemas.trip import TripCreateRequest
    from app.services.travel.journey_builder import (
        GeminiJourneyPlanPayload,
        GeminiTravelLegPayload,
        _build_legs_with_gemini,
    )

    plan = GeminiJourneyPlanPayload(
        legs=[
            GeminiTravelLegPayload(mode="flight", from_place="San Francisco (SFO)", to_place="Mykonos (JMK)"),
            GeminiTravelLegPayload(mode="taxi", from_place="Mykonos", to_place="Mykonos hotel", note="Transfer"),
            GeminiTravelLegPayload(mode="boat", from_place="Mykonos", to_place="Ios", provider_hint="SeaJets"),
            GeminiTravelLegPayload(mode="ferry", from_place="Ios", to_place="Santorini"),
            GeminiTravelLegPayload(mode="flight", from_place="Santorini (JTR)", to_place="San Francisco"),
        ]
    )
    monkeypatch.setattr(
        "app.services.agent_planner._generate_structured_with_gemini",
        lambda *args, **kwargs: plan,
    )
    payload = TripCreateRequest(
        origin="SFO",
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 20),
        destination_candidates=["Mykonos", "Ios"],
        trip_style="Relaxed island hopping with rest.",
        budget_range="mid",
        traveler_count=2,
        pace_preference="relaxed",
    )
    option = {
        "destination_order": ["Mykonos", "Ios"],
        "days_by_stop": [{"city": "Mykonos", "nights": 5}, {"city": "Ios", "nights": 5}],
        "pace_label": "Relaxed",
        "estimated_total_min": 4200,
        "return_city": "SFO",
    }
    settings = Settings(gemini_api_key="x", enable_real_agent=True)
    legs = _build_legs_with_gemini(settings, payload, option)

    from app.services.booking import resolve_iata_code

    # Modes normalized (taxi->transfer, boat->ferry); raw place kept so the IATA code survives.
    assert [leg.mode for leg in legs] == ["flight", "transfer", "ferry", "ferry", "flight"]
    assert legs[0].frm == "San Francisco (SFO)" and legs[0].to == "Mykonos (JMK)"
    assert resolve_iata_code(legs[0].frm) == "SFO"  # code recoverable for flight lookup
    # Outbound flight departs day 1; the home flight (from the Santorini gateway) on the last day.
    assert legs[0].day == date(2026, 8, 10)
    assert legs[-1].day == date(2026, 8, 20)
    assert legs[-1].frm == "Santorini (JTR)"
    # Gemini's ground-leg hints carry through.
    assert legs[2].provider == "SeaJets"


def test_normalize_days_by_stop_accepts_agent_city_night_maps() -> None:
    normalized = _normalize_days_by_stop(
        [{"Barcelona": 3}, {"Split": 5}],
        ["Barcelona", "Split"],
        8,
    )
    assert normalized == [
        {"city": "Barcelona", "nights": 3, "start_day": 1, "end_day": 3},
        {"city": "Split", "nights": 5, "start_day": 4, "end_day": 8},
    ]


def test_trip_planning_records_fallback_reason_when_live_agent_fails(client: TestClient, monkeypatch) -> None:
    token = register_user(client)["access_token"]

    monkeypatch.setattr(
        "app.services.trip_jobs.get_settings",
        lambda: Settings(
            app_env="test",
            database_url="sqlite:///./test_trip_architect.db",
            jwt_secret_key="test-secret",
            enable_real_agent=True,
            gemini_api_key="test-gemini",
        ),
    )

    def raise_live_agent_failure(*args, **kwargs):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota depleted")

    monkeypatch.setattr("app.services.agent_planner.TripPlanner._generate_with_gemini_options", raise_live_agent_failure)

    response = client.post("/api/trips", headers=auth_headers(token), json=trip_payload())

    assert response.status_code == 202
    trip = wait_for_trip(
        client,
        token,
        response.json()["id"],
        lambda payload: payload["status"] == "planned" and "fallback_reason" in payload["agent_runs"][0]["output_payload"],
    )
    assert trip["planning_mode"] == "mock"
    assert trip["agent_runs"][0]["output_payload"]["fallback_reason"].startswith(
        "The live Gemini, Tavily, or Google Places pipeline is currently unavailable"
    )
    assert trip["agent_runs"][0]["steps"][-1]["agent"] == "fallback-guard"


def test_trip_planning_bounds_gemini_enum_text(client: TestClient, monkeypatch) -> None:
    token = register_user(client)["access_token"]

    def fake_gemini_options(*args, **kwargs):
        return PlanningArtifacts(
            mode="gemini",
            planning_summary="Gemini produced verbose labels.",
            brief_summary="A short plan.",
            options=[
                {
                    "name": "Barcelona food weekend",
                    "summary": "A tight Barcelona plan.",
                    "rationale": "Matches the form input.",
                    "tradeoffs": ["Short trip from the west coast."],
                    "destination_order": ["Barcelona"],
                    "days_by_stop": [{"city": "Barcelona", "nights": 10, "start_day": 1, "end_day": 10}],
                    "pace_label": "Balanced but with long relaxed evening buffers and optional cafe stops",
                    "estimated_total_min": 2400,
                    "estimated_total_max": 3600,
                    "budget_confidence": "Medium confidence because June hotel pricing can swing by neighborhood",
                    "return_city": "SFO",
                    "fit_score": 9.1,
                }
            ],
            sources=[],
            steps=[],
        )

    monkeypatch.setattr("app.services.agent_planner.TripPlanner.generate_trip_options", fake_gemini_options)

    response = client.post("/api/trips", headers=auth_headers(token), json=trip_payload())

    assert response.status_code == 202
    trip = wait_for_trip(client, token, response.json()["id"], lambda payload: payload["status"] == "planned")
    assert trip["planning_mode"] == "gemini"
    assert len(trip["options"][0]["pace_label"]) <= 40
    assert trip["options"][0]["budget_confidence"] == "medium"


def test_trip_create_returns_pending_workspace_when_background_job_is_not_run(
    client: TestClient,
    monkeypatch,
) -> None:
    token = register_user(client)["access_token"]
    monkeypatch.setattr("app.api.trips.schedule_trip_options_generation", lambda trip_id: None)

    response = client.post("/api/trips", headers=auth_headers(token), json=trip_payload())

    assert response.status_code == 202
    trip = response.json()
    assert trip["status"] == "planning"
    assert trip["options"] == []
    assert trip["agent_runs"][0]["status"] == "running"


def test_build_flight_options_different_return_and_one_way() -> None:
    from app.services.agent_planner import _build_flight_options
    from app.schemas.trip import TripCreateRequest
    from datetime import date

    payload = TripCreateRequest(
        origin="SFO",
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 20),
        destination_candidates=["Barcelona", "Split"],
        trip_style="Vacation planning",
        budget_range="Mid-range",
        traveler_count=2,
        pace_preference="Balanced",
    )

    # 1. Test standard round-trip to origin
    option_rt = {
        "days_by_stop": [
            {"city": "Barcelona", "nights": 5},
            {"city": "Split", "nights": 5},
        ],
        "estimated_total_min": 2000,
        "return_city": "SFO",
    }
    flights_rt = _build_flight_options(payload, option_rt)
    assert flights_rt[0]["route_summary"] == "SFO → Barcelona / Split → SFO"
    assert "2026-08-20" in flights_rt[0]["booking_url"]  # Return date is present

    # 2. Test one-way trip
    option_ow = {
        "days_by_stop": [
            {"city": "Barcelona", "nights": 5},
            {"city": "Split", "nights": 5},
        ],
        "estimated_total_min": 2000,
        "return_city": "none",
    }
    flights_ow = _build_flight_options(payload, option_ow)
    assert flights_ow[0]["route_summary"] == "SFO → Barcelona (One-way)"
    assert flights_ow[1]["route_summary"] == "SFO → Barcelona one-way with regional transfers in between"
    assert "2026-08-20" not in flights_ow[0]["booking_url"]  # No return date for one-way flight

    # 3. Test open-jaw returning to a different city (e.g. BOS)
    option_oj = {
        "days_by_stop": [
            {"city": "Barcelona", "nights": 5},
            {"city": "Split", "nights": 5},
        ],
        "estimated_total_min": 2000,
        "return_city": "BOS",
    }
    flights_oj = _build_flight_options(payload, option_oj)
    assert flights_oj[0]["route_summary"] == "SFO → Barcelona / Split → BOS"
    assert flights_oj[1]["route_summary"] == "SFO → Barcelona outbound flight (return to BOS booked separately)"
    assert "2026-08-20" not in flights_oj[0]["booking_url"]  # No return date because return is separate

