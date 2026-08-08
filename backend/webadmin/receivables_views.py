"""Owner screens for payments, write-offs and the derived receivables position (M6).

Views parse and delegate (N-01). No model is imported here (N-02) — selectors exist
precisely so this file never has to.
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core.exceptions import DomainError
from customers import selectors as customer_selectors
from ledger import selectors as ledger_selectors
from orders import selectors as order_selectors
from receivables import selectors as receivable_selectors
from receivables import services as receivable_services


def _customer(request: HttpRequest, pk: int):
    return customer_selectors.visible_customers(request.user).filter(pk=pk).first()


def _parse_date(request: HttpRequest, name: str) -> date | None:
    raw = request.GET.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


# --------------------------------------------------------------------------- payments
@login_required
def payment_list(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "webadmin/payment_list.html",
        {
            "payments": receivable_selectors.search_payments(
                request.user, method=request.GET.get("method") or None
            )[:200],
            "method": request.GET.get("method", ""),
            "flash": request.session.pop("flash", ""),
        },
    )


@login_required
@require_http_methods(["POST"])
def payment_record(request: HttpRequest, pk: int) -> HttpResponse:
    customer = _customer(request, pk)
    if customer is not None:
        try:
            receivable_services.record_payment(
                actor=request.user,
                customer=customer,
                amount=request.POST.get("amount") or "0",
                method=request.POST.get("method", "CASH"),
                reference_number=request.POST.get("reference_number", ""),
                notes=request.POST.get("notes", ""),
            )
        except (DomainError, ArithmeticError, ValueError) as exc:
            request.session["flash"] = getattr(exc, "detail", str(exc))
    return redirect("webadmin:customer-ledger", pk=pk)


@login_required
@require_http_methods(["POST"])
def payment_reverse(request: HttpRequest, pk: int) -> HttpResponse:
    payment = receivable_selectors.get_payment_for(request.user, pk)
    if payment is not None:
        try:
            receivable_services.reverse_payment(
                actor=request.user, payment=payment, reason=request.POST.get("reason", "")
            )
        except DomainError as exc:
            request.session["flash"] = exc.detail
    return redirect("webadmin:payment-list")


@login_required
@require_http_methods(["POST"])
def write_off(request: HttpRequest, pk: int) -> HttpResponse:
    customer = _customer(request, pk)
    if customer is not None:
        try:
            receivable_services.write_off(
                actor=request.user,
                customer=customer,
                amount=request.POST.get("amount") or "0",
                reason=request.POST.get("reason", ""),
            )
        except (DomainError, ArithmeticError, ValueError) as exc:
            request.session["flash"] = getattr(exc, "detail", str(exc))
    return redirect("webadmin:customer-ledger", pk=pk)


# --------------------------------------------------------------------------- position
@login_required
def outstanding(request: HttpRequest, pk: int) -> HttpResponse:
    """The derived FIFO view for one customer (M6 §5A).

    Nothing on this page is stored. Ask again tomorrow and the same walk over the same
    immutable entries produces the same answer.
    """
    customer = _customer(request, pk)
    if customer is None:
        return redirect("webadmin:customer-list")
    position = receivable_selectors.outstanding_for(
        customer, as_of=_parse_date(request, "as_of")
    )
    return render(
        request,
        "webadmin/customer_outstanding.html",
        {
            "customer": customer,
            "position": position,
            "statement": receivable_selectors.customer_statement(
                customer,
                date_from=_parse_date(request, "date_from"),
                date_to=_parse_date(request, "date_to"),
            ),
            "credit_exposure": order_selectors.credit_exposure(customer),
            "entries": ledger_selectors.statement_for(customer),
            "flash": request.session.pop("flash", ""),
        },
    )


@login_required
def receivables_report(request: HttpRequest) -> HttpResponse:
    """Every customer with a position, oldest debt first.

    The collection question the owner actually asks is *"who is oldest and how much?"*,
    and a sorted list answers it — which is why `02A` §13.2 demoted a configurable
    bucketing engine to Edition 2 (M6 C-2).
    """
    positions = receivable_selectors.receivables_position(request.user)
    positions.sort(
        key=lambda p: (p.oldest.age_days if p.oldest else -1), reverse=True
    )
    names = {
        c.pk: c
        for c in receivable_selectors.visible_customers_for_receivables(request.user)
    }
    return render(
        request,
        "webadmin/receivables_position.html",
        {
            "rows": [(names.get(p.customer_id), p) for p in positions],
            "total": sum((p.total_outstanding for p in positions), start=0),
        },
    )
