from django.urls import path

from webadmin import fulfilment_views, master_views, views

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
    # --- TD-12: the zone screens that M1 left missing ---
    path("zones/new/", master_views.zone_form, name="zone-new"),
    path("zones/<int:pk>/", master_views.zone_form, name="zone-edit"),
    # --- stock (M2) ---
    path("stock/", master_views.stock_list, name="stock-list"),
    path("stock/movements/", master_views.stock_movements, name="stock-movements"),
    path("stock/entry/", master_views.stock_entry, name="stock-entry"),
    # --- commercial operations (M3) ---
    path("settings/", master_views.business_profile_form, name="business-profile"),
    path("orders/", master_views.order_list, name="order-list"),
    path("orders/new/", master_views.order_new, name="order-new"),
    path("orders/<int:pk>/", master_views.order_detail, name="order-detail"),
    path("orders/<int:pk>/confirm/", master_views.order_confirm, name="order-confirm"),
    path("orders/<int:pk>/cancel/", master_views.order_cancel, name="order-cancel"),
    # --- fulfilment and billing (M5) ---
    path("deliveries/", fulfilment_views.delivery_list, name="delivery-list"),
    path("orders/<int:pk>/assign/", fulfilment_views.delivery_assign, name="delivery-assign"),
    path(
        "deliveries/<int:pk>/dispatch/",
        fulfilment_views.delivery_dispatch,
        name="delivery-dispatch",
    ),
    path(
        "deliveries/<int:pk>/complete/",
        fulfilment_views.delivery_complete,
        name="delivery-complete",
    ),
    path("deliveries/<int:pk>/fail/", fulfilment_views.delivery_fail, name="delivery-fail"),
    path("invoices/", fulfilment_views.invoice_list, name="invoice-list"),
    path("invoices/<int:pk>/", fulfilment_views.invoice_detail, name="invoice-detail"),
    path("invoices/<int:pk>/pdf/", fulfilment_views.invoice_pdf, name="invoice-pdf"),
    path("orders/<int:pk>/invoice/", fulfilment_views.invoice_issue, name="invoice-issue"),
    path("receivables/", fulfilment_views.receivables, name="receivables"),
    path("customers/<int:pk>/ledger/", fulfilment_views.customer_ledger, name="customer-ledger"),
]
