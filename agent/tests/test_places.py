"""Unit tests for the Places tool (mocked HTTP)."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from app.tools import places


def _mock_response(payload, status=200):
    response = AsyncMock()
    response.status_code = status
    response.json = lambda: payload
    response.raise_for_status = lambda: None
    return response


@pytest.mark.anyio
async def test_missing_api_key_returns_error(monkeypatch):
    monkeypatch.delenv("PLACES_API_KEY", raising=False)
    result = await places.find_local_services("speech therapy", "Austin, TX")
    assert "error" in result


@pytest.mark.anyio
async def test_results_mapped_and_closed_places_filtered(monkeypatch):
    monkeypatch.setenv("PLACES_API_KEY", "test-key")
    payload = {
        "places": [
            {
                "id": "a",
                "displayName": {"text": "Austin Autism Center"},
                "formattedAddress": "1 Main St, Austin, TX 78701",
                "rating": 4.5,
                "userRatingCount": 12,
                "nationalPhoneNumber": "(512) 555-0100",
                "websiteUri": "https://example.org",
                "googleMapsUri": "https://maps.google.com/?cid=1",
                "businessStatus": "OPERATIONAL",
            },
            {
                "id": "b",
                "displayName": {"text": "Closed Clinic"},
                "businessStatus": "CLOSED_PERMANENTLY",
            },
        ]
    }
    client = AsyncMock()
    client.post.return_value = _mock_response(payload)
    client.__aenter__.return_value = client
    with patch.object(places.httpx, "AsyncClient", return_value=client):
        result = await places.find_local_services("autism therapy", "Austin, TX")

    assert len(result["results"]) == 1
    entry = result["results"][0]
    assert entry["name"] == "Austin Autism Center"
    assert entry["phone"] == "(512) 555-0100"
    assert entry["google_maps_link"] == "https://maps.google.com/?cid=1"

    body = client.post.call_args.kwargs["json"]
    assert body["textQuery"] == "autism therapy near Austin, TX"
    assert body["regionCode"] == "US"


@pytest.mark.anyio
async def test_empty_results_return_note(monkeypatch):
    monkeypatch.setenv("PLACES_API_KEY", "test-key")
    client = AsyncMock()
    client.post.return_value = _mock_response({})
    client.__aenter__.return_value = client
    with patch.object(places.httpx, "AsyncClient", return_value=client):
        result = await places.find_local_services("unicorn therapy", "Nowhere, KS")
    assert result["results"] == []
    assert "note" in result


@pytest.fixture
def anyio_backend():
    return "asyncio"
