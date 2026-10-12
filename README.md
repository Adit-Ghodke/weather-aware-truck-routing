# SafeHaul — Weather-Aware Truck Route Planner

SafeHaul evaluates multiple route alternatives between an origin and destination, samples checkpoints at regular intervals, fetches weather forecasts matching the truck's estimated arrival time (ETA), and scores weather risk against vehicle load weight to recommend the safest route.

---

### 🌐 Live Deployment
- **Frontend Web App (Vercel)**: [https://weather-aware-truck-routing-sandy.vercel.app/](https://weather-aware-truck-routing-sandy.vercel.app/)
- **Backend REST API (Render)**: [https://safehaul-backend1.onrender.com](https://safehaul-backend1.onrender.com)
  - API Health Check: [https://safehaul-backend1.onrender.com/api/v1/health/](https://safehaul-backend1.onrender.com/api/v1/health/)

---

## Features

- **Multi-Route Generation**: Generates 3 distinct route alternatives between origin and destination with parallel via-waypoint routing and strict geometric spur elimination.
- **Dynamic Checkpoint Sampling**: Samples checkpoints along each candidate route every 10, 25, or 50 miles based on route length.
- **Precision ETA & Weather Matching**: Computes cumulative driving time to each checkpoint and queries Open-Meteo hourly weather matching the truck's exact estimated arrival time.
- **Universal Timezone Resolution**: Worldwide IANA timezone and local offset detection at origin and along checkpoints via `GET /api/v1/timezones/resolve/`.
- **Load-Aware Risk Scoring**: Pure rule-based scoring engine classifying wind, rain, and snow risk, with load weight thresholds applied to sustained winds (e.g. >30,000 lb and >40,000 lb escalations).
- **Exact Lexicographic Route Recommendation**: Evaluates Severe miles, High miles, distance-weighted average risk, and travel time with transparent deciding-rule explanations and second-level tie breaking.
- **Corridor Weather Heatmap & 48-Hour Slider**: Visualizes weather risk strictly along the 40-mile highway corridor buffer with Doppler-style atmospheric glow, zero network requests during slider movement, and transparent clear weather.
- **Performance Optimized**: Sub-second cached route analysis (0.11s), lazy-loaded map bundle (77.5% smaller initial JS load), and WCAG-compliant high-contrast typography.

---

## Architecture

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
|    (toggleable)     |                       | | Mapbox       |   |
|  - Weather cache    |                       | | Directions   |   |
|    (30min TTL)      |                       | | Geocoding    |   |
|  - Heatmap cache    |                       | +--------------+   |
|    (30min TTL)      |                       | +--------------+   |
|  Fallback: custom   |                       | | Open-Meteo   |   |
|  ResilientCache     |                       | | Weather API  |   |
|  (LocMem fallback)  |                       | +--------------+   |
+---------------------+                       +--------------------+
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | React 18, TypeScript, Vite | User interface and client application |
| **UI Components** | Material UI (MUI) v5, MUI X Date Pickers | Form inputs, typography, layout, themes |
| **Server State** | TanStack Query v5 | API querying, caching, loading/error states |
| **Map Rendering** | Mapbox GL JS via react-map-gl | Geospatial routes, checkpoints, and heatmaps |
| **Backend** | Python 3.11+, Django 5, DRF | REST API, serialization, business logic |
| **Domain Logic** | Pure Python modules (`risk.py`, `eta.py`, `rank.py`) | Checkpoint sampling, risk rules, route ranking |
| **Caching** | Redis (Upstash) with `LocMemCache` fallback | Short-term cache for weather and corridor grids |
| **External APIs** | Mapbox Directions & Geocoding, Open-Meteo | Routing geometries, autocomplete, weather forecasts |
| **Container & Cloud** | Docker, Render (Backend API), Vercel (Frontend SPA) | Production deployment and local containerization |

---

## Risk Rules and Thresholds

Sustained wind is measured in mph. Rain and snow rates are measured in inches per hour.

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| **Wind** | <25 | 25–34 | 35–44 | 45–54 | ≥55 |
| **Rain** | <0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00 |
| **Snow** | <0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | >3.0 |

### Boundary Decisions
- **Wind**: Lower bounds 25, 35, 45, 55 are inclusive (`>=`). 34.9 mph is Moderate; 35.0 mph is High; 55.0 mph is No Travel.
- **Rain**: Lower bounds 0.10, 0.25, 0.50 are inclusive (`>=`). Severe covers 0.50 up to and including 1.00. No Travel is strictly greater than 1.00 (`> 1.00`).
- **Snow**: Lower bounds 0.5, 1.0, 2.0 are inclusive (`>=`). Severe covers 2.0 up to and including 3.0. No Travel is strictly greater than 3.0 (`> 3.0`).

### Vehicle Load Rules (Applied to Wind)
- Wind ≥ 55 mph → **No Travel** for any load.
- Wind 45–54 mph AND load > 30,000 lb → **No Travel**.
- Wind 35–44 mph AND load > 40,000 lb → **Severe**.
- "Greater than" is strict: exactly 30,000 lb or 40,000 lb does not trigger the load upgrade.
- A load rule can only raise a risk level, never lower it.

---

## Recommendation Rules

Routes are evaluated in this strict order (lexicographic comparison):
1. **Fewest Severe miles**
2. **Fewest High miles**
3. **Lowest average risk** (distance-weighted mean on 1–5 scale)
4. **Shortest travel time**

> [!NOTE]
> **Known Property of Average Risk Metric**: When two routes have identical Severe miles and High miles, Step 3 evaluates the distance-weighted average risk. A longer route with identical hazardous miles can have a marginally lower average risk score because its additional clear miles dilute the weighted average (e.g., Scenario 2 where Route C has 2.03 avg vs Route B's 2.10 avg with 187.5 Severe miles each). This directly follows the lexicographic rule specification.

**Disqualification**: Any route with a No Travel checkpoint is marked "Not recommended". If all candidate routes contain No Travel checkpoints, a prominent warning is issued ("Do not travel at this departure time"), and the least-bad route is identified.

---

## Ambiguity Resolutions

- **Sampling Interval**: Default auto-selection: ≤150 mi → 10 mi; 150–600 mi → 25 mi; >600 mi → 50 mi. User can override to 10, 25, or 50 miles. Origin (mile 0) and destination are always included.
- **ETA Calculation**: Calculated from Mapbox per-segment duration annotations. If per-segment durations are unavailable, proportional distance interpolation is used and marked approximate.
- **Time Zones**: Departure time is entered in origin local time, converted to UTC for calculations, and each checkpoint ETA is presented in the checkpoint's local time zone with abbreviation (e.g., "CST").
- **Weather Interpolation**: Wind speed is linearly interpolated between surrounding hours. Rain and snow totals use the hourly slot covering the ETA.
- **Wind Gusts**: Gusts are stored for display only and do not alter the risk classification.
- **Departure Limits**: Permitted between 1 hour in the past and 7 days in the future.
- **Load Limits**: Valid range is 1 to 80,000 lb.
- **Heatmap Slider**: Hour 0 represents departure time; slider covers 0 to 48 hours without network requests during adjustment.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Mapbox access token (free account at https://account.mapbox.com/)

### 1. Local Run (Without Docker)

```bash
# Clone and enter directory
cd "Weather-Aware Truck Routing"

# Copy environment template
cp .env.example .env
# Edit .env and set MAPBOX_ACCESS_TOKEN and VITE_MAPBOX_TOKEN

# Backend Setup
cd backend
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
# source venv/bin/activate

pip install -r requirements.txt -r requirements-dev.txt
python manage.py migrate
python manage.py runserver 8000

# Frontend Setup (in a separate terminal)
cd ../frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

### 2. Local Run (With Docker)

```bash
cp .env.example .env
# Set your MAPBOX_ACCESS_TOKEN in .env

docker compose up --build
```

---

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DEBUG` | No | `False` | Django debug mode |
| `SECRET_KEY` | Yes | - | Django secret key (min 50 characters) |
| `ALLOWED_HOSTS` | Yes | `localhost` | Comma-separated allowed hostnames |
| `DATABASE_URL` | No | SQLite | PostgreSQL connection URL |
| `REDIS_URL` | No | None (LocMem) | Redis connection URL |
| `MAPBOX_ACCESS_TOKEN` | Yes | - | Mapbox API public token |
| `ENABLE_ROUTE_CACHE` | No | `False` | Toggle for server-side route caching |
| `CORS_ALLOWED_ORIGINS` | Yes | `http://localhost:5173` | Allowed frontend origins |
| `VITE_API_BASE_URL` | Yes | `http://localhost:8000` | Frontend backend target |
| `VITE_MAPBOX_TOKEN` | Yes | - | Mapbox public token for map canvas |

---

## API Summary

Base path: `/api/v1/`

- `GET /api/v1/health/` — Health check endpoint returning `{ "status": "ok" }`.
- `GET /api/v1/geocode/?q=<query>` — Ephemeral address search suggestions (up to 5 results).
- `GET /api/v1/timezones/resolve/?lat=<lat>&lng=<lng>` — Resolves exact IANA timezone and abbreviation worldwide.
- `POST /api/v1/trips/analyze/` — Evaluates candidate routes, checkpoint risk, and recommendation.
- `POST /api/v1/trips/heatmap/` — Computes 49-hour weather risk grid along trip corridor.
- `GET /api/v1/trips/<uuid>/` — Retrieves stored trip analysis snapshot.

---

## Running Tests

```bash
# Backend Tests
cd backend
pytest -v

# Frontend Tests
cd frontend
npm test
```

---

## Known Limitations

- **Routing Profiles**: Routing calculations utilize passenger/driving profiles provided by Mapbox Directions. They do not incorporate commercial truck physical restrictions (bridge heights, gross vehicle weight limits, or hazardous material prohibitions).
- **Forecast Horizon**: Weather risk predictions rely on Open-Meteo's hourly forecast model, capped at 7 days ahead for route planning.

---

## Monorepo Structure

```
.
├── .env.example
├── .gitignore
├── docker-compose.yml
├── README.md
├── docs/
│   ├── BUILD_PLAN.md
│   └── LOOM_SCRIPT.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── manage.py
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── local.py
│   │   │   └── production.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── safehaul/
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── domain/
│   │   │   ├── constants.py
│   │   │   ├── risk.py
│   │   │   ├── sampling.py
│   │   │   ├── eta.py
│   │   │   ├── ranking.py
│   │   │   └── heatmap.py
│   │   └── adapters/
│   │       ├── cache.py
│   │       ├── mapbox.py
│   │       └── weather.py
│   └── tests/
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    └── src/
```
