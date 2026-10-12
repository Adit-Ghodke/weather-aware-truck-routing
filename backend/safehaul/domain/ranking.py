"""
SafeHaul route metrics aggregation and ranking — pure business logic.

Public API:
    compute_route_metrics(checkpoints, total_distance_miles) -> dict
    rank_routes(routes) -> dict

All algorithms are specified in docs/BUILD_PLAN.md §8e and §8f.
Zero Django or I/O imports.
"""

from __future__ import annotations

from safehaul.domain.constants import LEVEL_ORDER


def compute_route_metrics(
    checkpoints: list[dict],
    total_distance_miles: float,
) -> dict:
    """Aggregate checkpoint risk levels and segment miles into route metrics.

    Metrics computed (§8e):
      • severe_miles: sum of segment miles where checkpoint level == Severe
      • high_miles: sum of segment miles where level == High
      • moderate_miles: sum of segment miles where level == Moderate
      • low_miles: sum of segment miles where level == Low
      • no_travel_miles: sum of segment miles where level == No Travel
      • average_risk: mile-weighted average risk level (1.00 - 5.00)
      • worst_level: highest level across all checkpoints
    """
    severe_miles = 0.0
    high_miles = 0.0
    moderate_miles = 0.0
    low_miles = 0.0
    no_travel_miles = 0.0
    weighted_risk_sum = 0.0

    worst_level = "Low"
    worst_order = LEVEL_ORDER["Low"]

    for cp in checkpoints:
        level = cp.get("level", "Low")
        seg = float(cp.get("segment_miles", 0.0))
        order = LEVEL_ORDER.get(level, 1)

        if order > worst_order:
            worst_order = order
            worst_level = level

        weighted_risk_sum += order * seg

        if level == "Severe":
            severe_miles += seg
        elif level == "High":
            high_miles += seg
        elif level == "Moderate":
            moderate_miles += seg
        elif level == "Low":
            low_miles += seg
        elif level == "No Travel":
            no_travel_miles += seg

    dist = total_distance_miles if total_distance_miles > 0.0 else 1.0
    avg_risk = weighted_risk_sum / dist

    return {
        "severe_miles": round(severe_miles, 1),
        "high_miles": round(high_miles, 1),
        "moderate_miles": round(moderate_miles, 1),
        "low_miles": round(low_miles, 1),
        "no_travel_miles": round(no_travel_miles, 1),
        "average_risk": round(avg_risk, 2),
        "_average_risk_sort": round(avg_risk, 3),  # 3dp for tie-breaking
        "worst_level": worst_level,
    }


def _format_minutes(mins: int) -> str:
    """Format minutes with correct singular/plural grammar (§Fix 3)."""
    return f"{mins} minute" if mins == 1 else f"{mins} minutes"


def _format_seconds(secs: int) -> str:
    """Format seconds with correct singular/plural grammar."""
    return f"{secs} second" if secs == 1 else f"{secs} seconds"


def _build_explanation(
    r1: dict,
    r2: dict | None,
    all_no_travel: bool,
) -> str:
    """Generate human-readable explanation naming the deciding rule in plain words and with proper grammar."""
    r1_label = r1.get("label", "Recommended Route")
    r1_metrics = r1["metrics"]

    if all_no_travel:
        return (
            f"Deciding Rule: Fewest No Travel Miles. All candidate routes encounter No Travel conditions. "
            f"{r1_label} has the fewest No Travel miles ({r1_metrics['no_travel_miles']} mi). "
            f"Travel is not recommended at this departure time."
        )

    if not r2:
        return f"Deciding Rule: Lowest Weather Risk. {r1_label} is the safest available route with {r1_metrics['average_risk']:.2f} average risk."

    r2_label = r2.get("label", "Alternative Route")
    r2_metrics = r2["metrics"]

    dur_diff = round(r1.get("duration_minutes", 0) - r2.get("duration_minutes", 0))

    # Differing dimension 1: Severe miles
    if round(r1_metrics["severe_miles"], 1) < round(r2_metrics["severe_miles"], 1):
        base = (
            f"Deciding Rule: Fewest Severe Weather Miles. {r1_label} has {r1_metrics['severe_miles']} Severe miles vs "
            f"{r2_metrics['severe_miles']} on {r2_label}"
        )
        if dur_diff > 0:
            return f"{base} and is {_format_minutes(dur_diff)} longer, but significantly reduces severe weather exposure."
        elif dur_diff < 0:
            return f"{base} and is {_format_minutes(abs(dur_diff))} faster."
        return f"{base}."

    # Differing dimension 2: High miles
    if round(r1_metrics["high_miles"], 1) < round(r2_metrics["high_miles"], 1):
        base = (
            f"Deciding Rule: Fewest High Weather Miles. {r1_label} has {r1_metrics['high_miles']} High miles vs "
            f"{r2_metrics['high_miles']} on {r2_label}"
        )
        if dur_diff > 0:
            return f"{base} and is {_format_minutes(dur_diff)} longer, but avoids elevated weather risk."
        elif dur_diff < 0:
            return f"{base} and is {_format_minutes(abs(dur_diff))} faster."
        return f"{base}."

    # Differing dimension 3: Average risk
    if round(r1_metrics["average_risk"], 2) < round(r2_metrics["average_risk"], 2):
        base = (
            f"Deciding Rule: Lowest Average Weather Risk. {r1_label} has the lowest average risk "
            f"({r1_metrics['average_risk']:.2f} vs {r2_metrics['average_risk']:.2f})"
        )
        if dur_diff > 0:
            return f"{base} and is {_format_minutes(dur_diff)} longer."
        elif dur_diff < 0:
            return f"{base} and is {_format_minutes(abs(dur_diff))} faster."
        return f"{base}."

    # Differing dimension 4: Risk is equal across all dimensions
    sec1 = float(r1.get("duration_seconds", r1.get("duration_minutes", 0) * 60))
    sec2 = float(r2.get("duration_seconds", r2.get("duration_minutes", 0) * 60))
    dur_diff_mins = round(r2.get("duration_minutes", 0) - r1.get("duration_minutes", 0))

    if dur_diff_mins > 0:
        return f"Equal weather risk on all routes. {r1_label} is fastest by {_format_minutes(dur_diff_mins)}."
    elif dur_diff_mins == 0:
        dur_diff_secs = round(sec2 - sec1)
        if dur_diff_secs > 0:
            return f"Equal weather risk on all routes. {r1_label} is fastest by {_format_seconds(dur_diff_secs)}."
        else:
            return f"Routes are tied. {r1_label} is shown first."
    else:
        return f"Routes are tied. {r1_label} is shown first."



def rank_routes(routes: list[dict]) -> dict:
    """Rank candidate routes and produce recommendation + comparison table.

    Algorithm (§8f):
      1. Partition routes into ok_routes (no_travel_miles == 0) and no_travel_routes.
      2. If all routes are no_travel:
         - Rank by fewest no_travel_miles ASC, then severe_miles ASC, high_miles ASC, etc.
         - status = "not_recommended_all_routes"
         - warning = "Do not travel at this departure time"
      3. Otherwise:
         - Rank ok_routes lexicographically:
             a. severe_miles ASC (rounded to 1dp)
             b. high_miles ASC (rounded to 1dp)
             c. average_risk ASC (rounded to 3dp)
             d. duration_minutes ASC
         - Rank no_travel_routes by no_travel_miles ASC and append after ok_routes.
         - status = "recommended"
      4. Produce explanation comparing rank 1 vs rank 2.
    """
    if not routes:
        return {
            "recommended_route_id": None,
            "status": "no_routes",
            "explanation": "No routes available for analysis.",
            "warning": None,
            "comparison": [],
        }

    # Partition
    ok_routes: list[dict] = []
    no_travel_routes: list[dict] = []

    for r in routes:
        metrics = r.get("metrics", {})
        no_travel_m = float(metrics.get("no_travel_miles", 0.0))
        worst = metrics.get("worst_level", "Low")
        if no_travel_m > 0.0 or worst == "No Travel":
            no_travel_routes.append(r)
        else:
            ok_routes.append(r)

    all_no_travel = len(ok_routes) == 0

    if all_no_travel:
        # Sort no_travel_routes by fewest no_travel_miles, then severe, high, avg, duration
        no_travel_routes.sort(
            key=lambda r: (
                round(r["metrics"]["no_travel_miles"], 1),
                round(r["metrics"]["severe_miles"], 1),
                round(r["metrics"]["high_miles"], 1),
                round(r["metrics"]["average_risk"], 2),
                float(r.get("duration_seconds", r.get("duration_minutes", 0) * 60)),
            )
        )
        ranked = no_travel_routes
        status = "not_recommended_all_routes"
        warning = "Do not travel at this departure time"
    else:
        # Sort ok_routes per §8f rule 3
        ok_routes.sort(
            key=lambda r: (
                round(r["metrics"]["severe_miles"], 1),
                round(r["metrics"]["high_miles"], 1),
                round(r["metrics"]["average_risk"], 2),
                float(r.get("duration_seconds", r.get("duration_minutes", 0) * 60)),
            )
        )
        # Sort no_travel_routes by fewest no_travel_miles and append
        no_travel_routes.sort(
            key=lambda r: (
                round(r["metrics"]["no_travel_miles"], 1),
                round(r["metrics"]["severe_miles"], 1),
                round(r["metrics"]["high_miles"], 1),
                round(r["metrics"]["average_risk"], 2),
                float(r.get("duration_seconds", r.get("duration_minutes", 0) * 60)),
            )
        )
        ranked = ok_routes + no_travel_routes
        status = "recommended"
        warning = None

    # Assign ranks and build comparison table
    comparison: list[dict] = []
    for rank_idx, r in enumerate(ranked, start=1):
        r["rank"] = rank_idx
        is_nt = r in no_travel_routes
        comparison.append(
            {
                "route_id": r.get("id"),
                "label": r.get("label", f"Route {rank_idx}"),
                "rank": rank_idx,
                "status": "no_travel" if is_nt else "ok",
                "distance_miles": r.get("distance_miles", 0.0),
                "severe_miles": r["metrics"]["severe_miles"],
                "high_miles": r["metrics"]["high_miles"],
                "moderate_miles": r["metrics"]["moderate_miles"],
                "low_miles": r["metrics"]["low_miles"],
                "no_travel_miles": r["metrics"]["no_travel_miles"],
                "average_risk": r["metrics"]["average_risk"],
                "duration_minutes": r.get("duration_minutes", 0),
            }
        )

    r1 = ranked[0]
    r2 = ranked[1] if len(ranked) > 1 else None
    explanation = _build_explanation(r1, r2, all_no_travel=all_no_travel)

    return {
        "recommended_route_id": r1.get("id"),
        "status": status,
        "explanation": explanation,
        "warning": warning,
        "comparison": comparison,
    }
