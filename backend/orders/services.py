"""Order business rules — the only writer of SalesOrder and SalesOrderLine.

**This module creates no StockMovement and no ledger entry** (M3-6). An order is
commercial intent; stock is issued at dispatch (M5) and the receivable begins at the
invoice (M5). A boundary test proves it rather than trusting this docstring.

Every state-changing operation is audited, because an order is **mutable** and the audit
log is therefore the only record of what it used to say (R-3).
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from core.exceptions import PermissionDenied, ValidationFailed
from core.fields import to_money, to_quantity
from core.models import AuditLog, BusinessProfile
from core.permissions import Role, has_role, require_roles
from core.services import get_business_profile, record_audit
from orders.models import SalesOrder, SalesOrderLine
from orders.selectors import available_credit, credit_exposure
from pricing.services import compute_line

logger = logging.getLogger("districore.orders")

# M3-4: the state machine, declared once. A transition absent from this map is rejected.
# DISPATCHED and DELIVERED are reachable only from fulfilment (M5); M3 owns no path to
# them, which is how the M2 boundary is kept structurally rather than by convention.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    SalesOrder.Status.PLACED: frozenset({SalesOrder.Status.CONFIRMED, SalesOrder.Status.CANCELLED}),
    SalesOrder.Status.CONFIRMED: frozenset(
        {SalesOrder.Status.DISPATCHED, SalesOrder.Status.CANCELLED}
    ),
    SalesOrder.Status.DISPATCHED: frozenset({SalesOrder.Status.DELIVERED}),
    SalesOrder.Status.DELIVERED: frozenset(),
    SalesOrder.Status.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class CreditCheck:
    """The outcome of evaluating an order against a customer's limit (D-1, DV-9)."""

    breached: bool
    mode: str
    credit_limit_amount: Decimal
    exposure_amount: Decimal
    available_amount: Decimal


# --------------------------------------------------------------------------- capture
@transaction.atomic
def place_order(
    *,
    actor: Any,
    customer: Any,
    lines: list[dict[str, Any]],
    source: str = SalesOrder.Source.WEB,
    client_uuid: uuid_lib.UUID | str | None = None,
    expected_delivery_date: Any = None,
    notes: str = "",
    override_credit: bool = False,
) -> SalesOrder:
    """Capture an order.

    Idempotent on ``client_uuid`` (M3-5, BR-012): re-posting an accepted key returns the
    original order rather than creating a duplicate.
    """
    _require_capture_permission(actor, customer)

    if client_uuid:
        existing = SalesOrder.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing

    if not customer.is_active:
        raise ValidationFailed(
            "That customer is deactivated.",
            errors=[{"field": "customer", "code": "INACTIVE", "message": customer.code}],
        )
    if not lines:
        raise ValidationFailed(
            "An order needs at least one line.",
            errors=[{"field": "lines", "code": "REQUIRED", "message": "0 lines"}],
        )

    order = SalesOrder(
        order_number="",
        client_uuid=client_uuid or None,
        customer=customer,
        status=SalesOrder.Status.PLACED,
        source=source,
        order_date=timezone.localdate(),
        expected_delivery_date=expected_delivery_date,
        notes=notes,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    order.save()
    # D-3: derived from the primary key, so gaps are possible and no lock is taken. The
    # gapless, row-locked series belongs to invoices, where the law requires it.
    order.order_number = f"SO-{order.pk:08d}"
    order.save(update_fields=["order_number", "updated_at"])

    _replace_lines(actor=actor, order=order, lines=lines)
    check = _apply_credit_policy(actor=actor, order=order, override=override_credit)

    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type="sales_order",
        entity_id=order.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={
            "order_number": order.order_number,
            "customer": customer.code,
            "total_amount": order.total_amount,
            "status": order.status,
        },
    )
    logger.info(
        "order_placed",
        extra={
            "order_id": order.pk,
            "customer": customer.code,
            "total": str(order.total_amount),
            "credit_breached": check.breached,
        },
    )
    return order


@transaction.atomic
def amend_order(*, actor: Any, order: SalesOrder, lines: list[dict[str, Any]]) -> SalesOrder:
    """Replace an order's lines and re-run every rule (FR-ORD-031).

    Partial re-evaluation is not offered: pricing, discount bounds, totals and the credit
    check are recomputed together or not at all.
    """
    _require_capture_permission(actor, order.customer)
    if not order.is_editable:
        raise ValidationFailed(
            f"An order cannot be amended once it is {order.get_status_display().lower()}.",
            errors=[{"field": "status", "code": "NOT_EDITABLE", "message": order.status}],
        )
    before = _totals_snapshot(order)
    _replace_lines(actor=actor, order=order, lines=lines)
    _apply_credit_policy(actor=actor, order=order, override=False)
    record_audit(
        action=AuditLog.Action.UPDATE,
        entity_type="sales_order",
        entity_id=order.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state=before,
        after_state=_totals_snapshot(order),
    )
    return order


@transaction.atomic
def apply_line_discount(
    *, actor: Any, order: SalesOrder, line: SalesOrderLine, discount_amount: Decimal
) -> SalesOrder:
    """Apply a bounded manual discount to one line (FR-PRC-017/018).

    Audited separately from the order update: a discount is a margin decision, and PO-6
    exists because manual discounting is where margin leaks.
    """
    require_roles(actor, Role.OWNER)
    if not order.is_editable:
        raise ValidationFailed(
            "This order can no longer be discounted.",
            errors=[{"field": "status", "code": "NOT_EDITABLE", "message": order.status}],
        )

    amounts = compute_line(
        product=line.product,
        quantity=line.quantity,
        customer=order.customer,
        discount_amount=discount_amount,
    )
    previous = line.discount_amount
    line.discount_amount = amounts.discount_amount
    line.taxable_amount = amounts.taxable_amount
    line.tax_amount = amounts.tax_amount
    line.line_total = amounts.line_total
    line.discount_by = actor if getattr(actor, "pk", None) else None
    line.save(
        update_fields=[
            "discount_amount",
            "taxable_amount",
            "tax_amount",
            "line_total",
            "discount_by",
        ]
    )
    _recalculate_totals(order)

    record_audit(
        action=AuditLog.Action.DISCOUNT_APPLIED,
        entity_type="sales_order_line",
        entity_id=line.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"discount_amount": previous},
        after_state={
            "discount_amount": amounts.discount_amount,
            "order_number": order.order_number,
        },
    )
    return order


# --------------------------------------------------------------------------- lifecycle
@transaction.atomic
def confirm_order(*, actor: Any, order: SalesOrder) -> SalesOrder:
    """Accept the order. **Writes no stock** — confirmation is agreement, not dispatch."""
    require_roles(actor, Role.OWNER)
    _transition(actor=actor, order=order, to_status=SalesOrder.Status.CONFIRMED)
    return order


@transaction.atomic
def cancel_order(*, actor: Any, order: SalesOrder, reason: str) -> SalesOrder:
    """Cancel before dispatch. Nothing physical has happened, so nothing is reversed."""
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed(
            "A cancellation needs a reason.",
            errors=[{"field": "reason", "code": "REQUIRED", "message": ""}],
        )
    if has_role(actor, Role.RETAILER) and not has_role(actor, *Role.INTERNAL):
        if order.customer_id != getattr(actor, "customer_id", None):
            raise PermissionDenied("You may only cancel your own orders.")
    else:
        require_roles(actor, Role.OWNER)

    order.cancelled_reason = reason
    order.cancelled_at = timezone.now()
    order.cancelled_by = actor if getattr(actor, "pk", None) else None
    _transition(
        actor=actor,
        order=order,
        to_status=SalesOrder.Status.CANCELLED,
        extra_fields=["cancelled_reason", "cancelled_at", "cancelled_by"],
        audit_extra={"reason": reason},
    )
    return order


def _transition(
    *,
    actor: Any,
    order: SalesOrder,
    to_status: str,
    extra_fields: list[str] | None = None,
    audit_extra: dict[str, Any] | None = None,
) -> None:
    """The single place a status changes (M3-4).

    A transition not in ``ALLOWED_TRANSITIONS`` is rejected. The map is enforced here, in
    CORE, and never exposed as a settable field — a client that could PATCH ``status``
    would hold the state machine.
    """
    from_status = order.status
    if to_status not in ALLOWED_TRANSITIONS.get(from_status, frozenset()):
        raise ValidationFailed(
            f"An order cannot go from {from_status} to {to_status}.",
            errors=[
                {
                    "field": "status",
                    "code": "INVALID_TRANSITION",
                    "message": f"{from_status}->{to_status}",
                }
            ],
        )
    order.status = to_status
    order.save(update_fields=["status", "updated_at", *(extra_fields or [])])

    action_by_status: dict[str, str] = {
        SalesOrder.Status.CONFIRMED: AuditLog.Action.CONFIRM,
        SalesOrder.Status.CANCELLED: AuditLog.Action.CANCEL,
    }
    action = action_by_status.get(to_status, AuditLog.Action.UPDATE)
    record_audit(
        action=action,
        entity_type="sales_order",
        entity_id=order.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"status": from_status},
        after_state={"status": to_status, **(audit_extra or {})},
    )


# --------------------------------------------------------------------------- credit
def evaluate_credit(*, order: SalesOrder) -> CreditCheck:
    """Compare exposure against the limit (D-1, FR-ORD-020). Reads only."""
    profile: BusinessProfile = get_business_profile()
    customer = order.customer
    exposure = credit_exposure(customer)
    limit = to_money(customer.credit_limit_amount)
    return CreditCheck(
        breached=limit > 0 and exposure > limit,
        mode=profile.credit_limit_mode,
        credit_limit_amount=limit,
        exposure_amount=to_money(exposure),
        available_amount=to_money(available_credit(customer)),
    )


def _apply_credit_policy(*, actor: Any, order: SalesOrder, override: bool) -> CreditCheck:
    """DV-9: warn and let the owner override, or refuse outright.

    A credit limit of zero means "not set" and is never treated as a breach — the client
    confirmed the owner decides limits, and an unset limit must not block trading.
    """
    check = evaluate_credit(order=order)
    if not check.breached:
        return check

    if check.mode == BusinessProfile.CreditMode.BLOCK:
        raise CreditLimitExceeded(
            f"Order exceeds available credit of {check.available_amount} "
            f"for customer {order.customer.code}."
        )

    order.credit_warning_shown = True
    fields = ["credit_warning_shown", "updated_at"]
    if override and has_role(actor, Role.OWNER):
        order.credit_override_by = actor
        order.credit_override_at = timezone.now()
        fields += ["credit_override_by", "credit_override_at"]
    order.save(update_fields=fields)

    if order.credit_override_at is not None:
        record_audit(
            action=AuditLog.Action.CREDIT_OVERRIDE,
            entity_type="sales_order",
            entity_id=order.pk,
            actor=actor,
            surface=AuditLog.Surface.WEB,
            after_state={
                "order_number": order.order_number,
                "exposure_amount": check.exposure_amount,
                "credit_limit_amount": check.credit_limit_amount,
            },
        )
    return check


class CreditLimitExceeded(ValidationFailed):
    code, title, status = "CREDIT_LIMIT_EXCEEDED", "Credit limit exceeded", 409


# --------------------------------------------------------------------------- internals
def _require_capture_permission(actor: Any, customer: Any) -> None:
    """Owner captures any order; a retailer captures only their own (05 §8).

    Salesmen do **not** create orders in Edition 1 — field order capture was deferred
    (DV-1, 02A §5), which is what makes M9 sync an outbox rather than a reconciliation
    protocol.
    """
    if has_role(actor, Role.OWNER):
        return
    if has_role(actor, Role.RETAILER):
        if getattr(actor, "customer_id", None) == customer.pk:
            return
        raise PermissionDenied("You may only order for your own shop.")
    raise PermissionDenied("This action requires the owner or the shop's own login.")


def _entered_quantity(raw: dict[str, Any], product: Any) -> tuple[Decimal, Decimal | None]:
    """Resolve one line's quantity into (base_units, pack_quantity_or_None).

    **The caller states exactly one of ``quantity`` (base units) or ``pack_quantity``
    (packs).** Not a number plus a unit flag: that is two fields encoding one fact, they
    can disagree, and they did — an ``in_packs=True`` with no ``pack_quantity`` produced
    ``Decimal("None")``.

    Ambiguous input is refused rather than coerced. A silently guessed unit is how a
    2-pack order becomes a 2-piece order (M3-2).
    """
    base = raw.get("quantity")
    packs = raw.get("pack_quantity")

    if base is not None and packs is not None:
        raise ValidationFailed(
            "Give a quantity in base units or in packs, not both.",
            errors=[{"field": "quantity", "code": "AMBIGUOUS_UNIT", "message": product.code}],
        )
    if base is None and packs is None:
        raise ValidationFailed(
            "A line needs a quantity.",
            errors=[{"field": "quantity", "code": "REQUIRED", "message": product.code}],
        )

    if packs is not None:
        entered = to_quantity(packs)
        return product.to_base_units(entered, in_packs=True), entered
    return product.to_base_units(base), None


def _replace_lines(*, actor: Any, order: SalesOrder, lines: list[dict[str, Any]]) -> None:
    """Rebuild every line, resolving price and computing money at line level (M3-8)."""
    order.lines.all().delete()
    for index, raw in enumerate(lines, start=1):
        product = raw["product"]
        if not product.is_active:
            raise ValidationFailed(
                f"Product {product.code} is no longer available.",
                errors=[{"field": "product", "code": "INACTIVE", "message": product.code}],
            )

        # M3-2: stored quantity is ALWAYS base units; pack_quantity records what the
        # user actually typed, so a bill can be explained back to them.
        quantity, pack_quantity = _entered_quantity(raw, product)
        if quantity <= 0:
            raise ValidationFailed(
                "Quantity must be greater than zero.",
                errors=[{"field": "quantity", "code": "MIN_VALUE", "message": str(quantity)}],
            )

        amounts = compute_line(
            product=product,
            quantity=quantity,
            customer=order.customer,
            discount_amount=raw.get("discount_amount", 0),
        )
        SalesOrderLine.objects.create(
            sales_order=order,
            line_number=index,
            product=product,
            # M3-1: snapshots. A later price change must not alter this row.
            product_code=product.code,
            product_name=product.name,
            unit_name=product.unit_name,
            unit_price=amounts.unit_price,
            tax_rate_percent=amounts.tax_rate_percent,
            pack_size_snapshot=product.pack_size,
            quantity=quantity,
            pack_quantity=pack_quantity,
            discount_amount=amounts.discount_amount,
            discount_by=(
                actor if amounts.discount_amount > 0 and getattr(actor, "pk", None) else None
            ),
            taxable_amount=amounts.taxable_amount,
            tax_amount=amounts.tax_amount,
            line_total=amounts.line_total,
        )
    _recalculate_totals(order)


def _recalculate_totals(order: SalesOrder) -> None:
    """Sum the lines onto the order (M3-7).

    Totals are summed from **already-rounded line values** (M3-8): rounding once at the
    end would give a different figure, and the M5 invoice must agree to the paisa.
    """
    subtotal = discount = tax = total = Decimal("0.00")
    for line in order.lines.all():
        subtotal += to_money(line.unit_price * line.quantity)
        discount += line.discount_amount
        tax += line.tax_amount
        total += line.line_total
    order.subtotal_amount = to_money(subtotal)
    order.discount_amount = to_money(discount)
    order.tax_amount = to_money(tax)
    order.total_amount = to_money(total)
    order.save(
        update_fields=[
            "subtotal_amount",
            "discount_amount",
            "tax_amount",
            "total_amount",
            "updated_at",
        ]
    )


def _totals_snapshot(order: SalesOrder) -> dict[str, Any]:
    return {
        "subtotal_amount": order.subtotal_amount,
        "discount_amount": order.discount_amount,
        "tax_amount": order.tax_amount,
        "total_amount": order.total_amount,
    }
