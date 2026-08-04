"""Root URL configuration."""

from django.urls import include, path

from core.health import healthz

urlpatterns = [
    # Unversioned by design — /healthz is infrastructure, not API (05 §9.12).
    path("healthz", healthz, name="healthz"),
    path("api/v1/", include(("api.v1.urls", "api_v1"), namespace="v1")),
    path("", include("webadmin.urls")),
]
