"""Purchasing business rules — suppliers, purchase orders and goods receipts (D5 Stages 1-3).

N-01: every rule lives here. Views call these functions; they never reimplement any part of
them, and the import-linter contract forbids `webadmin` reaching `purchasing.models` directly.

**Owner only.** `05` §8 defines four roles — `OWNER`, `SALESMAN`, `DELIVERY`, `RETAILER` —
and none of the other three buys anything. This mirrors `inventory.services.receive_stock`:
*"Owner only in V1: there is no separate warehouse role."*
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from core.exceptions import ResourceNotFound, ValidationFailed
from core.fields import to_money, to_percent, to_quantity
from core.models import AuditLog
from core.permissions import Role, require_roles
from core.services import get_business_profile, record_audit
from inventory.services import receive_stock
from ledger.models import SupplierLedgerEntry
from ledger.services import record_supplier_entry
from purchasing.models import (
    GOODS_RECEIPT_NUMBER_SEQUENCE,
    PURCHASE_ORDER_NUMBER_SEQUENCE,
    SUPPLIER_PAYMENT_NUMBER_SEQUENCE,
    GoodsReceipt,
    GoodsReceiptLine,
    ProductSupplier,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierPayment,
)
from purchasing.selectors import received_quantities

#: Editable through `update_supplier`. `code` is absent deliberately: it is the supplier's
#: identity, it appears on documents, and renaming it would silently re-point history.
_SUPPLIER_FIELDS = frozenset(
    {
        "name",
        "contact_name",
        "phone",
        "alt_phone",
        "email",
        "billing_address",
        "dispatch_address",
        "gstin",
        "state_code",
        "payment_terms_days",
        "is_active",
    }
)

_ENTITY_SUPPLIER = "supplier"
_ENTITY_PRODUCT_SUPPLIER = "product_supplier"


def _audit_state(supplier: Supplier) -> dict[str, Any]:
    """The fields worth seeing in an audit diff. Not the whole row — addresses are long and
    an audit trail that nobody reads because it is noisy is not an audit trail.

    **The key is `supplier_code`, not `code`, and that is not cosmetic.** `core.services`
    scrubs audit payloads by key name, and `_SENSITIVE` contains `code` — it is there for OTP
    codes (`04` §T-05: *"An OTP is a credential"*), and the match is exact. A business
    identifier written under that key silently becomes `[redacted]`, which is what `customers`
    and `catalogue` have been doing since M1 without a test noticing. FR-AUD-006 covers
    credentials, password material and payment instruments; a supplier code is printed on
    purchase orders and is none of them. The policy is right and untouched — only the key
    is chosen to survive it.
    """
    return {
        "supplier_code": supplier.code,
        "name": supplier.name,
        "phone": supplier.phone,
        "gstin": supplier.gstin,
        "payment_terms_days": supplier.payment_terms_days,
        "is_active": supplier.is_active,
    }


def _clean_supplier_fields(fields: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in fields.items():
        if key not in _SUPPLIER_FIELDS:
            continue
        if key == "payment_terms_days":
            cleaned[key] = _payment_terms(value)
        elif key == "is_active":
            cleaned[key] = bool(value)
        else:
            cleaned[key] = str(value or "").strip()
    return cleaned


def _payment_terms(raw: Any) -> int:
    try:
        days = int(raw or 0)
    except (TypeError, ValueError):
        raise ValidationFailed("Payment terms must be a whole number of days.") from None
    if days < 0:
        # The CHECK constraint would also refuse this. Refusing here first turns a database
        # error into a message the user can act on.
        raise ValidationFailed("Payment terms cannot be negative.")
    return days


# --------------------------------------------------------------------------- supplier


@transaction.atomic
def create_supplier(
    *,
    actor: Any,
    code: str,
    name: str,
    phone: str,
    billing_address: str,
    **fields: Any,
) -> Supplier:
    """FR-PUR-001. Code, name, phone and billing address are the irreducible minimum."""
    require_roles(actor, Role.OWNER)

    # Canonical upper-case, the convention `create_customer` and `create_product` both use.
    # It is what makes the exact-match duplicate check below correct: without it "ACME" and
    # "acme" would both satisfy the unique index and be the same supplier to every human.
    code = (code or "").strip().upper()
    name = (name or "").strip()
    phone = (phone or "").strip()
    billing_address = (billing_address or "").strip()

    if not code:
        raise ValidationFailed("A supplier code is required.")
    if not name:
        raise ValidationFailed("A supplier name is required.")
    if not phone:
        raise ValidationFailed("A contact phone number is required.")
    if not billing_address:
        raise ValidationFailed("A billing address is required.")
    if Supplier.objects.filter(code=code).exists():
        raise ValidationFailed(
            "That supplier code is already in use.",
            errors=[{"field": "code", "code": "DUPLICATE", "message": code}],
        )

    supplier = Supplier.objects.create(
        code=code,
        name=name,
        phone=phone,
        billing_address=billing_address,
        created_by=actor if getattr(actor, "pk", None) else None,
        **_clean_supplier_fields(fields),
    )
    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type=_ENTITY_SUPPLIER,
        entity_id=supplier.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state=_audit_state(supplier),
    )
    return supplier


@transaction.atomic
def update_supplier(*, actor: Any, supplier: Supplier, **fields: Any) -> Supplier:
    """FR-PUR-001. `code` is not updatable — see `_SUPPLIER_FIELDS`."""
    require_roles(actor, Role.OWNER)
    before = _audit_state(supplier)

    cleaned = _clean_supplier_fields(fields)
    for key, value in cleaned.items():
        setattr(supplier, key, value)
    if "name" in cleaned and not supplier.name:
        raise ValidationFailed("A supplier name is required.")
    if "phone" in cleaned and not supplier.phone:
        raise ValidationFailed("A contact phone number is required.")
    if "billing_address" in cleaned and not supplier.billing_address:
        raise ValidationFailed("A billing address is required.")
    supplier.save()

    record_audit(
        action=AuditLog.Action.UPDATE,
        entity_type=_ENTITY_SUPPLIER,
        entity_id=supplier.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state=before,
        after_state=_audit_state(supplier),
    )
    return supplier


@transaction.atomic
def deactivate_supplier(*, actor: Any, supplier: Supplier) -> Supplier:
    """Never a delete. A supplier with history must stay resolvable (`PROTECT` everywhere)."""
    require_roles(actor, Role.OWNER)
    before = _audit_state(supplier)
    supplier.is_active = False
    supplier.save(update_fields=["is_active", "updated_at"])
    record_audit(
        action=AuditLog.Action.DEACTIVATE,
        entity_type=_ENTITY_SUPPLIER,
        entity_id=supplier.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state=before,
        after_state=_audit_state(supplier),
    )
    return supplier


# ------------------------------------------------------------------- product ↔ supplier


@transaction.atomic
def link_product_supplier(
    *,
    actor: Any,
    supplier: Supplier,
    product: Any,
    supplier_sku: str = "",
    is_preferred: bool = False,
) -> ProductSupplier:
    """FR-PUR-002. Idempotent on (product, supplier): re-linking updates rather than raising.

    Managed from the supplier side (`D5_Design_Review` §3.5, Q4 ruling), which is why the
    signature leads with `supplier`.
    """
    require_roles(actor, Role.OWNER)

    link, created = ProductSupplier.objects.get_or_create(
        product=product,
        supplier=supplier,
        defaults={"supplier_sku": (supplier_sku or "").strip()},
    )
    if not created:
        link.supplier_sku = (supplier_sku or "").strip()
        link.save(update_fields=["supplier_sku"])

    record_audit(
        action=AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE,
        entity_type=_ENTITY_PRODUCT_SUPPLIER,
        entity_id=link.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={
            "product_id": link.product_id,
            "supplier_id": link.supplier_id,
            "supplier_sku": link.supplier_sku,
        },
    )
    if is_preferred:
        set_preferred_supplier(actor=actor, product=product, supplier=supplier)
        link.refresh_from_db()
    return link


@transaction.atomic
def set_preferred_supplier(*, actor: Any, product: Any, supplier: Supplier) -> ProductSupplier:
    """FR-PUR-002. At most one preferred supplier per product.

    **The demotion and the promotion are one transaction**, because the partial unique index
    is real: promoting before demoting would collide, and demoting without promoting would
    leave a product with no preference where it had one.
    """
    require_roles(actor, Role.OWNER)

    link = ProductSupplier.objects.filter(product=product, supplier=supplier).first()
    if link is None:
        raise ValidationFailed("That product is not linked to that supplier.")

    ProductSupplier.objects.filter(product=product, is_preferred=True).exclude(pk=link.pk).update(
        is_preferred=False
    )
    if not link.is_preferred:
        link.is_preferred = True
        link.save(update_fields=["is_preferred"])

    record_audit(
        action=AuditLog.Action.UPDATE,
        entity_type=_ENTITY_PRODUCT_SUPPLIER,
        entity_id=link.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={
            "product_id": link.product_id,
            "supplier_id": link.supplier_id,
            "is_preferred": True,
        },
    )
    return link


@transaction.atomic
def unlink_product_supplier(*, actor: Any, supplier: Supplier, product: Any) -> None:
    """FR-PUR-002. Removes an association that has no history behind it.

    Deleting the *link* is safe in a way deleting a supplier is not: the row records only
    that a product may be bought from a supplier, and nothing references it. When purchase
    orders arrive (Stage 2) they will reference `product` and `supplier` directly, never
    this table, so an unlink can never orphan a document.
    """
    require_roles(actor, Role.OWNER)
    link = ProductSupplier.objects.filter(product=product, supplier=supplier).first()
    if link is None:
        raise ValidationFailed("That product is not linked to that supplier.")

    link_id = link.pk
    before = {
        "product_id": link.product_id,
        "supplier_id": link.supplier_id,
        "is_preferred": link.is_preferred,
    }
    link.delete()
    record_audit(
        action=AuditLog.Action.DEACTIVATE,
        entity_type=_ENTITY_PRODUCT_SUPPLIER,
        entity_id=link_id,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state=before,
    )


# ============================================================ purchase order (Stage 2)
#
# FR-PUR-003 (order and lines) and FR-PUR-005 (lifecycle). Nothing below moves stock or
# money: a purchase order is a commercial intention. Goods receipt, the supplier ledger and
# supplier payments arrive at Stages 3 and 4.


#: **The lifecycle, and the whole of it** (FR-PUR-005, `04` T-30.1).
#:
#: Declared complete even though Stage 2 exercises only the first three edges. The map *is*
#: the specification, and a map that grew with each stage would let a later author add an
#: edge nobody reviewed. `_transition` refuses anything absent from it.
#:
#: **`PARTIALLY_RECEIVED → PARTIALLY_RECEIVED` is a deliberate self-edge**: the second receipt
#: against an already-partly-received order re-enters the same state (FR-PUR-013). Routing it
#: through `_transition` keeps every status write on one path.
#:
#: **`CANCELLED` is reachable from `DRAFT` and `ISSUED` only.** Once stock has arrived an
#: order is short-closed, never cancelled — which is why the receiving states lead to
#: `CLOSED` and not back out.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    PurchaseOrder.Status.DRAFT: frozenset(
        {PurchaseOrder.Status.ISSUED, PurchaseOrder.Status.CANCELLED}
    ),
    PurchaseOrder.Status.ISSUED: frozenset(
        {
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
            PurchaseOrder.Status.RECEIVED,
            PurchaseOrder.Status.CANCELLED,
        }
    ),
    PurchaseOrder.Status.PARTIALLY_RECEIVED: frozenset(
        {
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
            PurchaseOrder.Status.RECEIVED,
            PurchaseOrder.Status.CLOSED,
        }
    ),
    PurchaseOrder.Status.RECEIVED: frozenset({PurchaseOrder.Status.CLOSED}),
    PurchaseOrder.Status.CLOSED: frozenset(),
    PurchaseOrder.Status.CANCELLED: frozenset(),
}

_ENTITY_PURCHASE_ORDER = "purchase_order"


def _next_po_number() -> str:
    """Allocate the next purchase-order reference (D-PUR-8).

    `nextval` is lock-free and concurrency-safe, and it is read **before** the insert so the
    row is written once. Gaps are permitted: an abandoned draft consumes a number, which is
    correct for a reference and would be a defect only for a statutory series — contrast
    `billing.services.allocate_number`, which locks a counter row precisely because invoices
    must be gapless (M5-4). The same reasoning `receivables._next_payment_number` records.
    """
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT nextval('{PURCHASE_ORDER_NUMBER_SEQUENCE}')")
        value = cursor.fetchone()[0]
    return f"PO-{value:08d}"


def _po_audit_state(purchase_order: PurchaseOrder) -> dict[str, Any]:
    """`po_number`, not `code` — see `_audit_state` for why that distinction is load-bearing."""
    return {
        "po_number": purchase_order.po_number,
        "supplier_code": purchase_order.supplier.code,
        "status": purchase_order.status,
        "total_amount": purchase_order.total_amount,
    }


def _transition(
    *,
    actor: Any,
    purchase_order: PurchaseOrder,
    to_status: str,
    extra_fields: list[str] | None = None,
    audit_extra: dict[str, Any] | None = None,
) -> None:
    """The single place a purchase order's status changes.

    A transition not in `ALLOWED_TRANSITIONS` is rejected. The map is enforced here and
    `status` is never exposed as a settable field — a caller that could assign it would hold
    the state machine. Same construction as `orders.services._transition` (M3-4).
    """
    from_status = purchase_order.status
    if to_status not in ALLOWED_TRANSITIONS.get(from_status, frozenset()):
        raise ValidationFailed(
            f"A purchase order cannot go from {from_status} to {to_status}.",
            errors=[
                {
                    "field": "status",
                    "code": "INVALID_TRANSITION",
                    "message": f"{from_status}->{to_status}",
                }
            ],
        )
    purchase_order.status = to_status
    purchase_order.save(update_fields=["status", "updated_at", *(extra_fields or [])])

    action_by_status: dict[str, str] = {
        PurchaseOrder.Status.ISSUED: AuditLog.Action.ISSUE,
        PurchaseOrder.Status.CANCELLED: AuditLog.Action.CANCEL,
    }
    record_audit(
        action=action_by_status.get(to_status, AuditLog.Action.UPDATE),
        entity_type=_ENTITY_PURCHASE_ORDER,
        entity_id=purchase_order.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"status": from_status},
        after_state={"status": to_status, **(audit_extra or {})},
    )


def _replace_lines(*, purchase_order: PurchaseOrder, lines: list[dict[str, Any]]) -> None:
    """Rebuild every line and recompute the header.

    **Whole-set replacement, never partial mutation** — the shape `orders._replace_lines`
    uses. Quantities, costs and totals are recomputed together or not at all.

    **No new tax engine** (ruling of 2026-08-26). The arithmetic reuses `core.fields`'
    primitives and the M3-8 rounding rule; it deliberately does **not** call
    `pricing.compute_line`, which resolves a *selling* price and answers a different question.
    There is no purchase-side price resolution and no purchase discount in v1.0.
    """
    purchase_order.lines.all().delete()
    if not lines:
        raise ValidationFailed(
            "A purchase order needs at least one line.",
            errors=[{"field": "lines", "code": "REQUIRED", "message": "0"}],
        )

    for index, raw in enumerate(lines, start=1):
        product = raw["product"]
        if not product.is_active:
            raise ValidationFailed(
                f"Product {product.code} is no longer available.",
                errors=[{"field": "product", "code": "INACTIVE", "message": product.code}],
            )

        quantity = to_quantity(raw["quantity_ordered"])
        if quantity <= 0:
            raise ValidationFailed(
                "Quantity must be greater than zero.",
                errors=[
                    {"field": "quantity_ordered", "code": "MIN_VALUE", "message": str(quantity)}
                ],
            )
        unit_cost = to_money(raw["unit_cost"])
        if unit_cost < 0:
            raise ValidationFailed(
                "A unit cost cannot be negative.",
                errors=[{"field": "unit_cost", "code": "MIN_VALUE", "message": str(unit_cost)}],
            )

        # Rounded at line level (M3-8). Rounding once at the end would give a different
        # figure, and the Stage 4 payable must agree to the paisa.
        taxable = to_money(unit_cost * quantity)
        tax_rate = to_percent(product.tax_rate_percent)
        tax = to_money(taxable * tax_rate / Decimal("100"))

        PurchaseOrderLine.objects.create(
            purchase_order=purchase_order,
            line_number=index,
            product=product,
            # Snapshots. A later rename or reprice must not alter this row.
            product_code=product.code,
            product_name=product.name,
            unit_name=product.unit_name,
            pack_size_snapshot=product.pack_size,
            quantity_ordered=quantity,
            unit_cost=unit_cost,
            tax_rate_percent=tax_rate,
            taxable_amount=taxable,
            tax_amount=tax,
            line_total=to_money(taxable + tax),
        )
    _recalculate_totals(purchase_order)


def _recalculate_totals(purchase_order: PurchaseOrder) -> None:
    """Sum already-rounded line values onto the header (M3-8)."""
    subtotal = tax = total = Decimal("0.00")
    for line in purchase_order.lines.all():
        subtotal += line.taxable_amount
        tax += line.tax_amount
        total += line.line_total
    purchase_order.subtotal_amount = to_money(subtotal)
    purchase_order.tax_amount = to_money(tax)
    purchase_order.total_amount = to_money(total)
    purchase_order.save(
        update_fields=["subtotal_amount", "tax_amount", "total_amount", "updated_at"]
    )


@transaction.atomic
def create_purchase_order(
    *,
    actor: Any,
    supplier: Supplier,
    order_date: date,
    lines: list[dict[str, Any]],
    expected_date: date | None = None,
    notes: str = "",
) -> PurchaseOrder:
    """FR-PUR-003.

    **`order_date` is required and caller-supplied.** P-4's reasoning applies to any surface:
    a machine clock must not decide a business fact. The web form defaults it to today; the
    service never does.

    **The number is allocated here, not at issue** (D-PUR-8). A draft is already a business
    document that support and audit need to be able to name.
    """
    require_roles(actor, Role.OWNER)

    if order_date is None:
        raise ValidationFailed("An order date is required.")
    if not supplier.is_active:
        raise ValidationFailed(
            f"Supplier {supplier.code} is inactive.",
            errors=[{"field": "supplier", "code": "INACTIVE", "message": supplier.code}],
        )
    if expected_date is not None and expected_date < order_date:
        raise ValidationFailed(
            "The expected date cannot be before the order date.",
            errors=[
                {
                    "field": "expected_date",
                    "code": "BEFORE_ORDER_DATE",
                    "message": str(expected_date),
                }
            ],
        )

    purchase_order = PurchaseOrder.objects.create(
        po_number=_next_po_number(),
        supplier=supplier,
        order_date=order_date,
        expected_date=expected_date,
        notes=(notes or "").strip(),
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    _replace_lines(purchase_order=purchase_order, lines=lines)

    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type=_ENTITY_PURCHASE_ORDER,
        entity_id=purchase_order.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state=_po_audit_state(purchase_order),
    )
    return purchase_order


@transaction.atomic
def amend_purchase_order(
    *, actor: Any, purchase_order: PurchaseOrder, lines: list[dict[str, Any]], **fields: Any
) -> PurchaseOrder:
    """FR-PUR-003. Replace the lines and re-run the arithmetic; drafts only.

    Partial re-evaluation is not offered: quantities, costs, tax and totals are recomputed
    together or not at all — the rule `orders.services.amend_order` states.
    """
    require_roles(actor, Role.OWNER)
    if not purchase_order.is_editable:
        raise ValidationFailed(
            "A purchase order cannot be amended once it is "
            f"{purchase_order.get_status_display().lower()}.",
            errors=[{"field": "status", "code": "NOT_EDITABLE", "message": purchase_order.status}],
        )

    before = _po_audit_state(purchase_order)
    changed: list[str] = []
    if "expected_date" in fields:
        expected = fields["expected_date"]
        if expected is not None and expected < purchase_order.order_date:
            raise ValidationFailed(
                "The expected date cannot be before the order date.",
                errors=[
                    {
                        "field": "expected_date",
                        "code": "BEFORE_ORDER_DATE",
                        "message": str(expected),
                    }
                ],
            )
        purchase_order.expected_date = expected
        changed.append("expected_date")
    if "notes" in fields:
        purchase_order.notes = str(fields["notes"] or "").strip()
        changed.append("notes")
    if changed:
        purchase_order.save(update_fields=[*changed, "updated_at"])

    _replace_lines(purchase_order=purchase_order, lines=lines)

    record_audit(
        action=AuditLog.Action.UPDATE,
        entity_type=_ENTITY_PURCHASE_ORDER,
        entity_id=purchase_order.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state=before,
        after_state=_po_audit_state(purchase_order),
    )
    return purchase_order


@transaction.atomic
def issue_purchase_order(*, actor: Any, purchase_order: PurchaseOrder) -> PurchaseOrder:
    """FR-PUR-005 — send the order to the supplier.

    **There is deliberately no approval call here.** `D5_Design_Review` §6 specifies the
    shared DR-10 contract and §6's ruling is explicit: until BD-4 decides whether DR-10 is in
    v1.0 and what the threshold is, **the call site does not exist** — not a placeholder, not
    a stub, not a `TODO` branch. FR-PUR-014 stays open. When it arrives it is one call to
    `core.services.request_approval` before the transition below, and no other line changes.

    **Re-issue is guarded by the lifecycle, not by the number.** `DRAFT → ISSUED` is the only
    edge into `ISSUED`, so a second attempt raises `INVALID_TRANSITION`. That is also the
    double-submit protection; `po_number` was allocated at creation and is never reallocated.
    """
    require_roles(actor, Role.OWNER)
    if not purchase_order.lines.exists():
        raise ValidationFailed(
            "A purchase order cannot be issued with no lines.",
            errors=[{"field": "lines", "code": "REQUIRED", "message": "0"}],
        )

    purchase_order.issued_at = timezone.now()
    purchase_order.issued_by = actor if getattr(actor, "pk", None) else None
    _transition(
        actor=actor,
        purchase_order=purchase_order,
        to_status=PurchaseOrder.Status.ISSUED,
        extra_fields=["issued_at", "issued_by"],
        audit_extra={"po_number": purchase_order.po_number},
    )
    return purchase_order


@transaction.atomic
def cancel_purchase_order(
    *, actor: Any, purchase_order: PurchaseOrder, reason: str
) -> PurchaseOrder:
    """FR-PUR-005. Reachable from `DRAFT` and `ISSUED` only.

    Once stock has arrived the order is short-closed instead — `PARTIALLY_RECEIVED` and
    `RECEIVED` have no edge to `CANCELLED`, and `_transition` refuses the attempt.
    """
    require_roles(actor, Role.OWNER)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed(
            "A cancellation reason is required.",
            errors=[{"field": "reason", "code": "REQUIRED", "message": ""}],
        )

    purchase_order.cancelled_reason = reason
    purchase_order.cancelled_at = timezone.now()
    purchase_order.cancelled_by = actor if getattr(actor, "pk", None) else None
    _transition(
        actor=actor,
        purchase_order=purchase_order,
        to_status=PurchaseOrder.Status.CANCELLED,
        extra_fields=["cancelled_reason", "cancelled_at", "cancelled_by"],
        audit_extra={"reason": reason},
    )
    return purchase_order


# ============================================================== goods receipt (Stage 3)
#
# FR-PUR-006 (receive against an order), FR-PUR-007 (the movement it produces), FR-PUR-008
# (variance), FR-PUR-009 (over-receipt tolerance), FR-PUR-010/011 (the payable) and
# FR-PUR-013 (partial receipts).
#
# **This is where a purchase order stops being an intention.** Everything above writes only
# `purchasing` rows; `create_goods_receipt` below writes a stock movement and a supplier
# ledger entry as well, and all three plus the lifecycle transition are one transaction.

_ENTITY_GOODS_RECEIPT = "goods_receipt"

#: The states goods may be received into, derived from nothing — stated, because the set is
#: not "whatever `ALLOWED_TRANSITIONS` permits". `DRAFT` is excluded because an unissued order
#: has not been placed with anyone; `RECEIVED`, `CLOSED` and `CANCELLED` because each is a
#: settled outcome. `PARTIALLY_RECEIVED` is included, and that is FR-PUR-013.
_RECEIVABLE_STATUSES = frozenset(
    {PurchaseOrder.Status.ISSUED, PurchaseOrder.Status.PARTIALLY_RECEIVED}
)


def _next_grn_number() -> str:
    """Allocate the next goods-receipt reference.

    `nextval`, lock-free, gaps permitted — the same reasoning `_next_po_number` records. A
    receipt reference is internal; nothing statutory is numbered here.
    """
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT nextval('{GOODS_RECEIPT_NUMBER_SEQUENCE}')")
        value = cursor.fetchone()[0]
    return f"GRN-{value:08d}"


def _grn_audit_state(receipt: GoodsReceipt) -> dict[str, Any]:
    """`grn_number` and `supplier_code`, never `code` — see `_audit_state` for why."""
    return {
        "grn_number": receipt.grn_number,
        "po_number": receipt.purchase_order.po_number,
        "supplier_code": receipt.purchase_order.supplier.code,
        "receipt_date": str(receipt.receipt_date),
        "total_amount": receipt.total_amount,
    }


def _acceptance_limit(*, ordered: Decimal, tolerance_percent: Decimal) -> Decimal:
    """The most that may ever be received against one ordered line (BD-2, D-PUR-4).

    ``ordered x (1 + tolerance/100)``, evaluated **cumulatively** across every receipt for
    that line. Cumulative rather than per receipt, because three receipts of 40% each would
    otherwise each pass and overshoot together; per line rather than per order, because a
    shortfall on one line must not finance an overage on another.

    The tolerance comes from `BusinessProfile` and **nothing here hard-codes a figure**. The
    default is `0.00`, so an unconfigured system refuses every over-receipt — the safest
    commercial position, and the one that relaxes later without a migration.
    """
    return to_quantity(ordered * (Decimal("100") + tolerance_percent) / Decimal("100"))


def _price_receipt_lines(
    *,
    purchase_order: PurchaseOrder,
    lines: list[dict[str, Any]],
    already_received: dict[int, Decimal],
    tolerance_percent: Decimal,
) -> list[dict[str, Any]]:
    """Validate every submitted line and compute its arithmetic. Writes nothing.

    **Pure, and deliberately so.** Because the totals are known before anything is inserted,
    the `GoodsReceipt` header can be created complete and never updated — which is what makes
    its immutability airtight rather than a rule with one sanctioned exception. A
    `_recalculate_totals` that had to go around `save()` would have been exactly such an
    exception, and the next author would have found it and reused it.

    **Costs are snapshotted from the PURCHASE ORDER LINE**, not from the product and not from
    the caller. What arrived is priced at what was agreed; a supplier's note that says
    otherwise is a commercial conversation, not a silent overwrite.
    """
    if not lines:
        raise ValidationFailed(
            "A goods receipt needs at least one line.",
            errors=[{"field": "lines", "code": "REQUIRED", "message": "0"}],
        )

    priced: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw in lines:
        po_line: PurchaseOrderLine = raw["purchase_order_line"]
        if po_line.purchase_order_id != purchase_order.pk:
            raise ValidationFailed(
                "That line belongs to a different purchase order.",
                errors=[
                    {
                        "field": "purchase_order_line",
                        "code": "WRONG_ORDER",
                        "message": str(po_line.pk),
                    }
                ],
            )
        # The unique constraint would also refuse this. Refusing here first names the line.
        if po_line.pk in seen:
            raise ValidationFailed(
                f"Line {po_line.line_number} appears twice in one receipt.",
                errors=[
                    {
                        "field": "purchase_order_line",
                        "code": "DUPLICATE_LINE",
                        "message": str(po_line.line_number),
                    }
                ],
            )
        seen.add(po_line.pk)

        quantity = to_quantity(raw["quantity_received"])
        if quantity <= 0:
            raise ValidationFailed(
                "A received quantity must be greater than zero.",
                errors=[
                    {"field": "quantity_received", "code": "MIN_VALUE", "message": str(quantity)}
                ],
            )

        # BD-2 / D-PUR-4, cumulative and per line.
        prior = already_received.get(po_line.pk, Decimal("0.000"))
        limit = _acceptance_limit(
            ordered=po_line.quantity_ordered, tolerance_percent=tolerance_percent
        )
        if prior + quantity > limit:
            raise ValidationFailed(
                f"Line {po_line.line_number} ({po_line.product_code}): receiving {quantity} "
                f"would bring the total to {prior + quantity}, above the {limit} permitted "
                f"for {po_line.quantity_ordered} ordered.",
                errors=[
                    {
                        "field": "quantity_received",
                        "code": "OVER_RECEIPT",
                        "message": str(prior + quantity),
                    }
                ],
            )

        # Rounded at line level (M3-8), from the PO line's frozen commercial terms.
        taxable = to_money(po_line.unit_cost * quantity)
        tax = to_money(taxable * po_line.tax_rate_percent / Decimal("100"))

        priced.append(
            {
                "purchase_order_line": po_line,
                "quantity_received": quantity,
                "unit_cost": po_line.unit_cost,
                "tax_rate_percent": po_line.tax_rate_percent,
                "taxable_amount": taxable,
                "tax_amount": tax,
                "line_total": to_money(taxable + tax),
            }
        )
    return priced


def _receipt_totals(priced: list[dict[str, Any]]) -> dict[str, Decimal]:
    """Sum already-rounded line values (M3-8).

    Rounding once at the end would give a different figure, and the payable raised in T-34
    must agree to the paisa with the lines that justify it.
    """
    zero = Decimal("0.00")
    return {
        "subtotal_amount": to_money(sum((row["taxable_amount"] for row in priced), zero)),
        "tax_amount": to_money(sum((row["tax_amount"] for row in priced), zero)),
        "total_amount": to_money(sum((row["line_total"] for row in priced), zero)),
    }


def _post_receipt_lines(
    *, actor: Any, receipt: GoodsReceipt, priced: list[dict[str, Any]]
) -> None:
    """Move the stock, then record the line that the movement belongs to.

    **The movement is created first and is never optional** — `GoodsReceiptLine.stock_movement`
    is `NOT NULL`, which makes a received line with no movement *unrepresentable* rather than
    merely discouraged (FR-PUR-007, `04` T-33). The movement points forward to the receipt
    through `source_document`; the line points back. Both directions resolve or the
    transaction does not commit.

    **It goes through `inventory.receive_stock`, not `record_movement`**, so the owner check
    and the always-positive rule (M2-11) apply to purchased stock exactly as they do to any
    other goods-in. That path is why `receive_stock` accepts a source document (D-PUR-10).
    """
    for row in priced:
        po_line: PurchaseOrderLine = row["purchase_order_line"]
        movement = receive_stock(
            actor=actor,
            product=po_line.product,
            quantity=row["quantity_received"],
            source_document=receipt,
            notes=f"{receipt.grn_number} line {po_line.line_number}",
        )
        GoodsReceiptLine.objects.create(
            goods_receipt=receipt, stock_movement=movement, **row
        )


def _settle_order_status(*, actor: Any, purchase_order: PurchaseOrder) -> None:
    """Move the order to `PARTIALLY_RECEIVED` or `RECEIVED` (FR-PUR-005, FR-PUR-013).

    **`RECEIVED` means every line has met or exceeded its ordered quantity**, not that a
    receipt happened. A short delivery leaves the order `PARTIALLY_RECEIVED` and open, which
    is what makes a second receipt against it possible; closing a short order early is a
    decision the owner takes explicitly, through `close_purchase_order`.

    The `PARTIALLY_RECEIVED → PARTIALLY_RECEIVED` self-edge in `ALLOWED_TRANSITIONS` exists
    for exactly this: the third receipt against a still-short order re-enters the same state
    and still goes through `_transition`, so every status write stays on one path.
    """
    received = received_quantities(purchase_order)
    complete = all(
        received.get(line.pk, Decimal("0.000")) >= line.quantity_ordered
        for line in purchase_order.lines.all()
    )
    _transition(
        actor=actor,
        purchase_order=purchase_order,
        to_status=(
            PurchaseOrder.Status.RECEIVED
            if complete
            else PurchaseOrder.Status.PARTIALLY_RECEIVED
        ),
    )


@transaction.atomic
def create_goods_receipt(
    *,
    actor: Any,
    purchase_order: PurchaseOrder,
    receipt_date: date,
    lines: list[dict[str, Any]],
    supplier_reference: str = "",
    notes: str = "",
) -> GoodsReceipt:
    """FR-PUR-006/007/008/009/010/011/013 — book goods in against an order.

    **Six things happen or none of them do**, which is why `@transaction.atomic` is on this
    function and not distributed among the pieces:

    1. the `GoodsReceipt` header;
    2. a `GoodsReceiptLine` per received line;
    3. a `StockMovement` per line, through `inventory.receive_stock` (FR-PUR-007);
    4. a `SupplierLedgerEntry` for the total, positive (FR-PUR-010/011, D-PUR-3);
    5. the purchase order's lifecycle transition (FR-PUR-005, FR-PUR-013);
    6. one audit row, for the receipt.

    A partial failure here is the one outcome the business cannot absorb: stock that arrived
    with no payable, or a payable for stock nobody has.

    **One audit row, not four.** The receipt is audited; the ledger entry is not, because R-3
    says an immutable row that already carries actor, timestamp, amount, narration and source
    document would only be duplicated by an audit of it. The stock movements are likewise
    their own record. Auditing all four would make the trail longer without making it truer.

    **Partial receipts are ordinary** (FR-PUR-013): each is a separate `GoodsReceipt` against
    the same order, and the acceptance limit is evaluated cumulatively across all of them.

    **A posted receipt cannot be corrected.** There is no amend, no reverse and no debit note
    in v1.0 — those need a separately approved design, and inventing one here would put an
    editable handle on two append-only tables.
    """
    require_roles(actor, Role.OWNER)

    if receipt_date is None:
        raise ValidationFailed("A receipt date is required.")
    if purchase_order.status not in _RECEIVABLE_STATUSES:
        raise ValidationFailed(
            "Goods can only be received against an issued purchase order, and this one is "
            f"{purchase_order.get_status_display().lower()}.",
            errors=[
                {"field": "status", "code": "NOT_RECEIVABLE", "message": purchase_order.status}
            ],
        )
    if receipt_date < purchase_order.order_date:
        raise ValidationFailed(
            "Goods cannot be received before the order was placed.",
            errors=[
                {"field": "receipt_date", "code": "BEFORE_ORDER_DATE", "message": str(receipt_date)}
            ],
        )

    priced = _price_receipt_lines(
        purchase_order=purchase_order,
        lines=lines,
        # Read BEFORE this receipt exists, so the cumulative limit is measured against what
        # had already arrived rather than against itself.
        already_received=received_quantities(purchase_order),
        tolerance_percent=to_percent(get_business_profile().over_receipt_tolerance_percent),
    )

    # Created complete. Every total is known before the insert, so this row is written once
    # and never touched again — which is what `GoodsReceipt.save()`'s refusal guarantees.
    receipt = GoodsReceipt.objects.create(
        grn_number=_next_grn_number(),
        purchase_order=purchase_order,
        receipt_date=receipt_date,
        supplier_reference=(supplier_reference or "").strip(),
        notes=(notes or "").strip(),
        received_by=actor if getattr(actor, "pk", None) else None,
        **_receipt_totals(priced),
    )
    _post_receipt_lines(actor=actor, receipt=receipt, priced=priced)

    # FR-PUR-010/011. Positive: a receipt increases what we owe (D-PUR-3). The narration is
    # written once and is what a supplier statement shows, so it must stand alone.
    #
    # **A zero-value receipt raises no payable, and that is not a special case being papered
    # over.** `PurchaseOrderLine` permits `unit_cost = 0` because free goods are legitimate
    # (`ck_po_line_unit_cost_non_negative`), so a receipt consisting only of free goods totals
    # zero — and `ck_sle_amount_non_zero` correctly refuses to record "we now owe nothing
    # more" as a ledger event. The stock still moved; there is simply no liability to raise.
    if receipt.total_amount != 0:
        record_supplier_entry(
            actor=actor,
            supplier=purchase_order.supplier,
            entry_type=SupplierLedgerEntry.Type.GOODS_RECEIPT,
            amount=receipt.total_amount,
            narration=f"{receipt.grn_number} against {purchase_order.po_number}",
            entry_date=receipt_date,
            source_document=receipt,
        )

    _settle_order_status(actor=actor, purchase_order=purchase_order)

    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type=_ENTITY_GOODS_RECEIPT,
        entity_id=receipt.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state=_grn_audit_state(receipt),
    )
    return receipt


# ==================================================== supplier opening balance (S4.1)
#
# BD-5, frozen in `D5_Stage4_Design_Review` v2.0.0 §4.1. What the distributor already owed
# a supplier on the day the system went live.
#
# **Nothing here is new structure.** Stage 3 built the whole of it: the partial unique index
# `uq_sle_one_opening_per_supplier`, the `ck_sle_sign` CHECK that deliberately leaves
# `OPENING` unsigned, `ck_sle_amount_non_zero`, and the immutability the ledger enforces on
# every entry. This section adds one service and no migration.

_OPENING_NARRATION = "Opening balance carried at go-live"


@transaction.atomic
def load_supplier_opening_balance(
    *,
    actor: Any,
    supplier: Supplier,
    amount: Decimal | str | int,
    entry_date: date,
) -> SupplierLedgerEntry:
    """What we owed this supplier at go-live (BD-5). Owner only.

    **The payables counterpart of `receivables.services.load_opening_balance`**, and it
    diverges from it in three places. Each divergence was ruled, and each is recorded here
    rather than left for a reader to discover by diffing the two functions.

    **1. It writes no audit row.** The customer version calls `record_audit` with
    `entity_type="customer_ledger_entry"`. That is the one place in the corpus where a
    ledger entry acquires an audit row, and R-3 is the rule it sits against: *a ledger entry
    is immutable and already carries actor, timestamp, amount, narration and its source
    document; an audit row would duplicate a record that cannot change.* Every one of those
    facts is true of the row below — `created_by` names the owner, `created_at` stamps it,
    `narration` says what it is — so R-3 applies with nothing left over. The supplier ledger
    is therefore strictly R-3-consistent, and the customer side's extra row is a legacy
    anomaly rather than the convention.

    **2. A second opening balance is refused, not returned.** The customer version is
    idempotent because it backs a bulk go-live import that may fail halfway and be re-run
    wholesale. There is no supplier equivalent: opening balances are entered per supplier,
    deliberately, and silently returning the existing entry when the caller supplied a
    different amount would report success for a change that did not happen. **The cost is
    stated:** a partial supplier load is not blindly re-runnable — a caller repeating one
    must skip suppliers already loaded, or handle the refusal.

    **3. `entry_date` is required, with no fallback.** The customer version defaults to
    `timezone.localdate()`. P-4's reasoning applies to any surface: **a machine clock must
    not decide a business fact**, and the date of an opening position is a business fact
    about a period that ended before this system existed. Dating it earlier than go-live is
    not merely permitted, it is usually correct — the balance ages from this date.

    **The amount may be negative, and that is the fourth difference.** The customer version
    refuses anything `<= 0` on the grounds that *"a customer who owes nothing needs no
    entry"*. A supplier opening position can legitimately be a credit — an advance paid, or
    goods returned before go-live — and `ck_sle_sign` was written in Stage 3 to permit it by
    omitting `OPENING` from both the debit and the credit lists. **Zero is still refused**,
    for the customer version's reason and because `ck_sle_amount_non_zero` would refuse it.
    """
    require_roles(actor, Role.OWNER)

    if entry_date is None:
        raise ValidationFailed(
            "An opening balance needs the date it applies to. It is a business fact about a "
            "period that ended before this system existed, so the system cannot supply it.",
            errors=[{"field": "entry_date", "code": "REQUIRED", "message": ""}],
        )

    amount = to_money(amount)
    if amount == 0:
        raise ValidationFailed(
            "An opening balance cannot be zero. A supplier we owe nothing needs no entry.",
            errors=[{"field": "amount", "code": "ZERO", "message": str(amount)}],
        )

    if _existing_opening(supplier) is not None:
        raise _duplicate_opening(supplier)

    try:
        # **The database is the guarantee, not the check above.** Two concurrent loads would
        # both pass it. The savepoint keeps the losing one recoverable, which matters because
        # this function is atomic and the caller may have work either side of it.
        with transaction.atomic():
            entry = record_supplier_entry(
                actor=actor,
                supplier=supplier,
                entry_type=SupplierLedgerEntry.Type.OPENING,
                amount=amount,
                narration=_OPENING_NARRATION,
                entry_date=entry_date,
                # No source document, deliberately: an opening balance predates the system,
                # so there is no document here to point at. `ck_sle_source_pair` requires
                # both halves or neither, and this is the "neither" case.
            )
    except IntegrityError:
        if _existing_opening(supplier) is None:  # pragma: no cover - another constraint fired
            raise
        raise _duplicate_opening(supplier) from None

    # **No log line here, and no `record_audit`.** `record_supplier_entry` already logs
    # `supplier_ledger_entry` with the supplier, type and amount; repeating it under a second
    # event name would put one act in the log twice under two names.
    return entry


def _existing_opening(supplier: Supplier) -> SupplierLedgerEntry | None:
    return SupplierLedgerEntry.objects.filter(
        supplier=supplier, entry_type=SupplierLedgerEntry.Type.OPENING
    ).first()


# ==================================================== supplier payment (S4.3, FR-PUR-012)
#
# Money paid to a supplier, and the reversal of it. Settlement is **derived** — BD-1 Option
# A — so nothing below records which receipts a payment cleared.

_ENTITY_SUPPLIER_PAYMENT = "supplier_payment"

#: Compared field-for-field when a `submission_id` is replayed. **Every caller-supplied
#: business field is here**, including `notes`: a replay whose only change is a note would
#: otherwise succeed while silently discarding the note, and ignoring is a quieter failure
#: than refusing rather than a smaller one.
_PAYMENT_PAYLOAD_FIELDS = (
    "supplier_id",
    "amount",
    "payment_date",
    "method",
    "reference_number",
    "notes",
)


def _next_supplier_payment_number() -> str:
    """Allocate the next supplier-payment reference.

    `nextval`, lock-free, gaps permitted — the reasoning `_next_po_number` records. A racer
    that loses the `submission_id` unique index consumes a number, which is correct for a
    reference and would be a defect only for a statutory series.
    """
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT nextval('{SUPPLIER_PAYMENT_NUMBER_SEQUENCE}')")
        value = cursor.fetchone()[0]
    return f"SPY-{value:08d}"


def _payment_audit_state(payment: SupplierPayment) -> dict[str, Any]:
    """`supplier_code` and `payment_number`, never `code` — see `_audit_state` for why.

    `submission_id` is deliberately absent: `core.services._SENSITIVE` redacts the key
    `token`, and while `submission_id` survives that filter, an idempotency key is not part
    of the business record. What happened is the payment.
    """
    return {
        "payment_number": payment.payment_number,
        "supplier_code": payment.supplier.code,
        "amount": payment.amount,
        "method": payment.method,
        "payment_date": str(payment.payment_date),
    }


def _replayed(existing: SupplierPayment, payload: dict[str, Any]) -> SupplierPayment:
    """Decide what a repeated `submission_id` means (S4.3 §3.7, rules S-3 and S-4).

    **Identical payload → return the original.** Idempotent success, not an error. The rule
    this repository already follows: `reverse_payment` returns the already-reversed payment,
    `load_opening_balance` returns the existing entry. The behavioural argument is the
    stronger one — an error makes the owner try again, and trying again is what produces
    duplicates.

    **Changed payload → refuse, loudly.** The owner pressed Back, edited a field and saved.
    They intend a correction, but a payment is immutable, so there is no correction — only a
    reversal and a new payment. Creating a second payment would pay twice; returning the
    original would let them believe the edit took. Neither is acceptable, so neither is done.
    """
    differences = sorted(
        field for field in _PAYMENT_PAYLOAD_FIELDS if getattr(existing, field) != payload[field]
    )
    if not differences:
        return existing
    raise ValidationFailed(
        f"Payment {existing.payment_number} was already recorded from this form, and a "
        f"payment cannot be changed ({', '.join(differences)} differ). To correct it, "
        "reverse that payment and record a new one.",
        errors=[
            {
                "field": "submission_id",
                "code": "SUBMISSION_REPLAYED_WITH_CHANGES",
                "message": ", ".join(differences),
            }
        ],
    )


@transaction.atomic
def record_supplier_payment(
    *,
    actor: Any,
    supplier: Supplier,
    submission_id: Any,
    amount: Decimal | str | int,
    method: str,
    payment_date: date,
    reference_number: str = "",
    notes: str = "",
) -> SupplierPayment:
    """FR-PUR-012 — pay a supplier. Owner only.

    **The payment and its ledger entry are one transaction.** A payment with no ledger entry
    would be money that left the building and never reduced what we owe; an entry with no
    payment would be the reverse. Neither is recoverable by inspection, so neither is
    permitted to exist.

    **`submission_id` is required and is the duplicate guarantee (E3).** It identifies one
    *form render*, which is what a logical payment attempt is: every real duplicate replays
    the same render, while a genuine second payment requires loading the form again. The
    `NOT NULL UNIQUE` index — not this function's lookup — is what decides a race.

    **Settlement is derived.** Nothing here records which goods receipts this payment
    cleared; `purchasing.selectors.supplier_position` recomputes that through `ledger.walk`
    on every read (BD-1 Option A).
    """
    require_roles(actor, Role.OWNER)

    if not submission_id:
        raise ValidationFailed(
            "A payment submission needs its form identifier. Reload the payment form and "
            "try again.",
            errors=[{"field": "submission_id", "code": "REQUIRED", "message": ""}],
        )
    if payment_date is None:
        raise ValidationFailed(
            "A payment date is required.",
            errors=[{"field": "payment_date", "code": "REQUIRED", "message": ""}],
        )
    if method not in SupplierPayment.Method.values:
        raise ValidationFailed(
            "Unknown payment method.",
            errors=[{"field": "method", "code": "INVALID", "message": str(method)}],
        )
    amount = to_money(amount)
    if amount <= 0:
        raise ValidationFailed(
            "A payment must be greater than zero.",
            errors=[{"field": "amount", "code": "MIN_VALUE", "message": str(amount)}],
        )

    payload = {
        "supplier_id": supplier.pk,
        "amount": amount,
        "payment_date": payment_date,
        "method": method,
        "reference_number": (reference_number or "").strip()[:100],
        "notes": (notes or "").strip(),
    }

    existing = SupplierPayment.objects.filter(submission_id=submission_id).first()
    if existing is not None:
        return _replayed(existing, payload)

    try:
        # **The savepoint is what makes the race survivable.** A check-then-insert on
        # `submission_id` races, and `uq_supplier_payment_submission` is the guarantee.
        # Without the savepoint an IntegrityError would abort the whole transaction and a
        # duplicate click would become a 500 instead of the original receipt.
        with transaction.atomic():
            payment = SupplierPayment.objects.create(
                submission_id=submission_id,
                payment_number=_next_supplier_payment_number(),
                supplier=supplier,
                paid_by=actor if getattr(actor, "pk", None) else None,
                **payload,
            )
    except IntegrityError:
        existing = SupplierPayment.objects.filter(submission_id=submission_id).first()
        if existing is None:  # pragma: no cover - a different constraint fired
            raise
        return _replayed(existing, payload)

    # The liability falls. Negative, because a positive amount increases what we owe
    # (D-PUR-3) and this reduces it. `source_document` resolves to "PAYMENT" through the
    # registry — the equality `ledger.walk` needs for the reversal to annul (U-1).
    record_supplier_entry(
        actor=actor,
        supplier=supplier,
        entry_type=SupplierLedgerEntry.Type.PAYMENT,
        amount=-amount,
        narration=f"Payment {payment.payment_number} ({payment.get_method_display()})",
        entry_date=payment_date,
        source_document=payment,
    )
    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type=_ENTITY_SUPPLIER_PAYMENT,
        entity_id=payment.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state=_payment_audit_state(payment),
    )
    return payment


@transaction.atomic
def reverse_supplier_payment(
    *, actor: Any, payment: SupplierPayment, reason: str, reversal_date: date
) -> SupplierPayment:
    """FR-PUR-012 — reverse a payment that did not stand. Owner only.

    **The original entry is never edited.** A compensating positive `ADJUSTMENT` is appended
    pointing at the same payment, and `ledger.walk` annuls the pair: both leave the walk, so
    the goods receipts this payment had settled **reappear at their original dates** rather
    than as fresh debt dated the reversal. That restoration is the whole point — treating a
    reversal as an ordinary debit would launder aged debt into new debt in a tool whose only
    job is to show which debt is oldest.

    **The lock is real and it locks the row this function mutates.** `reverse_supplier_payment`
    is the only writer of `is_reversed`, so every writer of that state contends on it.
    Without it two concurrent reversals both read `is_reversed = False` and both append a
    compensating entry, crediting the supplier twice.

    **`reversal_date` is caller-supplied and required** (ruling U-4), diverging from
    `receivables.reverse_payment`'s `timezone.localdate()`. It does not affect ageing — the
    pair is annulled whatever its date — but it does decide whether an `as_of` view taken
    between the payment and the reversal still shows the payment settling, which it should.
    """
    require_roles(actor, Role.OWNER)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed(
            "A reversal needs a reason.",
            errors=[{"field": "reason", "code": "REQUIRED", "message": ""}],
        )
    if reversal_date is None:
        raise ValidationFailed(
            "A reversal date is required.",
            errors=[{"field": "reversal_date", "code": "REQUIRED", "message": ""}],
        )

    locked = SupplierPayment.objects.select_for_update().filter(pk=payment.pk).first()
    if locked is None:  # pragma: no cover - the caller just fetched it
        raise ResourceNotFound("That payment no longer exists.")
    if locked.is_reversed:
        return locked  # idempotent: a second reversal is a no-op, not a second credit

    record_supplier_entry(
        actor=actor,
        supplier=locked.supplier,
        entry_type=SupplierLedgerEntry.Type.ADJUSTMENT,
        amount=locked.amount,
        narration=f"Reversal of payment {locked.payment_number}",
        entry_date=reversal_date,
        source_document=locked,
    )

    locked.is_reversed = True
    locked.reversed_reason = reason
    locked.reversed_at = timezone.now()
    locked.reversed_by = actor if getattr(actor, "pk", None) else None
    locked.save(update_fields=["is_reversed", "reversed_reason", "reversed_at", "reversed_by"])

    record_audit(
        action=AuditLog.Action.PAYMENT_REVERSE,
        entity_type=_ENTITY_SUPPLIER_PAYMENT,
        entity_id=locked.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"is_reversed": False},
        after_state={**_payment_audit_state(locked), "reason": reason},
    )
    return locked


def _duplicate_opening(supplier: Supplier) -> ValidationFailed:
    """One message, whether the pre-check or the unique index caught it."""
    return ValidationFailed(
        f"Supplier {supplier.code} already has an opening balance. A supplier has exactly "
        "one, and it cannot be replaced — the ledger is append-only.",
        errors=[
            {"field": "supplier", "code": "DUPLICATE_OPENING", "message": supplier.code}
        ],
    )


@transaction.atomic
def close_purchase_order(
    *, actor: Any, purchase_order: PurchaseOrder, reason: str
) -> PurchaseOrder:
    """FR-PUR-005 — short-close an order the supplier will not complete.

    **The counterpart to `cancel_purchase_order`, and the reason both exist.** Cancellation
    says the order never happened; it is unavailable once stock has arrived, because stock
    that arrived cannot be un-arrived. Closing says *no more will arrive* and leaves every
    receipt, movement and ledger entry standing.
    """
    require_roles(actor, Role.OWNER)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed(
            "A closing reason is required.",
            errors=[{"field": "reason", "code": "REQUIRED", "message": ""}],
        )
    _transition(
        actor=actor,
        purchase_order=purchase_order,
        to_status=PurchaseOrder.Status.CLOSED,
        audit_extra={"reason": reason},
    )
    return purchase_order
