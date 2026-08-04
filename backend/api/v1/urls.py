"""API v1 routes (05 §9).

Path versioning from the first endpoint: field devices run whatever build the salesman
last installed, and the version must be visible to both sides (AD-01, E-07).
"""

from django.urls import path

from api.v1 import auth_views

app_name = "v1"

urlpatterns = [
    path("auth/otp/request", auth_views.OtpRequestView.as_view(), name="otp-request"),
    path("auth/otp/verify", auth_views.OtpVerifyView.as_view(), name="otp-verify"),
    path("auth/login", auth_views.PasswordLoginView.as_view(), name="login"),
    path("auth/refresh", auth_views.RefreshView.as_view(), name="refresh"),
    path("auth/logout", auth_views.LogoutView.as_view(), name="logout"),
    path("auth/me", auth_views.MeView.as_view(), name="me"),
]
