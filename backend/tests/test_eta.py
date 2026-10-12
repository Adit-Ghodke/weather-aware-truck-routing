"""
Unit tests for SafeHaul ETA calculation and weather interpolation (Phase 4).

Specifications from BUILD_PLAN.md §8b, §8c, §A2, §A3, §A4, and §12.
"""

from datetime import UTC, datetime, timedelta, timezone

from safehaul.domain.eta import (
    compute_checkpoint_eta,
    compute_checkpoint_etas,
    get_precip_at_eta,
    interpolate_gust_at_eta,
    interpolate_wind_at_eta,
)


class TestComputeCheckpointETA:
    """Verify ETA calculation under per-segment and proportional fallback modes."""

    def test_eta_at_mile_zero_equals_departure_time(self):
        dep = datetime(2025, 1, 20, 14, 0, 0, tzinfo=UTC)
        eta, method = compute_checkpoint_eta(
            departure_datetime_utc=dep,
            checkpoint_mile_marker=0.0,
            total_distance_miles=100.0,
            total_duration_seconds=3600.0,
        )
        assert eta == dep
        assert method == "exact"

    def test_eta_at_end_equals_departure_plus_total_duration(self):
        dep = datetime(2025, 1, 20, 14, 0, 0, tzinfo=UTC)
        total_dist = 100.0
        total_dur = 7200.0  # 2 hours
        eta, method = compute_checkpoint_eta(
            departure_datetime_utc=dep,
            checkpoint_mile_marker=total_dist,
            total_distance_miles=total_dist,
            total_duration_seconds=total_dur,
        )
        assert eta == dep + timedelta(seconds=7200)
        assert method == "approximate"

    def test_per_segment_worked_example(self):
        """Worked example (§8b):
        Departure: 14:00:00 UTC
        Checkpoint at mile 50; segment 0-50 mi: 3600s
        Expected ETA = 15:00:00 UTC.
        """
        dep = datetime(2025, 1, 20, 14, 0, 0, tzinfo=UTC)
        segments = [
            {"start_mile": 0.0, "end_mile": 50.0, "duration_seconds": 3600.0},
            {"start_mile": 50.0, "end_mile": 100.0, "duration_seconds": 4000.0},
        ]
        eta, method = compute_checkpoint_eta(
            departure_datetime_utc=dep,
            checkpoint_mile_marker=50.0,
            route_segments=segments,
        )
        assert eta == datetime(2025, 1, 20, 15, 0, 0, tzinfo=UTC)
        assert method == "per_segment"

    def test_per_segment_interpolation_within_segment(self):
        """Checkpoint halfway through a segment gets halfway duration."""
        dep = datetime(2025, 1, 20, 14, 0, 0, tzinfo=UTC)
        segments = [
            {"start_mile": 0.0, "end_mile": 50.0, "duration_seconds": 3600.0},
        ]
        # Checkpoint at mile 25.0 -> halfway -> 1800s
        eta, method = compute_checkpoint_eta(
            departure_datetime_utc=dep,
            checkpoint_mile_marker=25.0,
            route_segments=segments,
        )
        assert eta == dep + timedelta(seconds=1800)
        assert method == "per_segment"

    def test_proportional_fallback_uniform_speed(self):
        """When segments are missing, proportional fallback calculates time = dur * (dist / total)."""
        dep = datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC)
        total_dist = 200.0
        total_dur = 7200.0  # 2 hours
        # At mile 50 (quarter distance) -> quarter time (1800s = 30 min)
        eta, method = compute_checkpoint_eta(
            departure_datetime_utc=dep,
            checkpoint_mile_marker=50.0,
            route_segments=None,
            total_distance_miles=total_dist,
            total_duration_seconds=total_dur,
        )
        assert eta == datetime(2025, 1, 20, 10, 30, 0, tzinfo=UTC)
        assert method == "approximate"

    def test_timezone_departure_offset_conversion(self):
        """A departure in CST (-06:00) represents the identical instant in UTC."""
        cst_offset = timezone(timedelta(hours=-6))
        dep_cst = datetime(2025, 1, 20, 8, 0, 0, tzinfo=cst_offset)
        dep_utc = dep_cst.astimezone(UTC)

        # 08:00 -06:00 is 14:00 UTC
        assert dep_utc.hour == 14

        eta, _ = compute_checkpoint_eta(
            departure_datetime_utc=dep_utc,
            checkpoint_mile_marker=0.0,
        )
        assert eta == datetime(2025, 1, 20, 14, 0, 0, tzinfo=UTC)

    def test_batch_checkpoint_etas_attachment(self):
        dep = datetime(2025, 1, 20, 12, 0, 0, tzinfo=UTC)
        cps = [
            {"mile_marker": 0.0},
            {"mile_marker": 50.0},
            {"mile_marker": 100.0},
        ]
        result = compute_checkpoint_etas(
            checkpoints=cps,
            departure_datetime_utc=dep,
            total_distance_miles=100.0,
            total_duration_seconds=3600.0,
        )
        assert len(result) == 3
        assert result[0]["eta_utc"] == dep
        assert result[1]["eta_utc"] == dep + timedelta(seconds=1800)
        assert result[2]["eta_utc"] == dep + timedelta(seconds=3600)


class TestWeatherLookupAtETA:
    """Verify linear interpolation of wind/gust and slot lookup of precipitation (§8c)."""

    def test_wind_linear_interpolation_halfway(self):
        h1 = datetime(2025, 1, 20, 14, 0, 0, tzinfo=UTC)
        h2 = datetime(2025, 1, 20, 15, 0, 0, tzinfo=UTC)
        weather = {
            h1: {"wind_mph": 20.0},
            h2: {"wind_mph": 30.0},
        }
        # At 14:30 (halfway), wind should be 25.0
        eta = datetime(2025, 1, 20, 14, 30, 0, tzinfo=UTC)
        interpolated = interpolate_wind_at_eta(weather, eta)
        assert interpolated == 25.0

    def test_wind_linear_interpolation_quarter(self):
        h1 = datetime(2025, 1, 20, 14, 0, 0, tzinfo=UTC)
        h2 = datetime(2025, 1, 20, 15, 0, 0, tzinfo=UTC)
        weather = {
            h1: {"wind_mph": 10.0},
            h2: {"wind_mph": 20.0},
        }
        # At 14:15 (1/4 hour), wind should be 12.5
        eta = datetime(2025, 1, 20, 14, 15, 0, tzinfo=UTC)
        assert interpolate_wind_at_eta(weather, eta) == 12.5

    def test_gust_interpolation(self):
        h1 = datetime(2025, 1, 20, 14, 0, 0, tzinfo=UTC)
        h2 = datetime(2025, 1, 20, 15, 0, 0, tzinfo=UTC)
        weather = {
            h1: {"gust_mph": 25.0},
            h2: {"gust_mph": 45.0},
        }
        eta = datetime(2025, 1, 20, 14, 30, 0, tzinfo=UTC)
        assert interpolate_gust_at_eta(weather, eta) == 35.0

    def test_precipitation_slot_lookup(self):
        """Precipitation rates are hourly totals for the preceding hour: slot h+1 covers [h, h+1)."""
        h1 = datetime(2025, 1, 20, 14, 0, 0, tzinfo=UTC)
        h2 = datetime(2025, 1, 20, 15, 0, 0, tzinfo=UTC)
        h3 = datetime(2025, 1, 20, 16, 0, 0, tzinfo=UTC)
        weather = {
            h1: {"rain_in_hr": 0.45, "snow_in_hr": 0.0},
            h2: {"rain_in_hr": 0.10, "snow_in_hr": 1.5},
            h3: {"rain_in_hr": 0.25, "snow_in_hr": 0.5},
        }
        # ETA at 14:45 uses slot 15:00 (accumulation during 14:00-15:00)
        eta1 = datetime(2025, 1, 20, 14, 45, 0, tzinfo=UTC)
        rain, snow = get_precip_at_eta(weather, eta1)
        assert rain == 0.10
        assert snow == 1.5

        # ETA at 15:05 uses slot 16:00 (accumulation during 15:00-16:00)
        eta2 = datetime(2025, 1, 20, 15, 5, 0, tzinfo=UTC)
        rain2, snow2 = get_precip_at_eta(weather, eta2)
        assert rain2 == 0.25
        assert snow2 == 0.5

    def test_open_meteo_preceding_hour_slot_exact_spec(self):
        """Fix 1 requirement:
        slot 07:00 = 0 mm, slot 08:00 = 7.62 mm, ETA 07:51 must give 0.30 in/hr.
        """
        slot_0700 = datetime(2026, 10, 12, 7, 0, 0, tzinfo=UTC)
        slot_0800 = datetime(2026, 10, 12, 8, 0, 0, tzinfo=UTC)
        weather = {
            slot_0700: {"rain_in_hr": round(0.0 / 25.4, 2), "snow_in_hr": 0.0},
            slot_0800: {"rain_in_hr": round(7.62 / 25.4, 2), "snow_in_hr": 0.0},
        }
        eta = datetime(2026, 10, 12, 7, 51, 0, tzinfo=UTC)
        rain, snow = get_precip_at_eta(weather, eta)
        assert rain == 0.30
        assert snow == 0.0


    def test_wind_and_gust_fallback_single_hour(self):
        h1 = datetime(2025, 1, 20, 14, 0, 0, tzinfo=UTC)
        weather = {h1: {"wind_mph": 18.0, "gust_mph": 28.0}}
        eta = datetime(2025, 1, 20, 14, 30, 0, tzinfo=UTC)
        assert interpolate_wind_at_eta(weather, eta) == 18.0
        assert interpolate_gust_at_eta(weather, eta) == 28.0

    def test_wind_and_gust_empty_weather_fallback(self):
        eta = datetime(2025, 1, 20, 14, 30, 0, tzinfo=UTC)
        assert interpolate_wind_at_eta({}, eta) == 0.0
        assert interpolate_gust_at_eta({}, eta) == 0.0

    def test_precip_missing_slot_fallback(self):
        eta = datetime(2025, 1, 20, 14, 30, 0, tzinfo=UTC)
        assert get_precip_at_eta({}, eta) == (0.0, 0.0)

    def test_zero_length_segment_within_route_segments(self):
        dep = datetime(2025, 1, 20, 14, 0, 0, tzinfo=UTC)
        segments = [{"start_mile": 10.0, "end_mile": 10.0, "duration_seconds": 0.0}]
        eta, method = compute_checkpoint_eta(dep, 10.0, route_segments=segments)
        assert eta == dep
        assert method == "per_segment"

    def test_missing_distance_duration_degenerate_fallback(self):
        dep = datetime(2025, 1, 20, 14, 0, 0, tzinfo=UTC)
        eta, method = compute_checkpoint_eta(dep, 50.0, route_segments=None, total_distance_miles=None)
        assert eta == dep
        assert method == "approximate"
