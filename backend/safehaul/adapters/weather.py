"""
SafeHaul Open-Meteo weather adapter — hourly forecasts with batching and caching.

Specifications:
  • Provider (§DR-02): Open-Meteo forecast API (free tier, no API key).
  • Units (§A4, §A13): wind_speed_unit=mph; rain: mm/h / 25.4; snowfall: cm/h / 2.54.
  • Batching (§A17, §10): multi-location requests chunked in batches of <= 50 locations.
  • Caching (§10): 30-minute TTL (1800s) on rounded 2dp coordinates.
  • Resilience: Backoff on HTTP 429, graceful partial return on network errors.
"""

from __future__ import annotations

import concurrent.futures
import logging
import time
from datetime import UTC, datetime
from typing import Any

import requests

from safehaul.adapters.base import BaseWeatherAdapter
from safehaul.adapters.cache import get_resilient_cache

logger = logging.getLogger(__name__)

OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"
MAX_BATCH_SIZE = 50
WEATHER_CACHE_TTL_SECONDS = 1800  # 30 minutes
MM_TO_INCHES = 1.0 / 25.4
CM_TO_INCHES = 1.0 / 2.54


class OpenMeteoWeatherAdapter(BaseWeatherAdapter):
    """Adapter for Open-Meteo hourly weather forecast API."""

    def __init__(
        self,
        timeout: float = 15.0,
        max_retries: int = 2,
        forecast_days: int = 7,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.forecast_days = forecast_days
        self.cache = get_resilient_cache()

    def _coord_key(self, lat: float, lng: float) -> tuple[float, float]:
        """Normalize coordinates to 2 decimal places (~1 km grid)."""
        return round(lat, 2), round(lng, 2)

    def _cache_key(self, lat2dp: float, lng2dp: float) -> str:
        """Cache key for all 7-day hourly forecast slots for this coordinate."""
        return f"weather_loc:{lat2dp}:{lng2dp}"

    def get_forecast_for_locations(
        self,
        locations: list[tuple[float, float]],
    ) -> dict[tuple[float, float], dict[datetime, dict[str, float]]]:
        """Fetch hourly forecasts for given [lat, lng] locations.

        Returns:
            dict mapping (round(lat, 2), round(lng, 2)) to:
                {
                    datetime_utc: {
                        "wind_mph": float,
                        "gust_mph": float,
                        "rain_in_hr": float,
                        "snow_in_hr": float,
                        "temp_f": float,
                    },
                    ...
                }
        """
        if not locations:
            return {}

        # 1. Deduplicate by 2-decimal-place grid
        unique_coords: list[tuple[float, float]] = []
        seen = set()
        for lat, lng in locations:
            norm = self._coord_key(lat, lng)
            if norm not in seen:
                seen.add(norm)
                unique_coords.append(norm)

        results: dict[tuple[float, float], dict[datetime, dict[str, float]]] = {}
        missing_coords: list[tuple[float, float]] = []

        # 2. Check resilient cache
        for lat2dp, lng2dp in unique_coords:
            c_key = self._cache_key(lat2dp, lng2dp)
            cached_data = self.cache.get(c_key)
            if cached_data:
                results[(lat2dp, lng2dp)] = cached_data
            else:
                missing_coords.append((lat2dp, lng2dp))

        # 3. If all locations were cached, return immediately
        if not missing_coords:
            return results

        # 4. Fetch missing locations in batches of <= 50 (concurrently using ThreadPoolExecutor)
        batches = [missing_coords[i : i + MAX_BATCH_SIZE] for i in range(0, len(missing_coords), MAX_BATCH_SIZE)]
        if len(batches) == 1:
            batch_results = self._fetch_batch(batches[0])
            for coord, hourly_data in batch_results.items():
                results[coord] = hourly_data
                c_key = self._cache_key(coord[0], coord[1])
                self.cache.set(c_key, hourly_data, timeout=WEATHER_CACHE_TTL_SECONDS)
        elif len(batches) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(batches))) as executor:
                future_to_batch = {executor.submit(self._fetch_batch, b): b for b in batches}
                for future in concurrent.futures.as_completed(future_to_batch):
                    try:
                        batch_results = future.result()
                        for coord, hourly_data in batch_results.items():
                            results[coord] = hourly_data
                            c_key = self._cache_key(coord[0], coord[1])
                            self.cache.set(c_key, hourly_data, timeout=WEATHER_CACHE_TTL_SECONDS)
                    except Exception as err:
                        logger.warning(f"Error fetching weather batch: {err}")

        return results

    def _fetch_batch(
        self,
        batch: list[tuple[float, float]],
    ) -> dict[tuple[float, float], dict[datetime, dict[str, float]]]:
        """Fetch a single batch of up to 50 coordinates from Open-Meteo."""
        lats_str = ",".join(str(lat) for lat, _ in batch)
        lngs_str = ",".join(str(lng) for _, lng in batch)

        params = {
            "latitude": lats_str,
            "longitude": lngs_str,
            "hourly": "temperature_2m,wind_speed_10m,wind_gusts_10m,rain,snowfall",
            "wind_speed_unit": "mph",
            "forecast_days": str(self.forecast_days),
        }

        response = self._request_with_retry(params)
        if response is None or response.status_code != 200:
            logger.warning("Open-Meteo request failed after retries; returning empty for batch.")
            return {}

        data = response.json()
        return self._parse_batch_response(batch, data)

    def _request_with_retry(self, params: dict) -> requests.Response | None:
        """Execute request with retries and backoff for HTTP 429 rate limits."""
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.get(OPEN_METEO_BASE_URL, params=params, timeout=self.timeout)
                if response.status_code == 200:
                    return response
                elif response.status_code == 429:
                    logger.warning(f"Open-Meteo HTTP 429 rate limit (attempt {attempt + 1}). Backing off.")
                    time.sleep(0.5 * (2**attempt))
                else:
                    logger.error(f"Open-Meteo returned HTTP {response.status_code}: {response.text[:200]}")
                    return None
            except requests.RequestException as err:
                logger.error(f"Network error on Open-Meteo attempt {attempt + 1}: {err}")
                if attempt == self.max_retries:
                    return None
                time.sleep(0.5 * (2**attempt))

        return None

    def _parse_batch_response(
        self,
        batch: list[tuple[float, float]],
        data: Any,
    ) -> dict[tuple[float, float], dict[datetime, dict[str, float]]]:
        """Parse single-object or array response from Open-Meteo."""
        results: dict[tuple[float, float], dict[datetime, dict[str, float]]] = {}

        # If 1 location requested, Open-Meteo returns a single dict
        if isinstance(data, dict):
            location_items = [data]
        elif isinstance(data, list):
            location_items = data
        else:
            return {}

        for idx, loc_item in enumerate(location_items):
            if idx >= len(batch):
                break
            coord = batch[idx]
            hourly_block = loc_item.get("hourly", {})
            results[coord] = self._parse_hourly_block(hourly_block)

        return results

    def _parse_hourly_block(
        self,
        hourly: dict,
    ) -> dict[datetime, dict[str, float]]:
        """Parse hourly block and convert units."""
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        winds = hourly.get("wind_speed_10m", [])
        gusts = hourly.get("wind_gusts_10m", [])
        rains = hourly.get("rain", [])
        snows = hourly.get("snowfall", [])

        parsed: dict[datetime, dict[str, float]] = {}

        for i, t_str in enumerate(times):
            # Parse ISO e.g. "2025-01-20T14:00" -> UTC datetime
            try:
                dt_utc = datetime.fromisoformat(t_str).replace(tzinfo=UTC)
            except (ValueError, TypeError):
                continue

            wind_mph = float(winds[i]) if i < len(winds) and winds[i] is not None else 0.0
            gust_mph = float(gusts[i]) if i < len(gusts) and gusts[i] is not None else wind_mph

            # Rain: mm/hr -> in/hr
            rain_mm = float(rains[i]) if i < len(rains) and rains[i] is not None else 0.0
            rain_in_hr = round(rain_mm * MM_TO_INCHES, 2)

            # Snow: cm/hr -> in/hr
            snow_cm = float(snows[i]) if i < len(snows) and snows[i] is not None else 0.0
            snow_in_hr = round(snow_cm * CM_TO_INCHES, 2)

            # Temp
            temp_c = float(temps[i]) if i < len(temps) and temps[i] is not None else 0.0
            temp_f = round(temp_c * 9.0 / 5.0 + 32.0, 1)

            parsed[dt_utc] = {
                "wind_mph": round(wind_mph, 1),
                "gust_mph": round(gust_mph, 1),
                "rain_in_hr": rain_in_hr,
                "snow_in_hr": snow_in_hr,
                "temp_f": temp_f,
            }

        return parsed
