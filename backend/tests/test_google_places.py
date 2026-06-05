from unittest.mock import MagicMock
import pytest
import httpx
from pydantic import BaseModel
from app.services.google_places import search_places

def test_search_places_filters_closed_businesses(monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "places": [
            {
                "displayName": {"text": "Closed Bakery"},
                "formattedAddress": "123 Closed St",
                "location": {"latitude": 10.0, "longitude": 20.0},
                "rating": 3.5,
                "userRatingCount": 10,
                "googleMapsUri": "https://maps.google.com/closed",
                "businessStatus": "CLOSED_PERMANENTLY",
                "currentOpeningHours": {"weekdayDescriptions": ["Closed permanently"]}
            },
            {
                "displayName": {"text": "Open Bakery"},
                "formattedAddress": "456 Open St",
                "location": {"latitude": 11.0, "longitude": 21.0},
                "rating": 4.5,
                "userRatingCount": 100,
                "googleMapsUri": "https://maps.google.com/open",
                "businessStatus": "OPERATIONAL",
                "currentOpeningHours": {"weekdayDescriptions": ["Mon-Fri: 9-5"]}
            }
        ]
    }
    
    # Mock httpx.Client.post to return our mock response
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: mock_response)
    
    result = search_places(
        api_key="fake-key",
        query="bakery",
        city="Paris",
        category="bakery",
        reason="morning pastry",
    )
    
    assert result is not None
    assert result.place is not None
    # Verify that the closed one was skipped and the operational one was selected
    assert result.place["name"] == "Open Bakery"
    assert result.place["business_status"] == "OPERATIONAL"

def test_search_places_returns_none_if_all_closed(monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "places": [
            {
                "displayName": {"text": "Temporarily Closed Hotel"},
                "formattedAddress": "789 Closed Rd",
                "location": {"latitude": 12.0, "longitude": 22.0},
                "rating": 4.0,
                "userRatingCount": 50,
                "googleMapsUri": "https://maps.google.com/temp",
                "businessStatus": "CLOSED_TEMPORARILY",
                "currentOpeningHours": {"weekdayDescriptions": ["Closed temporarily"]}
            }
        ]
    }
    
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: mock_response)
    
    result = search_places(
        api_key="fake-key",
        query="hotel",
        city="Paris",
        category="hotel",
        reason="stay",
    )
    
    assert result is not None
    assert result.place is None


class MockSchema(BaseModel):
    title: str

def test_gemini_retry_on_failure(monkeypatch):
    from google import genai
    from pydantic import BaseModel
    from app.services.agent_planner import _generate_structured_with_gemini
    from app.core.config import Settings

    calls = []

    class MockModels:
        def generate_content(self, model, contents, config):
            calls.append(config)
            if len(calls) == 1:
                mock_resp = MagicMock()
                mock_resp.text = "invalid json {"
                mock_resp.candidates = []
                return mock_resp
            else:
                mock_resp = MagicMock()
                mock_resp.text = '{"title": "Successful Retry"}'
                mock_resp.candidates = []
                return mock_resp

    class MockClient:
        def __init__(self, api_key):
            self.models = MockModels()

    monkeypatch.setattr(genai, "Client", MockClient)

    settings = Settings(
        gemini_api_key="fake-gemini-key",
        gemini_model="gemini-2.5-flash",
        tavily_api_key="fake-tavily-key",
        google_places_api_key="fake-places-key"
    )

    result = _generate_structured_with_gemini(
        settings=settings,
        prompt="Write a title",
        schema=MockSchema,
        temperature=0.2
    )

    assert result.title == "Successful Retry"
    assert len(calls) == 2
    assert calls[0].temperature == 0.2
    assert calls[1].temperature == 0.35

