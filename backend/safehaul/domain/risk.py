"""
SafeHaul risk classification — pure, deterministic, no I/O.

Public API:
    classify_checkpoint(wind_mph, rain_in_hr, snow_in_hr, load_lb) -> dict

Each function is stateless and depends only on constants.py.
All boundary rules are documented in docs/BUILD_PLAN.md §8d and §A10/A11.
"""

from __future__ import annotations

from safehaul.domain.constants import (
    LEVEL_ORDER,
    RAIN_NO_TRAVEL_THRESHOLD,
    RAIN_THRESHOLDS,
    SNOW_NO_TRAVEL_THRESHOLD,
    SNOW_THRESHOLDS,
    WIND_THRESHOLDS,
)

# ── Individual weather classifiers ─────────────────────────────────────────

def classify_wind(wind_mph: float) -> str:
    """Classify sustained wind speed (mph) into a risk level.

    Uses >= comparison against descending thresholds.
    """
    for threshold, level in WIND_THRESHOLDS:
        if wind_mph >= threshold:
            return level
    return "Low"  # pragma: no cover — 0 threshold always matches


def classify_rain(rain_in_hr: float) -> str:
    """Classify rain rate (in/hr) into a risk level.

    No Travel uses strict > (rain > 1.00).
    All other levels use >= against descending thresholds.
    """
    if rain_in_hr > RAIN_NO_TRAVEL_THRESHOLD:
        return "No Travel"
    for threshold, level in RAIN_THRESHOLDS:
        if rain_in_hr >= threshold:
            return level
    return "Low"  # pragma: no cover — 0 threshold always matches


def classify_snow(snow_in_hr: float) -> str:
    """Classify snow rate (in/hr) into a risk level.

    No Travel uses strict > (snow > 3.0).
    All other levels use >= against descending thresholds.
    """
    if snow_in_hr > SNOW_NO_TRAVEL_THRESHOLD:
        return "No Travel"
    for threshold, level in SNOW_THRESHOLDS:
        if snow_in_hr >= threshold:
            return level
    return "Low"  # pragma: no cover — 0 threshold always matches


# ── Load-weight adjustment ─────────────────────────────────────────────────

def apply_load_rules(
    wind_level: str,
    wind_mph: float,
    load_lb: int,
) -> tuple[str, str | None]:
    """Apply load-weight escalation rules to the wind risk level.

    Rules use strict greater-than (>) for load thresholds:
      • 45 <= wind < 55 AND load > 30,000 lb  → No Travel
      • 35 <= wind < 45 AND load > 40,000 lb  → Severe  (only if currently below)

    A load rule can only *raise* a risk level, never lower it.

    Returns:
        (adjusted_level, reason_string_or_None)
    """
    # Wind already at No Travel — nothing to escalate.
    if wind_mph >= 55:
        return wind_level, None

    # Rule 1: 45-54 mph + heavy load → No Travel
    if 45 <= wind_mph < 55 and load_lb > 30_000:
        return "No Travel", f"Wind {wind_mph:.1f} mph with {load_lb:,} lb load -> No Travel"

    # Rule 2: 35-44 mph + very heavy load → Severe (only raise)
    if 35 <= wind_mph < 45 and load_lb > 40_000:
        if LEVEL_ORDER[wind_level] < LEVEL_ORDER["Severe"]:
            return "Severe", f"Wind {wind_mph:.1f} mph with {load_lb:,} lb load -> Severe"

    return wind_level, None


# ── Composite checkpoint classifier ────────────────────────────────────────

def classify_checkpoint(
    wind_mph: float,
    rain_in_hr: float,
    snow_in_hr: float,
    load_lb: int,
) -> dict:
    """Classify a single checkpoint and return risk result dict.

    Returns:
        {
            "condition_levels": {"wind": str, "rain": str, "snow": str},
            "level": str,          # overall (worst of wind/rain/snow after load rules)
            "reason": str,         # human-readable explanation
        }
    """
    # 1. Base classification per weather variable.
    wind_base = classify_wind(wind_mph)

    # 2. Apply load-weight escalation to wind level.
    wind_level, load_reason = apply_load_rules(wind_base, wind_mph, load_lb)

    # 3. Classify precipitation.
    rain_level = classify_rain(rain_in_hr)
    snow_level = classify_snow(snow_in_hr)

    # 4. Condition levels dict (wind reflects load adjustment).
    condition_levels = {
        "wind": wind_level,
        "rain": rain_level,
        "snow": snow_level,
    }

    # 5. Overall risk = worst (highest LEVEL_ORDER) across all conditions.
    overall = max(condition_levels.values(), key=lambda lvl: LEVEL_ORDER[lvl])

    # 6. Build human-readable reason.
    if load_reason and wind_level == overall:
        reason = load_reason
    else:
        # List every condition that ties for the worst level.
        causes = [
            f"{key.title()} -> {val}"
            for key, val in condition_levels.items()
            if val == overall
        ]
        reason = "; ".join(causes)

    return {
        "condition_levels": condition_levels,
        "level": overall,
        "reason": reason,
    }
