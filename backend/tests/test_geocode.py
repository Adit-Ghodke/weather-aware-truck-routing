"""
Integration tests for SafeHaul Ephemeral Geocoding Endpoint (Phase 8).

Specifications (§7, §12):
  • GET /api/v1/geocode/?q=<string>
  • Validates q length (2..200 chars)
  • Returns <= 5 results with {label, lat, lng}
  • Strictly NO backend cache keys stored
  • 502 GEOCODING_UNAVAILABLE on external provider error
"""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from safehaul.adapters.base import GeocodingUnavailableException


@pytest.fixture
def api_client():
    return APIClient()


def make_mock_geocode_features():
    return [
        {
            "label": "Chicago, Illinois, United States",
            "lat": 41.8781,
            "lng": -87.6298,
        },
        {
            "label": "Chicago O'Hare International Airport, Illinois, United States",
            "lat": 41.9742,
            "lng": -87.9073,
        },
    ]


@pytest.mark.django_db
class TestGeocodeEndpoint:
    """Tests for GET /api/v1/geocode/."""

    @patch("safehaul.views.MapboxGeocodingAdapter.search")
    def test_geocode_success(self, mock_geocode, api_client):
        mock_geocode.return_value = make_mock_geocode_features()

        url = reverse("safehaul:geocode")
        response = api_client.get(url, {"q": "Chicago"})

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2
        r0 = data["results"][0]
        assert r0["label"] == "Chicago, Illinois, United States"
        assert r0["lat"] == 41.8781
        assert r0["lng"] == -87.6298

    @patch("safehaul.views.MapboxGeocodingAdapter.search")
    def test_geocode_no_backend_cache(self, mock_geocode, api_client):
        """Mapbox terms prohibit persistent/backend caching of temporary geocodes (§7)."""
        mock_geocode.return_value = make_mock_geocode_features()
        cache.clear()

        url = reverse("safehaul:geocode")
        response = api_client.get(url, {"q": "Chicago"})
        assert response.status_code == 200

        # Verify no cache key for this geocode query exists in cache
        assert cache.get("geocode:Chicago") is None
        assert cache.get("mapbox:geocode:Chicago") is None

    def test_geocode_missing_query(self, api_client):
        url = reverse("safehaul:geocode")
        response = api_client.get(url)

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "INVALID_QUERY"

    def test_geocode_query_too_short(self, api_client):
        url = reverse("safehaul:geocode")
        response = api_client.get(url, {"q": "C"})

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "INVALID_QUERY"

    def test_geocode_query_too_long(self, api_client):
        url = reverse("safehaul:geocode")
        response = api_client.get(url, {"q": "A" * 205})

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "INVALID_QUERY"

    @patch("safehaul.views.MapboxGeocodingAdapter.search")
    def test_geocode_provider_unavailable(self, mock_geocode, api_client):
        mock_geocode.side_effect = GeocodingUnavailableException("Mapbox rate limit exceeded")

        url = reverse("safehaul:geocode")
        response = api_client.get(url, {"q": "Denver"})

        assert response.status_code == 502
        data = response.json()
        assert data["error"]["code"] == "GEOCODING_UNAVAILABLE"
