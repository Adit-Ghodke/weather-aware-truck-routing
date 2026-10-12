"""
Unit tests for route corridor geometry validation: spur detection, overlap calculation, and candidate selection (§Fix 2).
"""

import pytest

from safehaul.domain.route_geometry import (
    compute_geometry_overlap_percent,
    detect_out_and_back_spur,
    evaluate_candidate_corridors,
)


@pytest.fixture
def clean_route_coordinates():
    """A clean direct highway corridor with no out-and-back spurs."""
    return [
        [-87.6298, 41.8781],
        [-88.0000, 41.7000],
        [-88.5000, 41.5000],
        [-89.2000, 41.3000],
        [-90.0000, 41.1000],
        [-91.0000, 40.8000],
        [-92.0000, 40.4000],
        [-93.0000, 39.8000],
        [-94.0000, 39.3000],
        [-94.5786, 39.0997],
    ]


@pytest.fixture
def route_with_spur_fixture():
    """A route fixture containing an out-and-back spur.

    The path travels along a main road, detours 1 km down a side road, makes a U-turn,
    and returns within ~30 m of the same side road heading in the opposite direction.
    """
    coords = [
        # Main highway approach
        [-91.0000, 40.0000],
        [-91.0100, 40.0100],
        [-91.0200, 40.0200],
        # Detour onto side road (traveling north-east)
        [-91.0250, 40.0280],
        [-91.0300, 40.0350],
        [-91.0350, 40.0420],
        # U-turn at end of spur
        [-91.0352, 40.0422],
        [-91.0350, 40.0423],
        # Returning along the same side road in reverse (heading south-west, within 20m)
        [-91.0351, 40.0420],
        [-91.0301, 40.0350],
        [-91.0251, 40.0280],
        # Re-joining main highway and continuing
        [-91.0300, 40.0200],
        [-91.0400, 40.0100],
        [-91.0500, 40.0000],
    ]
    return coords


class TestSpurDetection:
    """Verify that out-and-back spurs are reliably detected and clean routes pass."""

    def test_clean_route_has_no_spur(self, clean_route_coordinates):
        assert detect_out_and_back_spur(clean_route_coordinates) is False

    def test_fixture_with_spur_is_detected(self, route_with_spur_fixture):
        assert detect_out_and_back_spur(route_with_spur_fixture) is True

    def test_short_polyline_returns_false(self):
        assert detect_out_and_back_spur([[-90.0, 40.0], [-90.1, 40.1]]) is False


class TestGeometryOverlap:
    """Verify calculation of geometry overlap percentages."""

    def test_identical_routes_have_100_percent_overlap(self, clean_route_coordinates):
        ov = compute_geometry_overlap_percent(clean_route_coordinates, clean_route_coordinates)
        assert ov == 100.0

    def test_disjoint_routes_have_low_overlap(self, clean_route_coordinates):
        # Northern vs southern parallel corridors separated by ~2 degrees latitude (~140 miles)
        southern = [[p[0], p[1] - 2.0] for p in clean_route_coordinates]
        ov = compute_geometry_overlap_percent(clean_route_coordinates, southern)
        assert ov < 5.0


class TestCandidateCorridorEvaluation:
    """Verify filtering and selection of candidate routes (§Fix 2)."""

    def test_rejects_candidate_with_spur(self, clean_route_coordinates, route_with_spur_fixture):
        existing = [{"id": "r1", "distance_miles": 500.0, "geometry": {"coordinates": clean_route_coordinates}}]
        candidates = [
            {
                "id": "cand-spur",
                "distance_miles": 520.0,
                "duration_minutes": 500,
                "geometry": {"coordinates": route_with_spur_fixture},
            }
        ]
        best, records = evaluate_candidate_corridors(candidates, existing)
        assert best is None
        assert records[0]["has_spur"] is True
        assert records[0]["is_valid"] is False

    def test_rejects_candidate_with_over_80_percent_overlap(self, clean_route_coordinates):
        existing = [{"id": "r1", "distance_miles": 500.0, "geometry": {"coordinates": clean_route_coordinates}}]
        # Candidate sharing 90% of the same coordinates
        candidates = [
            {
                "id": "cand-overlapping",
                "distance_miles": 505.0,
                "duration_minutes": 510,
                "geometry": {"coordinates": clean_route_coordinates},
            }
        ]
        best, records = evaluate_candidate_corridors(candidates, existing, max_overlap_percent=80.0)
        assert best is None
        assert records[0]["max_overlap"] == 100.0
        assert records[0]["is_valid"] is False

    def test_rejects_candidate_exceeding_40_percent_length(self, clean_route_coordinates):
        existing = [{"id": "r1", "distance_miles": 500.0, "geometry": {"coordinates": clean_route_coordinates}}]
        # 500 * 1.40 = 700.0 miles max allowed
        candidates = [
            {
                "id": "cand-too-long",
                "distance_miles": 750.0,
                "duration_minutes": 800,
                "geometry": {"coordinates": [[-90.0, 35.0], [-94.0, 35.0]]},
            }
        ]
        best, records = evaluate_candidate_corridors(candidates, existing, max_length_ratio=1.40)
        assert best is None
        assert records[0]["is_too_long"] is True

    def test_selects_surviving_candidate_with_least_overlap(self, clean_route_coordinates):
        existing = [{"id": "r1", "distance_miles": 500.0, "geometry": {"coordinates": clean_route_coordinates}}]

        # Two valid candidates:
        # Candidate A: 50% overlap
        # Candidate B: 25% overlap
        cand_a_coords = [*clean_route_coordinates[:5], [-92.0, 38.0], [-93.0, 38.0], [-94.0, 38.0]]
        cand_b_coords = [[p[0], p[1] - 1.0] for p in clean_route_coordinates]  # parallel corridor

        candidates = [
            {
                "id": "cand-a",
                "distance_miles": 530.0,
                "duration_minutes": 520,
                "geometry": {"coordinates": cand_a_coords},
            },
            {
                "id": "cand-b",
                "distance_miles": 540.0,
                "duration_minutes": 515,
                "geometry": {"coordinates": cand_b_coords},
            },
        ]

        best, _records = evaluate_candidate_corridors(candidates, existing)
        assert best is not None
        assert best["id"] == "cand-b"  # least overlap wins
