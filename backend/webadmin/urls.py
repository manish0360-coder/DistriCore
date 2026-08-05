from django.urls import path

from webadmin import master_views, views

app_name = "webadmin"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.dashboard_view, name="dashboard"),
    # --- master data (M1) ---
    path("products/", master_views.product_list, name="product-list"),
    path("products/new/", master_views.product_form, name="product-new"),
    path("products/<int:pk>/", master_views.product_form, name="product-edit"),
    path("customers/", master_views.customer_list, name="customer-list"),
    path("customers/new/", master_views.customer_form, name="customer-new"),
    path("customers/<int:pk>/", master_views.customer_form, name="customer-edit"),
    path("zones/", master_views.zone_list, name="zone-list"),
    path("reason-codes/", master_views.reason_code_list, name="reason-code-list"),
]
