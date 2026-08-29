from django.urls import path

from webadmin import (
    fulfilment_views,
    master_views,
    purchasing_views,
    receivables_views,
    report_views,
    views,
)

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
    # --- suppliers (D5 Stage 1 — FR-PUR-001, FR-PUR-002) ---
    path("suppliers/", purchasing_views.supplier_list, name="supplier-list"),
    path("suppliers/new/", purchasing_views.supplier_form, name="supplier-new"),
    path("suppliers/<int:pk>/", purchasing_views.supplier_form, name="supplier-edit"),
    path(
        "suppliers/<int:pk>/products/",
        purchasing_views.supplier_products,
        name="supplier-products",
    ),
    # --- purchase orders (D5 Stage 2 — FR-PUR-003, FR-PUR-005) ---
    path("purchase-orders/", purchasing_views.purchase_order_list, name="purchase-order-list"),
    path("purchase-orders/new/", purchasing_views.purchase_order_form, name="purchase-order-new"),
    path(
        "purchase-orders/<int:pk>/",
        purchasing_views.purchase_order_detail,
        name="purchase-order-detail",
    ),
    path(
        "purchase-orders/<int:pk>/edit/",
        purchasing_views.purchase_order_form,
        name="purchase-order-edit",
    ),
    path(
        "purchase-orders/<int:pk>/issue/",
        purchasing_views.purchase_order_issue,
        name="purchase-order-issue",
    ),
    path(
        "purchase-orders/<int:pk>/cancel/",
        purchasing_views.purchase_order_cancel,
        name="purchase-order-cancel",
    ),
    path(
        "purchase-orders/<int:pk>/close/",
        purchasing_views.purchase_order_close,
        name="purchase-order-close",
    ),
    # --- goods receipts (D5 Stage 3 — FR-PUR-006…011, FR-PUR-013) ---
    #
    # The receive route is nested under the purchase order because that is what it acts on:
    # goods are always received *against* an order, never freestanding. There is deliberately
    # no edit or delete route — a posted receipt is immutable (`04` T-32).
    path(
        "purchase-orders/<int:pk>/receive/",
        purchasing_views.goods_receipt_form,
        name="goods-receipt-new",
    ),
    path("goods-receipts/", purchasing_views.goods_receipt_list, name="goods-receipt-list"),
    path(
        "goods-receipts/<int:pk>/",
        purchasing_views.goods_receipt_detail,
        name="goods-receipt-detail",
    ),
    # --- supplier payments (D5 Stage 4 S4.3 — FR-PUR-012) ---
    #
    # `pay/` is a **GET** and that is load-bearing: it mints the `submission_id` that makes
    # a duplicate POST identifiable (E3). Post/Redirect/Get after success, so a refresh
    # re-issues the GET and mints a fresh id — which is exactly why a deliberate second
    # payment works while a replay does not.
    path(
        "suppliers/<int:pk>/pay/",
        purchasing_views.supplier_payment_form,
        name="supplier-payment-new",
    ),
    path(
        "suppliers/<int:pk>/pay/record/",
        purchasing_views.supplier_payment_record,
        name="supplier-payment-record",
    ),
    path(
        "supplier-payments/",
        purchasing_views.supplier_payment_list,
        name="supplier-payment-list",
    ),
    path(
        "supplier-payments/<int:pk>/",
        purchasing_views.supplier_payment_detail,
        name="supplier-payment-detail",
    ),
    path(
        "supplier-payments/<int:pk>/reverse/",
        purchasing_views.supplier_payment_reverse,
        name="supplier-payment-reverse",
    ),
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
    # --- receivables (M6) ---
    path("payments/", receivables_views.payment_list, name="payment-list"),
    path(
        "payments/<int:pk>/reverse/",
        receivables_views.payment_reverse,
        name="payment-reverse",
    ),
    path(
        "customers/<int:pk>/pay/",
        receivables_views.payment_record,
        name="payment-record",
    ),
    path("customers/<int:pk>/write-off/", receivables_views.write_off, name="write-off"),
    path(
        "customers/<int:pk>/outstanding/",
        receivables_views.outstanding,
        name="customer-outstanding",
    ),
    path(
        "receivables/position/",
        receivables_views.receivables_report,
        name="receivables-position",
    ),
    # --- reports (M7). All accept ?format=csv (FR-RPT-012).
    path("reports/sales/", report_views.sales, name="report-sales"),
    path("reports/stock/", report_views.stock, name="report-stock"),
    path("reports/stock-variance/", report_views.stock_variance, name="report-stock-variance"),
    path("reports/returns/", report_views.returns, name="report-returns"),
    path("reports/receivables/", report_views.receivables, name="report-receivables"),
    path("reports/top-customers/", report_views.top_customers, name="report-top-customers"),
    path("reports/order-status/", report_views.order_status, name="report-order-status"),
    path(
        "customers/<int:pk>/statement.csv",
        report_views.customer_statement_csv,
        name="customer-statement-csv",
    ),
]
