import time
import requests

BASE_URL = "http://127.0.0.1:8000"

def benchmark():
    # 1. Analyze trip for Chicago -> Denver
    payload = {
        "origin": {"label": "Chicago, IL", "lat": 41.8781, "lng": -87.6298},
        "destination": {"label": "Denver, CO", "lat": 39.7392, "lng": -104.9903},
        "departure_datetime": "2026-10-13T16:00:00",
        "load_weight_lb": 35000,
    }
    
    print("Testing Analyze Trip (Chicago -> Denver)...")
    t0 = time.time()
    try:
        resp = requests.post(f"{BASE_URL}/api/v1/trips/analyze/", json=payload, timeout=60)
    except Exception as e:
        print(f"Server not running or connection error: {e}")
        return
    t1 = time.time()
    print(f"Analyze Trip: status={resp.status_code}, time={t1 - t0:.3f}s")
    if resp.status_code != 200:
        print(resp.text)
        return
    data = resp.json()
    trip_id = data["id"]
    print(f"Trip ID: {trip_id}")

    # 2. First Heatmap request
    heatmap_payload = {
        "trip_id": trip_id,
        "load_weight_lb": 35000,
    }
    print("Testing First Heatmap Load...")
    t2 = time.time()
    resp_hm1 = requests.post(f"{BASE_URL}/api/v1/trips/heatmap/", json=heatmap_payload, timeout=60)
    t3 = time.time()
    hm1_data = resp_hm1.json()
    grid_points = len(hm1_data.get("grid", []))
    print(f"Heatmap 1st Load: status={resp_hm1.status_code}, time={t3 - t2:.3f}s, grid_points={grid_points}")

    # 3. Second Heatmap request (Cached)
    print("Testing Second Heatmap Load (Cache Target < 1s)...")
    t4 = time.time()
    resp_hm2 = requests.post(f"{BASE_URL}/api/v1/trips/heatmap/", json=heatmap_payload, timeout=60)
    t5 = time.time()
    print(f"Heatmap 2nd Load: status={resp_hm2.status_code}, time={t5 - t4:.4f}s (Cache Hit)")

if __name__ == "__main__":
    benchmark()
