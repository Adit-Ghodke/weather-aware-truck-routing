"""
Integration tests for SafeHaul REST API Endpoints (Phase 6).

Covers:
  - POST /api/v1/trips/analyze/ (Success, Validations, Resilience, Non-blocking DB)
  - GET /api/v1/trips/<uuid>/ (Trip detail, 404 handling)
"""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from safehaul.adapters.base import RoutingUnavailableException
from safehaul.models import TripAnalysis


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def valid_trip_payload():
    dep_time = timezone.now() + timedelta(hours=2)
    return {
        "origin": {
            "lat": 41.8781,
            "lng": -87.6298,
            "label": "Chicago, IL",
        },
        "destination": {
            "lat": 39.0997,
            "lng": -94.5786,
            "label": "Kansas City, MO",
        },
        "departure_datetime": dep_time.isoformat(),
        "load_weight_lb": 35000,
        "sample_interval_miles": 25,
    }


def make_mock_routes():
    """Generates 3 synthetic candidate routes with valid coordinates and segments."""
    routes = []
    labels = ["Route 1 (I-55 / I-72)", "Route 2 (I-80 / I-35)", "Route 3 (US-36)"]
    distances = [510.0, 545.0, 530.0]
    durations = [28800, 31200, 30600]

    for i in range(3):
        # 5 coordinates along route
        coords = [
            [-87.6298, 41.8781],
            [-89.6501, 39.7817],
            [-91.5000, 39.7000],
            [-93.0000, 39.4000],
            [-94.5786, 39.0997],
        ]
        segments = [
            {"start_mile": 0.0, "end_mile": 250.0, "duration_seconds": 14400.0},
            {"start_mile": 250.0, "end_mile": distances[i], "duration_seconds": durations[i] - 14400.0},
        ]
        routes.append({
            "id": f"route-{i+1}",
            "label": labels[i],
            "distance_miles": distances[i],
            "duration_minutes": int(durations[i] / 60),
            "duration_seconds": durations[i],
            "geometry": {
                "type": "LineString",
                "coordinates": coords,
            },
            "segments": segments,
        })
    return routes


def make_mock_weather_forecast():
    """Generates synthetic hourly forecast data for any location."""
    now = timezone.now().replace(minute=0, second=0, microsecond=0)
    hourly = {}
    for h in range(48):
        dt = now + timedelta(hours=h)
        hourly[dt] = {
            "wind_mph": 20.0,
            "gust_mph": 25.0,
            "rain_in_hr": 0.0,
            "snow_in_hr": 0.0,
            "temp_f": 55.0,
        }
    return hourly


@pytest.mark.django_db
class TestAnalyzeTripEndpoint:
    """Integration test suite for POST /api/v1/trips/analyze/."""

    @patch("safehaul.views.MapboxRoutingAdapter.get_routes")
    @patch("safehaul.views.OpenMeteoWeatherAdapter.get_forecast_for_locations")
    def test_analyze_trip_success(
        self, mock_weather, mock_routing, api_client, valid_trip_payload
    ):
        mock_routing.return_value = make_mock_routes()
        # Weather adapter returns a dict mapping (lat, lng) to hourly dict
        mock_weather.side_effect = lambda locs: {
            (round(lat, 2), round(lng, 2)): make_mock_weather_forecast()
            for lat, lng in locs
        }

        url = reverse("safehaul:analyze-trip")
        response = api_client.post(url, valid_trip_payload, format="json")

        assert response.status_code == 200
        data = response.json()

        # Check top-level contract
        assert "id" in data
        assert "routes" in data
        assert "recommendation" in data
        assert "meta" in data

        # Check routes
        assert len(data["routes"]) == 3
        r1 = data["routes"][0]
        assert "checkpoints" in r1
        assert "metrics" in r1
        assert "arrival_datetime_utc" in r1
        assert "arrival_datetime_local" in r1

        # Check checkpoint fields
        cp0 = r1["checkpoints"][0]
        assert "lat" in cp0
        assert "lng" in cp0
        assert "weather" in cp0
        assert "level" in cp0
        assert "reason" in cp0
        assert "condition_levels" in cp0

        # Check recommendation
        rec = data["recommendation"]
        assert rec["recommended_route_id"] == "route-1"
        assert rec["status"] == "recommended"
        assert "explanation" in rec
        assert "comparison" in rec


        # Check DB persistence
        assert TripAnalysis.objects.filter(id=data["id"]).exists()
        persisted = TripAnalysis.objects.get(id=data["id"])
        assert persisted.load_weight_lb == 35000
        assert persisted.origin_label == "Chicago, IL"
        assert persisted.destination_label == "Kansas City, MO"

    def test_invalid_load_weight_negative(self, api_client, valid_trip_payload):
        valid_trip_payload["load_weight_lb"] = -100
        url = reverse("safehaul:analyze-trip")
        response = api_client.post(url, valid_trip_payload, format="json")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "INVALID_LOAD_WEIGHT"

    def test_invalid_load_weight_exceeds_maximum(self, api_client, valid_trip_payload):
        valid_trip_payload["load_weight_lb"] = 85000
        url = reverse("safehaul:analyze-trip")
        response = api_client.post(url, valid_trip_payload, format="json")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "INVALID_LOAD_WEIGHT"

    def test_invalid_departure_time_in_past(self, api_client, valid_trip_payload):
        past_time = timezone.now() - timedelta(hours=3)
        valid_trip_payload["departure_datetime"] = past_time.isoformat()
        url = reverse("safehaul:analyze-trip")
        response = api_client.post(url, valid_trip_payload, format="json")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "INVALID_DEPARTURE_TIME"

    def test_invalid_departure_time_too_far_future(self, api_client, valid_trip_payload):
        future_time = timezone.now() + timedelta(days=10)
        valid_trip_payload["departure_datetime"] = future_time.isoformat()
        url = reverse("safehaul:analyze-trip")
        response = api_client.post(url, valid_trip_payload, format="json")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "INVALID_DEPARTURE_TIME"

    def test_missing_origin(self, api_client, valid_trip_payload):
        del valid_trip_payload["origin"]
        url = reverse("safehaul:analyze-trip")
        response = api_client.post(url, valid_trip_payload, format="json")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"

    @patch("safehaul.views.MapboxRoutingAdapter.get_routes")
    @patch("safehaul.views.OpenMeteoWeatherAdapter.get_forecast_for_locations")
    def test_naive_departure_datetime_is_accepted(
        self, mock_weather, mock_routing, api_client, valid_trip_payload
    ):
        mock_routing.return_value = make_mock_routes()
        mock_weather.return_value = {}
        # Naive datetime string without timezone offset or Z
        from datetime import datetime as std_dt
        now_naive = std_dt.now().replace(microsecond=0) + timedelta(hours=2)
        valid_trip_payload["departure_datetime"] = now_naive.strftime("%Y-%m-%dT%H:%M:%S")

        url = reverse("safehaul:analyze-trip")
        response = api_client.post(url, valid_trip_payload, format="json")
        assert response.status_code == 200


    @patch("safehaul.views.MapboxRoutingAdapter.get_routes")
    def test_routing_provider_unavailable(self, mock_routing, api_client, valid_trip_payload):
        mock_routing.side_effect = RoutingUnavailableException("Mapbox timeout")
        url = reverse("safehaul:analyze-trip")
        response = api_client.post(url, valid_trip_payload, format="json")

        assert response.status_code == 502
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "ROUTING_UNAVAILABLE"

    @patch("safehaul.views.MapboxRoutingAdapter.get_routes")
    @patch("safehaul.views.OpenMeteoWeatherAdapter.get_forecast_for_locations")
    def test_weather_provider_failure_graceful_fallback(
        self, mock_weather, mock_routing, api_client, valid_trip_payload
    ):
        """Weather outage should not fail trip analysis; returns routes with warning (§7)."""
        mock_routing.return_value = make_mock_routes()
        mock_weather.side_effect = Exception("Open-Meteo 500 server error")

        url = reverse("safehaul:analyze-trip")
        response = api_client.post(url, valid_trip_payload, format="json")

        assert response.status_code == 200
        data = response.json()
        assert len(data["routes"]) == 3
        # Warning present in meta
        warnings = data["meta"]["warnings"]
        assert any("Weather forecast data unavailable" in w for w in warnings)

        # Checkpoints default to Low risk
        cp = data["routes"][0]["checkpoints"][0]
        assert cp["level"] == "Low"
        assert cp["weather_available"] is False

    @patch("safehaul.views.TripAnalysis.objects.create")
    @patch("safehaul.views.MapboxRoutingAdapter.get_routes")
    @patch("safehaul.views.OpenMeteoWeatherAdapter.get_forecast_for_locations")
    def test_db_persistence_failure_non_blocking(
        self, mock_weather, mock_routing, mock_create, api_client, valid_trip_payload
    ):
        """DB persistence failure must NOT block or fail the HTTP response (§6)."""
        mock_routing.return_value = make_mock_routes()
        mock_weather.return_value = {}
        mock_create.side_effect = Exception("Database disk full")

        url = reverse("safehaul:analyze-trip")
        response = api_client.post(url, valid_trip_payload, format="json")

        # Response must still succeed with 200 OK
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "routes" in data


@pytest.mark.django_db
class TestTripDetailEndpoint:
    """Integration test suite for GET /api/v1/trips/<uuid:trip_id>/."""

    def test_get_existing_trip(self, api_client):
        trip_id = uuid.uuid4()
        expected_json = {
            "id": str(trip_id),
            "routes": [{"id": "r1"}],
            "recommendation": {"recommended_route_id": "r1"},
        }
        TripAnalysis.objects.create(
            id=trip_id,
            origin_lat=41.8781,
            origin_lng=-87.6298,
            origin_label="Chicago, IL",
            destination_lat=39.0997,
            destination_lng=-94.5786,
            destination_label="Kansas City, MO",
            departure_datetime_utc=timezone.now(),
            load_weight_lb=35000,
            sample_interval_miles=25,
            result_json=expected_json,
        )

        url = reverse("safehaul:trip-detail", kwargs={"trip_id": trip_id})
        response = api_client.get(url)

        assert response.status_code == 200
        assert response.json() == expected_json

    def test_get_nonexistent_trip(self, api_client):
        fake_id = uuid.uuid4()
        url = reverse("safehaul:trip-detail", kwargs={"trip_id": fake_id})
        response = api_client.get(url)

        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "TRIP_NOT_FOUND"

    def test_trip_analysis_model_str(self):
        trip = TripAnalysis(
            id=uuid.uuid4(),
            origin_label="Chicago, IL",
            destination_label="Kansas City, MO",
        )
        assert "Chicago, IL -> Kansas City, MO" in str(trip)

    @patch("safehaul.views.MapboxRoutingAdapter.get_routes")
    def test_unexpected_routing_failure_503(self, mock_routing, api_client, valid_trip_payload):
        mock_routing.side_effect = RuntimeError("Fatal hardware crash")
        url = reverse("safehaul:analyze-trip")
        response = api_client.post(url, valid_trip_payload, format="json")

        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "ANALYSIS_FAILED"

    @patch("safehaul.views.MapboxRoutingAdapter.get_routes")
    @patch("safehaul.views.OpenMeteoWeatherAdapter.get_forecast_for_locations")
    def test_fewer_than_3_routes_warning(
        self, mock_weather, mock_routing, api_client, valid_trip_payload
    ):
        # Return only 2 routes
        routes = make_mock_routes()[:2]
        mock_routing.return_value = routes
        mock_weather.return_value = {}

        url = reverse("safehaul:analyze-trip")
        response = api_client.post(url, valid_trip_payload, format="json")

        assert response.status_code == 200
        data = response.json()
        assert any("Fewer than 3 candidate routes" in w for w in data["meta"]["warnings"])

    def test_timezone_resolve_endpoint(self, api_client):
        url = reverse("safehaul:timezone-resolve")
        # Chicago, USA
        resp = api_client.get(url, {"lat": 41.8781, "lng": -87.6298})
        assert resp.status_code == 200
        data = resp.json()
        assert data["timezone"] == "America/Chicago"
        assert data["abbr"] in ["CDT", "CST"]

        # Tokyo, Japan
        resp = api_client.get(url, {"lat": 35.6762, "lng": 139.6503})
        assert resp.status_code == 200
        data = resp.json()
        assert data["timezone"] == "Asia/Tokyo"
        assert data["abbr"] == "JST"

        # Paris, France
        resp = api_client.get(url, {"lat": 48.8566, "lng": 2.3522})
        assert resp.status_code == 200
        data = resp.json()
        assert data["timezone"] == "Europe/Paris"

        # Missing params
        resp = api_client.get(url)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_COORDINATES"

    @patch("safehaul.views.MapboxRoutingAdapter.get_routes")
    @patch("safehaul.views.OpenMeteoWeatherAdapter.get_forecast_for_locations")
    def test_browser_zone_kolkata_origin_chicago_input_16_00(
        self, mock_weather, mock_routing, api_client
    ):
        """Spec test: browser zone Asia/Kolkata, origin Chicago, input 16:00 -> ETA at mile 0 is 16:00 CDT = 21:00 UTC."""
        routes = make_mock_routes()
        mock_routing.return_value = routes
        mock_weather.return_value = {}

        now_utc = timezone.now()
        target_date = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
        input_datetime = f"{target_date}T16:00:00"

        payload = {
            "origin": {"label": "Chicago, IL", "lat": 41.8781, "lng": -87.6298},
            "destination": {"label": "Kansas City, MO", "lat": 39.0997, "lng": -94.5786},
            "departure_datetime": input_datetime,
            "load_weight_lb": 35000,
        }

        url = reverse("safehaul:analyze-trip")
        resp = api_client.post(url, payload, format="json")
        assert resp.status_code == 200
        data = resp.json()

        r1 = data["routes"][0]
        cp0 = r1["checkpoints"][0]
        assert cp0["mile_marker"] == 0.0

        # Mile 0 ETA in UTC must be 21:00:00Z (16:00 CDT + 5h = 21:00 UTC)
        assert cp0["eta_utc"].endswith("T21:00:00+00:00") or cp0["eta_utc"].endswith("T21:00:00Z")
        assert "16:00:00" in cp0["eta_local"]
        assert cp0["timezone_abbr"] in ["CDT", "CST"]



