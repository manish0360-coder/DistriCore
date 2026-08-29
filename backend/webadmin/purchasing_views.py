"""Purchasing screens — suppliers, purchase orders, goods receipts (D5 Stages 1-3).

Views hold no rules. Every mutation goes through `purchasing.services`, which is where
authorisation, validation and audit live (N-01); the import-linter contract forbids this
module importing `purchasing.models` at all.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from catalogue import selectors as product_selectors
from core.exceptions import DomainError
from purchasing import selectors as purchasing_selectors
from purchasing import services as purchasing_services
from webadmin.master_views import _page


@login_required
def supplier_list(request: HttpRequest) -> HttpResponse:
    queryset = purchasing_selectors.search_suppliers(term=request.GET.get("q", "")).order_by("name")
    return render(
        request,
        "webadmin/supplier_list.html",
        {"page": _page(request, queryset), "q": request.GET.get("q", "")},
    )


@login_required
@require_http_methods(["GET", "POST"])
def supplier_form(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    supplier = purchasing_selectors.search_suppliers().filter(pk=pk).first() if pk else None
    error = ""
    if request.method == "POST":
        data = request.POST
        try:
            if supplier is None:
                supplier = purchasing_services.create_supplier(
                    actor=request.user,
                    code=data.get("code", ""),
                    name=data.get("name", ""),
                    phone=data.get("phone", ""),
                    billing_address=data.get("billing_address", ""),
                    contact_name=data.get("contact_name", ""),
                    alt_phone=data.get("alt_phone", ""),
                    email=data.get("email", ""),
                    dispatch_address=data.get("dispatch_address", ""),
                    gstin=data.get("gstin", ""),
                    state_code=data.get("state_code", ""),
                    payment_terms_days=data.get("payment_terms_days", "0"),
                )
            else:
                purchasing_services.update_supplier(
                    actor=request.user,
                    supplier=supplier,
                    name=data.get("name", supplier.name),
                    contact_name=data.get("contact_name", ""),
                    phone=data.get("phone", supplier.phone),
                    alt_phone=data.get("alt_phone", ""),
                    email=data.get("email", ""),
                    billing_address=data.get("billing_address", supplier.billing_address),
                    dispatch_address=data.get("dispatch_address", ""),
                    gstin=data.get("gstin", ""),
                    state_code=data.get("state_code", ""),
                    payment_terms_days=data.get("payment_terms_days", "0"),
                    is_active=data.get("is_active") == "on",
                )
        except DomainError as exc:
            error = exc.detail
        else:
            return redirect("webadmin:supplier-edit", pk=supplier.pk)

    links = purchasing_selectors.products_for_supplier(supplier) if supplier else []
    return render(
        request,
        "webadmin/supplier_form.html",
        {
            "supplier": supplier,
            "links": links,
            "products": product_selectors.active_products().order_by("name") if supplier else [],
            "error": error,
        },
    )


@login_required
@require_http_methods(["POST"])
def supplier_products(request: HttpRequest, pk: int) -> HttpResponse:
    """FR-PUR-002, managed from the supplier side (D-PUR ruling, `D5_Design_Review` §3.5).

    One endpoint, three actions, because they are three buttons on one list and splitting
    them would put the same lookup and the same error handling in three places.
    """
    supplier = purchasing_selectors.search_suppliers().filter(pk=pk).first()
    if supplier is None:
        return redirect("webadmin:supplier-list")

    data = request.POST
    action = data.get("action", "")
    product = product_selectors.search_products().filter(pk=data.get("product") or 0).first()
    error = ""
    try:
        if product is None:
            raise DomainError("Select a product.")
        if action == "link":
            purchasing_services.link_product_supplier(
                actor=request.user,
                supplier=supplier,
                product=product,
                supplier_sku=data.get("supplier_sku", ""),
            )
        elif action == "prefer":
            purchasing_services.set_preferred_supplier(
                actor=request.user, product=product, supplier=supplier
            )
        elif action == "unlink":
            purchasing_services.unlink_product_supplier(
                actor=request.user, supplier=supplier, product=product
            )
    except DomainError as exc:
        error = exc.detail

    if not error:
        return redirect("webadmin:supplier-edit", pk=supplier.pk)
    return render(
        request,
        "webadmin/supplier_form.html",
        {
            "supplier": supplier,
            "links": purchasing_selectors.products_for_supplier(supplier),
            "products": product_selectors.active_products().order_by("name"),
            "error": error,
        },
    )


# ------------------------------------------------------------- purchase orders (Stage 2)


def _parsed_lines(request: HttpRequest) -> list[dict[str, object]]:
    """Turn the posted line rows into the service's input.

    Parsing only — no rules. A blank row is skipped so the form can offer spare rows; every
    other validation (quantity, cost, active product, at least one line) belongs to
    `purchasing.services` and is asserted there.
    """
    parsed: list[dict[str, object]] = []
    products = {str(p.pk): p for p in product_selectors.active_products()}
    for raw_product, raw_qty, raw_cost in zip(
        request.POST.getlist("product"),
        request.POST.getlist("quantity_ordered"),
        request.POST.getlist("unit_cost"),
        strict=False,
    ):
        if not raw_product or not (raw_qty or "").strip():
            continue
        product = products.get(raw_product)
        if product is None:
            raise DomainError("Select a product for every line.")
        try:
            quantity = Decimal((raw_qty or "0").strip())
            unit_cost = Decimal((raw_cost or "0").strip())
        except InvalidOperation:
            raise DomainError("Quantity and unit cost must be numbers.") from None
        parsed.append({"product": product, "quantity_ordered": quantity, "unit_cost": unit_cost})
    return parsed


def _parsed_date(raw: str) -> date | None:
    if not (raw or "").strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise DomainError("Dates must be in YYYY-MM-DD form.") from None


@login_required
def purchase_order_list(request: HttpRequest) -> HttpResponse:
    queryset = purchasing_selectors.search_purchase_orders(
        term=request.GET.get("q", ""), status=request.GET.get("status", "")
    )
    return render(
        request,
        "webadmin/purchase_order_list.html",
        {
            "page": _page(request, queryset),
            "q": request.GET.get("q", ""),
            "status": request.GET.get("status", ""),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def purchase_order_form(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create, or amend a draft. An issued order is read-only and redirects to its detail."""
    purchase_order = (
        purchasing_selectors.search_purchase_orders().filter(pk=pk).first() if pk else None
    )
    if purchase_order is not None and not purchase_order.is_editable:
        return redirect("webadmin:purchase-order-detail", pk=purchase_order.pk)

    error = ""
    if request.method == "POST":
        data = request.POST
        try:
            lines = _parsed_lines(request)
            if purchase_order is None:
                supplier = (
                    purchasing_selectors.search_suppliers()
                    .filter(pk=data.get("supplier") or 0)
                    .first()
                )
                if supplier is None:
                    raise DomainError("Select a supplier.")
                order_date = _parsed_date(data.get("order_date", ""))
                if order_date is None:
                    raise DomainError("An order date is required.")
                purchase_order = purchasing_services.create_purchase_order(
                    actor=request.user,
                    supplier=supplier,
                    order_date=order_date,
                    lines=lines,
                    expected_date=_parsed_date(data.get("expected_date", "")),
                    notes=data.get("notes", ""),
                )
            else:
                purchasing_services.amend_purchase_order(
                    actor=request.user,
                    purchase_order=purchase_order,
                    lines=lines,
                    expected_date=_parsed_date(data.get("expected_date", "")),
                    notes=data.get("notes", ""),
                )
        except DomainError as exc:
            error = exc.detail
        else:
            return redirect("webadmin:purchase-order-detail", pk=purchase_order.pk)

    return render(
        request,
        "webadmin/purchase_order_form.html",
        {
            "purchase_order": purchase_order,
            "lines": purchasing_selectors.lines_for(purchase_order) if purchase_order else [],
            "suppliers": purchasing_selectors.active_suppliers().order_by("name"),
            "products": product_selectors.active_products().order_by("name"),
            # The form defaults the order date to today; the service never does. A machine
            # clock may suggest a business fact, it may not decide one (P-4's reasoning).
            "today": date.today().isoformat(),
            "error": error,
        },
    )


@login_required
def purchase_order_detail(request: HttpRequest, pk: int) -> HttpResponse:
    purchase_order = purchasing_selectors.search_purchase_orders().filter(pk=pk).first()
    if purchase_order is None:
        return redirect("webadmin:purchase-order-list")
    return render(
        request,
        "webadmin/purchase_order_detail.html",
        {
            "purchase_order": purchase_order,
            "lines": purchasing_selectors.lines_for(purchase_order),
            # Added at Stage 3 alongside `lines` rather than replacing it: the existing table
            # renders line snapshots, and the variance is a second question about the same
            # rows (FR-PUR-008).
            "outstanding": purchasing_selectors.outstanding_lines(purchase_order),
            "receipts": purchasing_selectors.receipts_for(purchase_order),
            "error": request.GET.get("error", ""),
        },
    )


@login_required
@require_http_methods(["POST"])
def purchase_order_issue(request: HttpRequest, pk: int) -> HttpResponse:
    purchase_order = purchasing_selectors.search_purchase_orders().filter(pk=pk).first()
    if purchase_order is None:
        return redirect("webadmin:purchase-order-list")
    try:
        purchasing_services.issue_purchase_order(actor=request.user, purchase_order=purchase_order)
    except DomainError as exc:
        return render(
            request,
            "webadmin/purchase_order_detail.html",
            {
                "purchase_order": purchase_order,
                "lines": purchasing_selectors.lines_for(purchase_order),
                "error": exc.detail,
            },
        )
    return redirect("webadmin:purchase-order-detail", pk=purchase_order.pk)


@login_required
@require_http_methods(["POST"])
def purchase_order_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    purchase_order = purchasing_selectors.search_purchase_orders().filter(pk=pk).first()
    if purchase_order is None:
        return redirect("webadmin:purchase-order-list")
    try:
        purchasing_services.cancel_purchase_order(
            actor=request.user,
            purchase_order=purchase_order,
            reason=request.POST.get("reason", ""),
        )
    except DomainError as exc:
        return render(
            request,
            "webadmin/purchase_order_detail.html",
            {
                "purchase_order": purchase_order,
                "lines": purchasing_selectors.lines_for(purchase_order),
                "error": exc.detail,
            },
        )
    return redirect("webadmin:purchase-order-detail", pk=purchase_order.pk)


@login_required
@require_http_methods(["POST"])
def purchase_order_close(request: HttpRequest, pk: int) -> HttpResponse:
    """Short-close an order the supplier will not complete (FR-PUR-005)."""
    purchase_order = purchasing_selectors.search_purchase_orders().filter(pk=pk).first()
    if purchase_order is None:
        return redirect("webadmin:purchase-order-list")
    try:
        purchasing_services.close_purchase_order(
            actor=request.user,
            purchase_order=purchase_order,
            reason=request.POST.get("reason", ""),
        )
    except DomainError as exc:
        return render(
            request,
            "webadmin/purchase_order_detail.html",
            {
                "purchase_order": purchase_order,
                "lines": purchasing_selectors.lines_for(purchase_order),
                "receipts": purchasing_selectors.receipts_for(purchase_order),
                "error": exc.detail,
            },
        )
    return redirect("webadmin:purchase-order-detail", pk=purchase_order.pk)


# ------------------------------------------------------------- goods receipts (Stage 3)


def _parsed_receipt_lines(
    request: HttpRequest, outstanding: list[dict[str, Any]]
) -> list[dict[str, object]]:
    """Turn the posted receipt rows into the service's input.

    Parsing only — no rules. A blank quantity is skipped so the form can show every ordered
    line whether or not it is being received now; the acceptance limit, the duplicate check
    and "at least one line" all belong to `purchasing.services` and are asserted there.

    **The candidate lines come from `outstanding`, not from the POST body.** A posted
    `purchase_order_line` id is looked up in a set the server built for *this* order, so a
    forged id cannot reach the service — and if one did, the service's own `WRONG_ORDER`
    check would still refuse it.
    """
    by_id = {str(row["line"].pk): row["line"] for row in outstanding}
    parsed: list[dict[str, object]] = []
    for raw_line, raw_qty in zip(
        request.POST.getlist("purchase_order_line"),
        request.POST.getlist("quantity_received"),
        strict=False,
    ):
        if not (raw_qty or "").strip():
            continue
        po_line = by_id.get(raw_line)
        if po_line is None:
            raise DomainError("That line does not belong to this purchase order.")
        try:
            quantity = Decimal((raw_qty or "0").strip())
        except InvalidOperation:
            raise DomainError("Received quantities must be numbers.") from None
        parsed.append({"purchase_order_line": po_line, "quantity_received": quantity})
    return parsed


@login_required
def goods_receipt_list(request: HttpRequest) -> HttpResponse:
    queryset = purchasing_selectors.search_goods_receipts(term=request.GET.get("q", ""))
    return render(
        request,
        "webadmin/goods_receipt_list.html",
        {"page": _page(request, queryset), "q": request.GET.get("q", "")},
    )


@login_required
@require_http_methods(["GET", "POST"])
def goods_receipt_form(request: HttpRequest, pk: int) -> HttpResponse:
    """Book goods in against one purchase order (FR-PUR-006, FR-PUR-013).

    **There is no edit route and there will not be one.** `pk` is the purchase order, not a
    receipt: a posted receipt is immutable, so this screen only ever creates.
    """
    purchase_order = purchasing_selectors.search_purchase_orders().filter(pk=pk).first()
    if purchase_order is None:
        return redirect("webadmin:purchase-order-list")

    outstanding = purchasing_selectors.outstanding_lines(purchase_order)
    error = ""
    if request.method == "POST":
        data = request.POST
        try:
            receipt_date = _parsed_date(data.get("receipt_date", ""))
            if receipt_date is None:
                raise DomainError("A receipt date is required.")
            receipt = purchasing_services.create_goods_receipt(
                actor=request.user,
                purchase_order=purchase_order,
                receipt_date=receipt_date,
                lines=_parsed_receipt_lines(request, outstanding),
                supplier_reference=data.get("supplier_reference", ""),
                notes=data.get("notes", ""),
            )
        except DomainError as exc:
            error = exc.detail
            # Re-read: a failed attempt must not show figures from a transaction that rolled
            # back. `outstanding` above was computed before the POST and is still correct,
            # but re-reading states that intent rather than relying on it.
            outstanding = purchasing_selectors.outstanding_lines(purchase_order)
        else:
            return redirect("webadmin:goods-receipt-detail", pk=receipt.pk)

    return render(
        request,
        "webadmin/goods_receipt_form.html",
        {
            "purchase_order": purchase_order,
            "outstanding": outstanding,
            "receipts": purchasing_selectors.receipts_for(purchase_order),
            # The form suggests today; the service never defaults it (P-4's reasoning).
            "today": date.today().isoformat(),
            "error": error,
        },
    )


@login_required
def goods_receipt_detail(request: HttpRequest, pk: int) -> HttpResponse:
    receipt = purchasing_selectors.search_goods_receipts().filter(pk=pk).first()
    if receipt is None:
        return redirect("webadmin:goods-receipt-list")
    return render(
        request,
        "webadmin/goods_receipt_detail.html",
        {"receipt": receipt, "lines": purchasing_selectors.receipt_lines_for(receipt)},
    )


# ----------------------------------------------------------- supplier payments (S4.3)


@login_required
def supplier_payment_list(request: HttpRequest) -> HttpResponse:
    queryset = purchasing_selectors.search_supplier_payments(
        term=request.GET.get("q", ""), method=request.GET.get("method", "")
    )
    return render(
        request,
        "webadmin/supplier_payment_list.html",
        {
            "page": _page(request, queryset),
            "q": request.GET.get("q", ""),
            "method": request.GET.get("method", ""),
            "flash": request.session.pop("flash", ""),
        },
    )


@login_required
def supplier_payment_form(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the payment form and **mint the submission identity** (E3).

    **GET only, and that is the mechanism.** One `uuid4` per render is what makes a logical
    payment attempt identifiable: every real duplicate — double-click, browser Back,
    refresh on the POST result, a page restored from the bfcache — replays *this* render and
    therefore this id, while a genuine second payment means loading the form again and
    getting a different one.

    The view mints and passes; it decides nothing. Whether an id has been used is the
    service's question and the unique index's answer (N-01).
    """
    supplier = purchasing_selectors.search_suppliers().filter(pk=pk).first()
    if supplier is None:
        return redirect("webadmin:supplier-list")
    return render(
        request,
        "webadmin/supplier_payment_form.html",
        {
            "supplier": supplier,
            "submission_id": uuid.uuid4(),
            "position": purchasing_selectors.supplier_position(supplier),
            # The form suggests today; the service never defaults it (P-4's reasoning).
            "today": date.today().isoformat(),
            "flash": request.session.pop("flash", ""),
        },
    )


@login_required
@require_http_methods(["POST"])
def supplier_payment_record(request: HttpRequest, pk: int) -> HttpResponse:
    """Post/Redirect/Get. A refresh re-issues the GET and mints a **fresh** id."""
    supplier = purchasing_selectors.search_suppliers().filter(pk=pk).first()
    if supplier is None:
        return redirect("webadmin:supplier-list")

    data = request.POST
    try:
        payment_date = _parsed_date(data.get("payment_date", ""))
        if payment_date is None:
            raise DomainError("A payment date is required.")
        payment = purchasing_services.record_supplier_payment(
            actor=request.user,
            supplier=supplier,
            submission_id=data.get("submission_id") or None,
            amount=data.get("amount") or "0",
            method=data.get("method", "BANK"),
            payment_date=payment_date,
            reference_number=data.get("reference_number", ""),
            notes=data.get("notes", ""),
        )
    except (DomainError, ArithmeticError, ValueError) as exc:
        request.session["flash"] = getattr(exc, "detail", str(exc))
        return redirect("webadmin:supplier-payment-new", pk=supplier.pk)
    return redirect("webadmin:supplier-payment-detail", pk=payment.pk)


@login_required
def supplier_payment_detail(request: HttpRequest, pk: int) -> HttpResponse:
    payment = purchasing_selectors.get_supplier_payment(pk)
    if payment is None:
        return redirect("webadmin:supplier-payment-list")
    return render(
        request,
        "webadmin/supplier_payment_detail.html",
        {
            "payment": payment,
            "today": date.today().isoformat(),
            "flash": request.session.pop("flash", ""),
        },
    )


@login_required
@require_http_methods(["POST"])
def supplier_payment_reverse(request: HttpRequest, pk: int) -> HttpResponse:
    payment = purchasing_selectors.get_supplier_payment(pk)
    if payment is None:
        return redirect("webadmin:supplier-payment-list")
    try:
        reversal_date = _parsed_date(request.POST.get("reversal_date", ""))
        if reversal_date is None:
            raise DomainError("A reversal date is required.")
        purchasing_services.reverse_supplier_payment(
            actor=request.user,
            payment=payment,
            reason=request.POST.get("reason", ""),
            reversal_date=reversal_date,
        )
    except DomainError as exc:
        request.session["flash"] = exc.detail
    return redirect("webadmin:supplier-payment-detail", pk=payment.pk)
