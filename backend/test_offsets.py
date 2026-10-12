import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

import math
import requests
from safehaul.adapters.mapbox import MapboxRoutingAdapter, MAPBOX_DIRECTIONS_BASE_URL, METERS_TO_MILES
from safehaul.domain.route_geometry import evaluate_candidate_corridors, detect_out_and_back_spur, compute_geometry_overlap_percent

adapter = MapboxRoutingAdapter(enable_cache=False)
chicago = (41.8781, -87.6298)
kc = (39.0997, -94.5786)

# Get base routes
base_routes = adapter.get_routes(chicago, kc, enable_waypoint_fallback=False)
print(f"Base routes count: {len(base_routes)}")
for r in base_routes:
    print(f"  {r['label']}: {r['distance_miles']} mi, {r['duration_minutes']} min")

orig_lat, orig_lng = chicago
dest_lat, dest_lng = kc
mid_lat = (orig_lat + dest_lat) / 2.0
mid_lng = (orig_lng + dest_lng) / 2.0
d_lat = dest_lat - orig_lat
d_lng = dest_lng - orig_lng
norm = math.sqrt(d_lat**2 + d_lng**2) or 1.0
perp_lat = -d_lng / norm
perp_lng = d_lat / norm

offset_mags = [0.45, 0.8, 1.2, 1.6, 2.0, -0.45, -0.8, -1.2, -1.6, -2.0]
for off in offset_mags:
    wp_lat = mid_lat + perp_lat * off
    wp_lng = mid_lng + perp_lng * off
    coords_str = f"{orig_lng},{orig_lat};{wp_lng:.4f},{wp_lat:.4f};{dest_lng},{dest_lat}"
    url = f"{MAPBOX_DIRECTIONS_BASE_URL}/{coords_str}"
    params = {
        "geometries": "geojson",
        "overview": "full",
        "steps": "true",
        "annotations": "duration,distance",
        "access_token": adapter.access_token,
    }
    resp = requests.get(url, params=params, timeout=10.0)
    if resp.status_code != 200:
        continue
    data = resp.json()
    r = data["routes"][0]
    meters = float(r.get("distance", 0.0))
    dist_mi = round(meters * METERS_TO_MILES, 1)
    dur_min = round(float(r.get("duration", 0.0)) / 60.0)
    coords = r["geometry"]["coordinates"]
    spur = detect_out_and_back_spur(coords)
    best, records = evaluate_candidate_corridors([{"distance_miles": dist_mi, "duration_minutes": dur_min, "geometry": r["geometry"]}], base_routes)
    rec = records[0]
    print(f"Offset {off:+5.2f}: dist={dist_mi} mi, dur={dur_min} min, spur={spur}, max_overlap={rec['max_overlap']}%, valid={rec['is_valid']}")
