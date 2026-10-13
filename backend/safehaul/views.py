"""
SafeHaul REST API Views — Health, Trip Analysis, and Trip Details.

Specifications (§7):
  • POST /api/v1/trips/analyze/: Orchestrates routing, checkpoint sampling,
    weather forecasts, risk evaluation, route metrics, ranking, and non-blocking persistence.
  • GET /api/v1/trips/<uuid>/: Retrieves stored analysis snapshot.
  • GET /api/v1/health/: System liveness probe.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView, exception_handler

from safehaul.adapters.base import (
    GeocodingUnavailableException,
    RoutingUnavailableException,
)
from safehaul.adapters.cache import get_resilient_cache
from safehaul.adapters.mapbox import (
    MapboxGeocodingAdapter,
    MapboxRoutingAdapter,
)
from safehaul.adapters.weather import OpenMeteoWeatherAdapter
from safehaul.domain.eta import (
    compute_checkpoint_etas,
    get_precip_at_eta,
    get_weather_slots,
    interpolate_gust_at_eta,
    interpolate_wind_at_eta,
)
from safehaul.domain.heatmap import (
    compute_corridor_hourly_risks,
    generate_corridor_grid,
)
from safehaul.domain.ranking import compute_route_metrics, rank_routes
from safehaul.domain.risk import classify_checkpoint
from safehaul.domain.sampling import (
    auto_select_interval,
    compute_segment_miles,
    sample_checkpoints,
)
from safehaul.domain.timezones import format_local_eta
from safehaul.models import TripAnalysis
from safehaul.serializers import (
    AnalyzeTripInputSerializer,
    HeatmapInputSerializer,
)

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Standardized DRF exception handler matching the SafeHaul API contract:

    {"error": {"code": "...", "message": "...", "details": {...}}}
    """
    response = exception_handler(exc, context)

    if response is not None:
        code = "VALIDATION_ERROR"
        message = str(exc)
        details = {}

        if hasattr(exc, "detail") and isinstance(exc.detail, dict):
            details = exc.detail
            # Extract specific validator code (e.g. INVALID_LOAD_WEIGHT, INVALID_DEPARTURE_TIME)
            generic_codes = {"invalid", "required", "blank", "null"}
            for field, errs in details.items():
                if isinstance(errs, list) and errs:
                    err_item = errs[0]
                    item_code = getattr(err_item, "code", None)
                    if item_code and item_code not in generic_codes:
                        code = str(item_code).upper()
                        message = str(err_item)
                        break
                    else:
                        code = "VALIDATION_ERROR"
                        message = f"Validation error on '{field}': {err_item}"
                elif hasattr(errs, "code") and errs.code and errs.code not in generic_codes:
                    code = str(errs.code).upper()
                    message = str(errs)
                    break

        elif hasattr(exc, "detail") and isinstance(exc.detail, list):
            details = {"errors": exc.detail}
            message = "; ".join([str(e) for e in exc.detail])
        elif hasattr(exc, "default_code"):
            code = str(exc.default_code).upper()
            message = str(exc)

        response.data = {
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        }
    return response


class HealthCheckView(APIView):
    """GET /api/v1/health/

    Simple health check endpoint returning service status.
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request, *args, **kwargs):
        return Response(
            {
                "status": "ok",
                "timestamp": timezone.now().isoformat(),
            },
            status=status.HTTP_200_OK,
        )


class AnalyzeTripView(APIView):
    """POST /api/v1/trips/analyze/

    Core trip analysis endpoint — evaluates weather hazards along candidate routes.
    """
    authentication_classes = []
    permission_classes = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.routing_adapter = MapboxRoutingAdapter()
        self.weather_adapter = OpenMeteoWeatherAdapter()

    def post(self, request, *args, **kwargs):
        serializer = AnalyzeTripInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        origin = data["origin"]
        destination = data["destination"]
        departure_dt = data["departure_datetime"]
        departure_utc = departure_dt.astimezone(UTC)
        load_weight_lb = data["load_weight_lb"]
        user_interval = data.get("sample_interval_miles")

        warnings: list[str] = []

        # 1. Fetch candidate routes from Mapbox
        try:
            candidate_routes = self.routing_adapter.get_routes(
                origin=(origin["lat"], origin["lng"]),
                destination=(destination["lat"], destination["lng"]),
                enable_waypoint_fallback=True,
                departure_hour=departure_utc.hour,
            )
        except RoutingUnavailableException as err:
            logger.error(f"Routing unavailable: {err}")
            err_str = str(err).lower()
            if "maximum distance" in err_str or "noroute" in err_str or "0 routes" in err_str:
                return Response(
                    {
                        "error": {
                            "code": "NO_OVERLAND_ROUTE",
                            "message": "No drivable road route found between origin and destination. SafeHaul truck routing requires contiguous overland roadways.",
                            "details": {"reason": str(err)},
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {
                    "error": {
                        "code": "ROUTING_UNAVAILABLE",
                        "message": "Routing provider is currently unavailable.",
                        "details": {"reason": str(err)},
                    }
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as err:
            logger.exception(f"Unexpected routing failure: {err}")
            return Response(
                {
                    "error": {
                        "code": "ANALYSIS_FAILED",
                        "message": "Unexpected failure generating candidate routes.",
                        "details": {"reason": str(err)},
                    }
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if len(candidate_routes) < 3:
            warnings.append(
                f"Fewer than 3 candidate routes returned by routing provider ({len(candidate_routes)} available)."
            )

        # 2. Sample checkpoints, compute segment miles, and calculate ETAs for each route
        all_unique_coords: list[tuple[float, float]] = []

        interval_used = user_interval
        for route in candidate_routes:
            dist_mi = route["distance_miles"]
            interval = user_interval if user_interval else auto_select_interval(dist_mi)
            if not interval_used:
                interval_used = interval

            # Sample checkpoints along polyline
            checkpoints = sample_checkpoints(
                coordinates=route["geometry"]["coordinates"],
                sample_interval_miles=interval,
                total_distance_miles=dist_mi,
            )

            # Attribute segment miles
            seg_miles = compute_segment_miles(checkpoints, dist_mi)
            for i, cp in enumerate(checkpoints):
                cp["segment_miles"] = seg_miles[i]

            # Compute ETAs
            compute_checkpoint_etas(
                checkpoints=checkpoints,
                departure_datetime_utc=departure_utc,
                route_segments=route.get("segments"),
                total_distance_miles=dist_mi,
                total_duration_seconds=route.get("duration_seconds"),
            )

            # Local timezone info
            for cp in checkpoints:
                eta_local_iso, tz_name, tz_abbr = format_local_eta(
                    cp["eta_utc"], cp["lat"], cp["lng"]
                )
                cp["eta_local"] = eta_local_iso
                cp["timezone"] = tz_name
                cp["timezone_abbr"] = tz_abbr
                all_unique_coords.append((cp["lat"], cp["lng"]))

            route["checkpoints"] = checkpoints

        # 3. Batch-fetch weather forecasts for all checkpoints across all routes
        try:
            weather_forecasts = self.weather_adapter.get_forecast_for_locations(all_unique_coords)
        except Exception as err:
            logger.warning(f"Weather provider error: {err}")
            weather_forecasts = {}

        if not weather_forecasts:
            warnings.append("Weather forecast data unavailable; risk scores omitted.")

        # 4. Classify risk at each checkpoint & compute route metrics
        for route in candidate_routes:
            checkpoints = route["checkpoints"]

            for cp in checkpoints:
                norm_coord = (round(cp["lat"], 2), round(cp["lng"], 2))
                hourly_data = weather_forecasts.get(norm_coord)

                if hourly_data:
                    eta_dt = cp["eta_utc"]
                    wind_mph = interpolate_wind_at_eta(hourly_data, eta_dt)
                    gust_mph = interpolate_gust_at_eta(hourly_data, eta_dt)
                    rain_in_hr, snow_in_hr = get_precip_at_eta(hourly_data, eta_dt)

                    risk_result = classify_checkpoint(
                        wind_mph=wind_mph,
                        rain_in_hr=rain_in_hr,
                        snow_in_hr=snow_in_hr,
                        load_lb=load_weight_lb,
                    )

                    slots_info = get_weather_slots(eta_dt)
                    cp["weather"] = {
                        "wind_mph": wind_mph,
                        "gust_mph": gust_mph,
                        "rain_in_hr": rain_in_hr,
                        "snow_in_hr": snow_in_hr,
                        "precip_slot_utc": slots_info["precip_slot_utc"],
                        "wind_slots_utc": slots_info["wind_slots_utc"],
                    }
                    cp["condition_levels"] = risk_result["condition_levels"]
                    cp["level"] = risk_result["level"]
                    cp["reason"] = risk_result["reason"]
                    cp["weather_available"] = True
                else:
                    cp["weather"] = None
                    cp["condition_levels"] = {"wind": "Low", "rain": "Low", "snow": "Low"}
                    cp["level"] = "Low"
                    cp["reason"] = "Weather data unavailable"
                    cp["weather_available"] = False

            # Route aggregation metrics
            route["metrics"] = compute_route_metrics(checkpoints, route["distance_miles"])

            # Departure and arrival times
            dest_cp = checkpoints[-1]
            route["departure_datetime_utc"] = departure_utc.isoformat()
            route["arrival_datetime_utc"] = dest_cp["eta_utc"].isoformat()
            route["arrival_datetime_local"] = dest_cp["eta_local"]

            # Convert checkpoint eta_utc from datetime object to ISO string
            for cp in checkpoints:
                cp["eta_utc"] = cp["eta_utc"].isoformat()
                cp.pop("eta_method", None)

        # 5. Rank routes
        recommendation = rank_routes(candidate_routes)
        if recommendation.get("warning"):
            warnings.append(recommendation["warning"])

        # Strip internal computation fields
        for route in candidate_routes:
            route.pop("segments", None)
            route.pop("duration_seconds", None)
            if "metrics" in route:
                route["metrics"].pop("_average_risk_sort", None)

        # 6. Build final payload
        analysis_id = str(uuid.uuid4())
        payload = {
            "id": analysis_id,
            "routes": candidate_routes,
            "recommendation": recommendation,
            "meta": {
                "units": {
                    "distance": "miles",
                    "wind": "mph",
                    "precipitation": "in/hr",
                    "load": "lb",
                },
                "interval_miles": interval_used or 25,
                "routing_provider": "Mapbox Directions",
                "weather_provider": "Open-Meteo",
                "generated_at": timezone.now().isoformat(),
                "warnings": warnings,
            },
        # 7. Non-blocking persistence to database and cache (§6)
        try:
            self.cache.set(f"trip_analysis:{analysis_id}", payload, timeout=3600)
        except Exception:
            pass

        try:
            TripAnalysis.objects.create(
                id=analysis_id,
                origin_lat=origin["lat"],
                origin_lng=origin["lng"],
                origin_label=origin["label"],
                destination_lat=destination["lat"],
                destination_lng=destination["lng"],
                destination_label=destination["label"],
                departure_datetime_utc=departure_utc,
                load_weight_lb=load_weight_lb,
                sample_interval_miles=interval_used or 25,
                result_json=payload,
            )
        except Exception as db_err:
            logger.warning(f"TripAnalysis persistence failed (non-blocking): {db_err}")

        return Response(payload, status=status.HTTP_200_OK)


class TripDetailView(APIView):
    """GET /api/v1/trips/<uuid:trip_id>/

    Retrieves a stored trip analysis snapshot.
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request, trip_id, *args, **kwargs):
        try:
            trip = TripAnalysis.objects.get(id=trip_id)
        except TripAnalysis.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "TRIP_NOT_FOUND",
                        "message": f"Trip analysis with ID '{trip_id}' not found.",
                        "details": {},
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as db_err:
            return Response(
                {
                    "error": {
                        "code": "DATABASE_ERROR",
                        "message": f"Could not retrieve trip analysis: {db_err}",
                        "details": {},
                    }
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(trip.result_json, status=status.HTTP_200_OK)


class HeatmapView(APIView):
    """POST /api/v1/trips/heatmap/ (§7, §8g).

    Returns a 2D bounding-box corridor grid of up to 400 points, each
    with an array of 49 hourly risk scores (hours 0..48).
    """
    authentication_classes = []
    permission_classes = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.weather_adapter = OpenMeteoWeatherAdapter()
        self.cache = get_resilient_cache()

    def post(self, request, *args, **kwargs):
        serializer = HeatmapInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        trip_id = data.get("trip_id")
        load_weight_lb = data["load_weight_lb"]
        warnings: list[str] = []

        cache_key = None
        if trip_id:
            cache_key = f"heatmap_payload:{trip_id}:{load_weight_lb}"
            cached_payload = self.cache.get(cache_key)
            if cached_payload:
                return Response(cached_payload, status=status.HTTP_200_OK)

        all_coords: list[list[float]] = []
        departure_utc = None

        def _to_utc_dt(val):
            if val is None:
                return None
            if isinstance(val, str):
                try:
                    dt = datetime.fromisoformat(val)
                except ValueError:
                    return None
            else:
                dt = val
            if getattr(dt, "tzinfo", None) is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)

        # 1. If trip_id provided, check cache first, then database
        if trip_id:
            cached_trip = None
            try:
                cached_trip = self.cache.get(f"trip_analysis:{trip_id}")
            except Exception:
                pass

            if cached_trip and isinstance(cached_trip, dict):
                routes = cached_trip.get("routes", [])
                for r in routes:
                    geom = r.get("geometry", {})
                    all_coords.extend(geom.get("coordinates", []))
                    if not departure_utc and r.get("departure_datetime_utc"):
                        departure_utc = _to_utc_dt(r["departure_datetime_utc"])

            if not all_coords:
                try:
                    trip = TripAnalysis.objects.get(id=trip_id)
                    departure_utc = _to_utc_dt(trip.departure_datetime_utc)
                    result_json = trip.result_json or {}
                    routes = result_json.get("routes", [])
                    for r in routes:
                        geom = r.get("geometry", {})
                        all_coords.extend(geom.get("coordinates", []))
                except TripAnalysis.DoesNotExist:
                    logger.info(f"TripAnalysis {trip_id} not found in DB.")
                except Exception as db_err:
                    logger.warning(f"Database error looking up TripAnalysis {trip_id}: {db_err}")

        # 2. Fallback to corridor_geometry & departure_datetime if passed in request
        if not all_coords and data.get("corridor_geometry"):
            corridor_geom = data.get("corridor_geometry", {})
            routes = corridor_geom.get("routes", [])
            for r in routes:
                coords = r.get("coordinates", [])
                all_coords.extend(coords)

        if not departure_utc and data.get("departure_datetime"):
            departure_utc = _to_utc_dt(data["departure_datetime"])

        if not departure_utc:
            departure_utc = timezone.now().astimezone(UTC)

        if not all_coords:
            if trip_id and not data.get("corridor_geometry"):
                return Response(
                    {
                        "error": {
                            "code": "TRIP_NOT_FOUND",
                            "message": f"Trip analysis with ID '{trip_id}' not found. Please provide corridor_geometry.",
                            "details": {},
                        }
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(
                {
                    "error": {
                        "code": "INVALID_CORRIDOR",
                        "message": "No coordinates found to construct corridor bounding box.",
                        "details": {},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Generate grid points
        grid_points = generate_corridor_grid(all_coords)

        # 2. Fetch weather forecasts for grid points
        try:
            forecasts = self.weather_adapter.get_forecast_for_locations(grid_points)
        except Exception as err:
            logger.warning(f"Weather provider error on heatmap: {err}")
            forecasts = {}
            warnings.append("Weather provider unavailable; default risk scores used.")

        # 3. Compute 49 hourly risks for each grid point
        grid_data = compute_corridor_hourly_risks(
            grid_points=grid_points,
            departure_datetime_utc=departure_utc,
            forecasts=forecasts,
            load_weight_lb=load_weight_lb,
            num_hours=49,
        )

        response_payload = {
            "grid": grid_data,
            "hours": 49,
            "departure_datetime_utc": departure_utc.isoformat(),
            "meta": {
                "grid_points": len(grid_data),
                "max_points_cap": 400,
                "warnings": warnings,
            },
        }

        if cache_key:
            self.cache.set(cache_key, response_payload, timeout=3600)

        return Response(response_payload, status=status.HTTP_200_OK)


class GeocodeView(APIView):
    """GET /api/v1/geocode/?q=<string> (§7).

    Ephemeral geocoding passthrough to Mapbox Geocoding API.
    Strictly NO backend caching per Mapbox Temporary Geocoding Terms.
    """
    authentication_classes = []
    permission_classes = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.geocoding_adapter = MapboxGeocodingAdapter()

    def get(self, request, *args, **kwargs):
        query = request.query_params.get("q", "").strip()

        if not query or len(query) < 2 or len(query) > 200:
            return Response(
                {
                    "error": {
                        "code": "INVALID_QUERY",
                        "message": "Query parameter 'q' is required and must be between 2 and 200 characters.",
                        "details": {"q": query},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            results = self.geocoding_adapter.search(query=query, limit=5)

        except GeocodingUnavailableException as err:
            logger.error(f"Geocoding service unavailable: {err}")
            return Response(
                {
                    "error": {
                        "code": "GEOCODING_UNAVAILABLE",
                        "message": "Geocoding provider is currently unavailable.",
                        "details": {"reason": str(err)},
                    }
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as err:
            logger.exception(f"Unexpected geocoding error: {err}")
            return Response(
                {
                    "error": {
                        "code": "GEOCODING_UNAVAILABLE",
                        "message": "Unexpected error contacting geocoding service.",
                        "details": {"reason": str(err)},
                    }
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({"results": results}, status=status.HTTP_200_OK)


class TimezoneResolveView(APIView):
    """GET /api/v1/timezones/resolve/?lat=<float>&lng=<float>

    Universal endpoint resolving the exact worldwide IANA timezone and abbreviation
    for any coordinate on Earth.
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request, *args, **kwargs):
        try:
            lat = float(request.query_params.get("lat"))
            lng = float(request.query_params.get("lng"))
        except (TypeError, ValueError):
            return Response(
                {
                    "error": {
                        "code": "INVALID_COORDINATES",
                        "message": "Valid 'lat' and 'lng' query parameters are required.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        now_utc = timezone.now()
        _, tz_name, tz_abbr = format_local_eta(now_utc, lat, lng)
        return Response(
            {
                "timezone": tz_name,
                "abbr": tz_abbr,
                "lat": lat,
                "lng": lng,
            },
            status=status.HTTP_200_OK,
        )


