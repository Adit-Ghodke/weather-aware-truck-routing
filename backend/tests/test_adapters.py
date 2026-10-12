"""
Unit tests for SafeHaul Mapbox and Open-Meteo external adapters (Phase 5).

External APIs are mocked via requests_mock.
Tests routing, geocoding, weather forecasts, batching, and caching behaviors.
"""

import re
from datetime import UTC, datetime

import pytest
import requests

from safehaul.adapters.base import (
    GeocodingUnavailableException,
    RoutingUnavailableException,
)
from safehaul.adapters.mapbox import (
    MapboxGeocodingAdapter,
    MapboxRoutingAdapter,
)
from safehaul.adapters.weather import (
    OpenMeteoWeatherAdapter,
)

MAPBOX_URL_PATTERN = re.compile(r"https://api\.mapbox\.com/.*")
OPEN_METEO_URL_PATTERN = re.compile(r"https://api\.open-meteo\.com/.*")


class TestMapboxRoutingAdapter:
    """Verify Mapbox Directions adapter parsing, caching, and error resilience."""

    def test_get_routes_success(self, requests_mock):
        adapter = MapboxRoutingAdapter(access_token="test-token", enable_cache=False)
        mock_response = {
            "routes": [
                {
                    "distance": 160934.4,  # exactly 100 miles (1609.344 m/mi)
                    "duration": 7200.0,    # 120 minutes (2 hours)
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-87.6, 41.8], [-88.5, 41.2]],
                    },
                    "legs": [
                        {
                            "steps": [
                                {"distance": 80467.2, "duration": 3600.0},
                                {"distance": 80467.2, "duration": 3600.0},
                            ]
                        }
                    ],
                }
            ]
        }
        requests_mock.get(
            MAPBOX_URL_PATTERN,
            json=mock_response,
            status_code=200,
        )

        routes = adapter.get_routes(origin=(41.8, -87.6), destination=(41.2, -88.5))
        assert len(routes) == 1
        r = routes[0]
        assert r["id"] == "route-a"
        assert r["label"] == "Route A"
        assert r["distance_miles"] == 100.0
        assert r["duration_minutes"] == 120
        assert len(r["segments"]) == 2
        assert r["segments"][0]["start_mile"] == 0.0
        assert r["segments"][0]["end_mile"] == 50.0

    def test_routing_cache_behavior(self, requests_mock):
        """When enable_cache=True, second call uses cache without network request."""
        adapter = MapboxRoutingAdapter(access_token="test-token", enable_cache=True)
        mock_response = {
            "routes": [
                {
                    "distance": 80467.2,
                    "duration": 3600.0,
                    "geometry": {"type": "LineString", "coordinates": []},
                    "legs": [],
                }
            ]
        }
        mock_req = requests_mock.get(
            MAPBOX_URL_PATTERN,
            json=mock_response,
            status_code=200,
        )

        orig = (41.8, -87.6)
        dest = (41.2, -88.5)

        # Call 1 -> Network hit
        r1 = adapter.get_routes(orig, dest)
        assert mock_req.call_count == 1

        # Call 2 -> Cached hit (network call count remains 1)
        r2 = adapter.get_routes(orig, dest)
        assert mock_req.call_count == 1
        assert r1[0]["distance_miles"] == r2[0]["distance_miles"]

    def test_routing_http_error_raises_exception(self, requests_mock):
        adapter = MapboxRoutingAdapter(access_token="invalid-token", enable_cache=False)
        requests_mock.get(
            MAPBOX_URL_PATTERN,
            text="Unauthorized",
            status_code=401,
        )

        with pytest.raises(RoutingUnavailableException):
            adapter.get_routes(origin=(41.8, -87.6), destination=(41.2, -88.5))

    def test_routing_network_error_raises_exception(self, requests_mock):
        adapter = MapboxRoutingAdapter(access_token="test-token", enable_cache=False)
        requests_mock.get(
            MAPBOX_URL_PATTERN,
            exc=requests.exceptions.ConnectTimeout("Connection timed out"),
        )

        with pytest.raises(RoutingUnavailableException):
            adapter.get_routes(origin=(41.8, -87.6), destination=(41.2, -88.5))


class TestMapboxGeocodingAdapter:
    """Verify Mapbox Geocoding adapter parsing and ephemeral (no-cache) behavior."""

    def test_search_success(self, requests_mock):
        adapter = MapboxGeocodingAdapter(access_token="test-token")
        mock_response = {
            "features": [
                {
                    "place_name": "Chicago, Illinois, United States",
                    "center": [-87.6298, 41.8781],
                },
                {
                    "place_name": "Chicago Heights, Illinois, United States",
                    "center": [-87.6384, 41.5061],
                },
            ]
        }
        requests_mock.get(
            MAPBOX_URL_PATTERN,
            json=mock_response,
            status_code=200,
        )

        results = adapter.search("Chicago", limit=5)
        assert len(results) == 2
        assert results[0]["label"] == "Chicago, Illinois, United States"
        assert results[0]["lat"] == 41.8781
        assert results[0]["lng"] == -87.6298

    def test_search_short_query_returns_empty(self):
        adapter = MapboxGeocodingAdapter(access_token="test-token")
        assert adapter.search("a") == []
        assert adapter.search("   ") == []

    def test_search_http_error_raises_exception(self, requests_mock):
        adapter = MapboxGeocodingAdapter(access_token="test-token")
        requests_mock.get(
            MAPBOX_URL_PATTERN,
            text="Service Unavailable",
            status_code=503,
        )

        with pytest.raises(GeocodingUnavailableException):
            adapter.search("Denver")


class TestOpenMeteoWeatherAdapter:
    """Verify Open-Meteo forecast fetching, unit conversion, and rate limit handling."""

    def test_get_forecast_single_location(self, requests_mock):
        adapter = OpenMeteoWeatherAdapter()
        mock_response = {
            "hourly": {
                "time": ["2025-01-20T14:00", "2025-01-20T15:00"],
                "temperature_2m": [10.0, 15.0],      # Celsius
                "wind_speed_10m": [22.5, 31.0],      # mph
                "wind_gusts_10m": [30.0, 42.0],      # mph
                "rain": [25.4, 0.0],                 # 25.4 mm = 1.00 inch
                "snowfall": [0.0, 5.08],             # 5.08 cm = 2.00 inches
            }
        }
        requests_mock.get(
            OPEN_METEO_URL_PATTERN,
            json=mock_response,
            status_code=200,
        )

        locs = [(41.8781, -87.6298)]
        forecasts = adapter.get_forecast_for_locations(locs)

        coord_key = (41.88, -87.63)
        assert coord_key in forecasts

        loc_data = forecasts[coord_key]
        t1 = datetime(2025, 1, 20, 14, 0, tzinfo=UTC)
        assert t1 in loc_data
        assert loc_data[t1]["wind_mph"] == 22.5
        assert loc_data[t1]["gust_mph"] == 30.0
        assert loc_data[t1]["rain_in_hr"] == 1.00  # 25.4 mm -> 1.00 in
        assert loc_data[t1]["snow_in_hr"] == 0.00
        assert loc_data[t1]["temp_f"] == 50.0      # 10 C -> 50 F

        t2 = datetime(2025, 1, 20, 15, 0, tzinfo=UTC)
        assert loc_data[t2]["rain_in_hr"] == 0.00
        assert loc_data[t2]["snow_in_hr"] == 2.00  # 5.08 cm -> 2.00 in

    def test_forecast_caching_avoids_repeated_calls(self, requests_mock):
        adapter = OpenMeteoWeatherAdapter()
        mock_response = {
            "hourly": {
                "time": ["2025-01-20T12:00"],
                "temperature_2m": [0.0],
                "wind_speed_10m": [10.0],
                "wind_gusts_10m": [15.0],
                "rain": [0.0],
                "snowfall": [0.0],
            }
        }
        mock_req = requests_mock.get(
            OPEN_METEO_URL_PATTERN,
            json=mock_response,
            status_code=200,
        )

        locs = [(39.10, -94.58)]
        res1 = adapter.get_forecast_for_locations(locs)
        assert mock_req.call_count == 1

        # Second call uses resilient cache
        res2 = adapter.get_forecast_for_locations(locs)
        assert mock_req.call_count == 1
        assert res1 == res2

    def test_rate_limit_429_retry_and_success(self, requests_mock):
        """Open-Meteo returns HTTP 429 then 200 on retry."""
        adapter = OpenMeteoWeatherAdapter(max_retries=2)
        requests_mock.get(
            OPEN_METEO_URL_PATTERN,
            [
                {"text": "Rate limited", "status_code": 429},
                {
                    "json": {
                        "hourly": {
                            "time": ["2025-01-20T10:00"],
                            "temperature_2m": [5.0],
                            "wind_speed_10m": [15.0],
                            "wind_gusts_10m": [20.0],
                            "rain": [0.0],
                            "snowfall": [0.0],
                        }
                    },
                    "status_code": 200,
                },
            ],
        )

        locs = [(35.0, -100.0)]
        forecasts = adapter.get_forecast_for_locations(locs)
        assert (35.0, -100.0) in forecasts

    def test_forecast_network_failure_returns_empty_gracefully(self, requests_mock):
        adapter = OpenMeteoWeatherAdapter(max_retries=1)
        requests_mock.get(
            OPEN_METEO_URL_PATTERN,
            exc=requests.exceptions.ConnectTimeout("Timeout"),
        )

        locs = [(50.0, -110.0)]
        # Should gracefully return empty without crashing caller
        forecasts = adapter.get_forecast_for_locations(locs)
        assert forecasts == {}

    def test_forecast_empty_locations_returns_empty(self):
        adapter = OpenMeteoWeatherAdapter()
        assert adapter.get_forecast_for_locations([]) == {}

    def test_forecast_multi_location_list_response(self, requests_mock):
        adapter = OpenMeteoWeatherAdapter()
        mock_response = [
            {
                "hourly": {
                    "time": ["2025-01-20T10:00"],
                    "temperature_2m": [5.0],
                    "wind_speed_10m": [15.0],
                    "wind_gusts_10m": [20.0],
                    "rain": [0.0],
                    "snowfall": [0.0],
                }
            },
            {
                "hourly": {
                    "time": ["2025-01-20T10:00"],
                    "temperature_2m": [8.0],
                    "wind_speed_10m": [12.0],
                    "wind_gusts_10m": [18.0],
                    "rain": [1.0],
                    "snowfall": [0.0],
                }
            },
        ]
        requests_mock.get(OPEN_METEO_URL_PATTERN, json=mock_response, status_code=200)
        res = adapter.get_forecast_for_locations([(35.0, -100.0), (36.0, -101.0)])
        assert len(res) == 2
        assert (35.0, -100.0) in res
        assert (36.0, -101.0) in res

    def test_forecast_malformed_time_skipped(self, requests_mock):
        from django.core.cache import cache
        cache.clear()
        adapter = OpenMeteoWeatherAdapter()
        mock_response = {
            "hourly": {
                "time": ["invalid-date-string"],
                "temperature_2m": [5.0],
                "wind_speed_10m": [15.0],
                "wind_gusts_10m": [20.0],
                "rain": [0.0],
                "snowfall": [0.0],
            }
        }
        requests_mock.get(OPEN_METEO_URL_PATTERN, json=mock_response, status_code=200)
        res = adapter.get_forecast_for_locations([(49.0, -120.0)])
        assert (49.0, -120.0) in res
        assert res[(49.0, -120.0)] == {}  # parsed dict is empty due to invalid date


