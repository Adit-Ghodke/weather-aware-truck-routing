"""
SafeHaul Mapbox adapters — Directions (Routing) and Geocoding APIs.

Specifications:
  • Routing (§DR-01, §7, §A16): Directions API driving profile. Alternatives enabled.
    Per-request caching controlled by ENABLE_ROUTE_CACHE (default False).
  • Geocoding (§DR-01, §7, §A15): Ephemeral queries only. NO persistent backend cache.
"""

from __future__ import annotations

import concurrent.futures
import logging
import urllib.parse

import requests
from django.conf import settings

from safehaul.adapters.base import (
    BaseGeocodingAdapter,
    BaseRoutingAdapter,
    GeocodingUnavailableException,
    RoutingUnavailableException,
)
from safehaul.adapters.cache import get_resilient_cache
from safehaul.domain.route_geometry import evaluate_candidate_corridors

logger = logging.getLogger(__name__)

MAPBOX_DIRECTIONS_BASE_URL = "https://api.mapbox.com/directions/v5/mapbox/driving"
MAPBOX_GEOCODING_BASE_URL = "https://api.mapbox.com/geocoding/v5/mapbox.places"
METERS_TO_MILES = 1.0 / 1609.344
ROUTE_CACHE_TTL_SECONDS = 300  # 5 minutes


class MapboxRoutingAdapter(BaseRoutingAdapter):
    """Adapter for Mapbox Directions API."""

    def __init__(
        self,
        access_token: str | None = None,
        enable_cache: bool | None = None,
        timeout: float = 10.0,
    ):
        self.access_token = access_token or getattr(settings, "MAPBOX_ACCESS_TOKEN", "")
        if enable_cache is not None:
            self.enable_cache = enable_cache
        else:
            self.enable_cache = getattr(settings, "ENABLE_ROUTE_CACHE", True)
        self.timeout = timeout
        self.cache = get_resilient_cache()

    def _get_cache_key(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        departure_hour: int | None = None,
    ) -> str:
        orig_lat, orig_lng = origin
        dest_lat, dest_lng = destination
        dep_suffix = f":{departure_hour}" if departure_hour is not None else ""
        return f"routes:{round(orig_lat, 2):.2f}:{round(orig_lng, 2):.2f}:{round(dest_lat, 2):.2f}:{round(dest_lng, 2):.2f}{dep_suffix}"

    def get_routes(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        enable_waypoint_fallback: bool = False,
        departure_hour: int | None = None,
    ) -> list[dict]:
        """Fetch candidate routes from origin [lat, lng] to destination [lat, lng].

        Coordinates in Mapbox request URL format: lng,lat;lng,lat
        """
        orig_lat, orig_lng = origin
        dest_lat, dest_lng = destination

        # 1. Check cache if enabled
        cache_key = self._get_cache_key(origin, destination, departure_hour)
        if self.enable_cache:
            cached_routes = self.cache.get(cache_key)
            if cached_routes:
                logger.debug(f"MapboxRoutingAdapter: Cache hit for key {cache_key}")
                return cached_routes

        # 2. Build request URL and parameters
        coords_str = f"{orig_lng},{orig_lat};{dest_lng},{dest_lat}"
        url = f"{MAPBOX_DIRECTIONS_BASE_URL}/{coords_str}"
        params = {
            "alternatives": "true",
            "geometries": "geojson",
            "overview": "full",
            "steps": "true",
            "annotations": "duration,distance",
            "access_token": self.access_token,
        }

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as err:
            logger.error(f"Mapbox Directions request failed: {err}")
            raise RoutingUnavailableException(f"Network error contacting Mapbox Directions: {err}") from err

        if response.status_code != 200:
            logger.error(f"Mapbox Directions returned HTTP {response.status_code}: {response.text}")
            raise RoutingUnavailableException(
                f"Mapbox Directions error (HTTP {response.status_code}): {response.text[:200]}"
            )

        data = response.json()
        raw_routes = data.get("routes", [])
        if not raw_routes:
            raise RoutingUnavailableException("Mapbox Directions returned 0 routes for given coordinates.")

        parsed_routes = self._parse_routes(raw_routes)

        # 3. Via-waypoint fallback if fewer than 3 routes returned (§A9, §R1)
        if enable_waypoint_fallback and len(parsed_routes) < 3:
            parsed_routes = self._generate_waypoint_alternatives(
                origin, destination, parsed_routes, target_count=3
            )

        # 4. Store in cache if enabled
        if self.enable_cache:
            self.cache.set(cache_key, parsed_routes, timeout=ROUTE_CACHE_TTL_SECONDS)

        return parsed_routes

    def _fetch_single_waypoint_candidate(
        self,
        orig_lat: float,
        orig_lng: float,
        dest_lat: float,
        dest_lng: float,
        wp_lat: float,
        wp_lng: float,
    ) -> dict | None:
        coords_str = f"{orig_lng},{orig_lat};{wp_lng:.4f},{wp_lat:.4f};{dest_lng},{dest_lat}"
        url = f"{MAPBOX_DIRECTIONS_BASE_URL}/{coords_str}"
        params = {
            "geometries": "geojson",
            "overview": "full",
            "steps": "true",
            "annotations": "duration,distance",
            "access_token": self.access_token,
        }
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                return None
            data = resp.json()
            raw_list = data.get("routes", [])
            if not raw_list:
                return None

            raw_candidate = raw_list[0]
            meters = float(raw_candidate.get("distance", 0.0))
            seconds = float(raw_candidate.get("duration", 0.0))
            dist_mi = round(meters * METERS_TO_MILES, 1)
            dur_min = round(seconds / 60.0)

            return {
                "distance_miles": dist_mi,
                "duration_minutes": dur_min,
                "duration_seconds": seconds,
                "geometry": raw_candidate.get("geometry", {}),
                "segments": self._parse_segments(raw_candidate.get("legs", [])),
            }
        except Exception as err:
            logger.debug(f"Waypoint alternative request failed: {err}")
            return None

    def _generate_waypoint_alternatives(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        existing_routes: list[dict],
        target_count: int = 3,
    ) -> list[dict]:
        """Generate additional candidate routes by adding perpendicular via-waypoints (§A9, §R1, §Fix 2).

        Runs via-waypoint requests in parallel with ThreadPoolExecutor and stops early once
        a candidate passes all corridor validation checks (spurs, overlap <= 80%, length ratio <= 1.40).
        """
        orig_lat, orig_lng = origin
        dest_lat, dest_lng = destination

        d_lat = dest_lat - orig_lat
        d_lng = dest_lng - orig_lng
        norm = (d_lat**2 + d_lng**2)**0.5
        if norm < 0.001:
            return list(existing_routes)

        mid_lat = (orig_lat + dest_lat) / 2.0
        mid_lng = (orig_lng + dest_lng) / 2.0

        # Perpendicular unit vectors
        perp_lat = -d_lng / norm
        perp_lng = d_lat / norm

        # Offsets grouped into parallel batches to enable early stopping (§Fix 2)
        offset_batches = [
            [-2.0, -1.2, 0.45, 0.8, 1.6],
            [1.2, 2.0, -0.45, -0.8, -1.6],
        ]

        best_candidate = None
        for batch in offset_batches:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch)) as executor:
                futures = [
                    executor.submit(
                        self._fetch_single_waypoint_candidate,
                        orig_lat,
                        orig_lng,
                        dest_lat,
                        dest_lng,
                        mid_lat + perp_lat * off,
                        mid_lng + perp_lng * off,
                    )
                    for off in batch
                ]
                batch_candidates = [
                    cand for f in concurrent.futures.as_completed(futures) if (cand := f.result()) is not None
                ]

            if batch_candidates:
                best_candidate, _ = evaluate_candidate_corridors(
                    batch_candidates,
                    existing_routes,
                    max_overlap_percent=80.0,
                    max_length_ratio=1.40,
                )
                if best_candidate:
                    # Stop early once candidate passes all checks (§Fix 2)
                    break

        routes = list(existing_routes)
        if best_candidate:
            new_idx = len(routes)
            labels = ["Route A", "Route B", "Route C", "Route D", "Route E"]
            ids = ["route-a", "route-b", "route-c", "route-d", "route-e"]
            best_candidate["id"] = ids[new_idx] if new_idx < len(ids) else f"route-{new_idx + 1}"
            best_candidate["label"] = labels[new_idx] if new_idx < len(labels) else f"Route {new_idx + 1}"
            routes.append(best_candidate)
        else:
            logger.info("No waypoint alternative passed corridor validation (spurs/overlap/length). Returning valid routes only.")

        return routes

    def _parse_routes(self, raw_routes: list[dict]) -> list[dict]:
        labels = ["Route A", "Route B", "Route C", "Route D", "Route E"]
        ids = ["route-a", "route-b", "route-c", "route-d", "route-e"]

        parsed = []
        for idx, r in enumerate(raw_routes):
            route_id = ids[idx] if idx < len(ids) else f"route-{idx + 1}"
            label = labels[idx] if idx < len(labels) else f"Route {idx + 1}"

            meters = float(r.get("distance", 0.0))
            seconds = float(r.get("duration", 0.0))
            distance_miles = round(meters * METERS_TO_MILES, 1)
            duration_minutes = round(seconds / 60.0)

            geometry = r.get("geometry", {})
            legs = r.get("legs", [])

            # Parse segments from legs/steps for ETA calculation
            segments = self._parse_segments(legs)

            parsed.append(
                {
                    "id": route_id,
                    "label": label,
                    "distance_miles": distance_miles,
                    "duration_minutes": duration_minutes,
                    "duration_seconds": seconds,
                    "geometry": geometry,
                    "segments": segments,
                }
            )

        return parsed

    def _parse_segments(self, legs: list[dict]) -> list[dict]:
        """Extract sequential route segments with cumulative mile markers and duration."""
        segments = []
        cum_miles = 0.0

        for leg in legs:
            steps = leg.get("steps", [])
            for step in steps:
                step_dist_mi = step.get("distance", 0.0) * METERS_TO_MILES
                step_dur_s = step.get("duration", 0.0)
                end_mile = round(cum_miles + step_dist_mi, 4)

                segments.append(
                    {
                        "start_mile": round(cum_miles, 4),
                        "end_mile": end_mile,
                        "duration_seconds": step_dur_s,
                    }
                )
                cum_miles = end_mile

        return segments


class MapboxGeocodingAdapter(BaseGeocodingAdapter):
    """Adapter for Mapbox Temporary Geocoding API (Strictly ephemeral, NO caching)."""

    def __init__(
        self,
        access_token: str | None = None,
        timeout: float = 5.0,
    ):
        self.access_token = access_token or getattr(settings, "MAPBOX_ACCESS_TOKEN", "")
        self.timeout = timeout

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Search places by text query, returning up to 5 results {label, lat, lng}.

        NO backend caching per Mapbox Temporary Geocoding Terms (§A15).
        """
        clean_query = query.strip()
        if not clean_query or len(clean_query) < 2:
            return []

        encoded_query = urllib.parse.quote(clean_query)
        url = f"{MAPBOX_GEOCODING_BASE_URL}/{encoded_query}.json"
        params = {
            "limit": min(limit, 5),
            "types": "place,locality,neighborhood,address,poi",
            "access_token": self.access_token,
        }

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as err:
            logger.error(f"Mapbox Geocoding request failed: {err}")
            raise GeocodingUnavailableException(f"Network error contacting Mapbox Geocoding: {err}") from err

        if response.status_code != 200:
            logger.error(f"Mapbox Geocoding returned HTTP {response.status_code}: {response.text}")
            raise GeocodingUnavailableException(
                f"Mapbox Geocoding error (HTTP {response.status_code}): {response.text[:200]}"
            )

        data = response.json()
        features = data.get("features", [])

        results = []
        for feat in features:
            center = feat.get("center", [0.0, 0.0])
            results.append(
                {
                    "label": feat.get("place_name", clean_query),
                    "lng": round(center[0], 6),
                    "lat": round(center[1], 6),
                }
            )

        return results[:limit]

    geocode = search

