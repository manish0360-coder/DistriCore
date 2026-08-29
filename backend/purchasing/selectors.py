"""Purchasing read queries (D5 Stages 1-3, S4.3)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Q, QuerySet, Sum

from core.fields import to_quantity
from ledger.models import SupplierLedgerEntry
from ledger.walk import Position, WalkPolicy, walk
from purchasing.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    ProductSupplier,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierPayment,
)


def active_suppliers() -> QuerySet[Supplier]:
    return Supplier.objects.filter(is_active=True)


def search_suppliers(*, term: str = "", is_active: bool | None = None) -> QuerySet[Supplier]:
    qs = Supplier.objects.all()
    if term:
        qs = qs.filter(Q(name__icontains=term) | Q(code__icontains=term))
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs


def products_for_supplier(supplier: Supplier) -> QuerySet[ProductSupplier]:
    """The supplier form's association list (FR-PUR-002)."""
    return (
        ProductSupplier.objects.filter(supplier=supplier)
        .select_related("product")
        .order_by("product__name")
    )


def suppliers_for_product(product: Any) -> QuerySet[ProductSupplier]:
    """Preferred first, then by supplier name — the order a buyer would read them in."""
    return (
        ProductSupplier.objects.filter(product=product)
        .select_related("supplier")
        .order_by("-is_preferred", "supplier__name")
    )


# ------------------------------------------------------------- purchase orders (Stage 2)


def search_purchase_orders(
    *, term: str = "", status: str = "", supplier: Any = None
) -> QuerySet[PurchaseOrder]:
    qs = PurchaseOrder.objects.select_related("supplier")
    if term:
        qs = qs.filter(Q(po_number__icontains=term) | Q(supplier__name__icontains=term))
    if status:
        qs = qs.filter(status=status)
    if supplier is not None:
        qs = qs.filter(supplier=supplier)
    return qs


def lines_for(purchase_order: PurchaseOrder) -> QuerySet[PurchaseOrderLine]:
    return (
        PurchaseOrderLine.objects.filter(purchase_order=purchase_order)
        .select_related("product")
        .order_by("line_number")
    )


# ------------------------------------------------------------- goods receipts (Stage 3)


def received_quantities(purchase_order: PurchaseOrder) -> dict[int, Decimal]:
    """`{purchase_order_line_id: Σ quantity_received}` for one order.

    **One query for the whole order, not one per line.** The acceptance check in
    `services._price_receipt_lines` runs over every submitted line, and a per-line `Sum` would
    make an N-line receipt N+1 queries for a figure the database groups in a single pass.

    **It lives in `selectors`, and `services` imports it from here** — the direction
    `orders.services` established. One implementation of "how much has arrived so far", used
    by both the acceptance rule and the variance report, is what stops a report disagreeing
    with the screen that produced it.
    """
    rows = (
        GoodsReceiptLine.objects.filter(goods_receipt__purchase_order=purchase_order)
        .values("purchase_order_line_id")
        .annotate(total=Sum("quantity_received"))
    )
    return {row["purchase_order_line_id"]: to_quantity(row["total"]) for row in rows}


def search_goods_receipts(
    *, term: str = "", supplier: Any = None, purchase_order: Any = None
) -> QuerySet[GoodsReceipt]:
    qs = GoodsReceipt.objects.select_related("purchase_order", "purchase_order__supplier")
    if term:
        qs = qs.filter(
            Q(grn_number__icontains=term)
            | Q(supplier_reference__icontains=term)
            | Q(purchase_order__po_number__icontains=term)
        )
    if supplier is not None:
        qs = qs.filter(purchase_order__supplier=supplier)
    if purchase_order is not None:
        qs = qs.filter(purchase_order=purchase_order)
    return qs


def receipt_lines_for(receipt: GoodsReceipt) -> QuerySet[GoodsReceiptLine]:
    return (
        GoodsReceiptLine.objects.filter(goods_receipt=receipt)
        .select_related("purchase_order_line", "purchase_order_line__product", "stock_movement")
        .order_by("purchase_order_line__line_number")
    )


def receipts_for(purchase_order: PurchaseOrder) -> QuerySet[GoodsReceipt]:
    """Every receipt against one order, oldest first — the partial-delivery history."""
    return GoodsReceipt.objects.filter(purchase_order=purchase_order).order_by("receipt_date", "id")


def outstanding_lines(purchase_order: PurchaseOrder) -> list[dict[str, Any]]:
    """Per ordered line: ordered, received so far, and the variance (FR-PUR-008).

    **The variance is computed here and stored nowhere.** It is
    ``quantity_ordered - Σ quantity_received``; a stored column would be a second source of
    truth for a subtraction, which N-03/E-01 forbid for the reason they forbid a cached
    balance.

    A positive `outstanding` is a short delivery; a negative one is an over-receipt that the
    tolerance permitted. Both are reported rather than hidden, which is the same posture
    `inventory` takes on negative stock (D-2, ADR-0006).

    Returns plain dicts rather than annotating the queryset because the receipt form needs the
    figure alongside the line's own snapshot fields, and one grouped query plus a Python join
    beats a correlated subquery per line.
    """
    received = received_quantities(purchase_order)
    zero = Decimal("0.000")
    return [
        {
            "line": line,
            "received": received.get(line.pk, zero),
            "outstanding": to_quantity(line.quantity_ordered - received.get(line.pk, zero)),
        }
        for line in lines_for(purchase_order)
    ]


# ------------------------------------------------------------ supplier payments (S4.3)


#: The payables vocabulary, handed to a walk that knows none of it (S4.2).
#:
#: `reducing_type` names `DEBIT_NOTE` even though **v1.0 has no producer for one** —
#: `purchase_return` is Edition 2 (DV-8) and a posted goods receipt is immutable (`04`
#: T-32). Naming it costs nothing and means the day a debit note arrives, the walk already
#: reduces the receipt it references rather than settling the oldest one.
_SUPPLIER_POLICY = WalkPolicy(
    adjustment_type=SupplierLedgerEntry.Type.ADJUSTMENT,
    # A payment reversal points at a PAYMENT; a receipt cancellation at a GOODS_RECEIPT. In
    # each case the pointed-at document's type is *also* the target entry's `entry_type`,
    # which is the equality `ledger.walk` requires and the reason `SupplierPayment` is
    # registered as "PAYMENT" rather than "SUPPLIER_PAYMENT" (S4.3 U-1).
    annullable_source_types=(
        SupplierLedgerEntry.Type.GOODS_RECEIPT,
        SupplierLedgerEntry.Type.PAYMENT,
    ),
    reducing_type=SupplierLedgerEntry.Type.DEBIT_NOTE,
    target_type=SupplierLedgerEntry.Type.GOODS_RECEIPT,
)


def supplier_position(supplier: Supplier, *, as_of: date | None = None) -> Position:
    """What is still owed to one supplier, oldest first (FR-PUR-012, BD-1 Option A).

    **Derived on every read, stored nowhere.** There is no allocation table, no allocation
    column and no settled flag: which receipts a payment cleared is a *view*, recomputed
    from the immutable ledger, exactly as it is for customers.

    **The algorithm is `ledger.walk` and nothing here reimplements it** — `purchasing`
    supplies four type codes and the rows. An adversarial contract
    (`test_ledger_walk_boundary`) fails if a second implementation ever appears.

    `reduction_targets` is `{}` and is passed as a literal rather than queried: it maps a
    debit note to the receipt it reduces, and v1.0 can create neither.

    Returns `ledger.walk.Position` **unwrapped**. Ageing buckets are display and belong to
    S4.4 (ruling U-6); `AGING_BUCKET_DAYS` lives in `receivables`, which sits above
    `purchasing`, so it could not be imported here even if S4.3 wanted it.
    """
    on = as_of or date.today()
    entries = list(
        SupplierLedgerEntry.objects.filter(supplier=supplier, entry_date__lte=on).order_by(
            "entry_date", "id"
        )
    )
    return walk(
        party_id=supplier.pk,
        as_of=on,
        entries=entries,
        reduction_targets={},
        policy=_SUPPLIER_POLICY,
    )


def search_supplier_payments(
    *, term: str = "", supplier: Any = None, method: str = ""
) -> QuerySet[SupplierPayment]:
    qs = SupplierPayment.objects.select_related("supplier")
    if term:
        qs = qs.filter(
            Q(payment_number__icontains=term)
            | Q(reference_number__icontains=term)
            | Q(supplier__name__icontains=term)
        )
    if supplier is not None:
        qs = qs.filter(supplier=supplier)
    if method:
        qs = qs.filter(method=method)
    return qs


def get_supplier_payment(payment_id: int) -> SupplierPayment | None:
    return SupplierPayment.objects.select_related("supplier").filter(pk=payment_id).first()
