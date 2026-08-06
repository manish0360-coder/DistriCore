"""Billing read queries. Scope is derived from the actor, never accepted (AD-11)."""

from __future__ import annotations

from datetime import date
from typing import Any

from django.db.models import QuerySet

from billing.models import CreditNote, Invoice, InvoiceLine
from core.permissions import Role, has_role


def visible_invoices(actor: Any) -> QuerySet[Invoice]:
    """Invoices the caller may see (05 §8).

    A retailer sees only their own. A scope violation then looks like absence rather
    than refusal (05 §4.1) — a 403 would confirm the invoice exists.
    """
    base = Invoice.objects.select_related("customer", "issued_by")
    if has_role(actor, Role.OWNER):
        return base
    if has_role(actor, Role.SALESMAN, Role.DELIVERY):
        return base.filter(customer__zone__assigned_user=actor)
    if has_role(actor, Role.RETAILER):
        return base.filter(customer_id=getattr(actor, "customer_id", None) or 0)
    return base.none()


def search_invoices(
    actor: Any,
    *,
    customer_id: int | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    financial_year: str | None = None,
) -> QuerySet[Invoice]:
    queryset = visible_invoices(actor)
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if status:
        queryset = queryset.filter(status=status)
    if date_from is not None:
        queryset = queryset.filter(invoice_date__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(invoice_date__lte=date_to)
    if financial_year:
        queryset = queryset.filter(financial_year=financial_year)
    return queryset


def get_invoice_for(actor: Any, invoice_id: int) -> Invoice | None:
    return visible_invoices(actor).filter(pk=invoice_id).first()


def invoice_lines(invoice: Invoice) -> QuerySet[InvoiceLine]:
    """The lines, which render from themselves alone (M5-2)."""
    return InvoiceLine.objects.filter(invoice=invoice).order_by("line_number")


def get_invoice_line(invoice: Invoice, line_id: int) -> InvoiceLine | None:
    """Fetch one line of an invoice. Exists so no delivery layer imports the model."""
    return InvoiceLine.objects.filter(invoice=invoice, pk=line_id).first()


def visible_credit_notes(actor: Any) -> QuerySet[CreditNote]:
    base = CreditNote.objects.select_related("customer", "invoice", "issued_by")
    if has_role(actor, Role.OWNER):
        return base
    if has_role(actor, Role.SALESMAN, Role.DELIVERY):
        return base.filter(customer__zone__assigned_user=actor)
    if has_role(actor, Role.RETAILER):
        return base.filter(customer_id=getattr(actor, "customer_id", None) or 0)
    return base.none()


def get_credit_note_for(actor: Any, credit_note_id: int) -> CreditNote | None:
    return visible_credit_notes(actor).filter(pk=credit_note_id).first()
