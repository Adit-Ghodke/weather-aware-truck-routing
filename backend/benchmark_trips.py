import os
import time
import django
from datetime import datetime, UTC

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from safehaul.adapters.cache import get_resilient_cache
from safehaul.adapters.mapbox import MapboxRoutingAdapter
from safehaul.adapters.weather import OpenMeteoWeatherAdapter
from safehaul.domain.sampling import sample_checkpoints, compute_segment_miles, auto_select_interval
from safehaul.domain.eta import compute_checkpoint_etas, interpolate_wind_at_eta, get_precip_at_eta
from safehaul.domain.timezones import format_local_eta
from safehaul.domain.risk import classify_checkpoint
from safehaul.domain.ranking import compute_route_metrics, rank_routes

def run_trip_pipeline(origin, destination, dep_dt, load_weight, enable_cache=True):
    routing_adapter = MapboxRoutingAdapter(enable_cache=enable_cache)
    weather_adapter = OpenMeteoWeatherAdapter()

    t0 = time.perf_counter()

    # 1. Routing
    candidate_routes = routing_adapter.get_routes(
        origin,
        destination,
        enable_waypoint_fallback=True,
        departure_hour=dep_dt.hour,
    )
    t_routing = time.perf_counter() - t0

    # 2. Checkpoints & ETA
    t1 = time.perf_counter()
    all_coords = []
    for r in candidate_routes:
        dist = r["distance_miles"]
        interval = auto_select_interval(dist)
        cps = sample_checkpoints(r["geometry"]["coordinates"], interval, dist)
        seg_miles = compute_segment_miles(cps, dist)
        for i, cp in enumerate(cps):
            cp["segment_miles"] = seg_miles[i]
        compute_checkpoint_etas(cps, dep_dt, r.get("segments"), dist, r.get("duration_seconds"))
        for cp in cps:
            eta_local, tz_name, tz_abbr = format_local_eta(cp["eta_utc"], cp["lat"], cp["lng"])
            cp["eta_local"] = eta_local
            cp["timezone_abbr"] = tz_abbr
            all_coords.append((cp["lat"], cp["lng"]))
        r["checkpoints"] = cps
    unique_coords = list({(round(lat, 2), round(lng, 2)) for lat, lng in all_coords})
    t_checkpoints = time.perf_counter() - t1

    # 3. Weather fetch
    t2 = time.perf_counter()
    forecasts = weather_adapter.get_forecast_for_locations(unique_coords)
    t_weather = time.perf_counter() - t2

    # 4. Classification & ranking
    t3 = time.perf_counter()
    for r in candidate_routes:
        for cp in r["checkpoints"]:
            norm_coord = (round(cp["lat"], 2), round(cp["lng"], 2))
            hourly = forecasts.get(norm_coord)
            if hourly:
                wind = interpolate_wind_at_eta(hourly, cp["eta_utc"])
                rain, snow = get_precip_at_eta(hourly, cp["eta_utc"])
                risk = classify_checkpoint(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow, load_lb=load_weight)
                cp["level"] = risk["level"]
                cp["reason"] = risk["reason"]
            else:
                cp["level"] = "Low"
                cp["reason"] = "Weather unavailable"
        r["metrics"] = compute_route_metrics(r["checkpoints"], r["distance_miles"])

    rec = rank_routes(candidate_routes)
    t_ranking = time.perf_counter() - t3

    total_time = time.perf_counter() - t0

    return {
        "total_time": total_time,
        "routing_time": t_routing,
        "checkpoints_time": t_checkpoints,
        "weather_time": t_weather,
        "ranking_time": t_ranking,
        "routes_count": len(candidate_routes),
        "route_labels": [r["label"] for r in candidate_routes],
        "route_c": candidate_routes[2] if len(candidate_routes) > 2 else None,
        "recommendation": rec["explanation"],
    }

def main():
    cache = get_resilient_cache()
    chicago = (41.8781, -87.6298)
    kc = (39.0997, -94.5786)
    denver = (39.7392, -104.9903)
    departure_utc = datetime(2026, 10, 13, 15, 0, tzinfo=UTC)

    # 1. Chicago -> Kansas City COLD
    cache.clear()
    res_kc_cold = run_trip_pipeline(chicago, kc, departure_utc, 35000, enable_cache=True)
    print("\n--- CHICAGO -> KANSAS CITY (COLD) ---")
    print(f"Total time: {res_kc_cold['total_time']:.3f} s (Routing: {res_kc_cold['routing_time']:.3f} s, Weather: {res_kc_cold['weather_time']:.3f} s)")
    print(f"Routes: {res_kc_cold['routes_count']} - {res_kc_cold['route_labels']}")
    if res_kc_cold['route_c']:
        r_c = res_kc_cold['route_c']
        print(f"Route C: {r_c['distance_miles']} mi, {r_c['duration_minutes']} min")
    print(f"Deciding explanation: {res_kc_cold['recommendation']}")

    # 2. Chicago -> Kansas City WARM
    res_kc_warm = run_trip_pipeline(chicago, kc, departure_utc, 35000, enable_cache=True)
    print("\n--- CHICAGO -> KANSAS CITY (WARM) ---")
    print(f"Total time: {res_kc_warm['total_time']:.3f} s (Routing: {res_kc_warm['routing_time']:.3f} s, Weather: {res_kc_warm['weather_time']:.3f} s)")

    # 3. Chicago -> Denver COLD
    cache.clear()
    res_denver_cold = run_trip_pipeline(chicago, denver, departure_utc, 35000, enable_cache=True)
    print("\n--- CHICAGO -> DENVER (COLD) ---")
    print(f"Total time: {res_denver_cold['total_time']:.3f} s (Routing: {res_denver_cold['routing_time']:.3f} s, Weather: {res_denver_cold['weather_time']:.3f} s)")
    print(f"Routes: {res_denver_cold['routes_count']} - {res_denver_cold['route_labels']}")
    if res_denver_cold['route_c']:
        r_c = res_denver_cold['route_c']
        print(f"Route C: {r_c['distance_miles']} mi, {r_c['duration_minutes']} min")
    print(f"Deciding explanation: {res_denver_cold['recommendation']}")

if __name__ == "__main__":
    main()
