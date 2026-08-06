"""Billing business rules — the only writer of Invoice, CreditNote and their lines.

**The invoice is the moment money becomes owed.** It is a different boundary from the one
dispatch crosses, and this module writes no stock to keep that true (M5 §1, D-7).

Three rules here are load-bearing:

* **B-9 / M5-5** — issuing an invoice writes its ledger entry in the **same
  transaction**. An invoice without its entry is a corruption, not a delay.
* **M5-2** — every value on the document is snapshotted at issue and rendered from the
  document's own row thereafter (FR-BIL-008).
* **D-7 / M5-12** — a credit note writes **no stock movement**. It reverses money;
  goods come back through their own event.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from billing.models import (
    CreditNote,
    CreditNoteLine,
    Invoice,
    InvoiceLine,
    NumberSeries,
    financial_year_for,
)
from core.exceptions import ValidationFailed
from core.fields import to_money, to_quantity
from core.models import AuditLog, BusinessProfile
from core.permissions import Role, require_roles
from core.services import get_business_profile, record_audit
from customers.selectors import state_code_for
from ledger.models import CustomerLedgerEntry
from ledger.services import record_entry
from orders.models import SalesOrder

logger = logging.getLogger("districore.billing")

RUPEE = Decimal("1")

#: Defaults used when a financial year's series row does not yet exist.
_SERIES_DEFAULTS: dict[str, tuple[str, str]] = {
    NumberSeries.Key.INVOICE: ("INV/", "invoice"),
    NumberSeries.Key.CREDIT_NOTE: ("CN/", "credit note"),
}


# --------------------------------------------------------------------------- numbering
def allocate_number(*, series_key: str, on: date) -> tuple[NumberSeries, str]:
    """Allocate the next gapless number for a series (M5-4, FR-BIL-005/006).

    **Takes a row lock**, and must be called inside the transaction that inserts the
    document. Gapless and never-reused are in tension; the resolution is deliberate — a
    rollback releases the number *and* the document together, so nothing is left
    dangling and no issued document ever shares a number.

    The lock serialises document issue across the whole system. At roughly 200 documents
    a day that is free, and it is the only construction that makes the guarantee true
    under concurrency.
    """
    if series_key not in NumberSeries.Key.values:
        raise ValidationFailed(
            "Unknown number series.",
            errors=[{"field": "series_key", "code": "INVALID", "message": str(series_key)}],
        )
    year = financial_year_for(on)
    prefix, _label = _SERIES_DEFAULTS[series_key]

    series = NumberSeries.objects.filter(series_key=series_key, financial_year=year).first()
    if series is None:
        # A new financial year starts a new series (04 T-06). Created on demand so the
        # first invoice of April does not require a deployment.
        short = year[2:4] + "-" + year[-2:]
        series, _ = NumberSeries.objects.get_or_create(
            series_key=series_key,
            financial_year=year,
            defaults={"prefix": f"{prefix}{short}/"},
        )

    locked = NumberSeries.objects.select_for_update().get(pk=series.pk)
    if not locked.is_active:
        raise ValidationFailed(
            "That number series is not active.",
            errors=[{"field": "series_key", "code": "INACTIVE", "message": series_key}],
        )
    locked.current_value += 1
    locked.save(update_fields=["current_value"])
    return locked, locked.format(locked.current_value)


# --------------------------------------------------------------------------- snapshots
def _seller_snapshot(profile: BusinessProfile) -> dict[str, Any]:
    address = ", ".join(
        part
        for part in (
            profile.address_line1,
            profile.address_line2,
            profile.city,
            profile.state,
            profile.pin_code,
        )
        if part
    )
    return {
        "seller_legal_name": profile.legal_name,
        "seller_gstin": profile.gstin,
        "seller_address": address,
        "seller_state_code": profile.state_code,
    }


def _buyer_snapshot(customer: Any, *, seller_state_code: str) -> dict[str, Any]:
    """Snapshot the buyer, resolving the state code per D-3.

    ``customers.selectors.state_code_for`` answers *which state*; the fallback when it
    cannot is a tax decision and therefore belongs here. Intra-state is assumed — the
    client's retailers are local — and **the assumption is recorded on the document**
    rather than inferred later by whoever has to defend the split.
    """
    resolved = state_code_for(customer)
    assumed = not resolved
    return {
        "buyer_name": customer.shop_name,
        "buyer_gstin": customer.gstin,
        "buyer_address": customer.billing_address,
        "buyer_state_code": resolved or seller_state_code,
        "buyer_state_assumed": assumed,
    }


def _split_tax(*, tax_amount: Decimal, intra_state: bool) -> dict[str, Decimal]:
    """Split one tax figure into the CGST/SGST pair or a single IGST (M5-7).

    ``sgst = tax - cgst`` rather than a second halving: halving 165.67 twice and
    rounding each gives 82.84 + 82.84 = 165.68, which would not reconcile against the
    line it came from. Deriving the second half by subtraction makes the pair sum
    exactly, always.
    """
    tax_amount = to_money(tax_amount)
    if not intra_state:
        return {
            "cgst_amount": Decimal("0.00"),
            "sgst_amount": Decimal("0.00"),
            "igst_amount": tax_amount,
        }
    cgst = to_money(tax_amount / 2)
    return {
        "cgst_amount": cgst,
        "sgst_amount": to_money(tax_amount - cgst),
        "igst_amount": Decimal("0.00"),
    }


def _round_off(raw_total: Decimal) -> tuple[Decimal, Decimal]:
    """Round a document total to the rupee, returning (round_off, payable) — M5-11."""
    raw_total = to_money(raw_total)
    payable = raw_total.quantize(RUPEE, rounding=ROUND_HALF_UP)
    return to_money(payable - raw_total), to_money(payable)


# --------------------------------------------------------------------------- invoice
@transaction.atomic
def issue_invoice(
    *,
    actor: Any,
    order: SalesOrder,
    invoice_date: date | None = None,
    client_uuid: uuid_lib.UUID | str | None = None,
) -> Invoice:
    """Issue the tax invoice for a dispatched order (FR-BIL-001…008).

    The caller supplies the order and a date. **Nothing else** — every figure is derived
    from the order's own line snapshots and the profile, because a client that could
    supply amounts could supply wrong ones.

    **The order's state is re-read from the database, under a lock, and the caller's
    instance is not trusted.** A ``SalesOrder`` is mutable, so a Python object handed in
    by a caller is a snapshot of whenever that caller last loaded it — and
    ``dispatch_delivery`` moves the row through *its own* instance, leaving every other
    reference stale. Gating a legal document on a stale snapshot fails both ways: it
    refuses invoices for orders that have shipped, and it would issue one for an order
    that has since been cancelled.

    The lock is needed here regardless: this function allocates a gapless statutory
    number and must remain one-invoice-per-order under concurrency.
    """
    require_roles(actor, Role.OWNER)

    if client_uuid:
        existing = Invoice.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing

    order = SalesOrder.objects.select_for_update().get(pk=order.pk)

    existing = Invoice.objects.filter(sales_order=order).first()
    if existing is not None:
        return existing  # F-3: one invoice per order, whatever the concurrency

    # B-2 / FR-BIL-002: money is owed once the goods have gone, not before.
    if order.status not in (SalesOrder.Status.DISPATCHED, SalesOrder.Status.DELIVERED):
        raise ValidationFailed(
            "An invoice can only be issued for a dispatched order.",
            errors=[{"field": "status", "code": "NOT_DISPATCHED", "message": order.status}],
        )

    lines = list(order.lines.select_related("product").order_by("line_number"))
    if not lines:  # pragma: no cover - place_order refuses an empty order
        raise ValidationFailed(
            "An order with no lines cannot be invoiced.",
            errors=[{"field": "lines", "code": "REQUIRED", "message": "0 lines"}],
        )

    profile = get_business_profile()
    seller = _seller_snapshot(profile)
    buyer = _buyer_snapshot(order.customer, seller_state_code=seller["seller_state_code"])
    intra_state = buyer["buyer_state_code"] == seller["seller_state_code"]
    on = invoice_date or timezone.localdate()

    subtotal = discount = taxable = tax = Decimal("0.00")
    for line in lines:
        subtotal += to_money(line.unit_price * line.quantity)
        discount += line.discount_amount
        taxable += line.taxable_amount
        tax += line.tax_amount
    totals = _split_tax(tax_amount=tax, intra_state=intra_state)
    round_off, payable = _round_off(taxable + tax)

    series, number = allocate_number(series_key=NumberSeries.Key.INVOICE, on=on)
    invoice = Invoice(
        invoice_number=number,
        number_series=series,
        financial_year=series.financial_year,
        sales_order=order,
        client_uuid=client_uuid or None,
        customer=order.customer,
        invoice_date=on,
        subtotal_amount=to_money(subtotal),
        discount_amount=to_money(discount),
        taxable_amount=to_money(taxable),
        round_off_amount=round_off,
        total_amount=payable,
        issued_by=actor if getattr(actor, "pk", None) else None,
        **seller,
        **buyer,
        **totals,
    )
    invoice.save()

    for index, line in enumerate(lines, start=1):
        line_tax = _split_tax(tax_amount=line.tax_amount, intra_state=intra_state)
        InvoiceLine.objects.create(
            invoice=invoice,
            line_number=index,
            product=line.product,
            # M5-2: snapshots of snapshots. The order line already froze these at
            # capture; copying rather than re-reading is what makes the invoice agree
            # with the order to the paisa (M3-8).
            product_code=line.product_code,
            product_name=line.product_name,
            hsn_code=getattr(line.product, "hsn_code", "") or "",
            quantity=line.quantity,
            unit_name=line.unit_name,
            unit_price=line.unit_price,
            discount_amount=line.discount_amount,
            taxable_amount=line.taxable_amount,
            tax_rate_percent=line.tax_rate_percent,
            line_total=line.line_total,
            **line_tax,
        )

    # B-9 / M5-5 — the receivable begins here, in this transaction.
    record_entry(
        actor=actor,
        customer=order.customer,
        entry_type=CustomerLedgerEntry.Type.INVOICE,
        amount=invoice.total_amount,
        narration=f"Invoice {invoice.invoice_number}",
        entry_date=on,
        source_document=invoice,
        sales_order=order,
    )

    logger.info(
        "invoice_issued",
        extra={
            "invoice_id": invoice.pk,
            "invoice_number": invoice.invoice_number,
            "order_id": order.pk,
            "total": str(invoice.total_amount),
        },
    )
    return invoice


@transaction.atomic
def cancel_invoice(*, actor: Any, invoice: Invoice, reason: str) -> Invoice:
    """Cancel an invoice that should never have existed (D-4, 04 T-17).

    Tightly guarded: not once any credit note references it, and never silently — the
    compensating ledger entry is written here, because the ledger is append-only and a
    cancellation that left the debt standing would be worse than no cancellation.
    """
    require_roles(actor, Role.OWNER)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed(
            "A cancellation needs a reason.",
            errors=[{"field": "reason", "code": "REQUIRED", "message": ""}],
        )
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status == Invoice.Status.CANCELLED:
        return locked
    if locked.credit_notes.exists():
        raise ValidationFailed(
            "An invoice with credit notes against it cannot be cancelled. Credit the rest.",
            errors=[{"field": "status", "code": "HAS_CREDIT_NOTES", "message": "cancel"}],
        )

    locked.status = Invoice.Status.CANCELLED
    locked.cancelled_reason = reason
    locked.cancelled_at = timezone.now()
    locked.cancelled_by = actor if getattr(actor, "pk", None) else None
    locked.save(update_fields=["status", "cancelled_reason", "cancelled_at", "cancelled_by"])

    record_entry(
        actor=actor,
        customer=locked.customer,
        entry_type=CustomerLedgerEntry.Type.ADJUSTMENT,
        amount=-locked.total_amount,
        narration=f"Cancellation of invoice {locked.invoice_number}",
        entry_date=timezone.localdate(),
        source_document=locked,
        sales_order=locked.sales_order,
    )
    record_audit(
        action=AuditLog.Action.CANCEL,
        entity_type="invoice",
        entity_id=locked.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"status": Invoice.Status.ISSUED},
        after_state={"status": locked.status, "reason": reason},
    )
    return locked


# --------------------------------------------------------------------------- credit note
def credited_total(invoice: Invoice) -> Decimal:
    """Value already credited against an invoice. Zero, never None (R-1 shape)."""
    row = CreditNote.objects.filter(invoice=invoice).aggregate(total=Sum("total_amount"))
    return to_money(row["total"] or 0)


@transaction.atomic
def issue_credit_note(
    *,
    actor: Any,
    invoice: Invoice,
    lines: list[dict[str, Any]],
    reason: str,
    reason_code: Any = None,
    credit_note_date: date | None = None,
    client_uuid: uuid_lib.UUID | str | None = None,
) -> CreditNote:
    """Credit some or all of an invoice (FR-BIL-014/015/016).

    ``lines`` is a list of ``{"invoice_line": InvoiceLine, "quantity": Decimal}``. Every
    money figure is recomputed **from the invoice line's own snapshot**, never from
    current master data — a credit note that priced at today's rate would not reverse
    the document it references.

    **Writes no stock movement** (D-7). If goods came back, that is its own event.
    """
    require_roles(actor, Role.OWNER)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed(
            "A credit note needs a reason.",
            errors=[{"field": "reason", "code": "REQUIRED", "message": ""}],
        )
    if not lines:
        raise ValidationFailed(
            "A credit note needs at least one line.",
            errors=[{"field": "lines", "code": "REQUIRED", "message": "0 lines"}],
        )

    if client_uuid:
        existing = CreditNote.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing

    # F-8: the cap is an aggregate across rows, so it needs an anchor. Locking the
    # invoice serialises every credit note against it.
    locked_invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked_invoice.status == Invoice.Status.CANCELLED:
        raise ValidationFailed(
            "A cancelled invoice cannot be credited.",
            errors=[{"field": "invoice", "code": "CANCELLED", "message": invoice.invoice_number}],
        )

    intra_state = locked_invoice.igst_amount == 0
    on = credit_note_date or timezone.localdate()

    prepared: list[dict[str, Any]] = []
    subtotal = discount = taxable = tax = Decimal("0.00")
    for index, raw in enumerate(lines, start=1):
        source: InvoiceLine = raw["invoice_line"]
        if source.invoice_id != locked_invoice.pk:
            raise ValidationFailed(
                "That line does not belong to this invoice.",
                errors=[{"field": "lines", "code": "WRONG_INVOICE", "message": str(source.pk)}],
            )
        quantity = to_quantity(raw.get("quantity", source.quantity))
        if quantity <= 0:
            raise ValidationFailed(
                "A credited quantity must be greater than zero.",
                errors=[{"field": "quantity", "code": "MIN_VALUE", "message": str(quantity)}],
            )
        if quantity > source.quantity:
            raise ValidationFailed(
                "Cannot credit more than was invoiced.",
                errors=[
                    {
                        "field": "quantity",
                        "code": "EXCEEDS_INVOICED",
                        "message": f"{quantity} > {source.quantity}",
                    }
                ],
            )

        # Proportional to the invoiced quantity, from the invoice's own frozen values.
        share = quantity / source.quantity
        line_taxable = to_money(source.taxable_amount * share)
        line_tax = to_money((source.cgst_amount + source.sgst_amount + source.igst_amount) * share)
        line_discount = to_money(source.discount_amount * share)
        line_total = to_money(line_taxable + line_tax)

        subtotal += to_money(source.unit_price * quantity)
        discount += line_discount
        taxable += line_taxable
        tax += line_tax
        prepared.append(
            {
                "line_number": index,
                "product": source.product,
                "product_code": source.product_code,
                "product_name": source.product_name,
                "hsn_code": source.hsn_code,
                "quantity": quantity,
                "unit_name": source.unit_name,
                "unit_price": source.unit_price,
                "discount_amount": line_discount,
                "taxable_amount": line_taxable,
                "tax_rate_percent": source.tax_rate_percent,
                "line_total": line_total,
                **_split_tax(tax_amount=line_tax, intra_state=intra_state),
            }
        )

    round_off, payable = _round_off(taxable + tax)

    # B-7 / FR-BIL-016 — the invariant that cannot be a row constraint.
    already = credited_total(locked_invoice)
    if already + payable > locked_invoice.total_amount:
        raise ValidationFailed(
            "Total credited would exceed the invoice value.",
            errors=[
                {
                    "field": "lines",
                    "code": "EXCEEDS_INVOICE",
                    "message": f"{already + payable} > {locked_invoice.total_amount}",
                }
            ],
        )

    series, number = allocate_number(series_key=NumberSeries.Key.CREDIT_NOTE, on=on)
    note = CreditNote(
        credit_note_number=number,
        number_series=series,
        financial_year=series.financial_year,
        invoice=locked_invoice,
        client_uuid=client_uuid or None,
        customer=locked_invoice.customer,
        credit_note_date=on,
        reason=reason,
        reason_code=reason_code,
        seller_legal_name=locked_invoice.seller_legal_name,
        seller_gstin=locked_invoice.seller_gstin,
        seller_address=locked_invoice.seller_address,
        seller_state_code=locked_invoice.seller_state_code,
        buyer_name=locked_invoice.buyer_name,
        buyer_gstin=locked_invoice.buyer_gstin,
        buyer_address=locked_invoice.buyer_address,
        buyer_state_code=locked_invoice.buyer_state_code,
        buyer_state_assumed=locked_invoice.buyer_state_assumed,
        subtotal_amount=to_money(subtotal),
        discount_amount=to_money(discount),
        taxable_amount=to_money(taxable),
        round_off_amount=round_off,
        total_amount=payable,
        issued_by=actor if getattr(actor, "pk", None) else None,
        **_split_tax(tax_amount=tax, intra_state=intra_state),
    )
    note.save()
    for prepared_line in prepared:
        CreditNoteLine.objects.create(credit_note=note, **prepared_line)

    record_entry(
        actor=actor,
        customer=note.customer,
        entry_type=CustomerLedgerEntry.Type.CREDIT_NOTE,
        amount=-note.total_amount,
        narration=f"Credit note {note.credit_note_number} against {locked_invoice.invoice_number}",
        entry_date=on,
        source_document=note,
        sales_order=locked_invoice.sales_order,
    )
    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type="credit_note",
        entity_id=note.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={
            "credit_note_number": note.credit_note_number,
            "invoice_number": locked_invoice.invoice_number,
            "total_amount": note.total_amount,
            "reason": reason,
        },
    )
    logger.info(
        "credit_note_issued",
        extra={
            "credit_note_id": note.pk,
            "invoice_id": locked_invoice.pk,
            "total": str(note.total_amount),
        },
    )
    return note
