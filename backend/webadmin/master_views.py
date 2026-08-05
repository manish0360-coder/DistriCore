"""Master-data screens for the owner (ADR-003).

Simple lists, forms and tables — no dashboards, no charts (client direction 3).
Business rules are called, never reimplemented (N-01, BR-001).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from catalogue import selectors as product_selectors
from catalogue import services as product_services
from core.exceptions import DomainError
from customers import selectors as customer_selectors
from customers import services as customer_services
from inventory import selectors as reason_selectors

PAGE_SIZE = 25


def _page(request: HttpRequest, queryset: Any) -> Any:
    return Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))


def _decimal(raw: str, default: str = "0") -> Decimal:
    try:
        return Decimal(raw or default)
    except (InvalidOperation, TypeError):
        return Decimal(default)


# --------------------------------------------------------------------------- products
@login_required
def product_list(request: HttpRequest) -> HttpResponse:
    queryset = product_selectors.search_products(term=request.GET.get("q", "")).order_by("name")
    return render(
        request,
        "webadmin/product_list.html",
        {"page": _page(request, queryset), "q": request.GET.get("q", "")},
    )


@login_required
@require_http_methods(["GET", "POST"])
def product_form(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    product = product_selectors.search_products().filter(pk=pk).first() if pk else None
    error = ""
    if request.method == "POST":
        data = request.POST
        try:
            if product is None:
                product_services.create_product(
                    actor=request.user,
                    code=data.get("code", ""),
                    name=data.get("name", ""),
                    selling_price=_decimal(data.get("selling_price", "")),
                    description=data.get("description", ""),
                    hsn_code=data.get("hsn_code", ""),
                    tax_rate_percent=_decimal(data.get("tax_rate_percent", "")),
                    unit_name=data.get("unit_name") or "PCS",
                    pack_size=int(data.get("pack_size") or 1),
                    pack_name=data.get("pack_name") or "CASE",
                )
            else:
                product_services.update_product(
                    actor=request.user,
                    product=product,
                    name=data.get("name", product.name),
                    selling_price=_decimal(
                        data.get("selling_price", ""), str(product.selling_price)
                    ),
                    description=data.get("description", ""),
                    hsn_code=data.get("hsn_code", ""),
                    tax_rate_percent=_decimal(
                        data.get("tax_rate_percent", ""), str(product.tax_rate_percent)
                    ),
                    unit_name=data.get("unit_name") or "PCS",
                    pack_size=int(data.get("pack_size") or 1),
                    pack_name=data.get("pack_name") or "CASE",
                    is_active=data.get("is_active") == "on",
                )
        except DomainError as exc:
            error = exc.detail
        else:
            return redirect("webadmin:product-list")
    return render(request, "webadmin/product_form.html", {"product": product, "error": error})


# --------------------------------------------------------------------------- customers
@login_required
def customer_list(request: HttpRequest) -> HttpResponse:
    queryset = customer_selectors.search_customers(
        request.user, term=request.GET.get("q", "")
    ).order_by("shop_name")
    return render(
        request,
        "webadmin/customer_list.html",
        {"page": _page(request, queryset), "q": request.GET.get("q", "")},
    )


@login_required
@require_http_methods(["GET", "POST"])
def customer_form(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    customer = None
    if pk:
        try:
            customer = customer_services.get_customer_for(request.user, pk)
        except DomainError:
            return redirect("webadmin:customer-list")

    error = ""
    if request.method == "POST":
        data = request.POST
        zone_raw = data.get("zone_id") or ""
        common: dict[str, Any] = {
            "owner_name": data.get("owner_name", ""),
            "alt_phone": data.get("alt_phone", ""),
            "gstin": data.get("gstin", ""),
            "zone_id": int(zone_raw) if zone_raw.isdigit() else None,
            "delivery_address": data.get("delivery_address", ""),
            "credit_days": int(data.get("credit_days") or 0),
        }
        if data.get("credit_limit_amount"):
            common["credit_limit_amount"] = _decimal(data["credit_limit_amount"])
        try:
            if customer is None:
                customer_services.create_customer(
                    actor=request.user,
                    code=data.get("code", ""),
                    shop_name=data.get("shop_name", ""),
                    phone=data.get("phone", ""),
                    billing_address=data.get("billing_address", ""),
                    **common,
                )
            else:
                customer_services.update_customer(
                    actor=request.user,
                    customer=customer,
                    shop_name=data.get("shop_name", customer.shop_name),
                    phone=data.get("phone", customer.phone),
                    billing_address=data.get("billing_address", customer.billing_address),
                    is_active=data.get("is_active") == "on",
                    **common,
                )
        except DomainError as exc:
            error = exc.detail
        else:
            return redirect("webadmin:customer-list")

    return render(
        request,
        "webadmin/customer_form.html",
        {"customer": customer, "zones": customer_selectors.active_zones(), "error": error},
    )


# --------------------------------------------------------------------------- lookups
@login_required
def zone_list(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "webadmin/zone_list.html",
        {"page": _page(request, customer_selectors.active_zones().order_by("name"))},
    )


@login_required
def reason_code_list(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "webadmin/reason_code_list.html",
        {"page": _page(request, reason_selectors.active_reason_codes().order_by("code"))},
    )
