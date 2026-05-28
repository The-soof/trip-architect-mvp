from fastapi.testclient import TestClient

from app.services.agent_planner import _normalize_days_by_stop


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
    assert response.status_code == 201

    trip = response.json()
    assert trip["status"] == "planned"
    assert len(trip["options"]) >= 3
    assert trip["agent_runs"][0]["kind"] == "options"


def test_select_option_generates_itinerary_and_inventory(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    trip = client.post("/api/trips", headers=auth_headers(token), json=trip_payload()).json()
    selected_option_id = trip["options"][0]["id"]

    response = client.post(
        f"/api/trips/{trip['id']}/select-option/{selected_option_id}",
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["selected_option_id"] == selected_option_id
    assert len(updated["itineraries"]) == 1
    assert len(updated["itineraries"][0]["days"]) == 10
    assert len(updated["flight_options"]) >= 1
    assert len(updated["hotel_options"]) >= 1


def test_save_trip(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    trip = client.post("/api/trips", headers=auth_headers(token), json=trip_payload()).json()
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
    assert trip_response.status_code == 201
    trip = trip_response.json()
    assert trip["budget_range"] == "Luxury"
    assert trip["pace_preference"] == "Slow"
    assert "Traveler profile interests: Food, Design." in trip["trip_style"]


def test_duplicate_trip_creates_fresh_plan(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    original = client.post("/api/trips", headers=auth_headers(token), json=trip_payload()).json()

    duplicate_response = client.post(
        f"/api/trips/{original['id']}/duplicate",
        headers=auth_headers(token),
    )
    assert duplicate_response.status_code == 201
    duplicate = duplicate_response.json()
    assert duplicate["id"] != original["id"]
    assert duplicate["destination_candidates"] == original["destination_candidates"]
    assert duplicate["trip_style"] == original["trip_style"]
    assert len(duplicate["options"]) >= 3


def test_booking_selection_persists_and_counts_confirmed(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    trip = client.post("/api/trips", headers=auth_headers(token), json=trip_payload()).json()
    selected_option_id = trip["options"][0]["id"]
    selected_trip = client.post(
        f"/api/trips/{trip['id']}/select-option/{selected_option_id}",
        headers=auth_headers(token),
    ).json()

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
