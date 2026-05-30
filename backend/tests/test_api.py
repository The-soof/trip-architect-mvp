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
