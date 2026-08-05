"""API v1 routes (05 §9).

Path versioning from the first endpoint: field devices run whatever build the salesman
last installed, and the version must be visible to both sides (AD-01, E-07).
"""

from django.urls import path

from api.v1 import auth_views, master_views, stock_views

app_name = "v1"

urlpatterns = [
    path("auth/otp/request", auth_views.OtpRequestView.as_view(), name="otp-request"),
    path("auth/otp/verify", auth_views.OtpVerifyView.as_view(), name="otp-verify"),
    path("auth/login", auth_views.PasswordLoginView.as_view(), name="login"),
    path("auth/refresh", auth_views.RefreshView.as_view(), name="refresh"),
    path("auth/logout", auth_views.LogoutView.as_view(), name="logout"),
    path("auth/me", auth_views.MeView.as_view(), name="me"),
    # --- master data (M1) ---
    path("products", master_views.ProductListView.as_view(), name="product-list"),
    path("products/<int:pk>", master_views.ProductDetailView.as_view(), name="product-detail"),
    path("customers", master_views.CustomerListView.as_view(), name="customer-list"),
    path("customers/<int:pk>", master_views.CustomerDetailView.as_view(), name="customer-detail"),
    path("zones", master_views.ZoneListView.as_view(), name="zone-list"),
    path("reason-codes", master_views.ReasonCodeListView.as_view(), name="reason-code-list"),
    path("media", master_views.MediaUploadView.as_view(), name="media-upload"),
    path("media/<int:pk>", master_views.MediaDetailView.as_view(), name="media-detail"),
    # --- stock (M2) ---
    path("stock", stock_views.StockOnHandView.as_view(), name="stock-on-hand"),
    path("stock/movements", stock_views.StockMovementListView.as_view(), name="stock-movements"),
]
