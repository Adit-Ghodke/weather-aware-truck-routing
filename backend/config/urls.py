"""
URL configuration for SafeHaul project.
All API endpoints are mounted under /api/v1/.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("safehaul.urls")),
]
