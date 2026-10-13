from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def root_health_check(request):
    return JsonResponse(
        {
            "status": "healthy",
            "service": "SafeHaul API",
            "version": "1.0.0",
            "endpoints": {
                "health": "/api/v1/health/",
                "geocode": "/api/v1/geocode/",
                "analyze": "/api/v1/trips/analyze/",
                "heatmap": "/api/v1/trips/heatmap/",
                "timezones": "/api/v1/timezones/resolve/",
            },
        },
        status=200,
    )


urlpatterns = [
    path("", root_health_check, name="root-health"),
    path("health/", root_health_check, name="health-alias"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("safehaul.urls")),
]
