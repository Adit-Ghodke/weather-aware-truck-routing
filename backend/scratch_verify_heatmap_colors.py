from datetime import UTC, datetime, timedelta

from safehaul.domain.heatmap import (
    compute_corridor_hourly_risks,
    generate_corridor_grid,
)


def test_heatmap_colors():
    # Chicago -> Denver sample corridor points
    chicago = (41.8781, -87.6298)
    denver = (39.7392, -104.9903)
    grid_points = generate_corridor_grid([[chicago[1], chicago[0]], [denver[1], denver[0]]], max_points=20)
    departure_utc = datetime(2026, 10, 13, 21, 0, tzinfo=UTC)
    
    print(f"Generated {len(grid_points)} sample grid points for Chicago -> Denver.")

    # 1. Low Weather Test: 5 mph wind, 0 precip
    low_forecasts = {}
    for lat, lng in grid_points:
        norm = (round(lat, 2), round(lng, 2))
        low_forecasts[norm] = {
            departure_utc + timedelta(hours=h): {
                "wind_speed_mph": 5.0,
                "wind_gust_mph": 8.0,
                "precipitation_in_hr": 0.0,
                "rain_in_hr": 0.0,
                "snowfall_in_hr": 0.0,
            }
            for h in range(49)
        }

    low_risks = compute_corridor_hourly_risks(
        grid_points=grid_points,
        departure_datetime_utc=departure_utc,
        forecasts=low_forecasts,
        load_weight_lb=35000,
        num_hours=49,
    )
    
    all_low = all(all(r == 0 for r in pt["hour_risks"]) for pt in low_risks)
    print("EVIDENCE 1 - All Low Weather:")
    print(f"  All grid points risk == 0 (Low): {all_low}")
    print(f"  Sample hour_risks[0..5]: {low_risks[0]['hour_risks'][:5]} (0 = Low -> Green '#10B981')")

    # 2. Severe Weather Test: 50 mph wind on 35k lb truck -> Severe (3) / No Travel (4)
    severe_forecasts = {}
    for lat, lng in grid_points:
        norm = (round(lat, 2), round(lng, 2))
        severe_forecasts[norm] = {
            departure_utc + timedelta(hours=h): {
                "wind_mph": 50.0,
                "gust_mph": 60.0,
                "precipitation_in_hr": 0.0,
                "rain_in_hr": 0.0,
                "snowfall_in_hr": 0.0,
            }
            for h in range(49)
        }

    severe_risks = compute_corridor_hourly_risks(
        grid_points=grid_points,
        departure_datetime_utc=departure_utc,
        forecasts=severe_forecasts,
        load_weight_lb=35000,
        num_hours=49,
    )

    all_severe = all(all(r in (3, 4) for r in pt["hour_risks"]) for pt in severe_risks)
    print("\nEVIDENCE 2 - Severe Weather:")
    print(f"  All grid points risk in (3, 4) (Severe/No Travel): {all_severe}")
    print(f"  Sample hour_risks[0..5]: {severe_risks[0]['hour_risks'][:5]} (3 = Severe -> Red '#EF4444', 4 = No Travel -> '#991B1B')")

if __name__ == "__main__":
    test_heatmap_colors()
