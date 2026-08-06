"""API v1 routes (05 §9).

Path versioning from the first endpoint: field devices run whatever build the salesman
last installed, and the version must be visible to both sides (AD-01, E-07).
"""

from django.urls import path

from api.v1 import auth_views, billing_views, master_views, order_views, stock_views

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
    # --- commercial operations (M3) ---
    path("orders", order_views.OrderListView.as_view(), name="order-list"),
    path("orders/<int:pk>", order_views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<int:pk>/confirm", order_views.OrderConfirmView.as_view(), name="order-confirm"),
    path("orders/<int:pk>/cancel", order_views.OrderCancelView.as_view(), name="order-cancel"),
    path(
        "customers/<int:pk>/credit",
        order_views.CustomerCreditView.as_view(),
        name="customer-credit",
    ),
    # --- fulfilment (M5) ---
    path("deliveries", billing_views.DeliveryListView.as_view(), name="delivery-list"),
    path("deliveries/<int:pk>", billing_views.DeliveryDetailView.as_view(), name="delivery-detail"),
    path(
        "deliveries/<int:pk>/dispatch",
        billing_views.DeliveryDispatchView.as_view(),
        name="delivery-dispatch",
    ),
    path(
        "deliveries/<int:pk>/complete",
        billing_views.DeliveryCompleteView.as_view(),
        name="delivery-complete",
    ),
    path(
        "deliveries/<int:pk>/fail",
        billing_views.DeliveryFailView.as_view(),
        name="delivery-fail",
    ),
    # --- billing (M5) ---
    path("invoices", billing_views.InvoiceListView.as_view(), name="invoice-list"),
    path("invoices/<int:pk>", billing_views.InvoiceDetailView.as_view(), name="invoice-detail"),
    path(
        "invoices/<int:pk>/cancel",
        billing_views.InvoiceCancelView.as_view(),
        name="invoice-cancel",
    ),
    path("invoices/<int:pk>/pdf", billing_views.InvoicePdfView.as_view(), name="invoice-pdf"),
    path("credit-notes", billing_views.CreditNoteListView.as_view(), name="credit-note-list"),
    # --- ledger (M5) ---
    path(
        "customers/<int:pk>/ledger",
        billing_views.CustomerLedgerView.as_view(),
        name="customer-ledger",
    ),
    path(
        "customers/<int:pk>/balance",
        billing_views.CustomerBalanceView.as_view(),
        name="customer-balance",
    ),
]
