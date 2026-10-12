"""
SafeHaul adapter base classes and custom exceptions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

# ── Custom Exceptions ───────────────────────────────────────────────────────

class SafeHaulAdapterException(Exception):
    """Base exception for all adapter errors."""


class RoutingUnavailableException(SafeHaulAdapterException):
    """Raised when routing engine (Mapbox Directions) fails or is unreachable."""


class GeocodingUnavailableException(SafeHaulAdapterException):
    """Raised when geocoding service (Mapbox Geocoding) fails or is unreachable."""


class WeatherUnavailableException(SafeHaulAdapterException):
    """Raised when weather forecast service (Open-Meteo) fails or is unreachable."""


# ── Abstract Interfaces ────────────────────────────────────────────────────

class BaseRoutingAdapter(ABC):
    """Interface for routing engines."""

    @abstractmethod
    def get_routes(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> list[dict]:
        """Fetch candidate routes from origin [lat, lng] to destination [lat, lng]."""


class BaseGeocodingAdapter(ABC):
    """Interface for geocoding services."""

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Search places by text query, returning list of {label, lat, lng}."""


class BaseWeatherAdapter(ABC):
    """Interface for weather forecast providers."""

    @abstractmethod
    def get_forecast_for_locations(
        self,
        locations: list[tuple[float, float]],
    ) -> dict[tuple[float, float], dict]:
        """Fetch hourly weather forecasts for given [lat, lng] points."""
