from django.urls import path

from safehaul.views import (
    AnalyzeTripView,
    GeocodeView,
    HealthCheckView,
    HeatmapView,
    TimezoneResolveView,
    TripDetailView,
)

app_name = "safehaul"

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health"),
    path("geocode/", GeocodeView.as_view(), name="geocode"),
    path("timezones/resolve/", TimezoneResolveView.as_view(), name="timezone-resolve"),
    path("trips/analyze/", AnalyzeTripView.as_view(), name="analyze-trip"),
    path("trips/heatmap/", HeatmapView.as_view(), name="heatmap"),
    path("trips/<uuid:trip_id>/", TripDetailView.as_view(), name="trip-detail"),
]



