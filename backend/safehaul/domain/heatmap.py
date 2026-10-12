"""
SafeHaul Domain: Corridor Heatmap Grid Generation and Hourly Risk Matrix (§8g).

Specifications:
  • Bounding box of all candidate route coordinates + HEATMAP_BUFFER_DEG = 0.5.
  • Grid resolution: target ~0.1 degree steps, dynamically scaled to enforce
    a hard upper cap of MAX_HEATMAP_POINTS = 400.
  • For each grid point, computes 49 hourly risk scores (hours 0 to 48) where:
    0 = Low, 1 = Moderate, 2 = High, 3 = Severe, 4 = No Travel.
  • Pure Python domain logic (zero Django ORM dependencies).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from safehaul.domain.constants import (
    HEATMAP_BUFFER_DEG,
    LEVEL_ORDER,
    MAX_HEATMAP_POINTS,
)
from safehaul.domain.eta import (
    get_precip_at_eta,
    interpolate_wind_at_eta,
)
from safehaul.domain.risk import classify_checkpoint


def generate_corridor_grid(
    coordinates: list[list[float] | tuple[float, float]],
    max_points: int = MAX_HEATMAP_POINTS,
    buffer_deg: float = HEATMAP_BUFFER_DEG,
) -> list[tuple[float, float]]:
    """Generate a regular 2D grid covering the bounding box of route coordinates.

    Args:
        coordinates: List of [lng, lat] or (lng, lat) coordinates from routes.
        max_points: Hard upper bound on returned grid points (<= 400).
        buffer_deg: Expansion degrees added to each bounding box edge (0.5).

    Returns:
        List of (lat, lng) tuples within the corridor bounding box.
    """
    if not coordinates:
        return []

    # coordinates are typically [lng, lat]
    lngs = [c[0] for c in coordinates]
    lats = [c[1] for c in coordinates]

    min_lat = max(min(lats) - buffer_deg, -90.0)
    max_lat = min(max(lats) + buffer_deg, 90.0)
    min_lng = max(min(lngs) - buffer_deg, -180.0)
    max_lng = min(max(lngs) + buffer_deg, 180.0)

    lat_span = max_lat - min_lat
    lng_span = max_lng - min_lng

    # Degenerate single point
    if lat_span < 1e-6 and lng_span < 1e-6:
        return [(round((min_lat + max_lat) / 2, 4), round((min_lng + max_lng) / 2, 4))]

    # Target resolution ~0.1 degree step
    step = 0.1

    # Check total points at 0.1 degree step
    n_lat = max(math.ceil(lat_span / step) + 1, 1)
    n_lng = max(math.ceil(lng_span / step) + 1, 1)
    total_est = n_lat * n_lng

    # Scale step up if estimated point count exceeds cap
    if total_est > max_points:
        scale = math.sqrt(total_est / (max_points * 0.95))
        step *= scale
        n_lat = max(math.ceil(lat_span / step) + 1, 1)
        n_lng = max(math.ceil(lng_span / step) + 1, 1)

    grid: list[tuple[float, float]] = []
    # Generate points
    for i in range(n_lat):
        cur_lat = round(min_lat + i * step, 4)
        if cur_lat > max_lat + 1e-6:
            break
        for j in range(n_lng):
            cur_lng = round(min_lng + j * step, 4)
            if cur_lng > max_lng + 1e-6:
                break
            grid.append((cur_lat, cur_lng))
            if len(grid) >= max_points:
                return grid

    return grid


def compute_corridor_hourly_risks(
    grid_points: list[tuple[float, float]],
    departure_datetime_utc: datetime,
    forecasts: dict[tuple[float, float], dict[datetime, dict[str, float]]],
    load_weight_lb: int,
    num_hours: int = 49,
) -> list[dict[str, Any]]:
    """Compute hourly risk levels for each grid point across 0..48 hours.

    Args:
        grid_points: List of (lat, lng) grid positions.
        departure_datetime_utc: Departure timestamp in UTC.
        forecasts: Dict mapping (round(lat, 2), round(lng, 2)) -> hourly weather dict.
        load_weight_lb: Truck cargo load weight in lbs.
        num_hours: Number of hourly forecast slices (default 49: hours 0..48).

    Returns:
        List of dicts: {"lat": float, "lng": float, "hour_risks": list[int]}
        where hour_risks values are 0=Low, 1=Moderate, 2=High, 3=Severe, 4=No Travel.
    """
    results: list[dict[str, Any]] = []

    for lat, lng in grid_points:
        norm_coord = (round(lat, 2), round(lng, 2))
        hourly_weather = forecasts.get(norm_coord, {})

        hour_risks: list[int] = []
        for h in range(num_hours):
            target_dt = departure_datetime_utc + timedelta(hours=h)

            if hourly_weather:
                wind_mph = interpolate_wind_at_eta(hourly_weather, target_dt)
                rain_in_hr, snow_in_hr = get_precip_at_eta(hourly_weather, target_dt)

                risk_eval = classify_checkpoint(
                    wind_mph=wind_mph,
                    rain_in_hr=rain_in_hr,
                    snow_in_hr=snow_in_hr,
                    load_lb=load_weight_lb,
                )
                level_order = LEVEL_ORDER.get(risk_eval["level"], 1)
                risk_val = level_order - 1  # Map 1..5 to 0..4
            else:
                risk_val = 0  # Default Low risk when weather unavailable

            hour_risks.append(risk_val)

        results.append(
            {
                "lat": lat,
                "lng": lng,
                "hour_risks": hour_risks,
            }
        )

    return results
