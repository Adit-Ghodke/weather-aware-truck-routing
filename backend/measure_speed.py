import time
import os
import requests
import math
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from datetime import datetime, UTC
from safehaul.adapters.mapbox import (
    MapboxRoutingAdapter,
    MAPBOX_DIRECTIONS_BASE_URL,
    METERS_TO_MILES,
)
from safehaul.adapters.weather import OpenMeteoWeatherAdapter
from safehaul.domain.sampling import sample_checkpoints, compute_segment_miles, auto_select_interval
from safehaul.domain.eta import compute_checkpoint_etas
from safehaul.domain.timezones import format_local_eta
from safehaul.domain.risk import classify_checkpoint
from safehaul.domain.ranking import compute_route_metrics, rank_routes
from safehaul.domain.route_geometry import evaluate_candidate_corridors

def profile_chicago_denver():
    chicago = (41.8781, -87.6298)
    denver = (39.7392, -104.9903)
    departure_utc = datetime(2026, 10, 13, 14, 0, tzinfo=UTC)
    load_weight_lb = 35000

    routing_adapter = MapboxRoutingAdapter(enable_cache=False)
    weather_adapter = OpenMeteoWeatherAdapter()

    total_start = time.perf_counter()

    # Step 1: Mapbox base call
    t0 = time.perf_counter()
    orig_lat, orig_lng = chicago
    dest_lat, dest_lng = denver
    coords_str = f"{orig_lng},{orig_lat};{dest_lng},{dest_lat}"
    url = f"{MAPBOX_DIRECTIONS_BASE_URL}/{coords_str}"
    params = {
        "alternatives": "true",
        "geometries": "geojson",
        "overview": "full",
        "steps": "true",
        "annotations": "duration,distance",
        "access_token": routing_adapter.access_token,
    }
    resp = requests.get(url, params=params, timeout=10.0)
    base_data = resp.json()
    base_routes = routing_adapter._parse_routes(base_data.get("routes", []))
    t_base = time.perf_counter() - t0

    # Step 2: Via-waypoint candidate calls (sequential baseline)
    mid_lat = (orig_lat + dest_lat) / 2.0
    mid_lng = (orig_lng + dest_lng) / 2.0
    d_lat = dest_lat - orig_lat
    d_lng = dest_lng - orig_lng
    norm = math.sqrt(d_lat**2 + d_lng**2) or 1.0
    perp_lat = -d_lng / norm
    perp_lng = d_lat / norm

    offset_mags = [0.45, 0.8, 1.2, 1.6, 2.0, -0.45, -0.8, -1.2, -1.6, -2.0]
    waypoint_timings = []
    raw_candidates = []

    for off in offset_mags:
        tw0 = time.perf_counter()
        wp_lat = mid_lat + perp_lat * off
        wp_lng = mid_lng + perp_lng * off
        wp_coords = f"{orig_lng},{orig_lat};{wp_lng:.4f},{wp_lat:.4f};{dest_lng},{dest_lat}"
        wp_url = f"{MAPBOX_DIRECTIONS_BASE_URL}/{wp_coords}"
        wp_params = {
            "geometries": "geojson",
            "overview": "full",
            "steps": "true",
            "annotations": "duration,distance",
            "access_token": routing_adapter.access_token,
        }
        w_resp = requests.get(wp_url, params=wp_params, timeout=10.0)
        tw_elapsed = time.perf_counter() - tw0
        waypoint_timings.append((off, tw_elapsed))

        if w_resp.status_code == 200:
            routes_list = w_resp.json().get("routes", [])
            if routes_list:
                cand = routes_list[0]
                meters = float(cand.get("distance", 0.0))
                seconds = float(cand.get("duration", 0.0))
                raw_candidates.append({
                    "distance_miles": round(meters * METERS_TO_MILES, 1),
                    "duration_minutes": round(seconds / 60.0),
                    "duration_seconds": seconds,
                    "geometry": cand.get("geometry", {}),
                    "segments": routing_adapter._parse_segments(cand.get("legs", [])),
                })

    # Step 3: Overlap and spur checks
    t_geom_start = time.perf_counter()
    best_candidate, records = evaluate_candidate_corridors(
        raw_candidates,
        base_routes,
        max_overlap_percent=80.0,
        max_length_ratio=1.40,
    )
    t_geom = time.perf_counter() - t_geom_start

    all_routes = list(base_routes)
    if best_candidate:
        best_candidate["id"] = "route-c"
        best_candidate["label"] = "Route C"
        all_routes.append(best_candidate)

    # Step 4: Checkpoints sampling & ETA
    t_sample_start = time.perf_counter()
    all_unique_coords = []
    for r in all_routes:
        dist_mi = r["distance_miles"]
        interval = auto_select_interval(dist_mi)
        checkpoints = sample_checkpoints(r["geometry"]["coordinates"], interval, dist_mi)
        seg_miles = compute_segment_miles(checkpoints, dist_mi)
        for i, cp in enumerate(checkpoints):
            cp["segment_miles"] = seg_miles[i]
        compute_checkpoint_etas(checkpoints, departure_utc, r.get("segments"), dist_mi, r.get("duration_seconds"))
        for cp in checkpoints:
            eta_local_iso, tz_name, tz_abbr = format_local_eta(cp["eta_utc"], cp["lat"], cp["lng"])
            cp["eta_local"] = eta_local_iso
            cp["timezone_abbr"] = tz_abbr
            all_unique_coords.append((cp["lat"], cp["lng"]))
        r["checkpoints"] = checkpoints
    unique_coords = list({(round(lat, 2), round(lng, 2)) for lat, lng in all_unique_coords})
    t_sample = time.perf_counter() - t_sample_start

    # Step 5: Weather fetch
    t_weather_start = time.perf_counter()
    weather_data = weather_adapter.get_forecast_for_locations(unique_coords)
    t_weather = time.perf_counter() - t_weather_start

    # Step 6: Classification and ranking
    t_class_start = time.perf_counter()
    from safehaul.domain.eta import interpolate_wind_at_eta, get_precip_at_eta
    for r in all_routes:
        for cp in r["checkpoints"]:
            norm_coord = (round(cp["lat"], 2), round(cp["lng"], 2))
            hourly = weather_data.get(norm_coord)
            if hourly:
                wind = interpolate_wind_at_eta(hourly, cp["eta_utc"])
                rain, snow = get_precip_at_eta(hourly, cp["eta_utc"])
                risk = classify_checkpoint(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow, load_lb=load_weight_lb)
                cp["level"] = risk["level"]
                cp["reason"] = risk["reason"]
            else:
                cp["level"] = "Low"
                cp["reason"] = "Weather unavailable"
        r["metrics"] = compute_route_metrics(r["checkpoints"], r["distance_miles"])
    recommendation = rank_routes(all_routes)
    t_class = time.perf_counter() - t_class_start

    total_time = time.perf_counter() - total_start

    print("================ TIMING TABLE (CHICAGO -> DENVER COLD) ================")
    print(f"| Component                                      | Time (s) |")
    print(f"|------------------------------------------------|----------|")
    print(f"| Mapbox base call (alternatives=true)           | {t_base:8.3f} |")
    for off, dur in waypoint_timings:
        print(f"|   Via-waypoint offset {off:+5.2f}° call               | {dur:8.3f} |")
    total_wp = sum(d for _, d in waypoint_timings)
    print(f"| Via-waypoint calls sum (10 calls sequential)   | {total_wp:8.3f} |")
    print(f"| Overlap and spur checks (geometry evaluation)  | {t_geom:8.3f} |")
    print(f"| Sampling & ETA calculation                     | {t_sample:8.3f} |")
    print(f"| Open-Meteo weather fetch ({len(unique_coords)} grid points)       | {t_weather:8.3f} |")
    print(f"| Risk classification and ranking                | {t_class:8.3f} |")
    print(f"|------------------------------------------------|----------|")
    print(f"| TOTAL PIPELINE TIME                            | {total_time:8.3f} |")
    print("=========================================================================")

if __name__ == "__main__":
    profile_chicago_denver()
