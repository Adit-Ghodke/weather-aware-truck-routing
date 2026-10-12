"""
Unit tests for SafeHaul checkpoint sampling and segment attribution (Phase 4).

Specifications from BUILD_PLAN.md §8a, §8e, §A1, §A12, and §12.
"""

import pytest

from safehaul.domain.constants import MILE_TOLERANCE
from safehaul.domain.sampling import (
    auto_select_interval,
    compute_cumulative_distances,
    compute_segment_miles,
    haversine_distance,
    interpolate_coordinate,
    sample_checkpoints,
)


class TestAutoSelectInterval:
    """Verify automatic interval selection per §A1."""

    @pytest.mark.parametrize("distance, expected", [
        (0.0, 10),
        (50.0, 10),
        (150.0, 10),     # boundary <= 150
        (150.1, 25),    # > 150
        (300.0, 25),
        (600.0, 25),    # boundary <= 600
        (600.1, 50),    # > 600
        (1200.0, 50),
    ])
    def test_auto_interval_thresholds(self, distance, expected):
        assert auto_select_interval(distance) == expected


class TestHaversineAndCumulative:
    """Verify distance calculations and polyline accumulation."""

    def test_haversine_zero_distance_same_point(self):
        coord = [-87.6298, 41.8781]  # Chicago [lng, lat]
        assert haversine_distance(coord, coord) == 0.0

    def test_haversine_known_distance(self):
        # Chicago to Kansas City: roughly ~410 miles direct
        chicago = [-87.6298, 41.8781]
        kc = [-94.5786, 39.0997]
        dist = haversine_distance(chicago, kc)
        assert 390.0 < dist < 430.0

    def test_cumulative_distances_empty_and_single(self):
        assert compute_cumulative_distances([]) == []
        assert compute_cumulative_distances([[-87.6, 41.8]]) == [0.0]

    def test_cumulative_distances_monotonic(self):
        coords = [
            [-87.6, 41.8],
            [-88.0, 41.5],
            [-89.0, 41.0],
            [-90.0, 40.5],
        ]
        cum = compute_cumulative_distances(coords)
        assert len(cum) == len(coords)
        assert cum[0] == 0.0
        for i in range(1, len(cum)):
            assert cum[i] > cum[i - 1]


class TestInterpolateCoordinate:
    """Verify linear interpolation along polylines."""

    def test_interpolate_start_and_end(self):
        coords = [[-90.0, 30.0], [-90.0, 31.0]]  # ~69 miles north
        cum = compute_cumulative_distances(coords)
        total = cum[-1]

        start_lng, start_lat = interpolate_coordinate(coords, cum, 0.0)
        assert start_lng == -90.0
        assert start_lat == 30.0

        end_lng, end_lat = interpolate_coordinate(coords, cum, total)
        assert end_lng == -90.0
        assert end_lat == 31.0

    def test_interpolate_midpoint(self):
        coords = [[-90.0, 30.0], [-90.0, 31.0]]
        cum = compute_cumulative_distances(coords)
        mid_mile = cum[-1] / 2.0

        mid_lng, mid_lat = interpolate_coordinate(coords, cum, mid_mile)
        assert mid_lng == -90.0
        assert abs(mid_lat - 30.5) < 0.001


class TestSampleCheckpoints:
    """Verify checkpoint sampling algorithm §8a."""

    def test_worked_example_from_spec(self):
        """Spec §8a worked example: 130-mile route, 50-mile interval.
        Checkpoints expected at miles 0, 50, 100, 130.
        """
        # Create a straight line of length 130 miles
        # At latitude ~0, 1 degree longitude is ~69.17 miles
        coords = [[0.0, 0.0], [0.0, 130.0 / 69.0]]  # approx 130 miles
        checkpoints = sample_checkpoints(coords, sample_interval_miles=50, total_distance_miles=130.0)

        assert len(checkpoints) == 4
        assert checkpoints[0]["mile_marker"] == 0.0
        assert checkpoints[1]["mile_marker"] == 50.0
        assert checkpoints[2]["mile_marker"] == 100.0
        assert checkpoints[3]["mile_marker"] == 130.0

        # Verify origin and destination are exact
        assert checkpoints[0]["index"] == 0
        assert checkpoints[-1]["index"] == 3

    def test_origin_always_at_mile_zero(self):
        coords = [[-87.6298, 41.8781], [-94.5786, 39.0997]]
        checkpoints = sample_checkpoints(coords, sample_interval_miles=25, total_distance_miles=400.0)
        assert checkpoints[0]["mile_marker"] == 0.0
        assert checkpoints[0]["index"] == 0

    def test_destination_always_at_end(self):
        coords = [[-87.6298, 41.8781], [-94.5786, 39.0997]]
        total_dist = 412.4
        checkpoints = sample_checkpoints(coords, sample_interval_miles=50, total_distance_miles=total_dist)
        assert checkpoints[-1]["mile_marker"] == total_dist

    def test_deduplication_when_last_sample_very_close_to_destination(self):
        """If target_miles sample is within 0.01 miles of destination, deduplicate."""
        # 100.008 mile route sampled at 25 miles:
        # samples at 0, 25, 50, 75, 100.0
        # Remaining distance to dest is 0.008 miles (<= 0.01).
        coords = [[0.0, 0.0], [0.0, 1.5]]
        checkpoints = sample_checkpoints(coords, sample_interval_miles=25, total_distance_miles=100.008)

        # The last checkpoint must be deduplicated and adjusted to 100.01 (destination)
        assert checkpoints[-1]["mile_marker"] == 100.01
        # Total count should be 5 (0, 25, 50, 75, 100.01), not 6
        assert len(checkpoints) == 5

    def test_merge_when_last_interval_shorter_than_10_percent(self):
        """Fix 4: If last interval is shorter than 10% of sample interval, merge so final checkpoint is destination only."""
        coords = [[0.0, 0.0], [0.0, 1.5]]
        # 102-mile route with 25-mile interval: regular samples at 0, 25, 50, 75, 100.
        # Remaining distance is 2.0 miles, which is < 2.5 miles (10% of 25).
        # Must merge so final checkpoint is at 102.0 only (5 checkpoints total: 0, 25, 50, 75, 102.0).
        checkpoints = sample_checkpoints(coords, sample_interval_miles=25, total_distance_miles=102.0)
        assert len(checkpoints) == 5
        assert checkpoints[-1]["mile_marker"] == 102.0
        assert [cp["mile_marker"] for cp in checkpoints] == [0.0, 25.0, 50.0, 75.0, 102.0]


    def test_degenerate_zero_distance_route(self):
        coords = [[-87.6, 41.8]]
        checkpoints = sample_checkpoints(coords, sample_interval_miles=25, total_distance_miles=0.0)
        assert len(checkpoints) == 1
        assert checkpoints[0]["mile_marker"] == 0.0

    def test_empty_coordinates_returns_empty(self):
        assert sample_checkpoints([], 25) == []


class TestComputeSegmentMiles:
    """Verify segment mile attribution per §8e and §A12."""

    def test_worked_example_segment_miles(self):
        """Worked example (§8a & §8e):
        Checkpoints at miles [0, 50, 100, 130].
        Expected segments:
          seg[0] = 50 / 2 = 25
          seg[1] = 50 / 2 + 50 / 2 = 50
          seg[2] = 50 / 2 + 30 / 2 = 40
          seg[3] = 30 / 2 = 15
        Sum = 25 + 50 + 40 + 15 = 130.
        """
        cps = [
            {"mile_marker": 0.0},
            {"mile_marker": 50.0},
            {"mile_marker": 100.0},
            {"mile_marker": 130.0},
        ]
        segs = compute_segment_miles(cps, total_distance_miles=130.0)
        assert segs == [25.0, 50.0, 40.0, 15.0]
        assert abs(sum(segs) - 130.0) < MILE_TOLERANCE

    def test_segment_miles_sum_equals_route_total(self):
        """Test on various irregular intervals that sum equals route total within MILE_TOLERANCE."""
        cps = [
            {"mile_marker": 0.0},
            {"mile_marker": 12.3},
            {"mile_marker": 37.8},
            {"mile_marker": 89.1},
            {"mile_marker": 154.67},
        ]
        total = 154.67
        segs = compute_segment_miles(cps, total_distance_miles=total)
        assert len(segs) == len(cps)
        assert abs(sum(segs) - total) < MILE_TOLERANCE

    def test_single_checkpoint_segment_is_total(self):
        cps = [{"mile_marker": 0.0}]
        segs = compute_segment_miles(cps, total_distance_miles=10.0)
        assert segs == [10.0]

    def test_empty_checkpoints_returns_empty(self):
        assert compute_segment_miles([], total_distance_miles=0.0) == []

    def test_interpolate_coordinate_empty_raises_value_error(self):
        with pytest.raises(ValueError):
            interpolate_coordinate([], [], 10.0)

    def test_interpolate_coordinate_zero_length_segment(self):
        coords = [[-90.0, 30.0], [-90.0, 30.0]]
        cum = [0.0, 0.0]
        lng, lat = interpolate_coordinate(coords, cum, 0.0)
        assert (lng, lat) == (-90.0, 30.0)

    def test_segment_miles_tolerance_exceeded_raises_error(self):
        cps = [{"mile_marker": 0.0}, {"mile_marker": 50.0}]
        # Checkpoints only span 50 miles, but claim total is 100 miles
        with pytest.raises(ValueError):
            compute_segment_miles(cps, total_distance_miles=100.0)

    def test_interpolate_zero_length_subsegment(self):
        coords = [[-90.0, 30.0], [-90.0, 30.0], [-91.0, 31.0]]
        cum = [0.0, 0.0, 10.0]
        # target_mile 0.0 falls in first segment where seg_len == 0.0
        lng, lat = interpolate_coordinate(coords, cum, 0.0)
        assert (lng, lat) == (-90.0, 30.0)

    def test_interpolate_loop_fallback(self):
        coords = [[-90.0, 30.0], [-91.0, 31.0]]
        cum = [0.0, 9.99]
        # target_mile just under total_dist but past seg_end
        lng, lat = interpolate_coordinate(coords, cum, 9.995)
        assert (lng, lat) == (-91.0, 31.0)

