# SafeHaul — BUILD PLAN
> Weather-aware truck route planner | Version 1.0 | Phase 0

---

## Table of Contents
1. [Goal and Scope](#1-goal-and-scope)
2. [Assumptions and Open Questions](#2-assumptions-and-open-questions)
3. [Architecture](#3-architecture)
4. [Decision Records](#4-decision-records)
5. [Folder Structure](#5-folder-structure)
6. [Data Model](#6-data-model)
7. [API Specification](#7-api-specification)
8. [Algorithm Specifications](#8-algorithm-specifications)
9. [Frontend Plan](#9-frontend-plan)
10. [Performance Plan](#10-performance-plan)
11. [Phased Task List](#11-phased-task-list)
12. [Test Plan](#12-test-plan)
13. [Deployment Plan](#13-deployment-plan)
14. [Risk Register](#14-risk-register)
15. [Documentation Plan](#15-documentation-plan)
16. [Expected Final Output](#16-expected-final-output)

---

## 1. Goal and Scope

SafeHaul is a web application that helps truck drivers select the safest route for a given trip by overlaying real weather forecasts on each candidate route, computing a risk score at regular checkpoints, and recommending the best route based on risk severity and travel time.

The user supplies origin, destination, departure date/time, and load weight. The app returns three route options, each annotated with weather-derived risk levels at checkpoints spaced every 10, 25, or 50 miles (auto-selected by route length). It also shows a weather heatmap along the trip corridor with a 0–48-hour forecast slider that requires no network calls after the initial load.

**Out of scope:**
- User authentication, accounts, or saved trips
- Payment or subscription features
- Mobile-native app (iOS/Android)
- Truck-restriction-aware routing (commercial vehicle height/weight restrictions)
- Real-time traffic data
- Turn-by-turn navigation
- Custom routing engine (all routing via third-party API)
- Push notifications or alerts
- Multi-stop trip planning (more than one origin + one destination)
- Historical weather data (forecasts only, up to 7 days ahead)
- Administrative dashboard or analytics
- Chat or support features

---

## 2. Assumptions and Open Questions

Each ambiguity from the specification is resolved here. These decisions are documented in the README.

| # | Ambiguity | Resolution |
|---|---|---|
| A1 | Sampling interval selection | User may choose 10, 25, or 50 miles. Default auto-selection: <=150 mi -> 10 mi; 150-600 mi -> 25 mi; >600 mi -> 50 mi. Always include origin (mile 0) and destination (route end). |
| A2 | ETA calculation method | Use per-segment duration data from Mapbox Directions `annotation: "duration"` field. If only total duration is available, fall back to proportional distance (time = total_duration x segment_distance / total_distance) and flag as "approximate" in the checkpoint object. |
| A3 | Time zone handling | Departure date/time is interpreted in the origin's local time zone (looked up from lat/lng using the `timezonefinder` Python library). All internal calculations use UTC. Each checkpoint ETA is displayed in that checkpoint's local time zone (also resolved via `timezonefinder`), labelled with the abbreviated zone name (e.g., "CST"). Daylight-saving transitions are handled by Python's `zoneinfo` module. |
| A4 | Weather lookup at ETA | Open-Meteo returns hourly values. Wind speed (`wind_speed_10m`) is an instantaneous value -- interpolate linearly between the two surrounding hourly slots at the checkpoint ETA. Precipitation rates (`rain` and `snowfall`) are hourly totals for the preceding hour -- use the hourly slot that covers the ETA (slot `h` covers time `[h, h+1)`). Request units: `wind_speed_unit=mph`, precipitation in default mm/h then convert: rain_in_hr = mm_per_hr / 25.4, snowfall per Open-Meteo docs (cm/hr -> in/hr = cm/hr / 2.54). All requests use UTC times. |
| A5 | Wind classification basis | Use sustained wind speed (`wind_speed_10m`). Gusts (`wind_gusts_10m`) are fetched and stored in the checkpoint object for display only; they never change the risk level. |
| A6 | Departure time limits | Must not be more than 1 hour in the past relative to current UTC time. Must not be more than 7 days in the future (Open-Meteo default is 7 days, up to 16 days; verified). Return HTTP 400 with error code `INVALID_DEPARTURE_TIME` if out of range. |
| A7 | Load weight limits | Accept 1 to 80,000 lb (inclusive). Store limits as named constants `LOAD_MIN_LB = 1` and `LOAD_MAX_LB = 80_000` in `backend/safehaul/domain/constants.py`. Return HTTP 400 with `INVALID_LOAD_WEIGHT` if outside range. |
| A8 | Heatmap hour 0 | Hour 0 = departure time. Slider covers [0, 48] inclusive (49 snapshots). No network calls on slider move; all data is pre-fetched and sent in the initial heatmap response. |
| A9 | Route count | Request alternatives from Mapbox Directions API. If fewer than 3 are returned, generate additional candidates by adding via-waypoints perpendicular to the midpoint of the existing routes, deduplicate by geometry overlap (Hausdorff distance threshold). If fewer than 3 remain after deduplication, show what is available with a warning in `meta.warnings`. |
| A10 | Boundary rule for risk thresholds | Wind: lower bounds 25, 35, 45, 55 are inclusive (>=). Rain: lower bounds 0.10, 0.25, 0.50, and strictly >1.00 for No Travel. Snow: lower bounds 0.5, 1.0, 2.0, and strictly >3.0 for No Travel. A value belongs to the highest level whose lower bound it meets. |
| A11 | Load rule "greater than" | The load rules use strict greater-than (>). A load of exactly 30,000 lb does NOT trigger the 45-54 mph rule. Exactly 40,000 lb does NOT trigger the 35-44 mph rule. |
| A12 | Segment mile attribution | Each checkpoint represents its surrounding road segment. Segment length = (distance to prev checkpoint / 2) + (distance to next checkpoint / 2). First checkpoint segment = half-distance to next. Last checkpoint segment = half-distance from previous. All segments must sum to the exact route distance (within floating-point tolerance of 0.001 miles). |
| A13 | Open-Meteo precipitation units | Open-Meteo returns rain in mm/h and snowfall in cm/h by default. Convert: `rain_in_hr = rain_mm_hr / 25.4`, `snow_in_hr = snow_cm_hr / 2.54`. |
| A14 | Cold-start demo prep | Deployment notes include a warmup request to call the health endpoint before the demo to avoid Cloud Run cold-start latency. |
| A15 | Geocoding caching prohibition | Per Mapbox Temporary Geocoding Terms, coordinate results CANNOT be cached or stored. Therefore, backend 24h caching of geocode queries is eliminated. Autocomplete is debounced (300ms) on the frontend for the active user session only, with no persistent backend cache. (Verified fact) |
| A16 | Directions caching terms (NEEDS OWNER VERIFICATION) | Mapbox Terms Section 3.1 permit temporary caching only as necessary to enable application functioning on an end user's device. Server-side route caching is NOT claimed as legally approved; it requires owner verification. Route caching is disabled by default (`ENABLE_ROUTE_CACHE=false`), using only per-request in-memory deduplication during analysis execution. (Design decision) |
| A17 | Open-Meteo usage limits & batching | 7-day default (configurable up to 16 days), multi-location syntax, and response array behavior are verified. Free non-commercial limits (<10,000 calls/day, 5,000/hr, 600/min per IP) are usage limits, not an availability or latency SLA. The 30-minute weather cache and HTTP 429 backoff are planned mitigations, not guarantees that rate limits will never be reached. SafeHaul enforces a 7-day trip planning limit and conservative batches of up to 50 locations. No 1,000-location maximum or 300ms latency is claimed. (Verified facts & design decisions) |
| A18 | Redis fallback design requirement | Django does NOT automatically fall back to LocMemCache when Redis fails. A custom `ResilientCache` wrapper design is required to intercept Redis errors and delegate to in-memory `LocMemCache`. Scheduled for Phase 5 implementation and testing; not yet implemented. (Design requirement) |

---

## 3. Architecture

### System Components

```
+---------------------------------------------------------------+
|                        USER BROWSER                           |
|                                                               |
|  +------------------+    +-------------------------------+    |
|  |   Left Panel     |    |         Map Panel             |    |
|  |  (Trip Form,     |    | (Mapbox GL JS via react-map-gl)|   |
|  |   Route Cards,   |    | Routes, Checkpoints, Heatmap  |    |
|  |   Comparison)    |    |                               |    |
|  +------------------+    +-------------------------------+    |
|                                                               |
|  React 18 + TypeScript + Vite + MUI + TanStack Query         |
+----------------------------+----------------------------------+
                             | HTTPS REST
                             v
+---------------------------------------------------------------+
|                    DJANGO BACKEND (Cloud Run)                 |
|                                                               |
|  +--------+  +-----------+  +----------+  +--------------+   |
|  | Views  |  | Serializers|  |  Domain  |  | API Adapters |   |
|  | (DRF)  |  |(Validation)|  |  Logic   |  | (Routing,    |   |
|  |        |  |           |  | (risk.py,|  |  Weather,    |   |
|  |        |  |           |  |  eta.py, |  |  Geocoding)  |   |
|  |        |  |           |  |  rank.py)|  |              |   |
|  +--------+  +-----------+  +----------+  +--------------+   |
|                                                               |
|  +--------------+  +--------------+  +--------------------+  |
|  |  Django ORM  |  | Django Cache |  | DRF Throttling     |  |
|  | (SQLite /    |  |  Framework   |  |                    |  |
|  |  Postgres)   |  |              |  |                    |  |
|  +--------------+  +------+-------+  +--------------------+  |
+---------------------------------------------------------------+
                            |               |
              +-------------+               +------------------+
              v                                                v
+---------------------+                       +--------------------+
|  Redis (Upstash)    |                       |  External APIs     |
|  - Route cache      |                       | +--------------+   |
|    (5min TTL,       |                       | | Mapbox       |   |
|     toggleable)     |                       | | Directions   |   |
|  - Weather cache    |                       | | Geocoding    |   |
|    (30min TTL)      |                       | +--------------+   |
|  - Heatmap cache    |                       | +--------------+   |
|    (30min TTL)      |                       | | Open-Meteo   |   |
|  Fallback: custom   |                       | | Weather API  |   |
|  ResilientCache     |                       | +--------------+   |
|  (LocMem fallback)  |                       +--------------------+
+---------------------+
```

### Request Flow: "Analyze Trip"

```
1.  User fills form -> clicks "Analyze"
2.  Frontend POST /api/v1/trips/analyze/ {origin, destination, departure_datetime, load_weight_lb}
3.  Backend validates inputs (serializer)
4.  Backend geocodes origin/destination if only address strings given (ephemeral, not stored or cached per Mapbox Terms)
5.  Backend calls Mapbox Directions API for 3 routes (cached only if ENABLE_ROUTE_CACHE enabled; UNVERIFIED ToS status)
6.  Backend samples checkpoints along each route geometry at selected interval
7.  Backend computes ETA at each checkpoint from per-segment duration data
8.  Backend converts ETAs to UTC; groups checkpoints by hour/location for batched weather fetch
9.  Backend calls Open-Meteo forecast API for each unique (lat, lng) checkpoint
    - Cache key: rounded (lat 2dp, lng 2dp) + date_hour -> 30min TTL
    - Fetch 48-hour window in one request per location; extract needed hours
10. Backend applies risk rules (wind, rain, snow, load) -> checkpoint risk levels
11. Backend computes route metrics (severe_miles, high_miles, etc.) using segment attribution
12. Backend ranks routes per recommendation rules
13. Backend persists TripAnalysis record (failure does not block response)
14. Backend returns full JSON response
15. Frontend renders route cards, map layers, checkpoint popups
```

### Request Flow: "Heatmap"

```
1. Frontend POST /api/v1/trips/heatmap/ {trip_id or corridor_geometry, departure_datetime, load_weight_lb}
2. Backend builds corridor grid (bounding box of all routes, ~25-mile buffer, capped at MAX_HEATMAP_POINTS)
3. For each grid point, fetch 49-hour weather forecast (Open-Meteo, same cache layer)
4. Apply risk rules for each grid point at each hour -> 49 risk values per point
5. Return flat array of {lat, lng, hour_risks: [0..48]} in one response
6. Frontend stores array in memory; slider updates Mapbox feature-state paint property per hour
   -> zero network calls on slider move
```

---

## 4. Decision Records

### DR-01: Routing and Geocoding Provider -- Mapbox

| Field | Detail |
|---|---|
| **Options** | Mapbox Directions + Geocoding; Google Maps Platform; HERE Routing |
| **Choice** | Mapbox |
| **Reason** | Single SDK covers both routing and geocoding. react-map-gl is the standard React wrapper for Mapbox GL JS. Free tier is sufficient for a portfolio project. Alternatives endpoint exists for getting multiple routes. |
| **Free tier quotas (Verified)** | 50,000 web map loads/month; 100,000 temporary geocoding requests/month; 100,000 Directions requests/month (confirmed against Mapbox pricing). |
| **Sign-up required** | Yes -- https://account.mapbox.com/auth/signup/ -- no credit card required to start on free tier. |
| **Geocoding Terms (Verified)** | Mapbox Temporary Geocoding Terms prohibit caching or storing coordinate results. Geocoding results are strictly ephemeral; NO backend cache. Debouncing (300ms) handled on frontend for active UI session. |
| **Directions Caching (NEEDS OWNER VERIFICATION)** | Mapbox Terms Section 3.1 permit caching only as necessary for application functioning on an end user's device. Server-side route caching is NOT claimed to be legally approved. Kept disabled by default (`ENABLE_ROUTE_CACHE=false`) pending verification by owner. Per-request in-memory deduplication used during trip analysis. |
| **Truck profiles** | Mapbox Directions uses a driving profile, not a commercial vehicle profile. Stated in README as a known limitation. |
| **Fallback** | Returns error `ROUTING_UNAVAILABLE` and shows clear message. No silent fallback to another provider. |

### DR-02: Weather Provider -- Open-Meteo

| Field | Detail |
|---|---|
| **Options** | Open-Meteo (free, no key); OpenWeatherMap One Call 3.0; Tomorrow.io |
| **Choice** | Open-Meteo |
| **Reason** | Completely free, no API key, no credit card, hourly forecasts, supports multiple variables (wind, rain, snow). |
| **Forecast horizon (Verified)** | Default 7-day hourly forecast; configurable up to 16 days via `forecast_days` parameter (verified). SafeHaul enforces a conservative 7-day planning limit. |
| **Multi-location syntax & response (Verified)** | Comma-separated coordinates `latitude=lat1,lat2&longitude=lng1,lng2` supported; returns a JSON array of location objects (verified). |
| **Usage limits (Verified / Usage terms)** | Free non-commercial usage limits are less than 10,000 calls/day, 5,000/hour, and 600/minute per IP under CC-BY 4.0. These are usage limits, not an availability or latency SLA. The 30-minute weather cache and HTTP 429 backoff are planned mitigations, not guarantees that rate limits will never be reached. |
| **Batching & Latency (Design decisions)** | Multi-location requests are chunked into conservative batches of up to 50 locations per request. No 1,000-location maximum or guaranteed 300 ms response time is claimed; latency will be measured during testing. |
| **Sign-up required** | None |
| **Fallback** | Checkpoints returned with `weather_available: false`. Warning added to `meta.warnings`. Risk scores omitted for affected checkpoints. |

### DR-03: Map Library -- react-map-gl (Mapbox GL JS)

| Field | Detail |
|---|---|
| **Options** | react-map-gl; Leaflet + React-Leaflet; MapLibre GL JS |
| **Choice** | react-map-gl (Mapbox GL JS) |
| **Reason** | GeoJSON layers with feature-state updates enable the heatmap slider to repaint without React re-renders. Consistent with Mapbox routing/geocoding choice. |
| **Fallback** | MapLibre GL JS is a drop-in open-source replacement if Mapbox terms change. |

### DR-04: Frontend Hosting -- Firebase Hosting

| Field | Detail |
|---|---|
| **Options** | Firebase Hosting; Vercel; Netlify |
| **Choice** | Firebase Hosting |
| **Reason** | Free tier generous for a portfolio project. Simple CLI deploy. Google Cloud ecosystem consistency. |
| **Free tier** | 10 GB storage, 360 MB/day transfer on Spark plan. UNVERIFIED -- confirm at https://firebase.google.com/pricing |
| **Sign-up** | Google account required. No credit card needed for Spark plan. |
| **Fallback** | Vercel -- zero-config static site deploy, also free. |

### DR-05: Backend Hosting -- Google Cloud Run

| Field | Detail |
|---|---|
| **Choice** | Google Cloud Run (specified in prompt) |
| **Free tier** | 2 million requests/month, 360,000 vCPU-seconds, 180,000 GiB-seconds. UNVERIFIED -- confirm at https://cloud.google.com/run/pricing |
| **Sign-up** | Google Cloud account required. Credit card required for billing setup. |

### DR-06: Redis -- Upstash

| Field | Detail |
|---|---|
| **Choice** | Upstash managed Redis |
| **Reason** | Free tier, no credit card required for hobby tier, HTTP/TCP client works from Cloud Run. |
| **Free tier quotas (Verified)** | 500,000 commands/month (~16k/day), 256 MB storage, 10 GB monthly bandwidth. Pricing plan comparison lists 1 free database (while FAQ mentions up to 10); SafeHaul conservatively plans for exactly 1 database. No credit card required. |
| **Fallback Design Requirement** | Django does NOT automatically fall back to `LocMemCache` when Redis fails. A custom `ResilientCache` wrapper design is specified to intercept Redis connection/timeout errors and route to in-memory `LocMemCache`. This is a design requirement scheduled for implementation and test in Phase 5; it is not yet implemented. |

---

## 5. Folder Structure

```
safehaul/                              <- monorepo root
|-- .env.example                       <- all required env vars, no real values
|-- .gitignore
|-- docker-compose.yml                 <- local dev: backend + redis
|-- README.md
|-- docs/
|   |-- BUILD_PLAN.md                  <- this file
|   `-- LOOM_SCRIPT.md
|
|-- backend/
|   |-- Dockerfile
|   |-- requirements.txt
|   |-- requirements-dev.txt           <- pytest, responses, etc.
|   |-- manage.py
|   |-- config/
|   |   |-- __init__.py
|   |   |-- settings/
|   |   |   |-- __init__.py
|   |   |   |-- base.py
|   |   |   |-- local.py
|   |   |   `-- production.py
|   |   |-- urls.py
|   |   `-- wsgi.py
|   |-- safehaul/                      <- main Django app
|   |   |-- __init__.py
|   |   |-- apps.py
|   |   |-- models.py                  <- TripAnalysis model
|   |   |-- serializers.py             <- DRF input/output serializers
|   |   |-- views.py                   <- DRF APIViews
|   |   |-- urls.py
|   |   |-- domain/                    <- pure business logic, no I/O
|   |   |   |-- __init__.py
|   |   |   |-- constants.py           <- all thresholds, limits, magic numbers
|   |   |   |-- risk.py                <- classify_checkpoint_risk()
|   |   |   |-- sampling.py            <- sample_checkpoints()
|   |   |   |-- eta.py                 <- compute_eta()
|   |   |   |-- ranking.py             <- rank_routes()
|   |   |   `-- heatmap.py             <- build_corridor_grid()
|   |   |-- adapters/                  <- thin wrappers over external APIs
|   |   |   |-- __init__.py
|   |   |   |-- base.py                <- abstract interfaces
|   |   |   |-- mapbox.py              <- MapboxRoutingAdapter, MapboxGeocodingAdapter
|   |   |   `-- weather.py             <- OpenMeteoWeatherAdapter
|   |   `-- migrations/
|   |       `-- 0001_initial.py
|   `-- tests/
|       |-- __init__.py
|       |-- conftest.py
|       |-- test_risk.py               <- all golden tests + extras
|       |-- test_sampling.py
|       |-- test_eta.py
|       |-- test_ranking.py
|       |-- test_heatmap.py
|       `-- test_api.py                <- integration tests, external APIs mocked
|
`-- frontend/
    |-- package.json
    |-- tsconfig.json                  <- strict mode
    |-- vite.config.ts
    |-- .eslintrc.cjs
    |-- .prettierrc
    |-- index.html
    |-- public/
    `-- src/
        |-- main.tsx
        |-- App.tsx
        |-- theme.ts                   <- MUI theme
        |-- constants.ts               <- risk colors, labels, etc.
        |-- types/
        |   `-- api.ts                 <- TypeScript types matching API response shapes
        |-- api/
        |   |-- client.ts              <- Axios/fetch base client
        |   |-- trips.ts               <- analyzeTrip(), fetchHeatmap()
        |   `-- geocode.ts             <- geocodeSearch()
        |-- components/
        |   |-- TripForm/
        |   |   |-- TripForm.tsx
        |   |   |-- AddressAutocomplete.tsx
        |   |   `-- index.ts
        |   |-- RouteCards/
        |   |   |-- RouteCard.tsx
        |   |   |-- RouteCardList.tsx
        |   |   `-- index.ts
        |   |-- RecommendationPanel/
        |   |   |-- RecommendationPanel.tsx
        |   |   |-- ComparisonTable.tsx
        |   |   `-- index.ts
        |   |-- MapView/
        |   |   |-- MapView.tsx
        |   |   |-- RouteLayer.tsx
        |   |   |-- CheckpointLayer.tsx
        |   |   |-- HeatmapLayer.tsx
        |   |   |-- CheckpointPopup.tsx
        |   |   `-- index.ts
        |   `-- shared/
        |       |-- RiskBadge.tsx
        |       |-- LoadingState.tsx
        |       `-- ErrorState.tsx
        |-- hooks/
        |   |-- useAnalyzeTrip.ts      <- TanStack Query wrapper
        |   `-- useHeatmap.ts
        `-- utils/
            |-- units.ts               <- formatDistance, formatDuration, etc.
            |-- risk.ts                <- riskLevelToColor, riskLevelToLabel
            `-- time.ts                <- formatETA, formatLocalTime
```

---

## 6. Data Model

### TripAnalysis

Purpose: persist a snapshot of each analysis so `/api/v1/trips/<uuid>/` can return it later. Persistence failure must never break the analysis response -- the view catches all DB errors and proceeds.

```python
class TripAnalysis(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Raw user inputs -- stored for debugging and potential future retrieval
    origin_lat = models.FloatField()
    origin_lng = models.FloatField()
    origin_label = models.CharField(max_length=500)
    destination_lat = models.FloatField()
    destination_lng = models.FloatField()
    destination_label = models.CharField(max_length=500)
    departure_datetime_utc = models.DateTimeField()
    load_weight_lb = models.IntegerField()
    sample_interval_miles = models.IntegerField()
    # Full analysis result serialized as JSON -- avoids separate tables for
    # routes/checkpoints which would complicate the schema without benefit.
    result_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["created_at"])]
```

No other models. The route, checkpoint, and weather data all live inside `result_json`. This avoids a complex normalized schema for data that is never queried across trips.

---

## 7. API Specification

Base URL: `/api/v1/`

All error responses:
```json
{"error": {"code": "ERROR_CODE", "message": "Human readable message.", "details": {}}}
```

---

### GET /api/v1/health/

No parameters.

**Response 200:**
```json
{"status": "ok", "timestamp": "2025-01-15T10:00:00Z"}
```

---

### GET /api/v1/geocode/?q=\<string\>

**Query params:** `q` (required, string, 2-200 chars)

**Response 200:**
```json
{
  "results": [
    {"label": "Chicago, Illinois, United States", "lat": 41.8781, "lng": -87.6298},
    {"label": "Chicago O'Hare International Airport, Illinois", "lat": 41.9742, "lng": -87.9073}
  ]
}
```
Up to 5 results. Empty array if no match.

**Cache:** NONE on backend. Per Mapbox Temporary Geocoding Terms, temporary geocoding results cannot be cached or stored. Input queries are debounced (300ms) on the frontend within the active user session.

**Errors:** 400 `INVALID_QUERY`; 502 `GEOCODING_UNAVAILABLE`

---

### POST /api/v1/trips/analyze/

**Request body:**
```json
{
  "origin": {"lat": 41.8781, "lng": -87.6298, "label": "Chicago, IL"},
  "destination": {"lat": 39.0997, "lng": -94.5786, "label": "Kansas City, MO"},
  "departure_datetime": "2025-01-20T08:00:00-06:00",
  "load_weight_lb": 35000,
  "sample_interval_miles": 25
}
```

**Validation rules:**
- `origin.lat`: -90 to 90, required
- `origin.lng`: -180 to 180, required
- `origin.label`: string, max 500 chars, required
- `destination.*`: same as origin
- `departure_datetime`: ISO 8601 with timezone offset; not >1h in past, not >7 days in future
- `load_weight_lb`: integer, 1-80,000, required
- `sample_interval_miles`: integer, one of [10, 25, 50], optional (auto if omitted)

**Response 200 (abbreviated):**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "routes": [
    {
      "id": "route-a",
      "label": "Route A",
      "geometry": {"type": "LineString", "coordinates": [...]},
      "distance_miles": 512.4,
      "duration_minutes": 487,
      "departure_datetime_utc": "2025-01-20T14:00:00Z",
      "arrival_datetime_utc": "2025-01-20T22:07:00Z",
      "arrival_datetime_local": "2025-01-20T16:07:00-06:00",
      "checkpoints": [
        {
          "index": 0,
          "mile_marker": 0.0,
          "lat": 41.8781,
          "lng": -87.6298,
          "eta_utc": "2025-01-20T14:00:00Z",
          "eta_local": "2025-01-20T08:00:00-06:00",
          "timezone": "America/Chicago",
          "timezone_abbr": "CST",
          "segment_miles": 12.5,
          "weather": {
            "wind_mph": 22.3,
            "gust_mph": 31.0,
            "rain_in_hr": 0.05,
            "snow_in_hr": 0.0
          },
          "condition_levels": {"wind": "Low", "rain": "Low", "snow": "Low"},
          "level": "Low",
          "reason": "Wind 22.3 mph -> Low",
          "weather_available": true
        }
      ],
      "metrics": {
        "severe_miles": 0.0,
        "high_miles": 14.2,
        "moderate_miles": 88.5,
        "low_miles": 409.7,
        "no_travel_miles": 0.0,
        "average_risk": 1.28,
        "worst_level": "High"
      }
    }
  ],
  "recommendation": {
    "recommended_route_id": "route-b",
    "status": "recommended",
    "explanation": "Route B has 0 Severe miles vs 0 on Route A and is 22 minutes longer, but has the lowest average risk (1.18 vs 1.28).",
    "comparison": [
      {
        "route_id": "route-a", "label": "Route A",
        "severe_miles": 0.0, "high_miles": 14.2,
        "moderate_miles": 88.5, "average_risk": 1.28,
        "duration_minutes": 487, "status": "ok", "rank": 2
      }
    ]
  },
  "meta": {
    "units": {"distance": "miles", "wind": "mph", "precipitation": "in/hr", "load": "lb"},
    "interval_miles": 25,
    "routing_provider": "Mapbox Directions",
    "weather_provider": "Open-Meteo",
    "generated_at": "2025-01-20T12:00:00Z",
    "warnings": []
  }
}
```

**Errors:** 400 `INVALID_DEPARTURE_TIME`; 400 `INVALID_LOAD_WEIGHT`; 400 `INVALID_COORDINATES`; 502 `ROUTING_UNAVAILABLE`; 503 `ANALYSIS_FAILED`

---

### POST /api/v1/trips/heatmap/

**Request body:**
```json
{
  "trip_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "load_weight_lb": 35000
}
```

OR (when trip_id not available):
```json
{
  "corridor_geometry": {"routes": [{"type": "LineString", "coordinates": [...]}]},
  "departure_datetime": "2025-01-20T08:00:00-06:00",
  "load_weight_lb": 35000
}
```

**Grid:** bounding box of all route geometries expanded by 0.5 degrees. Grid resolution ~0.1 degree steps. Hard cap: `MAX_HEATMAP_POINTS = 400`.

**Response 200:**
```json
{
  "grid": [
    {"lat": 41.9, "lng": -87.6, "hour_risks": [1, 1, 2, 2, 3, 2, 1, 1]}
  ],
  "hours": 49,
  "departure_datetime_utc": "2025-01-20T14:00:00Z",
  "meta": {"grid_points": 312, "max_points_cap": 400, "warnings": []}
}
```

`hour_risks` is an array of 49 integers indexed [0..48]: 0=Low, 1=Moderate, 2=High, 3=Severe, 4=No Travel.

---

### GET /api/v1/trips/\<uuid\>/

Returns stored TripAnalysis. Same shape as POST analyze response.

**Errors:** 404 `TRIP_NOT_FOUND`

---

## 8. Algorithm Specifications

### 8a. Checkpoint Sampling

```
INPUT: route_geometry (list of [lng, lat] coords with cumulative distances)
       sample_interval_miles (10, 25, or 50)
       total_distance_miles

OUTPUT: list of checkpoints with {mile_marker, lat, lng}

ALGORITHM:
  checkpoints = []
  target_miles = 0.0

  # Always include origin
  checkpoints.append(interpolate(geometry, mile=0))
  target_miles += sample_interval_miles

  WHILE target_miles < total_distance_miles:
    checkpoints.append(interpolate(geometry, mile=target_miles))
    target_miles += sample_interval_miles

  # Always include destination (deduplicate if last target was very close)
  dest = interpolate(geometry, mile=total_distance_miles)
  if distance(checkpoints[-1], dest) > 0.01 miles:
    checkpoints.append(dest)

  return checkpoints

INTERPOLATION:
  Walk cumulative distance array to find the segment containing target_mile.
  Within the segment, interpolate linearly by fraction:
    fraction = (target_mile - seg_start_mile) / (seg_end_mile - seg_start_mile)
    lat = seg_start_lat + fraction * (seg_end_lat - seg_start_lat)
    lng = seg_start_lng + fraction * (seg_end_lng - seg_start_lng)
```

**Worked example (50-mile interval, 130-mile route):**
- Checkpoint 0: mile 0 (origin)
- Checkpoint 1: mile 50
- Checkpoint 2: mile 100
- Checkpoint 3: mile 130 (destination)
- Segment miles: [25, 50, 40, 15] -- first=25 (half of 50), last=15 (half of 30), sum=130 check

---

### 8b. ETA Calculation

```
INPUT: departure_datetime_utc
       checkpoint_mile_marker
       route_segments [{start_mile, end_mile, duration_seconds}]

OUTPUT: eta_utc (datetime), method_used (string)

ALGORITHM (per_segment):
  elapsed_seconds = 0
  for seg in route_segments:
    if seg.end_mile <= checkpoint_mile_marker:
      elapsed_seconds += seg.duration_seconds
    elif seg.start_mile < checkpoint_mile_marker < seg.end_mile:
      fraction = (checkpoint_mile_marker - seg.start_mile) / (seg.end_mile - seg.start_mile)
      elapsed_seconds += seg.duration_seconds * fraction
      break
  eta_utc = departure_datetime_utc + timedelta(seconds=elapsed_seconds)

FALLBACK (proportional):
  fraction = checkpoint_mile_marker / total_distance_miles
  elapsed_seconds = total_duration_seconds * fraction
  return eta_utc, "approximate"
```

**Worked example:**
- Departure: 2025-01-20 14:00:00 UTC
- Checkpoint at mile 50; segment 0-50 mi: 3600s
- ETA = 14:00:00 + 3600s = 15:00:00 UTC

---

### 8c. Weather Lookup at ETA

```
WIND (instantaneous -- linear interpolation):
  h_floor = floor(eta_utc to hour boundary)
  h_ceil = h_floor + 1 hour
  fraction = (eta_utc - h_floor).seconds / 3600
  wind_mph = weather[h_floor].wind + fraction * (weather[h_ceil].wind - weather[h_floor].wind)

RAIN (preceding-hour total -- use slot that covers ETA):
  h_slot = floor(eta_utc to hour boundary)  # slot h covers [h, h+1)
  rain_in_hr = weather[h_slot].rain_in_hr

SNOW (same method as rain):
  snow_in_hr = weather[h_slot].snow_in_hr

GUST (instantaneous, same interpolation as wind, display only):
  gust_mph = interpolate(weather, eta_utc, "gust")
```

---

### 8d. Risk Classification and Load Rules

```python
# Constants (from constants.py)
WIND_THRESHOLDS = [(55, "No Travel"), (45, "Severe"), (35, "High"), (25, "Moderate"), (0, "Low")]
RAIN_NO_TRAVEL_THRESHOLD = 1.00   # strictly greater than
RAIN_THRESHOLDS = [(0.50, "Severe"), (0.25, "High"), (0.10, "Moderate"), (0, "Low")]
SNOW_NO_TRAVEL_THRESHOLD = 3.0    # strictly greater than
SNOW_THRESHOLDS = [(2.0, "Severe"), (1.0, "High"), (0.5, "Moderate"), (0, "Low")]
LEVEL_ORDER = {"Low": 1, "Moderate": 2, "High": 3, "Severe": 4, "No Travel": 5}

def classify_wind(wind_mph):
    for threshold, level in WIND_THRESHOLDS:
        if wind_mph >= threshold:
            return level
    return "Low"

def classify_rain(rain_in_hr):
    if rain_in_hr > RAIN_NO_TRAVEL_THRESHOLD:
        return "No Travel"
    for threshold, level in RAIN_THRESHOLDS:
        if rain_in_hr >= threshold:
            return level
    return "Low"

def classify_snow(snow_in_hr):
    if snow_in_hr > SNOW_NO_TRAVEL_THRESHOLD:
        return "No Travel"
    for threshold, level in SNOW_THRESHOLDS:
        if snow_in_hr >= threshold:
            return level
    return "Low"

def apply_load_rules(wind_level, wind_mph, load_lb):
    """Returns (adjusted_level, reason_string_or_None).
    Load rules can only raise a level, never lower it."""
    if wind_mph >= 55:
        return wind_level, None   # already No Travel
    if 45 <= wind_mph < 55 and load_lb > 30_000:
        return "No Travel", f"Wind {wind_mph:.1f} mph with {load_lb:,} lb load -> No Travel"
    if 35 <= wind_mph < 45 and load_lb > 40_000:
        # Only raise to Severe if wind_level is currently below Severe
        if LEVEL_ORDER[wind_level] < LEVEL_ORDER["Severe"]:
            return "Severe", f"Wind {wind_mph:.1f} mph with {load_lb:,} lb load -> Severe"
    return wind_level, None

def classify_checkpoint(wind_mph, rain_in_hr, snow_in_hr, load_lb):
    wind_base = classify_wind(wind_mph)
    wind_level, load_reason = apply_load_rules(wind_base, wind_mph, load_lb)
    rain_level = classify_rain(rain_in_hr)
    snow_level = classify_snow(snow_in_hr)
    levels = {"wind": wind_level, "rain": rain_level, "snow": snow_level}
    overall = max(levels.values(), key=lambda l: LEVEL_ORDER[l])
    if load_reason:
        reason = load_reason
    else:
        causes = [f"{k.title()} -> {v}" for k, v in levels.items() if v == overall]
        reason = "; ".join(causes)
    return {"condition_levels": levels, "level": overall, "reason": reason}
```

**Boundary verification:**
- Wind 25.0: 25 >= 25 -> Moderate
- Wind 34.9: 34.9 >= 25 but 34.9 < 35 -> Moderate
- Wind 35.0: 35.0 >= 35 -> High
- Rain 1.00: 1.00 > 1.00 is False; 1.00 >= 0.50 -> Severe
- Rain 1.01: 1.01 > 1.00 -> No Travel
- Snow 3.0: 3.0 > 3.0 is False; 3.0 >= 2.0 -> Severe
- Snow 3.01: 3.01 > 3.0 -> No Travel

---

### 8e. Route Aggregation Metrics

```
For each checkpoint i in [0, N-1]:
  if i == 0:
    seg_miles[0] = road_distance(cp[0], cp[1]) / 2
  elif i == N-1:
    seg_miles[N-1] = road_distance(cp[N-2], cp[N-1]) / 2
  else:
    seg_miles[i] = road_distance(cp[i-1], cp[i]) / 2 + road_distance(cp[i], cp[i+1]) / 2

  # road_distance = difference in cumulative mile markers (not great-circle)

assert abs(sum(seg_miles) - total_route_miles) < MILE_TOLERANCE  # MILE_TOLERANCE = 0.001

# Aggregate
for level in LEVELS:
  metrics[level + "_miles"] = sum(seg_miles[i] for i where cp[i].level == level)

# Mile-weighted average risk
average_risk = sum(LEVEL_ORDER[cp[i].level] * seg_miles[i] for i) / total_route_miles
```

---

### 8f. Route Ranking

```
1. Partition: no_travel_routes (any checkpoint == "No Travel") vs ok_routes

2. If ALL routes are no_travel:
   - Add warning "Do not travel at this departure time" to meta
   - Still rank by fewest no_travel_miles and return least-bad route
   - status = "not_recommended_all_routes"

3. Rank ok_routes (lexicographic):
   a. severe_miles ASC (rounded to 1dp)
   b. high_miles ASC (rounded to 1dp)
   c. average_risk ASC (rounded to 3dp)
   d. duration_minutes ASC

4. Rank no_travel_routes by fewest no_travel_miles, appended after ok_routes

5. Build explanation comparing rank 1 vs rank 2 on first differing dimension

6. Return comparison table with all routes, rank, all metrics, status
```

---

### 8g. Heatmap Grid Generation

```
1. Bounding box of all route coordinates + HEATMAP_BUFFER_DEG = 0.5

2. Grid: target ~0.1 degree steps, scale to keep points <= MAX_HEATMAP_POINTS=400

3. For each grid point:
   For each hour h in [0, 48]:
     eta_utc = departure_utc + timedelta(hours=h)
     weather = extract_weather_at_hour(cached_forecast, eta_utc)
     risk = classify_checkpoint(weather.wind, weather.rain, weather.snow, load_lb)
     hour_risks[h] = LEVEL_ORDER[risk.level] - 1  # 0-indexed

4. Return grid with hour_risks arrays (49 integers per point)
```

---

### Golden Tests

| Test | Wind | Rain | Snow | Load | Expected | Note |
|------|------|------|------|------|----------|------|
| GT-01 | 24.9 | 0 | 0 | 50,000 | Low | wind just below Moderate |
| GT-02 | 25 | 0 | 0 | 10,000 | Moderate | wind exactly at Moderate |
| GT-03 | 40 | 0 | 0 | 40,000 | High | load exactly 40k, rule not triggered |
| GT-04 | 40 | 0 | 0 | 40,001 | Severe | load > 40k, rule triggered |
| GT-05 | 45 | 0 | 0 | 30,000 | Severe | load exactly 30k, wind=Severe base |
| GT-06 | 50 | 0 | 0 | 30,001 | No Travel | load > 30k at 45-54 mph |
| GT-07 | 55 | 0 | 0 | 1,000 | No Travel | wind at No Travel boundary |
| GT-08 | 10 | 0.25 | 0 | 20,000 | High | rain at High boundary |
| GT-09 | 10 | 1.00 | 0 | 20,000 | Severe | rain at Severe/NoTravel boundary |
| GT-10 | 10 | 1.01 | 0 | 20,000 | No Travel | rain strictly > 1.00 |
| GT-11 | 10 | 0 | 3.0 | 20,000 | Severe | snow at Severe/NoTravel boundary |
| GT-12 | 10 | 0 | 3.01 | 20,000 | No Travel | snow strictly > 3.0 |
| GT-13 | 30 | 0.30 | 0.2 | 20,000 | High | worst wins: rain=High |
| GT-14 | 0 | 0 | 0 | 1 | Low | all-zero, minimum load |
| GT-15 | 54.9 | 0 | 0 | 1 | Severe | wind just below No Travel |
| GT-16 | 55.0 | 0 | 0 | 80,000 | No Travel | No Travel wind, max load |
| GT-17 | 44.9 | 0 | 0 | 40,001 | Severe | load rule: 35-44 mph, load > 40k |
| GT-18 | 35.0 | 0 | 0 | 40,001 | Severe | load rule: exactly at lower bound 35 |
| GT-19 | 34.9 | 0 | 0 | 40,001 | Moderate | wind < 35, load rule inapplicable |
| GT-20 | 45.0 | 0 | 0 | 30,001 | No Travel | load rule: exactly at lower bound 45 |
| GT-21 | 10 | 0 | 0.5 | 1 | Moderate | snow at Moderate boundary |
| GT-22 | 10 | 0 | 1.0 | 1 | High | snow at High boundary |
| GT-23 | 10 | 0 | 2.0 | 1 | Severe | snow at Severe boundary |
| GT-24 | 10 | 0.10 | 0 | 1 | Moderate | rain at Moderate boundary |
| GT-25 | 10 | 0.50 | 0 | 1 | Severe | rain at Severe boundary |
| GT-26 | 35 | 0.30 | 1.5 | 45,000 | Severe | wind+load->Severe, rain=High, snow=High; load rule wins |
| GT-27 | 46 | 1.10 | 0 | 25,000 | No Travel | rain NoTravel dominates |
| GT-28 | 20 | 0.20 | 1.2 | 79,999 | High | wind=Low, rain=Moderate, snow=High (1.2 in/hr >= 1.0); snow wins |
| GT-29 | 25 | 0.10 | 0.5 | 10,000 | Moderate | all conditions exactly at Moderate |
| GT-30 | 47 | 0 | 0 | 30,000 | Severe | wind 45-54, load exactly 30k, no load rule |

---

## 9. Frontend Plan

### Component Tree

```
App
+-- ThemeProvider (MUI)
`-- QueryClientProvider (TanStack Query)
    `-- Layout (two-column: Panel + Map)
        +-- LeftPanel
        |   +-- TripForm
        |   |   +-- AddressAutocomplete (origin)
        |   |   +-- AddressAutocomplete (destination)
        |   |   +-- DateTimePicker (MUI X)
        |   |   +-- LoadWeightField
        |   |   `-- AnalyzeButton
        |   +-- [loading] LoadingState (3 skeleton cards)
        |   +-- [error] ErrorState + RetryButton
        |   +-- [results] RouteCardList
        |   |   +-- RouteCard x3 (clickable)
        |   |   `-- RecommendationBanner
        |   `-- [results] RecommendationPanel
        |       +-- ExplanationText
        |       `-- ComparisonTable
        `-- MapPanel
            +-- [results] HeatmapToggle + HourSlider
            `-- MapView (react-map-gl)
                +-- RouteLayer x3 (GeoJSON line layers)
                +-- CheckpointLayer (GeoJSON circle layer, risk-colored)
                +-- CheckpointPopup (on checkpoint click)
                `-- HeatmapLayer (Mapbox heatmap, feature-state updates)
```

### State Management

- **Server state**: TanStack Query (`useAnalyzeTrip`, `useHeatmap`)
- **UI state**: React `useState`
  - `selectedRouteId: string | null`
  - `selectedCheckpointId: string | null`
  - `heatmapHour: number` (0-48)
  - `heatmapVisible: boolean`
- **Heatmap data**: `useRef` after fetch -- avoids re-renders on slider move
- **Slider**: updates Mapbox feature-state directly via `mapRef.current.setFeatureState(...)` -- zero React re-renders per tick

### Loading, Error, Empty States

- **Empty**: form only, placeholder "Enter a trip to see routes"
- **Loading**: skeleton cards, map spinner overlay, button disabled + "Analyzing..."
- **Partial failure**: routes shown, warning banner: "Weather data unavailable for N checkpoints"
- **Full error**: readable message card + "Try again" button

### Responsive Layout

- >= 900px: side-by-side, map fills right 60%, panel left 40%
- < 900px: map 50vh on top, panel scrollable below

### Accessibility

- All inputs have `<label>` or `aria-label`
- Color paired with text label or icon (never color alone)
- `aria-live="polite"` on results area
- Keyboard navigation for all interactive elements
- Contrast >= 4.5:1 for all text

### Performance Approach (Map)

- Checkpoints: single GeoJSON `circle` layer, not DOM markers
- Heatmap: Mapbox `feature-state` updates per hour (no GeoJSON rebuild)
- Route geometries simplified server-side before sending
- Map code lazy-loaded via `React.lazy()` + `Suspense`
- Slider throttled to 50ms

---

## 10. Performance Plan

### Cache Keys and TTLs

| Data | Cache Key Pattern | TTL | Compliance / Verification Status |
|------|------------------|-----|---------------------------------|
| Geocoding | NONE (no backend cache) | 0s | Required by Mapbox Temporary Geocoding Terms (no caching allowed) |
| Routes | `routes:{orig_lat2}:{orig_lng2}:{dest_lat2}:{dest_lng2}` | 300s (5min) | Disabled by default (`ENABLE_ROUTE_CACHE=false`); server-side route caching is NOT claimed as legally approved and needs owner verification |
| Weather | `weather:{lat2dp}:{lng2dp}:{date_ymd}:{hour_utc}` | 1,800s (30min) | Permitted (Open-Meteo CC-BY 4.0) |
| Heatmap | `heatmap:{corridor_hash8}:{depart_hour_utc}:{load_lb}` | 1,800s (30min) | Permitted (computed internal risk grid) |

`lat2dp` = rounded to 2 decimal places (~1 km grid).

### Request Batching

- Open-Meteo: multi-location coordinate syntax (`latitude=lat1,lat2&longitude=lng1,lng2`) and response array behavior are verified.
- Batch size limit: chunked into conservative batches of up to 50 locations per request. No 1,000-location maximum is claimed.
- Latency: no 300 ms response time is guaranteed; actual response time is not an SLA and will be measured empirically during testing.

### Measurable Targets

| Metric | Target |
|--------|--------|
| POST /analyze/ cold cache | < 10 seconds |
| POST /analyze/ warm cache | < 1 second |
| Heatmap load | < 5 seconds |
| Slider frame time | < 16ms (no visible stutter) |
| Frontend initial bundle | < 500 KB gzipped |

### Backend Optimizations

- DRF throttling: 60/min on `/analyze/`, 120/min on `/geocode/`
- Request timeouts: 10s routing, 15s weather
- Retry with exponential backoff: max 2 retries for external calls
- Resilient cache wrapper (planned design): `ResilientCache` wrapper to intercept Redis connection errors and route to `LocMemCache` so cache outages never crash requests (scheduled for Phase 5 implementation and testing)
- Payload: route geometries simplified server-side (Douglas-Peucker, tolerance 0.0001 degrees)

---

## 11. Phased Task List

Total estimated: **15.5 hours**

| # | Phase | Outcome | Acceptance Criteria | Est. Hours |
|---|-------|---------|---------------------|------------|
| 1 | Repo scaffolding | Monorepo with correct folder structure | `docker-compose up` starts backend + Redis; `/api/v1/health/` responds | 0.5 |
| 2 | Django project setup | Django app runs; migrations applied | `python manage.py check` passes; health endpoint returns 200 | 1.0 |
| 3 | Domain: risk module | Pure risk classification, all load rules | All 30 golden tests pass (`pytest tests/test_risk.py`) | 1.5 |
| 4 | Domain: sampling, ETA, ranking | Checkpoints sampled; ETAs computed; routes ranked | Segment miles sum to route total; ranking matches spec in tests | 2.0 |
| 5 | API adapters & Cache resilience | Mapbox + Open-Meteo wrappers; custom ResilientCache (Redis + LocMemCache fallback) | ResilientCache tested with mocked Redis outage; external APIs mocked | 1.5 |
| 6 | Analyze trip endpoint | Full POST /api/v1/trips/analyze/ | 3 routes returned; validations enforced; DB record written | 2.0 |
| 7 | Heatmap endpoint | POST /api/v1/trips/heatmap/ | <=400 grid points, 49 hour_risks each; batched in chunks of <=50 points | 1.5 |
| 8 | Geocode endpoint | GET /api/v1/geocode/ | <=5 results; ephemeral passthrough (no backend caching per Mapbox ToS) | 0.5 |
| 9 | Frontend setup | Vite dev server; MUI theme applied | `npm run dev` opens themed page at localhost:5173; no TS errors | 0.5 |
| 10 | Trip form | Address autocomplete; form validates; Analyze calls API | Debounced geocode (300ms); inline validation; button disabled during load | 1.0 |
| 11 | Map + routes + checkpoints | 3 route lines + risk-colored checkpoints; popup on click | GeoJSON layers; popup shows all required fields; map fits routes | 1.5 |
| 12 | Route cards + recommendation | Cards with metrics + badges; clicking highlights route | Recommended badge; comparison table shown | 0.5 |
| 13 | Heatmap layer + slider | Heatmap overlay + 0-48h slider, no network on move | Feature-state update; throttled slider; legend visible | 1.0 |
| 14 | Loading/error/empty states | All 3 UI states visible | No blank screens; retry button works | 0.5 |
| 15 | Frontend tests | Vitest unit tests for utils | formatDistance, formatDuration, riskLevelToColor tests pass | 0.5 |
| 16 | Docker, deployment, docs | Full Docker build; deployed | Health endpoint live on Cloud Run; frontend live on Firebase | 1.0 |

---

## 12. Test Plan

### Backend Unit Tests (pytest)

**`test_risk.py`** -- All 30 golden tests, parametrized with `@pytest.mark.parametrize`.

**`test_sampling.py`**:
- Checkpoint count correct for various route lengths and intervals
- Segment miles sum equals route total (within MILE_TOLERANCE = 0.001)
- Origin always mile 0, destination always at end
- Deduplication when last checkpoint is within 0.01 miles of destination

**`test_eta.py`**:
- ETA at mile 0 equals departure time
- ETA at end equals departure + total duration
- Midpoint ETA correctly interpolated
- Time zone: departure in -06:00 stored correctly in UTC
- Proportional fallback produces correct result for uniform-speed segments

**`test_ranking.py`**:
- Route with 0 severe miles ranked above route with severe miles
- Fewer high miles breaks severe-miles tie
- Average risk breaks high-miles tie
- Duration breaks average-risk tie
- No Travel routes ranked below all ok routes
- All-No-Travel case: warning present, least-bad returned
- MILE_TOLERANCE constant used for comparison

**`test_heatmap.py`**:
- Grid point count <= MAX_HEATMAP_POINTS
- Each point has exactly 49 hour_risks
- Risk values in [0, 4]
- Corridor hash stable for same input

### Backend Integration Tests (external APIs mocked)

**`test_api.py`** using `responses` library:
- `test_analyze_trip_success`: 200, 3 routes, recommendation
- `test_analyze_trip_departure_in_past`: 400 INVALID_DEPARTURE_TIME
- `test_analyze_trip_invalid_load`: 400 INVALID_LOAD_WEIGHT
- `test_analyze_trip_weather_failure`: checkpoints have `weather_available: false`; warning in meta
- `test_geocode_success`: 200, <=5 results (verifying no backend cache key is written)
- `test_cache_resilient_fallback`: simulates Redis connection/timeout error; verifies all cache reads/writes transparently fall back to LocMemCache without throwing exceptions
- `test_heatmap_success`: 200, grid_points <= 400
- `test_health`: 200 {"status": "ok"}

### Frontend Unit Tests (Vitest)

- `units.test.ts`: formatDistance(512.4) -> "512.4 mi"; formatDuration(487) -> "8 hr 7 min"
- `risk.test.ts`: riskLevelToColor for all 5 levels returns non-null values
- `time.test.ts`: ETA formatting with timezone abbreviation

### Manual End-to-End Scenarios

**Scenario 1 -- Low-risk trip:**
- Denver, CO -> Salt Lake City, UT; tomorrow 9 AM local; 20,000 lb
- Expected: 3 routes; most checkpoints Low/Moderate; no No Travel; recommendation shown; heatmap works.

**Scenario 2 -- Severe weather trip:**
- Minneapolis, MN -> Chicago, IL; winter departure; 50,000 lb
- Expected: some Severe/High checkpoints; recommendation shows fewest Severe miles; explanation mentions tradeoff.

**Scenario 3 -- All routes No Travel:**
- Any origin/destination with mock blizzard (55+ mph winds everywhere)
- Expected: "Do not travel" banner; all routes "Not recommended"; least-bad shown; no crash.

---

## 13. Deployment Plan

### Prerequisites
- Google Cloud account with billing enabled (credit card required)
- Mapbox account: https://account.mapbox.com/auth/signup/
- Upstash account: https://console.upstash.com (no credit card for free tier)
- Docker Desktop installed
- Firebase CLI: `npm install -g firebase-tools`
- gcloud CLI installed and authenticated

### Step 1: Create API Keys
1. **Mapbox**: account.mapbox.com -> Tokens -> Create a public token -> copy to `.env` as `MAPBOX_ACCESS_TOKEN`
2. **Upstash Redis**: Create a Redis database -> copy Redis URL as `REDIS_URL=rediss://default:<token>@<host>:6379`
3. **Open-Meteo**: No key needed.
4. **Google Cloud**: `gcloud auth login && gcloud config set project <project-id>`

### Step 2: Local Development
```bash
cp .env.example .env
# Edit .env with real values

docker-compose up -d
# OR without Docker:
cd backend && python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt && pip install -r requirements-dev.txt
python manage.py migrate && python manage.py runserver

cd frontend && npm install && npm run dev
# Open http://localhost:5173
```

### Step 3: Run Tests
```bash
cd backend && pytest --tb=short
cd frontend && npm run test
```

### Step 4: Build and Deploy Backend
```bash
cd backend
gcloud builds submit --tag gcr.io/<PROJECT_ID>/safehaul-backend
gcloud run deploy safehaul-backend \
  --image gcr.io/<PROJECT_ID>/safehaul-backend \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars DJANGO_SETTINGS_MODULE=config.settings.production,SECRET_KEY=<secret>,MAPBOX_ACCESS_TOKEN=<token>,REDIS_URL=<upstash-url>,ALLOWED_HOSTS=<run-url>,CORS_ALLOWED_ORIGINS=https://<firebase-url>
```

### Step 5: Deploy Frontend
```bash
cd frontend
# Set VITE_API_BASE_URL=https://<cloud-run-url> in .env.production
npm run build
firebase login && firebase init hosting  # public dir: dist, SPA: yes
firebase deploy
```

### Step 6: Verify
```bash
curl https://<cloud-run-url>/api/v1/health/
# Expected: {"status":"ok", ...}

# Open https://<firebase-url> in browser
# Check: no console errors, form works, analysis returns results
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SETTINGS_MODULE` | Yes | `config.settings.production` in prod |
| `SECRET_KEY` | Yes | Django secret key (min 50 chars) |
| `DEBUG` | No | `False` in production |
| `ALLOWED_HOSTS` | Yes (prod) | Comma-separated allowed hosts |
| `DATABASE_URL` | No | Postgres URL; SQLite if unset |
| `REDIS_URL` | No | Redis URL; LocMemCache if unset |
| `MAPBOX_ACCESS_TOKEN` | Yes | Mapbox public token |
| `CORS_ALLOWED_ORIGINS` | Yes (prod) | Frontend origin URL |
| `VITE_API_BASE_URL` | Yes (frontend) | Backend URL |
| `VITE_MAPBOX_TOKEN` | Yes (frontend) | Same Mapbox token |

---

## 14. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | Mapbox returns fewer than 3 routes | Medium | Medium | Via-waypoint algorithm to create alternatives; warn user if < 3 distinct routes |
| R2 | Open-Meteo rate limit or downtime | Low | High | 30min cache; `weather_available: false` on failure; clear UI warning; no fake data |
| R3 | Cloud Run cold start during demo | High | Medium | Set minimum instances = 1; warmup request in deployment checklist |
| R4 | Time zone calculation errors | Medium | High | `timezonefinder` + `zoneinfo`; unit tests covering DST edge cases; display TZ abbreviation in UI |
| R5 | Redis unavailable (quota/outage) | Low | Low | Django does NOT fall back automatically; planned ResilientCache wrapper will catch Redis errors and route to LocMemCache; scheduled to be implemented and verified in Phase 5 |
| R6 | API keys expired during grading | Low | High | Check quotas before demo; document fallback mock data option |
| R7 | Segment miles don't sum to route total | Low | High | Assert abs(sum - total) < MILE_TOLERANCE in domain logic; unit test this invariant |
| R8 | Open-Meteo unit ambiguity (mm vs in) | Medium | High | Read docs; unit-test conversion; integration test with real API response shape |
| R9 | Mapbox Directions caching terms | Low | Medium | Server-side route caching is not claimed as approved; disabled by default (`ENABLE_ROUTE_CACHE=false`). Requires owner verification against applicable Mapbox terms. |

---

## 15. Documentation Plan

### README.md Sections
1. What SafeHaul does (2 sentences)
2. Screenshot placeholder
3. Feature list
4. Architecture diagram
5. Tech stack table
6. Quick start (without Docker)
7. Quick start (with Docker)
8. Environment variables table
9. API summary (endpoints, one line each)
10. Risk classification rules + boundary decisions
11. Recommendation rules (plain language)
12. Ambiguity decisions
13. How to run tests
14. Deployment steps
15. Known limitations (driving profile not truck-restriction-aware; 7-day forecast limit)
16. Project structure

### LOOM_SCRIPT.md Outline

| Timestamp | Topic |
|-----------|-------|
| 0:00 | Problem -- why weather + load matter for truck drivers |
| 0:30 | Live demo: Chicago -> Kansas City trip |
| 1:30 | Walk through 3 route cards and metrics |
| 2:30 | Click a checkpoint popup -- ETA, weather, risk reason |
| 3:30 | Recommendation panel and comparison table |
| 4:30 | Enable heatmap, drag slider through 48 hours |
| 5:30 | Architecture overview |
| 6:30 | Caching and performance -- warm vs cold request times |
| 7:00 | Show test run output |
| 8:00 | Trade-offs and future improvements |
| 9:00 | Wrap up |

---

## 16. Expected Final Output

**Sample trip:** Chicago, IL -> Kansas City, MO | Jan 20 2025 08:00 CST | 35,000 lb

1. **Empty state**: Trip form with Origin, Destination, date-time picker, load weight field, and "Analyze" button. Map shows default US view.

2. **Autocomplete**: Typing "Chicago" shows 5 suggestions in a dropdown. User selects "Chicago, Illinois, United States." Same for Kansas City. Departure set to Jan 20 08:00 AM local. Load: 35000 lb. Click "Analyze."

3. **Loading**: Button shows "Analyzing..." (disabled). Three skeleton route cards appear in left panel. Map shows loading spinner.

4. **Route cards**: Three cards labeled Route A, B, C each showing: distance (e.g., "512.4 mi"), duration ("8 hr 7 min"), arrival time ("4:07 PM CST"), risk metrics ("0 Severe | 14.2 High mi"), average risk bar, and either a green "Recommended" or grey "Not recommended" badge.

5. **Map**: Three route lines in distinct colors (blue, teal, purple). Selected (recommended) route is slightly thicker. Small circles along routes colored by risk level (green/yellow/orange/red). Map fits bounding box of all routes.

6. **Recommendation panel**: "Route B is recommended. Route B has 0 Severe miles vs 0 on Route A, has fewer High miles (9.3 vs 14.2), and is 22 minutes longer." Comparison table shows all three routes with metrics side by side.

7. **Checkpoint popup**: Click an orange checkpoint on Route A. Popup: "Mile 125.0 | ETA: 10:30 AM CST (Jan 20) | Wind: 38.2 mph | Gusts: 47 mph | Rain: 0.12 in/hr | Snow: 0 | Risk: High | Reason: Wind 38.2 mph -> High."

8. **Heatmap**: Click "Show Heatmap." Color gradient overlay appears on the map. Slider reads "Hour 0 -- Jan 20, 8:00 AM CST." Drag to Hour 24 -- overlay colors update instantly, no loading indicator. Legend shows Low (green) to No Travel (dark purple).

9. **No Travel scenario**: If trip passes through 55+ mph wind zones, a red banner reads: "Do not travel at this departure time. All routes pass through No Travel conditions." All cards show "Not recommended." Least-bad route still identified.

This is the definition of done. Every item above must be verifiable in the deployed app.

---

*End of BUILD_PLAN.md*
