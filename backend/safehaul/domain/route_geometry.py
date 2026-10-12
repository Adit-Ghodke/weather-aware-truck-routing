"""
SafeHaul route geometry validation — spur detection and route corridor overlap analysis.

Specifications (§Fix 2):
  • Detect out-and-back spurs: path returns within ~100m of an earlier point in the opposite direction.
  • Compute geometry overlap percentage against existing route corridors.
  • Reject candidates that share >80% geometry, contain spurs, or are >40% longer than fastest route.
  • Pure domain logic — zero Django or network dependencies.
"""

from __future__ import annotations

import math
from typing import Any


def haversine_distance_meters(
    p1: list[float] | tuple[float, float],
    p2: list[float] | tuple[float, float],
) -> float:
    """Great-circle distance between two [lng, lat] coordinates in meters."""
    R = 6371000.0  # Earth radius in meters
    lng1, lat1 = p1[0], p1[1]
    lng2, lat2 = p2[0], p2[1]

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return R * c


def detect_out_and_back_spur(
    coordinates: list[list[float] | tuple[float, float]],
    threshold_meters: float = 120.0,
    min_along_meters: float = 400.0,
    max_spur_loop_meters: float = 50000.0,
) -> bool:
    """Detect if a polyline contains an out-and-back spur using spatial indexing.

    A spur occurs when a route travels forward, detours/turns around, and returns within
    ~100m of an earlier point traveling in the opposite direction (heading reversal).
    """
    n = len(coordinates)
    if n < 4:
        return False

    # Compute cumulative distance along the polyline in meters
    cum_meters = [0.0]
    for i in range(n - 1):
        cum_meters.append(cum_meters[-1] + haversine_distance_meters(coordinates[i], coordinates[i + 1]))

    # Step through points to keep sample count bounded
    step = max(1, n // 300)
    indices = list(range(0, n - 1, step))
    if indices[-1] != n - 2:
        indices.append(n - 2)

    # Spatial grid index for O(N) neighbor lookups (§Fix 2)
    cell_size = 0.002  # ~200m spatial grid
    grid: dict[tuple[int, int], list[int]] = {}
    headings: dict[int, tuple[float, float, float]] = {}

    for idx in indices:
        p = coordinates[idx]
        p_next = coordinates[idx + 1]
        v_lng = p_next[0] - p[0]
        v_lat = p_next[1] - p[1]
        norm = math.sqrt(v_lng**2 + v_lat**2)
        if norm >= 1e-9:
            headings[idx] = (v_lng / norm, v_lat / norm, cum_meters[idx])
            gx = int(p[0] / cell_size)
            gy = int(p[1] / cell_size)
            grid.setdefault((gx, gy), []).append(idx)

    for i in indices:
        if i not in headings:
            continue
        vi_lng, vi_lat, i_along = headings[i]
        p_i = coordinates[i]
        gx = int(p_i[0] / cell_size)
        gy = int(p_i[1] / cell_size)

        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cell_idxs = grid.get((gx + dx, gy + dy))
                if not cell_idxs:
                    continue
                for j in cell_idxs:
                    if j <= i:
                        continue
                    vj_lng, vj_lat, j_along = headings[j]
                    along_dist = j_along - i_along
                    if along_dist < min_along_meters or along_dist > max_spur_loop_meters:
                        continue
                    if haversine_distance_meters(p_i, coordinates[j]) <= threshold_meters:
                        cos_theta = vi_lng * vj_lng + vi_lat * vj_lat
                        if cos_theta < -0.5:
                            return True

    return False


def compute_geometry_overlap_percent(
    candidate_coords: list[list[float] | tuple[float, float]],
    reference_coords: list[list[float] | tuple[float, float]],
    threshold_meters: float = 250.0,
) -> float:
    """Compute the percentage of candidate route coordinates that lie within
    threshold_meters of any point on the reference route.
    """
    if not candidate_coords or not reference_coords:
        return 0.0

    # Build a spatial grid for fast spatial indexing
    cell_deg = 0.005  # ~500m grid cell
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for ref_pt in reference_coords:
        gx = int(ref_pt[0] / cell_deg)
        gy = int(ref_pt[1] / cell_deg)
        grid.setdefault((gx, gy), []).append((ref_pt[0], ref_pt[1]))

    # Sample candidate coordinates if large, ensuring fast O(sample) check (§Fix 2)
    sample_coords = candidate_coords
    if len(candidate_coords) > 250:
        step = max(1, len(candidate_coords) // 250)
        sample_coords = candidate_coords[::step]

    shared_count = 0
    for cand_pt in sample_coords:
        gx = int(cand_pt[0] / cell_deg)
        gy = int(cand_pt[1] / cell_deg)
        found = False
        for dx in (-1, 0, 1):
            if found:
                break
            for dy in (-1, 0, 1):
                cell_points = grid.get((gx + dx, gy + dy))
                if not cell_points:
                    continue
                for ref_pt in cell_points:
                    if haversine_distance_meters(cand_pt, ref_pt) <= threshold_meters:
                        found = True
                        break
        if found:
            shared_count += 1

    return round((shared_count / len(sample_coords)) * 100.0, 1)


def evaluate_candidate_corridors(
    candidate_routes: list[dict[str, Any]],
    existing_routes: list[dict[str, Any]],
    max_overlap_percent: float = 80.0,
    max_length_ratio: float = 1.40,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Filter and rank candidate routes according to corridor uniqueness criteria.

    Rules (§Fix 2):
      • Reject if shares >80% geometry with an existing route.
      • Reject if contains an out-and-back spur (returns within ~100m in opposite direction).
      • Reject if >40% longer than the fastest existing route.
      • Select the surviving candidate that minimizes maximum overlap with existing routes.

    Returns:
        (best_surviving_candidate_or_None, list_of_evaluation_records)
    """
    if not candidate_routes:
        return None, []

    fastest_dist = min(float(r.get("distance_miles", 0.0)) for r in existing_routes) if existing_routes else 0.0
    records: list[dict[str, Any]] = []
    survivors: list[tuple[float, dict[str, Any]]] = []

    for idx, cand in enumerate(candidate_routes):
        cand_coords = cand.get("geometry", {}).get("coordinates", [])
        dist_mi = float(cand.get("distance_miles", 0.0))
        dur_min = float(cand.get("duration_minutes", 0.0))

        # 1. Spur check
        has_spur = detect_out_and_back_spur(cand_coords)

        # 2. Length check
        is_too_long = (dist_mi > fastest_dist * max_length_ratio) if fastest_dist > 0 else False

        # 3. Overlap check with every existing route
        overlaps: list[float] = []
        for exist in existing_routes:
            exist_coords = exist.get("geometry", {}).get("coordinates", [])
            ov = compute_geometry_overlap_percent(cand_coords, exist_coords)
            overlaps.append(ov)

        max_ov = max(overlaps) if overlaps else 0.0
        exceeds_overlap = max_ov > max_overlap_percent

        is_valid = (not has_spur) and (not is_too_long) and (not exceeds_overlap)

        records.append(
            {
                "candidate_index": idx,
                "distance_miles": dist_mi,
                "duration_minutes": dur_min,
                "has_spur": has_spur,
                "is_too_long": is_too_long,
                "max_overlap": max_ov,
                "overlaps": overlaps,
                "is_valid": is_valid,
            }
        )

        if is_valid:
            # Rank surviving candidate by lowest max overlap
            survivors.append((max_ov, cand))

    if not survivors:
        return None, records

    # Sort survivors by least overlap
    survivors.sort(key=lambda s: s[0])
    best_candidate = survivors[0][1]
    return best_candidate, records
