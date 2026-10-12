"""
SafeHaul domain constants — every threshold, limit, and magic number.

All values are documented in docs/BUILD_PLAN.md §8d and §A7/A10/A11.
This module has ZERO imports (no Django, no third-party).
"""

# ── Load weight limits (lbs, inclusive) ─────────────────────────────────────
LOAD_MIN_LB: int = 1
LOAD_MAX_LB: int = 80_000

# ── Risk level ordering (higher = worse) ───────────────────────────────────
LEVEL_ORDER: dict[str, int] = {
    "Low": 1,
    "Moderate": 2,
    "High": 3,
    "Severe": 4,
    "No Travel": 5,
}

# ── Wind thresholds (mph, >= comparison, descending order) ─────────────────
# Each tuple: (lower_bound_inclusive, risk_level)
WIND_THRESHOLDS: list[tuple[float, str]] = [
    (55, "No Travel"),
    (45, "Severe"),
    (35, "High"),
    (25, "Moderate"),
    (0, "Low"),
]

# ── Rain thresholds (in/hr) ────────────────────────────────────────────────
# No Travel uses strict greater-than (> 1.00).
RAIN_NO_TRAVEL_THRESHOLD: float = 1.00
# Remaining levels use >= comparison, descending order.
RAIN_THRESHOLDS: list[tuple[float, str]] = [
    (0.50, "Severe"),
    (0.25, "High"),
    (0.10, "Moderate"),
    (0, "Low"),
]

# ── Snow thresholds (in/hr) ────────────────────────────────────────────────
# No Travel uses strict greater-than (> 3.0).
SNOW_NO_TRAVEL_THRESHOLD: float = 3.0
# Remaining levels use >= comparison, descending order.
SNOW_THRESHOLDS: list[tuple[float, str]] = [
    (2.0, "Severe"),
    (1.0, "High"),
    (0.5, "Moderate"),
    (0, "Low"),
]

# ── Sampling / metrics tolerances ──────────────────────────────────────────
MILE_TOLERANCE: float = 0.001  # max acceptable rounding error in segment sums

# ── Sampling constants ─────────────────────────────────────────────────────
ALLOWED_SAMPLE_INTERVALS: list[int] = [10, 25, 50]
DEFAULT_SAMPLE_INTERVAL: int = 25
INTERVAL_SHORT_ROUTE_MAX_MILES: float = 150.0
INTERVAL_MEDIUM_ROUTE_MAX_MILES: float = 600.0
DESTINATION_DEDUPLICATION_THRESHOLD_MILES: float = 0.01
EARTH_RADIUS_MILES: float = 3958.8

# ── Heatmap limits ─────────────────────────────────────────────────────────
MAX_HEATMAP_POINTS: int = 400
HEATMAP_BUFFER_DEG: float = 0.5
