"""
Golden tests for SafeHaul risk classification (Phase 3).

30 parametrized test cases covering every threshold boundary, load-weight
rule, and multi-condition interaction defined in BUILD_PLAN.md §8d.

Each test calls classify_checkpoint() with exact inputs and asserts the
overall risk level.  No I/O, no Django, no mocks — pure logic tests.
"""

import pytest

from safehaul.domain.constants import LEVEL_ORDER
from safehaul.domain.risk import (
    apply_load_rules,
    classify_checkpoint,
    classify_rain,
    classify_snow,
    classify_wind,
)

# ═══════════════════════════════════════════════════════════════════════════
# Golden Tests — 30 cases from BUILD_PLAN.md (GT-01 … GT-30)
# ═══════════════════════════════════════════════════════════════════════════

GOLDEN_CASES = [
    # (id, wind, rain, snow, load, expected_level, note)
    ("GT-01", 24.9, 0, 0, 50_000, "Low", "wind just below Moderate"),
    ("GT-02", 25, 0, 0, 10_000, "Moderate", "wind exactly at Moderate"),
    ("GT-03", 40, 0, 0, 40_000, "High", "load exactly 40k, rule not triggered"),
    ("GT-04", 40, 0, 0, 40_001, "Severe", "load > 40k, rule triggered"),
    ("GT-05", 45, 0, 0, 30_000, "Severe", "load exactly 30k, wind=Severe base"),
    ("GT-06", 50, 0, 0, 30_001, "No Travel", "load > 30k at 45-54 mph"),
    ("GT-07", 55, 0, 0, 1_000, "No Travel", "wind at No Travel boundary"),
    ("GT-08", 10, 0.25, 0, 20_000, "High", "rain at High boundary"),
    ("GT-09", 10, 1.00, 0, 20_000, "Severe", "rain at Severe/NoTravel boundary"),
    ("GT-10", 10, 1.01, 0, 20_000, "No Travel", "rain strictly > 1.00"),
    ("GT-11", 10, 0, 3.0, 20_000, "Severe", "snow at Severe/NoTravel boundary"),
    ("GT-12", 10, 0, 3.01, 20_000, "No Travel", "snow strictly > 3.0"),
    ("GT-13", 30, 0.30, 0.2, 20_000, "High", "worst wins: rain=High"),
    ("GT-14", 0, 0, 0, 1, "Low", "all-zero, minimum load"),
    ("GT-15", 54.9, 0, 0, 1, "Severe", "wind just below No Travel"),
    ("GT-16", 55.0, 0, 0, 80_000, "No Travel", "No Travel wind, max load"),
    ("GT-17", 44.9, 0, 0, 40_001, "Severe", "load rule: 35-44 mph, load > 40k"),
    ("GT-18", 35.0, 0, 0, 40_001, "Severe", "load rule: exactly at lower bound 35"),
    ("GT-19", 34.9, 0, 0, 40_001, "Moderate", "wind < 35, load rule inapplicable"),
    ("GT-20", 45.0, 0, 0, 30_001, "No Travel", "load rule: exactly at lower bound 45"),
    ("GT-21", 10, 0, 0.5, 1, "Moderate", "snow at Moderate boundary"),
    ("GT-22", 10, 0, 1.0, 1, "High", "snow at High boundary"),
    ("GT-23", 10, 0, 2.0, 1, "Severe", "snow at Severe boundary"),
    ("GT-24", 10, 0.10, 0, 1, "Moderate", "rain at Moderate boundary"),
    ("GT-25", 10, 0.50, 0, 1, "Severe", "rain at Severe boundary"),
    ("GT-26", 35, 0.30, 1.5, 45_000, "Severe", "wind+load->Severe, rain=High, snow=High; load rule wins"),
    ("GT-27", 46, 1.10, 0, 25_000, "No Travel", "rain NoTravel dominates"),
    ("GT-28", 20, 0.20, 1.2, 79_999, "High", "wind=Low, rain=Moderate, snow=High; snow wins"),
    ("GT-28-alt", 20, 0.20, 0.8, 79_999, "Moderate", "snow=0.8 is Moderate [0.5, 1.0); all Moderate"),
    ("GT-29", 25, 0.10, 0.5, 10_000, "Moderate", "all conditions exactly at Moderate"),
    ("GT-30", 47, 0, 0, 30_000, "Severe", "wind 45-54, load exactly 30k, no load rule"),
]


@pytest.mark.parametrize(
    "test_id, wind, rain, snow, load, expected, note",
    GOLDEN_CASES,
    ids=[c[0] for c in GOLDEN_CASES],
)
def test_golden_risk(test_id, wind, rain, snow, load, expected, note):
    """Verify classify_checkpoint returns the correct overall risk level."""
    result = classify_checkpoint(wind, rain, snow, load)
    assert result["level"] == expected, (
        f"{test_id} ({note}): "
        f"expected '{expected}', got '{result['level']}'. "
        f"condition_levels={result['condition_levels']}, reason='{result['reason']}'"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests — individual classifiers
# ═══════════════════════════════════════════════════════════════════════════

class TestClassifyWind:
    """Verify wind classifier boundaries."""

    @pytest.mark.parametrize("mph, expected", [
        (0, "Low"),
        (24.9, "Low"),
        (25, "Moderate"),
        (34.9, "Moderate"),
        (35, "High"),
        (44.9, "High"),
        (45, "Severe"),
        (54.9, "Severe"),
        (55, "No Travel"),
        (100, "No Travel"),
    ])
    def test_wind_boundaries(self, mph, expected):
        assert classify_wind(mph) == expected


class TestClassifyRain:
    """Verify rain classifier boundaries (>= for levels, strict > for No Travel)."""

    @pytest.mark.parametrize("rate, expected", [
        (0, "Low"),
        (0.09, "Low"),
        (0.10, "Moderate"),
        (0.24, "Moderate"),
        (0.25, "High"),
        (0.49, "High"),
        (0.50, "Severe"),
        (1.00, "Severe"),      # exactly at boundary → NOT No Travel
        (1.01, "No Travel"),   # strictly > 1.00
        (5.0, "No Travel"),
    ])
    def test_rain_boundaries(self, rate, expected):
        assert classify_rain(rate) == expected


class TestClassifySnow:
    """Verify snow classifier boundaries (>= for levels, strict > for No Travel)."""

    @pytest.mark.parametrize("rate, expected", [
        (0, "Low"),
        (0.49, "Low"),
        (0.5, "Moderate"),
        (0.99, "Moderate"),
        (1.0, "High"),
        (1.99, "High"),
        (2.0, "Severe"),
        (3.0, "Severe"),       # exactly at boundary → NOT No Travel
        (3.01, "No Travel"),   # strictly > 3.0
        (10.0, "No Travel"),
    ])
    def test_snow_boundaries(self, rate, expected):
        assert classify_snow(rate) == expected


class TestApplyLoadRules:
    """Verify load-weight escalation rules."""

    def test_wind_already_no_travel_no_change(self):
        """Wind >= 55 → already No Travel, load rule has no effect."""
        level, reason = apply_load_rules("No Travel", 55, 80_000)
        assert level == "No Travel"
        assert reason is None

    def test_45_54_load_over_30k_escalates(self):
        """45-54 mph wind + load > 30,000 lb → No Travel."""
        level, reason = apply_load_rules("Severe", 50, 30_001)
        assert level == "No Travel"
        assert reason is not None

    def test_45_54_load_exactly_30k_no_escalation(self):
        """45-54 mph wind + load = 30,000 lb → stays Severe (strict >)."""
        level, reason = apply_load_rules("Severe", 50, 30_000)
        assert level == "Severe"
        assert reason is None

    def test_35_44_load_over_40k_escalates_to_severe(self):
        """35-44 mph wind + load > 40,000 lb → Severe (only if below)."""
        level, reason = apply_load_rules("High", 40, 40_001)
        assert level == "Severe"
        assert reason is not None

    def test_35_44_load_exactly_40k_no_escalation(self):
        """35-44 mph wind + load = 40,000 lb → stays High (strict >)."""
        level, reason = apply_load_rules("High", 40, 40_000)
        assert level == "High"
        assert reason is None

    def test_load_rule_never_lowers_level(self):
        """If wind is already Severe in 35-44 range, load rule doesn't change it."""
        # This shouldn't normally happen (35-44 mph → High base), but tests the guard.
        level, reason = apply_load_rules("Severe", 40, 40_001)
        assert level == "Severe"
        assert reason is None  # already at Severe, no escalation message

    def test_below_35_mph_no_load_rule(self):
        """Wind < 35 mph → no load rule applies regardless of weight."""
        level, reason = apply_load_rules("Moderate", 30, 80_000)
        assert level == "Moderate"
        assert reason is None


class TestClassifyCheckpointStructure:
    """Verify the structure and fields of the classify_checkpoint return dict."""

    def test_return_has_required_keys(self):
        result = classify_checkpoint(10, 0, 0, 10_000)
        assert "condition_levels" in result
        assert "level" in result
        assert "reason" in result

    def test_condition_levels_has_three_keys(self):
        result = classify_checkpoint(10, 0, 0, 10_000)
        assert set(result["condition_levels"].keys()) == {"wind", "rain", "snow"}

    def test_all_returned_levels_are_valid(self):
        result = classify_checkpoint(35, 0.30, 1.5, 45_000)
        for val in result["condition_levels"].values():
            assert val in LEVEL_ORDER, f"'{val}' not in LEVEL_ORDER"
        assert result["level"] in LEVEL_ORDER

    def test_reason_is_non_empty_string(self):
        result = classify_checkpoint(10, 0, 0, 10_000)
        assert isinstance(result["reason"], str)
        assert len(result["reason"]) > 0

    def test_load_reason_appears_when_load_rule_fires(self):
        """When load rule escalates, reason should mention load weight."""
        result = classify_checkpoint(50, 0, 0, 30_001)
        assert "lb load" in result["reason"]
        assert "No Travel" in result["reason"]

    def test_reason_lists_causes_when_no_load_rule(self):
        """When no load rule fires, reason lists the dominant condition(s)."""
        result = classify_checkpoint(10, 0.30, 0, 10_000)
        assert "Rain" in result["reason"]

    def test_precipitation_dominance_over_lesser_load_escalation(self):
        """If load rule raises wind to Severe, but rain is No Travel, rain wins and reason reflects No Travel."""
        result = classify_checkpoint(40, 1.5, 0, 45_000)
        assert result["level"] == "No Travel"
        assert result["condition_levels"]["wind"] == "Severe"
        assert result["condition_levels"]["rain"] == "No Travel"
        assert result["reason"] == "Rain -> No Travel"

    def test_multiple_tied_worst_conditions(self):
        """When multiple conditions tie for worst, all tied conditions are in reason."""
        result = classify_checkpoint(40, 0.30, 0, 10_000)
        assert result["level"] == "High"
        assert "Wind -> High" in result["reason"]
        assert "Rain -> High" in result["reason"]
