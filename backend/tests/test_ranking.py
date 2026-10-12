"""
Unit tests for SafeHaul route aggregation metrics and ranking (Phase 4).

Specifications from BUILD_PLAN.md §8e, §8f, and §12.
"""


from safehaul.domain.ranking import (
    compute_route_metrics,
    rank_routes,
)


class TestComputeRouteMetrics:
    """Verify route metrics aggregation from checkpoints (§8e)."""

    def test_single_level_route(self):
        checkpoints = [
            {"level": "Low", "segment_miles": 50.0},
            {"level": "Low", "segment_miles": 50.0},
        ]
        metrics = compute_route_metrics(checkpoints, total_distance_miles=100.0)
        assert metrics["low_miles"] == 100.0
        assert metrics["severe_miles"] == 0.0
        assert metrics["average_risk"] == 1.0
        assert metrics["worst_level"] == "Low"

    def test_mixed_levels_route(self):
        checkpoints = [
            {"level": "Low", "segment_miles": 20.0},
            {"level": "Moderate", "segment_miles": 30.0},
            {"level": "High", "segment_miles": 40.0},
            {"level": "Severe", "segment_miles": 10.0},
        ]
        # Sum = 100 miles
        # Weighted sum = 1*20 + 2*30 + 3*40 + 4*10 = 20 + 60 + 120 + 40 = 240
        # Average risk = 240 / 100 = 2.40
        metrics = compute_route_metrics(checkpoints, total_distance_miles=100.0)
        assert metrics["low_miles"] == 20.0
        assert metrics["moderate_miles"] == 30.0
        assert metrics["high_miles"] == 40.0
        assert metrics["severe_miles"] == 10.0
        assert metrics["no_travel_miles"] == 0.0
        assert metrics["average_risk"] == 2.40
        assert metrics["worst_level"] == "Severe"


class TestRankRoutes:
    """Verify lexicographic ranking and recommendation rules (§8f)."""

    def test_fewer_severe_miles_wins(self):
        """Rule 3a: Route with fewer severe miles ranks higher."""
        r1 = {
            "id": "route-a", "label": "Route A", "duration_minutes": 500,
            "metrics": {
                "severe_miles": 0.0, "high_miles": 20.0, "moderate_miles": 50.0,
                "low_miles": 100.0, "no_travel_miles": 0.0, "average_risk": 1.4,
                "worst_level": "High",
            },
        }
        r2 = {
            "id": "route-b", "label": "Route B", "duration_minutes": 450,  # faster but has severe miles
            "metrics": {
                "severe_miles": 5.0, "high_miles": 10.0, "moderate_miles": 50.0,
                "low_miles": 100.0, "no_travel_miles": 0.0, "average_risk": 1.5,
                "worst_level": "Severe",
            },
        }
        rec = rank_routes([r2, r1])
        assert rec["recommended_route_id"] == "route-a"
        assert rec["comparison"][0]["route_id"] == "route-a"
        assert rec["comparison"][1]["route_id"] == "route-b"
        assert "Severe miles" in rec["explanation"]

    def test_fewer_high_miles_breaks_severe_tie(self):
        """Rule 3b: When severe miles are equal, fewer high miles wins."""
        r1 = {
            "id": "route-a", "label": "Route A", "duration_minutes": 400,
            "metrics": {
                "severe_miles": 0.0, "high_miles": 15.0, "moderate_miles": 50.0,
                "low_miles": 100.0, "no_travel_miles": 0.0, "average_risk": 1.5,
                "worst_level": "High",
            },
        }
        r2 = {
            "id": "route-b", "label": "Route B", "duration_minutes": 380,
            "metrics": {
                "severe_miles": 0.0, "high_miles": 25.0, "moderate_miles": 50.0,
                "low_miles": 100.0, "no_travel_miles": 0.0, "average_risk": 1.6,
                "worst_level": "High",
            },
        }
        rec = rank_routes([r2, r1])
        assert rec["recommended_route_id"] == "route-a"
        assert "High miles" in rec["explanation"]

    def test_average_risk_breaks_high_miles_tie(self):
        """Rule 3c: When severe and high miles are equal, lower average risk wins."""
        r1 = {
            "id": "route-a", "label": "Route A", "duration_minutes": 450,
            "metrics": {
                "severe_miles": 0.0, "high_miles": 10.0, "moderate_miles": 20.0,
                "low_miles": 100.0, "no_travel_miles": 0.0, "average_risk": 1.25,
                "_average_risk_sort": 1.251, "worst_level": "High",
            },
        }
        r2 = {
            "id": "route-b", "label": "Route B", "duration_minutes": 400,
            "metrics": {
                "severe_miles": 0.0, "high_miles": 10.0, "moderate_miles": 50.0,
                "low_miles": 70.0, "no_travel_miles": 0.0, "average_risk": 1.45,
                "_average_risk_sort": 1.450, "worst_level": "High",
            },
        }
        rec = rank_routes([r2, r1])
        assert rec["recommended_route_id"] == "route-a"
        assert "average risk" in rec["explanation"]

    def test_duration_breaks_average_risk_tie(self):
        """Rule 3d: When all risk metrics tie, shorter duration wins."""
        r1 = {
            "id": "route-fast", "label": "Fast Route", "duration_minutes": 300,
            "metrics": {
                "severe_miles": 0.0, "high_miles": 10.0, "moderate_miles": 20.0,
                "low_miles": 70.0, "no_travel_miles": 0.0, "average_risk": 1.30,
                "_average_risk_sort": 1.300, "worst_level": "High",
            },
        }
        r2 = {
            "id": "route-slow", "label": "Slow Route", "duration_minutes": 350,
            "metrics": {
                "severe_miles": 0.0, "high_miles": 10.0, "moderate_miles": 20.0,
                "low_miles": 70.0, "no_travel_miles": 0.0, "average_risk": 1.30,
                "_average_risk_sort": 1.300, "worst_level": "High",
            },
        }
        rec = rank_routes([r2, r1])
        assert rec["recommended_route_id"] == "route-fast"
        assert "fastest by 50 minutes" in rec["explanation"]

    def test_no_travel_routes_ranked_below_all_ok_routes(self):
        """Rule 1 & 3: A route with any No Travel miles ranks below any OK route."""
        r_ok = {
            "id": "route-ok", "label": "OK Route", "duration_minutes": 600,
            "metrics": {
                "severe_miles": 50.0, "high_miles": 20.0, "moderate_miles": 10.0,
                "low_miles": 0.0, "no_travel_miles": 0.0, "average_risk": 3.6,
                "worst_level": "Severe",
            },
        }
        r_notravel = {
            "id": "route-blizzard", "label": "Blizzard Route", "duration_minutes": 200,
            "metrics": {
                "severe_miles": 0.0, "high_miles": 0.0, "moderate_miles": 0.0,
                "low_miles": 100.0, "no_travel_miles": 2.0, "average_risk": 1.8,
                "worst_level": "No Travel",
            },
        }
        rec = rank_routes([r_notravel, r_ok])
        assert rec["recommended_route_id"] == "route-ok"
        assert rec["comparison"][0]["route_id"] == "route-ok"
        assert rec["comparison"][0]["status"] == "ok"
        assert rec["comparison"][1]["route_id"] == "route-blizzard"
        assert rec["comparison"][1]["status"] == "no_travel"

    def test_all_no_travel_routes_scenario(self):
        """Rule 2: When ALL routes are No Travel:
        - status = 'not_recommended_all_routes'
        - warning present
        - ranked by fewest no_travel_miles ASC
        """
        r1 = {
            "id": "route-a", "label": "Route A", "duration_minutes": 400,
            "metrics": {
                "severe_miles": 10.0, "high_miles": 10.0, "moderate_miles": 10.0,
                "low_miles": 50.0, "no_travel_miles": 15.0, "average_risk": 3.8,
                "worst_level": "No Travel",
            },
        }
        r2 = {
            "id": "route-b", "label": "Route B", "duration_minutes": 420,
            "metrics": {
                "severe_miles": 10.0, "high_miles": 10.0, "moderate_miles": 10.0,
                "low_miles": 50.0, "no_travel_miles": 5.0,  # fewest No Travel miles
                "average_risk": 3.2, "worst_level": "No Travel",
            },
        }
        rec = rank_routes([r1, r2])
        assert rec["status"] == "not_recommended_all_routes"
        assert rec["warning"] == "Do not travel at this departure time"
        assert rec["recommended_route_id"] == "route-b"
        assert rec["comparison"][0]["route_id"] == "route-b"
        assert "fewest No Travel miles" in rec["explanation"]

    def test_empty_routes_handling(self):
        rec = rank_routes([])
        assert rec["recommended_route_id"] is None
        assert rec["status"] == "no_routes"

    def test_single_route_recommendation(self):
        r1 = {
            "id": "route-only", "label": "Only Route", "duration_minutes": 180,
            "metrics": {
                "severe_miles": 0.0, "high_miles": 0.0, "moderate_miles": 10.0,
                "low_miles": 50.0, "no_travel_miles": 0.0, "average_risk": 1.17,
                "worst_level": "Moderate",
            },
        }
        rec = rank_routes([r1])
        assert rec["recommended_route_id"] == "route-only"
        assert "safest available route" in rec["explanation"]

    def test_metrics_zero_distance_handling(self):
        metrics = compute_route_metrics([{"level": "Low", "segment_miles": 0.0}], total_distance_miles=0.0)
        assert metrics["average_risk"] == 0.0

    def test_severe_miles_advantage_and_faster(self):
        r1 = {
            "id": "r1", "label": "Route 1", "duration_minutes": 100,
            "metrics": {"severe_miles": 0.0, "high_miles": 0.0, "moderate_miles": 0.0, "low_miles": 100.0, "no_travel_miles": 0.0, "average_risk": 1.0, "worst_level": "Low"},
        }
        r2 = {
            "id": "r2", "label": "Route 2", "duration_minutes": 150,
            "metrics": {"severe_miles": 10.0, "high_miles": 0.0, "moderate_miles": 0.0, "low_miles": 90.0, "no_travel_miles": 0.0, "average_risk": 1.3, "worst_level": "Severe"},
        }
        rec = rank_routes([r1, r2])
        assert "minutes faster" in rec["explanation"]

    def test_high_miles_advantage_and_faster(self):
        r1 = {
            "id": "r1", "label": "Route 1", "duration_minutes": 100,
            "metrics": {"severe_miles": 0.0, "high_miles": 5.0, "moderate_miles": 0.0, "low_miles": 95.0, "no_travel_miles": 0.0, "average_risk": 1.1, "worst_level": "High"},
        }
        r2 = {
            "id": "r2", "label": "Route 2", "duration_minutes": 130,
            "metrics": {"severe_miles": 0.0, "high_miles": 15.0, "moderate_miles": 0.0, "low_miles": 85.0, "no_travel_miles": 0.0, "average_risk": 1.3, "worst_level": "High"},
        }
        rec = rank_routes([r1, r2])
        assert "minutes faster" in rec["explanation"]

    def test_avg_risk_advantage_and_faster(self):
        r1 = {
            "id": "r1", "label": "Route 1", "duration_minutes": 100,
            "metrics": {"severe_miles": 0.0, "high_miles": 5.0, "moderate_miles": 5.0, "low_miles": 90.0, "no_travel_miles": 0.0, "average_risk": 1.15, "_average_risk_sort": 1.15, "worst_level": "High"},
        }
        r2 = {
            "id": "r2", "label": "Route 2", "duration_minutes": 120,
            "metrics": {"severe_miles": 0.0, "high_miles": 5.0, "moderate_miles": 10.0, "low_miles": 85.0, "no_travel_miles": 0.0, "average_risk": 1.25, "_average_risk_sort": 1.25, "worst_level": "High"},
        }
        rec = rank_routes([r1, r2])
        assert "minutes faster" in rec["explanation"]

    def test_compute_metrics_with_no_travel_checkpoints(self):
        checkpoints = [
            {"level": "Low", "segment_miles": 40.0},
            {"level": "No Travel", "segment_miles": 60.0},
        ]
        metrics = compute_route_metrics(checkpoints, total_distance_miles=100.0)
        assert metrics["low_miles"] == 40.0
        assert metrics["no_travel_miles"] == 60.0
        assert metrics["worst_level"] == "No Travel"

    def test_explanation_identical_duration_ties(self):
        # 1. severe miles differs, duration exactly equal
        r1 = {
            "id": "r1", "label": "Route 1", "duration_minutes": 500,
            "metrics": {"severe_miles": 0.0, "high_miles": 10.0, "moderate_miles": 10.0, "low_miles": 80.0, "no_travel_miles": 0.0, "average_risk": 1.2, "worst_level": "High"}
        }
        r2 = {
            "id": "r2", "label": "Route 2", "duration_minutes": 500,
            "metrics": {"severe_miles": 5.0, "high_miles": 10.0, "moderate_miles": 10.0, "low_miles": 75.0, "no_travel_miles": 0.0, "average_risk": 1.5, "worst_level": "Severe"}
        }
        rec = rank_routes([r1, r2])
        assert rec["explanation"] == "Deciding Rule: Fewest Severe Weather Miles. Route 1 has 0.0 Severe miles vs 5.0 on Route 2."

        # 2. high miles differs, duration exactly equal
        r2["metrics"]["severe_miles"] = 0.0
        r2["metrics"]["high_miles"] = 20.0
        rec = rank_routes([r1, r2])
        assert rec["explanation"] == "Deciding Rule: Fewest High Weather Miles. Route 1 has 10.0 High miles vs 20.0 on Route 2."

        # 3. average risk differs, duration exactly equal
        r2["metrics"]["high_miles"] = 10.0
        r2["metrics"]["average_risk"] = 1.4
        rec = rank_routes([r1, r2])
        assert "Deciding Rule: Lowest Average Weather Risk." in rec["explanation"]

    def test_deciding_rule_fewest_severe_miles(self):
        r1 = {
            "id": "r1", "label": "Route 1", "duration_minutes": 200, "duration_seconds": 12000,
            "metrics": {"severe_miles": 0.0, "high_miles": 10.0, "moderate_miles": 10.0, "low_miles": 80.0, "no_travel_miles": 0.0, "average_risk": 1.5, "worst_level": "High"}
        }
        r2 = {
            "id": "r2", "label": "Route 2", "duration_minutes": 180, "duration_seconds": 10800,
            "metrics": {"severe_miles": 5.0, "high_miles": 5.0, "moderate_miles": 10.0, "low_miles": 80.0, "no_travel_miles": 0.0, "average_risk": 1.4, "worst_level": "Severe"}
        }
        rec = rank_routes([r1, r2])
        assert rec["recommended_route_id"] == "r1"
        assert "Deciding Rule: Fewest Severe Weather Miles." in rec["explanation"]
        assert "Route 1 has 0.0 Severe miles vs 5.0 on Route 2" in rec["explanation"]

    def test_deciding_rule_fewest_high_miles(self):
        r1 = {
            "id": "r1", "label": "Route 1", "duration_minutes": 200, "duration_seconds": 12000,
            "metrics": {"severe_miles": 0.0, "high_miles": 5.0, "moderate_miles": 10.0, "low_miles": 85.0, "no_travel_miles": 0.0, "average_risk": 1.4, "worst_level": "High"}
        }
        r2 = {
            "id": "r2", "label": "Route 2", "duration_minutes": 180, "duration_seconds": 10800,
            "metrics": {"severe_miles": 0.0, "high_miles": 15.0, "moderate_miles": 5.0, "low_miles": 80.0, "no_travel_miles": 0.0, "average_risk": 1.3, "worst_level": "High"}
        }
        rec = rank_routes([r1, r2])
        assert rec["recommended_route_id"] == "r1"
        assert "Deciding Rule: Fewest High Weather Miles." in rec["explanation"]
        assert "Route 1 has 5.0 High miles vs 15.0 on Route 2" in rec["explanation"]

    def test_deciding_rule_lowest_average_risk(self):
        r1 = {
            "id": "r1", "label": "Route 1", "duration_minutes": 200, "duration_seconds": 12000,
            "metrics": {"severe_miles": 0.0, "high_miles": 0.0, "moderate_miles": 10.0, "low_miles": 90.0, "no_travel_miles": 0.0, "average_risk": 1.10, "worst_level": "Moderate"}
        }
        r2 = {
            "id": "r2", "label": "Route 2", "duration_minutes": 190, "duration_seconds": 11400,
            "metrics": {"severe_miles": 0.0, "high_miles": 0.0, "moderate_miles": 30.0, "low_miles": 70.0, "no_travel_miles": 0.0, "average_risk": 1.30, "worst_level": "Moderate"}
        }
        rec = rank_routes([r1, r2])
        assert rec["recommended_route_id"] == "r1"
        assert "Deciding Rule: Lowest Average Weather Risk." in rec["explanation"]
        assert "Route 1 has the lowest average risk (1.10 vs 1.30)" in rec["explanation"]

    def test_equal_risk_differing_minutes(self):
        r1 = {
            "id": "r1", "label": "Route A", "duration_minutes": 200, "duration_seconds": 12000,
            "metrics": {"severe_miles": 0.0, "high_miles": 0.0, "moderate_miles": 10.0, "low_miles": 90.0, "no_travel_miles": 0.0, "average_risk": 1.10, "worst_level": "Moderate"}
        }
        r2 = {
            "id": "r2", "label": "Route B", "duration_minutes": 215, "duration_seconds": 12900,
            "metrics": {"severe_miles": 0.0, "high_miles": 0.0, "moderate_miles": 10.0, "low_miles": 90.0, "no_travel_miles": 0.0, "average_risk": 1.10, "worst_level": "Moderate"}
        }
        rec = rank_routes([r1, r2])
        assert rec["recommended_route_id"] == "r1"
        assert rec["explanation"] == "Equal weather risk on all routes. Route A is fastest by 15 minutes."
        assert "Lowest Overall Weather Risk" not in rec["explanation"]

    def test_equal_risk_equal_minutes_differing_seconds(self):
        r1 = {
            "id": "r1", "label": "Route A", "duration_minutes": 200, "duration_seconds": 12015,
            "metrics": {"severe_miles": 0.0, "high_miles": 0.0, "moderate_miles": 10.0, "low_miles": 90.0, "no_travel_miles": 0.0, "average_risk": 1.10, "worst_level": "Moderate"}
        }
        r2 = {
            "id": "r2", "label": "Route B", "duration_minutes": 200, "duration_seconds": 12060,
            "metrics": {"severe_miles": 0.0, "high_miles": 0.0, "moderate_miles": 10.0, "low_miles": 90.0, "no_travel_miles": 0.0, "average_risk": 1.10, "worst_level": "Moderate"}
        }
        rec = rank_routes([r1, r2])
        assert rec["recommended_route_id"] == "r1"
        assert rec["explanation"] == "Equal weather risk on all routes. Route A is fastest by 45 seconds."
        assert "Lowest Overall Weather Risk" not in rec["explanation"]

    def test_equal_risk_equal_seconds_tied(self):
        r1 = {
            "id": "r1", "label": "Route A", "duration_minutes": 200, "duration_seconds": 12000,
            "metrics": {"severe_miles": 0.0, "high_miles": 0.0, "moderate_miles": 10.0, "low_miles": 90.0, "no_travel_miles": 0.0, "average_risk": 1.10, "worst_level": "Moderate"}
        }
        r2 = {
            "id": "r2", "label": "Route B", "duration_minutes": 200, "duration_seconds": 12000,
            "metrics": {"severe_miles": 0.0, "high_miles": 0.0, "moderate_miles": 10.0, "low_miles": 90.0, "no_travel_miles": 0.0, "average_risk": 1.10, "worst_level": "Moderate"}
        }
        rec = rank_routes([r1, r2])
        assert rec["recommended_route_id"] == "r1"
        assert rec["explanation"] == "Routes are tied. Route A is shown first."
        assert "Lowest Overall Weather Risk" not in rec["explanation"]

