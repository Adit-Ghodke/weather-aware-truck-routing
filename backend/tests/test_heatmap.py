"""
Unit and integration tests for SafeHaul Corridor Heatmap (Phase 7).

Specifications (§7, §8g, §12):
  • Grid point count <= MAX_HEATMAP_POINTS (400)
  • Each point has exactly 49 hour_risks (hours 0..48)
  • Risk values in [0, 4]
  • Handles POST with trip_id or corridor_geometry
  • Graceful fallback when weather is unavailable
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from safehaul.domain.constants import MAX_HEATMAP_POINTS
from safehaul.domain.heatmap import (
    compute_corridor_hourly_risks,
    generate_corridor_grid,
)
from safehaul.models import TripAnalysis


@pytest.fixture
def api_client():
    return APIClient()


def make_sample_weather(now_utc: datetime):
    """Synthetic hourly forecast for 49 hours."""
    hourly = {}
    for h in range(49):
        dt = now_utc + timedelta(hours=h)
        # Alternate wind: Low at start, Severe at h=20
        wind = 15.0 if h < 20 else 46.0
        hourly[dt] = {
            "wind_mph": wind,
            "gust_mph": wind + 5.0,
            "rain_in_hr": 0.0,
            "snow_in_hr": 0.0,
            "temp_f": 60.0,
        }
    return hourly


class TestGenerateCorridorGrid:
    """Verify corridor bounding box generation and hard point cap (§8g)."""

    def test_empty_coordinates_returns_empty(self):
        assert generate_corridor_grid([]) == []

    def test_single_point_returns_single_center_when_zero_buffer(self):
        grid = generate_corridor_grid([[-87.62, 41.88]], buffer_deg=0.0)
        assert len(grid) == 1
        assert grid[0] == (41.88, -87.62)

    def test_single_point_with_default_buffer_under_cap(self):
        grid = generate_corridor_grid([[-87.62, 41.88]])
        assert len(grid) == 121
        assert len(grid) <= MAX_HEATMAP_POINTS


    def test_moderate_span_under_cap(self):
        # Coordinates spanning ~2 degrees lat and 2 degrees lng
        coords = [
            [-87.0, 41.0],
            [-88.0, 42.0],
            [-89.0, 43.0],
        ]
        grid = generate_corridor_grid(coords, max_points=400, buffer_deg=0.5)
        assert len(grid) > 0
        assert len(grid) <= MAX_HEATMAP_POINTS

        # Verify within buffered bounds
        for lat, lng in grid:
            assert 40.5 <= lat <= 43.5 + 1e-4
            assert -89.5 <= lng <= -86.5 + 1e-4

    def test_transcontinental_span_respects_hard_cap(self):
        # Spanning from NYC (-74, 40) to LA (-118, 34)
        coords = [
            [-74.0, 40.7],
            [-90.0, 38.6],
            [-105.0, 39.7],
            [-118.2, 34.0],
        ]
        grid = generate_corridor_grid(coords, max_points=400, buffer_deg=0.5)
        assert len(grid) > 0
        assert len(grid) <= MAX_HEATMAP_POINTS


class TestComputeCorridorHourlyRisks:
    """Verify hourly risk matrix computation (§8g)."""

    def test_hourly_risks_shape_and_values(self):
        now_utc = datetime(2025, 1, 20, 12, 0, 0, tzinfo=UTC)
        grid_points = [(41.88, -87.63), (39.10, -94.58)]
        forecasts = {
            (41.88, -87.63): make_sample_weather(now_utc),
            (39.10, -94.58): make_sample_weather(now_utc),
        }

        results = compute_corridor_hourly_risks(
            grid_points=grid_points,
            departure_datetime_utc=now_utc,
            forecasts=forecasts,
            load_weight_lb=35000,
            num_hours=49,
        )

        assert len(results) == 2
        for pt in results:
            assert "lat" in pt
            assert "lng" in pt
            assert len(pt["hour_risks"]) == 49
            for r in pt["hour_risks"]:
                assert r in [0, 1, 2, 3, 4]  # 0=Low, 1=Moderate, 2=High, 3=Severe, 4=No Travel

        # At h=0 wind is 15 mph -> Low (0)
        assert results[0]["hour_risks"][0] == 0
        # At h=20 wind is 46 mph with load 35,000 lb -> No Travel (4) (load > 30k at 45-54 mph escalates to No Travel)
        assert results[0]["hour_risks"][20] == 4

    def test_missing_weather_defaults_to_low_risk(self):
        now_utc = datetime(2025, 1, 20, 12, 0, 0, tzinfo=UTC)
        grid_points = [(45.0, -90.0)]
        results = compute_corridor_hourly_risks(
            grid_points=grid_points,
            departure_datetime_utc=now_utc,
            forecasts={},  # No forecasts
            load_weight_lb=20000,
            num_hours=49,
        )
        assert len(results) == 1
        assert len(results[0]["hour_risks"]) == 49
        assert all(r == 0 for r in results[0]["hour_risks"])


@pytest.mark.django_db
class TestHeatmapEndpoint:
    """Integration test suite for POST /api/v1/trips/heatmap/."""

    @patch("safehaul.views.OpenMeteoWeatherAdapter.get_forecast_for_locations")
    def test_heatmap_with_existing_trip_id(self, mock_weather, api_client):
        now = timezone.now()
        mock_weather.side_effect = lambda locs: {
            (round(lat, 2), round(lng, 2)): make_sample_weather(now)
            for lat, lng in locs
        }

        trip_id = uuid.uuid4()
        result_json = {
            "routes": [
                {
                    "id": "r1",
                    "geometry": {
                        "coordinates": [
                            [-87.6298, 41.8781],
                            [-90.0000, 40.5000],
                            [-94.5786, 39.0997],
                        ]
                    },
                }
            ]
        }
        TripAnalysis.objects.create(
            id=trip_id,
            origin_lat=41.8781,
            origin_lng=-87.6298,
            origin_label="Chicago, IL",
            destination_lat=39.0997,
            destination_lng=-94.5786,
            destination_label="Kansas City, MO",
            departure_datetime_utc=now,
            load_weight_lb=35000,
            sample_interval_miles=25,
            result_json=result_json,
        )

        url = reverse("safehaul:heatmap")
        payload = {
            "trip_id": str(trip_id),
            "load_weight_lb": 35000,
        }
        response = api_client.post(url, payload, format="json")

        assert response.status_code == 200
        data = response.json()

        assert "grid" in data
        assert "hours" in data
        assert data["hours"] == 49
        assert "departure_datetime_utc" in data
        assert "meta" in data
        assert len(data["grid"]) <= 400
        assert data["meta"]["max_points_cap"] == 400

    @patch("safehaul.views.OpenMeteoWeatherAdapter.get_forecast_for_locations")
    def test_heatmap_with_corridor_geometry(self, mock_weather, api_client):
        now = timezone.now() + timedelta(hours=1)
        mock_weather.return_value = {}

        url = reverse("safehaul:heatmap")
        payload = {
            "corridor_geometry": {
                "routes": [
                    {
                        "type": "LineString",
                        "coordinates": [
                            [-87.62, 41.88],
                            [-94.58, 39.10],
                        ],
                    }
                ]
            },
            "departure_datetime": now.isoformat(),
            "load_weight_lb": 42000,
        }
        response = api_client.post(url, payload, format="json")

        assert response.status_code == 200
        data = response.json()
        assert len(data["grid"]) <= 400
        assert data["hours"] == 49

    def test_heatmap_nonexistent_trip_id_returns_404(self, api_client):
        fake_id = str(uuid.uuid4())
        url = reverse("safehaul:heatmap")
        payload = {"trip_id": fake_id, "load_weight_lb": 30000}
        response = api_client.post(url, payload, format="json")

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "TRIP_NOT_FOUND"

    def test_heatmap_missing_both_trip_and_geometry(self, api_client):
        url = reverse("safehaul:heatmap")
        payload = {"load_weight_lb": 30000}
        response = api_client.post(url, payload, format="json")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_heatmap_empty_geometry_coordinates(self, api_client):
        url = reverse("safehaul:heatmap")
        now = timezone.now() + timedelta(hours=1)
        payload = {
            "corridor_geometry": {"routes": []},
            "departure_datetime": now.isoformat(),
            "load_weight_lb": 30000,
        }
        response = api_client.post(url, payload, format="json")

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "INVALID_CORRIDOR"
