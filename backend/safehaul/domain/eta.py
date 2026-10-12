"""
SafeHaul ETA calculation and weather slot interpolation — pure business logic.

Public API:
    compute_checkpoint_eta(...) -> tuple[datetime, str]
    compute_checkpoint_etas(...) -> list[dict]
    interpolate_wind_at_eta(weather_by_hour, eta_utc) -> float
    interpolate_gust_at_eta(weather_by_hour, eta_utc) -> float
    get_precip_at_eta(weather_by_hour, eta_utc) -> tuple[float, float]

All algorithms are specified in docs/BUILD_PLAN.md §8b, §8c, and §A2/A4.
Zero Django or external network dependencies.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def compute_checkpoint_eta(
    departure_datetime_utc: datetime,
    checkpoint_mile_marker: float,
    route_segments: list[dict] | None = None,
    total_distance_miles: float | None = None,
    total_duration_seconds: float | None = None,
) -> tuple[datetime, str]:
    """Compute the estimated time of arrival (ETA in UTC) at a given mile marker.

    Methods (§8b, §A2):
      1. per_segment: Uses per-segment duration data from routing directions.
      2. approximate (proportional): Falls back to total_duration * (mile / total_dist)
         when segment data is missing or incomplete.

    Returns:
        (eta_utc: datetime, method: str)  where method is "per_segment" or "approximate"
    """
    # Origin is always exactly at departure time
    if checkpoint_mile_marker <= 0.0:
        return departure_datetime_utc, "exact"

    # Attempt per-segment computation if segments are provided
    if route_segments:
        elapsed_seconds = 0.0
        covered = False
        for seg in route_segments:
            seg_start = float(seg["start_mile"])
            seg_end = float(seg["end_mile"])
            seg_dur = float(seg["duration_seconds"])

            if seg_end <= checkpoint_mile_marker:
                elapsed_seconds += seg_dur
            elif seg_start <= checkpoint_mile_marker <= seg_end:
                seg_span = seg_end - seg_start
                if seg_span > 1e-9:
                    fraction = (checkpoint_mile_marker - seg_start) / seg_span
                else:
                    fraction = 0.0
                elapsed_seconds += seg_dur * fraction
                covered = True
                break

        # If checkpoint falls within or at the end of the segments
        if covered or (route_segments and checkpoint_mile_marker >= route_segments[-1]["end_mile"]):
            eta = departure_datetime_utc + timedelta(seconds=round(elapsed_seconds))
            return eta, "per_segment"

    # Proportional fallback
    if total_distance_miles and total_duration_seconds and total_distance_miles > 0:
        fraction = checkpoint_mile_marker / total_distance_miles
        fraction = max(0.0, min(1.0, fraction))
        elapsed_seconds = total_duration_seconds * fraction
        eta = departure_datetime_utc + timedelta(seconds=round(elapsed_seconds))
        return eta, "approximate"

    # Degenerate fallback (0 speed / unknown duration)
    return departure_datetime_utc, "approximate"


def compute_checkpoint_etas(
    checkpoints: list[dict],
    departure_datetime_utc: datetime,
    route_segments: list[dict] | None = None,
    total_distance_miles: float | None = None,
    total_duration_seconds: float | None = None,
) -> list[dict]:
    """Attach computed eta_utc and eta_method to each checkpoint dict in-place."""
    for cp in checkpoints:
        mile = cp.get("mile_marker", 0.0)
        eta_utc, method = compute_checkpoint_eta(
            departure_datetime_utc=departure_datetime_utc,
            checkpoint_mile_marker=mile,
            route_segments=route_segments,
            total_distance_miles=total_distance_miles,
            total_duration_seconds=total_duration_seconds,
        )
        cp["eta_utc"] = eta_utc
        cp["eta_method"] = method
    return checkpoints


# ── Weather Lookup at ETA (§8c, §A4) ──────────────────────────────────────

def _get_hour_boundary(dt: datetime) -> datetime:
    """Floor a datetime to the top of the hour."""
    return dt.replace(minute=0, second=0, microsecond=0)


def interpolate_wind_at_eta(
    weather_by_hour: dict[datetime, dict],
    eta_utc: datetime,
) -> float:
    """Instantaneous wind speed (mph) via linear interpolation between hourly slots.

    Formula (§8c):
      fraction = (eta_utc - h_floor).seconds / 3600
      wind = weather[h_floor].wind + fraction * (weather[h_ceil].wind - weather[h_floor].wind)
    """
    h_floor = _get_hour_boundary(eta_utc)
    h_ceil = h_floor + timedelta(hours=1)

    if h_floor in weather_by_hour and h_ceil in weather_by_hour:
        w_floor = float(weather_by_hour[h_floor].get("wind_mph", 0.0))
        w_ceil = float(weather_by_hour[h_ceil].get("wind_mph", 0.0))
        fraction = (eta_utc - h_floor).total_seconds() / 3600.0
        return round(w_floor + fraction * (w_ceil - w_floor), 1)

    if h_floor in weather_by_hour:
        return round(float(weather_by_hour[h_floor].get("wind_mph", 0.0)), 1)

    return 0.0


def interpolate_gust_at_eta(
    weather_by_hour: dict[datetime, dict],
    eta_utc: datetime,
) -> float:
    """Instantaneous wind gust (mph) via linear interpolation (display only)."""
    h_floor = _get_hour_boundary(eta_utc)
    h_ceil = h_floor + timedelta(hours=1)

    if h_floor in weather_by_hour and h_ceil in weather_by_hour:
        g_floor = float(weather_by_hour[h_floor].get("gust_mph", 0.0))
        g_ceil = float(weather_by_hour[h_ceil].get("gust_mph", 0.0))
        fraction = (eta_utc - h_floor).total_seconds() / 3600.0
        return round(g_floor + fraction * (g_ceil - g_floor), 1)

    if h_floor in weather_by_hour:
        return round(float(weather_by_hour[h_floor].get("gust_mph", 0.0)), 1)

    return 0.0


def get_precip_at_eta(
    weather_by_hour: dict[datetime, dict],
    eta_utc: datetime,
) -> tuple[float, float]:
    """Retrieve hourly precipitation totals (in/hr) for rain and snow covering ETA.

    Open-Meteo Convention (§8c, §A4):
      Hourly precipitation data (rain, snowfall) is defined as the "preceding hour sum"
      representing total accumulation during the hour leading up to the slot timestamp.
      Therefore, precipitation at an ETA uses the slot whose timestamp is the next full
      hour after the ETA (e.g. ETA 07:51 UTC uses slot 08:00 UTC).
    Returns:
        (rain_in_hr, snow_in_hr)
    """
    h_floor = _get_hour_boundary(eta_utc)
    # The slot whose timestamp is the next full hour after the ETA
    h_next = h_floor + timedelta(hours=1)

    if h_next in weather_by_hour:
        rain = float(weather_by_hour[h_next].get("rain_in_hr", 0.0))
        snow = float(weather_by_hour[h_next].get("snow_in_hr", 0.0))
        return round(rain, 2), round(snow, 2)

    # Fallback to floor hour if next hour is beyond forecast boundary
    if h_floor in weather_by_hour:
        rain = float(weather_by_hour[h_floor].get("rain_in_hr", 0.0))
        snow = float(weather_by_hour[h_floor].get("snow_in_hr", 0.0))
        return round(rain, 2), round(snow, 2)

    return 0.0, 0.0


def get_weather_slots(eta_utc: datetime) -> dict[str, Any]:
    """Return slot timestamps for weather variables at ETA."""
    h_floor = _get_hour_boundary(eta_utc)
    h_ceil = h_floor + timedelta(hours=1)
    return {
        "precip_slot_utc": h_ceil.isoformat(),
        "wind_slots_utc": [h_floor.isoformat(), h_ceil.isoformat()],
    }

