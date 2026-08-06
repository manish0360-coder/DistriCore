"""Owner screens for fulfilment, billing and the customer ledger (M5).

Views parse and delegate. Every rule lives in a service (N-01), and no model is imported
here (N-02) — selectors exist precisely so this file never has to.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from billing import pdf as billing_pdf
from billing import selectors as billing_selectors
from billing import services as billing_services
from core.exceptions import DomainError
from core.media import open_media
from customers import selectors as customer_selectors
from fulfilment import selectors as delivery_selectors
from fulfilment import services as delivery_services
from identity import selectors as identity_selectors
from ledger import selectors as ledger_selectors
from orders import selectors as order_selectors


# --------------------------------------------------------------------------- delivery
@login_required
def delivery_list(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "webadmin/delivery_list.html",
        {
            "deliveries": delivery_selectors.search_deliveries(
                request.user, status=request.GET.get("status") or None
            )[:200],
            "status": request.GET.get("status", ""),
        },
    )


@login_required
@require_http_methods(["POST"])
def delivery_assign(request: HttpRequest, pk: int) -> HttpResponse:
    order = order_selectors.get_order_for(request.user, pk)
    assignee = identity_selectors.get_active_user(int(request.POST.get("assigned_user_id") or 0))
    if order is not None and assignee is not None:
        try:
            delivery_services.assign_delivery(
                actor=request.user, order=order, assigned_user=assignee
            )
        except DomainError as exc:
            request.session["flash"] = exc.detail
    return redirect("webadmin:order-detail", pk=pk)


@login_required
@require_http_methods(["POST"])
def delivery_dispatch(request: HttpRequest, pk: int) -> HttpResponse:
    delivery = delivery_selectors.get_delivery_for(request.user, pk)
    if delivery is not None:
        try:
            delivery_services.dispatch_delivery(
                actor=request.user,
                delivery=delivery,
                override_reason=request.POST.get("override_reason", ""),
            )
        except DomainError as exc:
            request.session["flash"] = exc.detail
    return redirect("webadmin:delivery-list")


@login_required
@require_http_methods(["POST"])
def delivery_complete(request: HttpRequest, pk: int) -> HttpResponse:
    delivery = delivery_selectors.get_delivery_for(request.user, pk)
    if delivery is not None:
        try:
            delivery_services.complete_delivery(
                actor=request.user,
                delivery=delivery,
                recipient_name=request.POST.get("recipient_name", ""),
            )
        except DomainError as exc:
            request.session["flash"] = exc.detail
    return redirect("webadmin:delivery-list")


@login_required
@require_http_methods(["POST"])
def delivery_fail(request: HttpRequest, pk: int) -> HttpResponse:
    delivery = delivery_selectors.get_delivery_for(request.user, pk)
    if delivery is not None:
        try:
            delivery_services.fail_delivery(
                actor=request.user, delivery=delivery, reason=request.POST.get("reason", "")
            )
        except DomainError as exc:
            request.session["flash"] = exc.detail
    return redirect("webadmin:delivery-list")


# --------------------------------------------------------------------------- billing
@login_required
def invoice_list(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "webadmin/invoice_list.html",
        {
            "invoices": billing_selectors.search_invoices(
                request.user, status=request.GET.get("status") or None
            )[:200],
            "flash": request.session.pop("flash", ""),
        },
    )


@login_required
def invoice_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """The invoice as HTML — **the same template WeasyPrint renders** (00 §7)."""
    invoice = billing_selectors.get_invoice_for(request.user, pk)
    if invoice is None:
        return redirect("webadmin:invoice-list")
    return HttpResponse(billing_pdf.render_invoice_html(invoice))


@login_required
def invoice_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = billing_selectors.get_invoice_for(request.user, pk)
    if invoice is None:
        return redirect("webadmin:invoice-list")
    media = billing_pdf.invoice_pdf(actor=request.user, invoice=invoice)
    handle, content_type = open_media(media)
    return FileResponse(
        handle,
        content_type=content_type,
        filename=f"{invoice.invoice_number.replace('/', '-')}.pdf",
    )


@login_required
@require_http_methods(["POST"])
def invoice_issue(request: HttpRequest, pk: int) -> HttpResponse:
    order = order_selectors.get_order_for(request.user, pk)
    if order is not None:
        try:
            billing_services.issue_invoice(actor=request.user, order=order)
        except DomainError as exc:
            request.session["flash"] = exc.detail
    return redirect("webadmin:order-detail", pk=pk)


# --------------------------------------------------------------------------- ledger
@login_required
def customer_ledger(request: HttpRequest, pk: int) -> HttpResponse:
    customer = customer_selectors.visible_customers(request.user).filter(pk=pk).first()
    if customer is None:
        return redirect("webadmin:customer-list")
    settled = order_selectors.settled_balance(customer)
    open_value = order_selectors.open_order_value(customer)
    return render(
        request,
        "webadmin/customer_ledger.html",
        {
            "customer": customer,
            "entries": ledger_selectors.statement_for(customer),
            "settled_balance": settled,
            "open_order_value": open_value,
            "credit_exposure": settled + open_value,
        },
    )


@login_required
def receivables(request: HttpRequest) -> HttpResponse:
    """Every customer with their balance.

    R-1 in the place it was predicted: a customer who owes nothing shows ``0.00`` rather
    than dropping out of the report the owner reads and acts on.
    """
    return render(
        request,
        "webadmin/receivables.html",
        {"customers": ledger_selectors.outstanding_balances()},
    )
