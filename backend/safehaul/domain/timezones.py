"""
SafeHaul timezone resolution and local formatting.

Specifications (§A3, §7):
  • Resolves timezone name (e.g. "America/Chicago") from coordinates [lat, lng].
  • Attempts timezonefinder; seamlessly falls back to resilient North American
    geographic longitude bands if C-extension DLLs are blocked by OS security policies.
  • Converts UTC ETA to local datetime with ISO-8601 offset and timezone abbreviation (e.g. "CST").
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Global cached instance of TimezoneFinder (if working)
_TF_INSTANCE = None
_TF_FAILED = False


def _get_timezone_finder():
    global _TF_INSTANCE, _TF_FAILED
    if _TF_FAILED:
        return None
    if _TF_INSTANCE is None:
        try:
            from timezonefinder import TimezoneFinder
            _TF_INSTANCE = TimezoneFinder()
        except Exception as err:
            logger.warning(f"TimezoneFinder unavailable ({err}); using geographic fallback.")
            _TF_FAILED = True
            return None
    return _TF_INSTANCE


def resolve_timezone_name(lat: float, lng: float) -> str:
    """Resolve IANA timezone string (e.g. 'America/Chicago') from [lat, lng]."""
    tf = _get_timezone_finder()
    if tf is not None:
        try:
            tz_name = tf.timezone_at(lng=lng, lat=lat)
            if tz_name:
                return tz_name
        except Exception:
            pass

    # Resilient geographic fallback if TimezoneFinder is unavailable:
    # 1. North American corridor
    if -170.0 <= lng <= -50.0 and 15.0 <= lat <= 75.0:
        if lat > 50.0 and lng < -130.0:
            return "America/Anchorage"
        if lat < 25.0 and lng < -150.0:
            return "Pacific/Honolulu"
        if lng >= -85.0:
            return "America/New_York"
        elif lng >= -103.0:
            return "America/Chicago"
        elif lng >= -115.0:
            return "America/Denver"
        else:
            return "America/Los_Angeles"

    # 2. Universal global fallback by longitude (15° per hour)
    offset_hours = round(lng / 15.0)
    if offset_hours == 0:
        return "UTC"
    elif offset_hours > 0:
        return f"Etc/GMT-{offset_hours}"
    else:
        return f"Etc/GMT+{abs(offset_hours)}"


def format_local_eta(
    dt_utc: datetime,
    lat: float,
    lng: float,
) -> tuple[str, str, str]:
    """Convert UTC ETA to local time strings for a given coordinate.

    Returns:
        (eta_local_iso, timezone_name, timezone_abbr)
        Example: ("2025-01-20T08:00:00-06:00", "America/Chicago", "CST")
    """
    tz_name = resolve_timezone_name(lat, lng)
    try:
        zone = ZoneInfo(tz_name)
        dt_local = dt_utc.astimezone(zone)
        eta_local_iso = dt_local.isoformat()
        tz_abbr = dt_local.strftime("%Z")
    except Exception:
        eta_local_iso = dt_utc.isoformat()
        tz_name = "UTC"
        tz_abbr = "UTC"

    return eta_local_iso, tz_name, tz_abbr
