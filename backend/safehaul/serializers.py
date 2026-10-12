"""
SafeHaul input/output serializers for DRF endpoints.

Validations enforced (§7, §A6, §A7):
  • origin & destination coordinates in [-90, 90] and [-180, 180]
  • departure_datetime not > 1 hour in past and not > 7 days in future
  • load_weight_lb between 1 and 80,000 lb (inclusive)
  • sample_interval_miles in [10, 25, 50] (optional)
"""

from __future__ import annotations

from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework import serializers

from safehaul.domain.constants import (
    ALLOWED_SAMPLE_INTERVALS,
    LOAD_MAX_LB,
    LOAD_MIN_LB,
)
from safehaul.domain.timezones import resolve_timezone_name


class CoordinateSerializer(serializers.Serializer):
    """Origin or destination coordinate specification."""
    lat = serializers.FloatField(
        min_value=-90.0,
        max_value=90.0,
        error_messages={"invalid": "Latitude must be a valid float between -90 and 90."},
    )
    lng = serializers.FloatField(
        min_value=-180.0,
        max_value=180.0,
        error_messages={"invalid": "Longitude must be a valid float between -180 and 180."},
    )
    label = serializers.CharField(max_length=500, required=True, allow_blank=False)


class AnalyzeTripInputSerializer(serializers.Serializer):
    """Input serializer for POST /api/v1/trips/analyze/."""
    origin = CoordinateSerializer(required=True)
    destination = CoordinateSerializer(required=True)
    departure_datetime = serializers.DateTimeField(required=True)
    load_weight_lb = serializers.IntegerField(required=True)
    sample_interval_miles = serializers.ChoiceField(
        choices=ALLOWED_SAMPLE_INTERVALS,
        required=False,
        allow_null=True,
    )

    def validate_load_weight_lb(self, value: int) -> int:
        if not (LOAD_MIN_LB <= value <= LOAD_MAX_LB):
            raise serializers.ValidationError(
                f"Load weight must be between {LOAD_MIN_LB:,} and {LOAD_MAX_LB:,} lb.",
                code="INVALID_LOAD_WEIGHT",
            )
        return value

    def validate(self, attrs):
        origin = attrs.get("origin")
        departure_dt = attrs.get("departure_datetime")

        if origin and departure_dt:
            tz_name = resolve_timezone_name(origin["lat"], origin["lng"])
            try:
                origin_tz = ZoneInfo(tz_name)
            except Exception:
                origin_tz = UTC

            # Check if input was naive local wall-clock string (e.g. "YYYY-MM-DDTHH:mm:ss" without offset/Z)
            # DRF's DateTimeField automatically attaches UTC to naive inputs when USE_TZ=True.
            raw_val = self.initial_data.get("departure_datetime") if isinstance(self.initial_data, dict) else None
            is_naive_input = False
            if isinstance(raw_val, str):
                time_portion = raw_val.split("T")[-1] if "T" in raw_val else raw_val
                is_naive_input = not time_portion.endswith("Z") and "+" not in time_portion and "-" not in time_portion

            if is_naive_input or timezone.is_naive(departure_dt):
                departure_dt = departure_dt.replace(tzinfo=origin_tz)

            now_utc = timezone.now()
            departure_utc = departure_dt.astimezone(UTC)
            min_time = now_utc - timedelta(hours=1)
            max_time = now_utc + timedelta(days=7)

            if departure_utc < min_time or departure_utc > max_time:
                raise serializers.ValidationError(
                    {"departure_datetime": "Departure time must not be more than 1 hour in the past or more than 7 days in the future."},
                    code="INVALID_DEPARTURE_TIME",
                )

            attrs["departure_datetime"] = departure_dt
            attrs["departure_datetime_utc"] = departure_utc

        return attrs


class HeatmapInputSerializer(serializers.Serializer):
    """Input serializer for POST /api/v1/trips/heatmap/ (§7)."""
    trip_id = serializers.UUIDField(required=False, allow_null=True)
    corridor_geometry = serializers.DictField(required=False, allow_null=True)
    departure_datetime = serializers.DateTimeField(required=False, allow_null=True)
    load_weight_lb = serializers.IntegerField(required=True)

    def validate_load_weight_lb(self, value: int) -> int:
        if not (LOAD_MIN_LB <= value <= LOAD_MAX_LB):
            raise serializers.ValidationError(
                f"Load weight must be between {LOAD_MIN_LB:,} and {LOAD_MAX_LB:,} lb.",
                code="INVALID_LOAD_WEIGHT",
            )
        return value

    def validate(self, attrs):
        trip_id = attrs.get("trip_id")
        corridor_geo = attrs.get("corridor_geometry")
        departure_dt = attrs.get("departure_datetime")

        if not trip_id and not corridor_geo:
            raise serializers.ValidationError(
                "Either 'trip_id' or 'corridor_geometry' must be provided.",
                code="REQUIRED",
            )

        if not trip_id and not departure_dt:
            raise serializers.ValidationError(
                "When 'trip_id' is not provided, 'departure_datetime' is required.",
                code="REQUIRED",
            )

        return attrs

