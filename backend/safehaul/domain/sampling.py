"""
SafeHaul checkpoint sampling and segment attribution — pure business logic.

Public API:
    auto_select_interval(distance_miles) -> int
    haversine_distance(coord1, coord2) -> float
    compute_cumulative_distances(coordinates) -> list[float]
    sample_checkpoints(coordinates, sample_interval_miles, total_distance_miles) -> list[dict]
    compute_segment_miles(checkpoints, total_distance_miles) -> list[float]

All algorithms are specified in docs/BUILD_PLAN.md §8a, §8e, and §A1/A12.
Coordinates follow GeoJSON convention: [longitude, latitude].
Zero Django or I/O imports.
"""

from __future__ import annotations

import math

from safehaul.domain.constants import (
    EARTH_RADIUS_MILES,
    INTERVAL_MEDIUM_ROUTE_MAX_MILES,
    INTERVAL_SHORT_ROUTE_MAX_MILES,
    MILE_TOLERANCE,
)


def auto_select_interval(distance_miles: float) -> int:
    """Automatically choose sampling interval based on total route distance.

    Rules (§A1):
      • <= 150 mi  → 10 miles
      • 150-600 mi → 25 miles
      • > 600 mi   → 50 miles
    """
    if distance_miles <= INTERVAL_SHORT_ROUTE_MAX_MILES:
        return 10
    if distance_miles <= INTERVAL_MEDIUM_ROUTE_MAX_MILES:
        return 25
    return 50


def haversine_distance(
    coord1: tuple[float, float] | list[float],
    coord2: tuple[float, float] | list[float],
) -> float:
    """Compute great-circle distance between two [lng, lat] points in miles."""
    lng1, lat1 = coord1[0], coord1[1]
    lng2, lat2 = coord2[0], coord2[1]

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_MILES * c


def compute_cumulative_distances(
    coordinates: list[list[float] | tuple[float, float]],
) -> list[float]:
    """Compute cumulative polyline distances in miles from origin to each vertex."""
    if not coordinates:
        return []

    cumulative = [0.0]
    total = 0.0
    for i in range(1, len(coordinates)):
        seg_dist = haversine_distance(coordinates[i - 1], coordinates[i])
        total += seg_dist
        cumulative.append(total)
    return cumulative


def interpolate_coordinate(
    coordinates: list[list[float] | tuple[float, float]],
    cumulative_distances: list[float],
    target_mile: float,
) -> tuple[float, float]:
    """Linearly interpolate [lng, lat] along a polyline at a target mile marker."""
    if not coordinates:
        raise ValueError("Cannot interpolate on empty coordinates")

    if target_mile <= 0.0 or len(coordinates) == 1:
        return float(coordinates[0][0]), float(coordinates[0][1])

    total_dist = cumulative_distances[-1]
    if target_mile >= total_dist:
        return float(coordinates[-1][0]), float(coordinates[-1][1])

    # Find the segment [i, i+1] containing target_mile
    for i in range(len(cumulative_distances) - 1):
        seg_start = cumulative_distances[i]
        seg_end = cumulative_distances[i + 1]
        if seg_start <= target_mile <= seg_end:
            seg_len = seg_end - seg_start
            if seg_len <= 1e-9:
                fraction = 0.0
            else:
                fraction = (target_mile - seg_start) / seg_len

            lng = coordinates[i][0] + fraction * (coordinates[i + 1][0] - coordinates[i][0])
            lat = coordinates[i][1] + fraction * (coordinates[i + 1][1] - coordinates[i][1])
            return round(lng, 6), round(lat, 6)

    # Fallback to last coordinate
    return float(coordinates[-1][0]), float(coordinates[-1][1])


def sample_checkpoints(
    coordinates: list[list[float] | tuple[float, float]],
    sample_interval_miles: int,
    total_distance_miles: float | None = None,
) -> list[dict]:
    """Sample checkpoints along a route geometry at regular mile intervals.

    Guarantees:
      • Origin (mile 0.0) is always included.
      • Destination is always at the end.
      • If the last regular sample is within 0.01 mi of destination, it is deduplicated.

    Returns:
        list of dicts: [
            {"index": int, "mile_marker": float, "lat": float, "lng": float},
            ...
        ]
    """
    if not coordinates:
        return []

    cumulative = compute_cumulative_distances(coordinates)
    route_total_miles = total_distance_miles if total_distance_miles is not None else cumulative[-1]

    # Handle degenerate 0-mile routes
    if route_total_miles <= 0.0 or len(coordinates) == 1:
        return [
            {
                "index": 0,
                "mile_marker": 0.0,
                "lat": round(float(coordinates[0][1]), 6),
                "lng": round(float(coordinates[0][0]), 6),
            }
        ]

    checkpoints: list[dict] = []

    # 1. Always include origin (mile 0.0)
    origin_lng, origin_lat = interpolate_coordinate(coordinates, cumulative, 0.0)
    checkpoints.append(
        {
            "index": 0,
            "mile_marker": 0.0,
            "lat": origin_lat,
            "lng": origin_lng,
        }
    )

    # 2. Sample along route at target intervals
    target_miles = float(sample_interval_miles)
    while target_miles < route_total_miles:
        lng, lat = interpolate_coordinate(coordinates, cumulative, target_miles)
        checkpoints.append(
            {
                "index": len(checkpoints),
                "mile_marker": round(target_miles, 2),
                "lat": lat,
                "lng": lng,
            }
        )
        target_miles += float(sample_interval_miles)

    # 3. Always include destination. If the remaining distance from the last
    # sample is shorter than 10% of the sample interval, merge it so the final
    # checkpoint is the destination only (§Fix 4).
    dest_lng, dest_lat = float(coordinates[-1][0]), float(coordinates[-1][1])
    distance_to_dest = route_total_miles - checkpoints[-1]["mile_marker"]
    min_final_interval = 0.10 * float(sample_interval_miles)

    if distance_to_dest >= min_final_interval or len(checkpoints) == 1:
        checkpoints.append(
            {
                "index": len(checkpoints),
                "mile_marker": round(route_total_miles, 2),
                "lat": round(dest_lat, 6),
                "lng": round(dest_lng, 6),
            }
        )
    else:
        # Merge: adjust last checkpoint to be the exact destination
        checkpoints[-1]["mile_marker"] = round(route_total_miles, 2)
        checkpoints[-1]["lat"] = round(dest_lat, 6)
        checkpoints[-1]["lng"] = round(dest_lng, 6)


    # Re-index to ensure contiguous 0-based indices
    for idx, cp in enumerate(checkpoints):
        cp["index"] = idx

    return checkpoints


def compute_segment_miles(
    checkpoints: list[dict],
    total_distance_miles: float,
) -> list[float]:
    """Compute attributed segment length in miles for each checkpoint.

    Attribution rule (§A12):
      • First checkpoint: half-distance to checkpoint 1.
      • Middle checkpoint i: half-distance to (i-1) + half-distance to (i+1).
      • Last checkpoint: half-distance from checkpoint (N-2).
      • Segments sum to exact route distance (within MILE_TOLERANCE = 0.001 mi).
    """
    n = len(checkpoints)
    if n == 0:
        return []
    if n == 1:
        return [round(total_distance_miles, 2)]

    seg_miles: list[float] = [0.0] * n

    # Half-distance to next for first checkpoint
    seg_miles[0] = (checkpoints[1]["mile_marker"] - checkpoints[0]["mile_marker"]) / 2.0

    # Middle checkpoints
    for i in range(1, n - 1):
        prev_half = (checkpoints[i]["mile_marker"] - checkpoints[i - 1]["mile_marker"]) / 2.0
        next_half = (checkpoints[i + 1]["mile_marker"] - checkpoints[i]["mile_marker"]) / 2.0
        seg_miles[i] = prev_half + next_half

    # Half-distance from previous for last checkpoint
    seg_miles[-1] = (checkpoints[-1]["mile_marker"] - checkpoints[-2]["mile_marker"]) / 2.0

    # Mathematical telescoping sum check:
    # seg_miles[0] + ... + seg_miles[-1] == checkpoints[-1]["mile_marker"] - checkpoints[0]["mile_marker"]
    total_seg = sum(seg_miles)
    error = abs(total_seg - total_distance_miles)
    if error >= MILE_TOLERANCE:
        raise ValueError(
            f"Segment miles sum {total_seg:.4f} does not match total route distance "
            f"{total_distance_miles:.4f} (difference {error:.4f} exceeds {MILE_TOLERANCE})"
        )

    # Round segments cleanly to 2 decimal places, adjusting last element for precision
    rounded_segs = [round(m, 2) for m in seg_miles]
    remainder = round(total_distance_miles - sum(rounded_segs), 2)
    if abs(remainder) > 0:
        rounded_segs[-1] = round(rounded_segs[-1] + remainder, 2)

    return rounded_segs
