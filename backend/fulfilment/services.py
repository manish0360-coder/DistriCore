"""Fulfilment business rules — the only writer of Delivery.

**Dispatch is the point at which commercial intent becomes physical fact** (M5 §1).
This module writes stock; it writes no ledger entry, because money is owed at the
invoice, not at the loading bay.

Two decisions from `M5_Design_Review.md` are load-bearing here:

* **D-1 / M5-1** — the ISSUE is written at **dispatch**, not at delivery. Stock leaves
  the distributor's control when the goods are loaded, not when a signature is
  obtained. Issuing at delivery would let a stock count taken while the van is out
  overstate on hand, and would let the owner promise goods already on a van.
* **D-8** — credit exposure is re-evaluated **here**, immediately before the movements
  are written, using ``orders.services.evaluate_credit`` unchanged. Exposure at
  confirmation is a prediction; exposure at dispatch is a fact.

Unlike M2, this module **takes a lock**. M2 needed none because appends never contend.
Here the decision to append depends on a prior read — "has this already been
dispatched?" — and a read-then-write across rows needs an anchor. The delivery row is
that anchor.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import ResourceNotFound, ValidationFailed
from core.models import AuditLog, BusinessProfile
from core.permissions import Role, has_role, require_roles
from core.services import record_audit
from fulfilment.models import Delivery
from inventory.models import StockMovement
from inventory.services import record_movement
from orders.models import SalesOrder
from orders.services import CreditLimitExceeded, evaluate_credit, mark_delivered, mark_dispatched

logger = logging.getLogger("districore.fulfilment")


# --------------------------------------------------------------------------- assign
@transaction.atomic
def assign_delivery(
    *,
    actor: Any,
    order: SalesOrder,
    assigned_user: Any,
    client_uuid: uuid_lib.UUID | str | None = None,
) -> Delivery:
    """Create the delivery record for a confirmed order (FR-FUL-001).

    Idempotent on ``client_uuid`` and, independently, on the order: one delivery per
    order is a database fact (``uq_delivery_sales_order``), not a service-layer hope.

    The order is re-read rather than trusted, for the same reason ``issue_invoice``
    re-reads it: a ``SalesOrder`` is mutable, so a caller's instance is a snapshot. This
    one is far less dangerous — a stale instance could at worst create a stray PENDING
    delivery for a cancelled order, and dispatch would then refuse it — but it is the
    same defect, and leaving half a class of bug fixed is how it comes back.
    """
    require_roles(actor, Role.OWNER)

    if client_uuid:
        existing = Delivery.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing

    order = SalesOrder.objects.get(pk=order.pk)

    existing = Delivery.objects.filter(sales_order=order).first()
    if existing is not None:
        return existing

    if order.status != SalesOrder.Status.CONFIRMED:
        raise ValidationFailed(
            "Only a confirmed order can be assigned for delivery.",
            errors=[{"field": "status", "code": "NOT_CONFIRMED", "message": order.status}],
        )
    if not has_role(assigned_user, *Role.INTERNAL):
        raise ValidationFailed(
            "Deliveries are assigned to internal staff only.",
            errors=[{"field": "assigned_user", "code": "NOT_INTERNAL", "message": "role"}],
        )

    delivery = Delivery.objects.create(
        sales_order=order,
        client_uuid=client_uuid or None,
        assigned_user=assigned_user,
        status=Delivery.Status.PENDING,
    )
    if order.assigned_user_id != getattr(assigned_user, "pk", None):
        order.assigned_user = assigned_user
        order.save(update_fields=["assigned_user", "updated_at"])

    record_audit(
        action=AuditLog.Action.UPDATE,
        entity_type="delivery",
        entity_id=delivery.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={
            "order_number": order.order_number,
            "assigned_user_id": getattr(assigned_user, "pk", None),
            "status": delivery.status,
        },
    )
    return delivery


# --------------------------------------------------------------------------- dispatch
@transaction.atomic
def dispatch_delivery(*, actor: Any, delivery: Delivery, override_reason: str = "") -> Delivery:
    """Send the goods. **Writes the ISSUE movements** (M5-1, FR-FUL-003).

    Order of operations matters and is not incidental:

    1. lock the delivery row — the anchor for "has this already gone out?";
    2. re-evaluate credit (D-8) **before anything is written**, so a refusal costs
       nothing and leaves no partial state;
    3. write one ISSUE per line, each carrying ``source_document = Delivery``;
    4. move the order to ``DISPATCHED`` through the orders state machine.

    All in one transaction. A dispatch that issued some lines and not others would be a
    stock ledger that cannot be reconciled against any document.
    """
    require_roles(actor, Role.OWNER)

    locked = Delivery.objects.select_for_update().filter(pk=delivery.pk).first()
    if locked is None:  # pragma: no cover - the caller just fetched it
        raise ResourceNotFound("That delivery no longer exists.")

    # F-5 / idempotent: a retried dispatch returns the original rather than issuing
    # stock a second time.
    if locked.dispatched_at is not None:
        return locked

    order = locked.sales_order
    if order.status != SalesOrder.Status.CONFIRMED:
        raise ValidationFailed(
            "Only a confirmed order can be dispatched.",
            errors=[{"field": "status", "code": "NOT_CONFIRMED", "message": order.status}],
        )

    _apply_dispatch_credit_policy(actor=actor, order=order, override_reason=override_reason)

    lines = list(order.lines.select_related("product").all())
    if not lines:  # pragma: no cover - place_order refuses an empty order
        raise ValidationFailed(
            "An order with no lines cannot be dispatched.",
            errors=[{"field": "lines", "code": "REQUIRED", "message": "0 lines"}],
        )
    for line in lines:
        record_movement(
            actor=actor,
            product=line.product,
            quantity=-abs(line.quantity),
            movement_type=StockMovement.Type.ISSUE,
            source_document=locked,
            notes=f"Dispatch of {order.order_number} line {line.line_number}",
        )

    locked.dispatched_at = timezone.now()
    locked.save(update_fields=["dispatched_at", "updated_at"])
    mark_dispatched(actor=actor, order=order)

    record_audit(
        action=AuditLog.Action.ISSUE,
        entity_type="delivery",
        entity_id=locked.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={
            "order_number": order.order_number,
            "line_count": len(lines),
            "dispatched_at": locked.dispatched_at.isoformat(),
        },
    )
    logger.info(
        "delivery_dispatched",
        extra={"delivery_id": locked.pk, "order_id": order.pk, "lines": len(lines)},
    )
    return locked


def _apply_dispatch_credit_policy(*, actor: Any, order: SalesOrder, override_reason: str) -> None:
    """D-8 — the credit gate that actually matters.

    The *measurement* is ``orders.services.evaluate_credit``, unchanged and shared with
    order capture. A second implementation could drift, and a credit rule that differs
    by caller is worse than no credit rule (the PO-6 discipline applied to credit).

    The *policy* is deliberately different from capture's. At capture a breach is a
    warning on a promise that costs nothing to withdraw. Here the van is loaded, so:

    * ``WARN`` mode records the breach and proceeds;
    * ``BLOCK`` mode refuses **unless the owner supplies a reason**, which is audited.

    Refusing outright with no override would teach staff to send the goods and record
    nothing — the ADR-0006 failure — and an unrecorded dispatch is worse than a
    recorded over-limit one.
    """
    check = evaluate_credit(order=order)
    if not check.breached:
        return

    override_reason = (override_reason or "").strip()
    if check.mode == BusinessProfile.CreditMode.BLOCK and not override_reason:
        raise CreditLimitExceeded(
            f"Dispatch would exceed the credit limit for customer {order.customer.code}. "
            f"Exposure {check.exposure_amount} against limit {check.credit_limit_amount}."
        )

    order.credit_warning_shown = True
    fields = ["credit_warning_shown", "updated_at"]
    if override_reason:
        order.credit_override_by = actor if getattr(actor, "pk", None) else None
        order.credit_override_at = timezone.now()
        fields += ["credit_override_by", "credit_override_at"]
    order.save(update_fields=fields)

    record_audit(
        action=AuditLog.Action.CREDIT_OVERRIDE,
        entity_type="sales_order",
        entity_id=order.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={
            "order_number": order.order_number,
            "at": "DISPATCH",
            "exposure_amount": check.exposure_amount,
            "credit_limit_amount": check.credit_limit_amount,
            "reason": override_reason,
        },
    )


# --------------------------------------------------------------------------- outcome
@transaction.atomic
def complete_delivery(
    *,
    actor: Any,
    delivery: Delivery,
    recipient_name: str = "",
    delivered_at: Any = None,
    latitude: Decimal | None = None,
    longitude: Decimal | None = None,
    photo_media: Any = None,
    device_id: str = "",
    client_uuid: uuid_lib.UUID | str | None = None,
) -> Delivery:
    """Record a successful handover (FR-FUL-006). **Writes no stock.**

    The goods left at dispatch. Delivery confirms where they ended up; it does not move
    them again.

    **Idempotent on ``client_uuid`` (TD-39, `05` §6 and §9.4).** The key is stored in
    ``outcome_client_uuid``, which is *not* ``Delivery.client_uuid`` — that one identifies
    the assignment. Omitting the key leaves every prior behaviour exactly as it was.
    """
    require_roles(actor, *Role.INTERNAL)

    replay = _replay_of(client_uuid)
    if replay is not None:
        return replay  # I-4: the original resource, not a duplicate and not an error

    locked = _lock_dispatched(delivery)

    if locked.status != Delivery.Status.PENDING:
        return locked  # F-5: completing twice is a no-op, not a second delivery

    locked.outcome_client_uuid = _as_uuid(client_uuid)
    locked.status = Delivery.Status.DELIVERED
    locked.delivered_at = delivered_at or timezone.now()
    locked.recipient_name = recipient_name[:200]
    locked.latitude = latitude
    locked.longitude = longitude
    locked.photo_media = photo_media
    locked.device_id = device_id[:64]
    locked.synced_at = timezone.now()
    try:
        # The savepoint matters, exactly as in `record_payment`: a check-then-write on
        # `outcome_client_uuid` races, and `delivery_outcome_client_uuid_key` is the
        # guarantee (I-6). Without it an IntegrityError would abort the caller's whole
        # transaction, turning a legitimate retry into a 500 instead of the original row.
        with transaction.atomic():
            locked.save(
                update_fields=[
                    "outcome_client_uuid",
                    "status",
                    "delivered_at",
                    "recipient_name",
                    "latitude",
                    "longitude",
                    "photo_media",
                    "device_id",
                    "synced_at",
                    "updated_at",
                ]
            )
    except IntegrityError:
        if not client_uuid:
            raise
        replay = _replay_of(client_uuid)
        if replay is None:  # pragma: no cover - a different constraint fired
            raise
        return replay
    mark_delivered(actor=actor, order=locked.sales_order)

    record_audit(
        action=AuditLog.Action.UPDATE,
        entity_type="delivery",
        entity_id=locked.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"status": Delivery.Status.PENDING},
        after_state={
            "status": locked.status,
            "recipient_name": locked.recipient_name,
            "delivered_at": locked.delivered_at.isoformat(),
        },
    )
    return locked


@transaction.atomic
def fail_delivery(
    *,
    actor: Any,
    delivery: Delivery,
    reason: str,
    device_id: str = "",
    client_uuid: uuid_lib.UUID | str | None = None,
) -> Delivery:
    """Record a failed handover and **bring the goods back** (M5-9, Scenario B).

    Writes a RETURN movement per line. It does **not** delete or edit the ISSUE: two rows
    then record what physically happened — the goods left, and the goods came back — and
    the ledger keeps its property of explaining every divergence.

    It writes **no credit note and touches no invoice.** Whether the customer should be
    billed for goods they never received is a separate commercial decision, taken
    separately, because the goods may simply be redelivered tomorrow. That separation is
    what makes the double-restock of Scenario F impossible.

    **Idempotent on ``client_uuid`` (TD-39).** The identity is claimed *before* the RETURN
    movements are written, not after: if the claim loses a race, the savepoint rolls back
    and the goods are never returned twice. Writing the movements first and the key second
    would leave a duplicate restock behind at exactly the moment the key told us not to.
    """
    require_roles(actor, *Role.INTERNAL)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed(
            "A failed delivery needs a reason.",
            errors=[{"field": "reason", "code": "REQUIRED", "message": ""}],
        )

    replay = _replay_of(client_uuid)
    if replay is not None:
        return replay  # I-4

    locked = _lock_dispatched(delivery)
    if locked.status != Delivery.Status.PENDING:
        return locked  # F-6: failing twice must not return the stock a second time

    locked.outcome_client_uuid = _as_uuid(client_uuid)
    locked.status = Delivery.Status.FAILED
    locked.failure_reason = reason
    locked.device_id = device_id[:64]
    locked.synced_at = timezone.now()
    try:
        with transaction.atomic():
            locked.save(
                update_fields=[
                    "outcome_client_uuid",
                    "status",
                    "failure_reason",
                    "device_id",
                    "synced_at",
                    "updated_at",
                ]
            )
    except IntegrityError:
        if not client_uuid:
            raise
        replay = _replay_of(client_uuid)
        if replay is None:  # pragma: no cover - a different constraint fired
            raise
        return replay

    # Only now, with the outcome identity durably claimed, does stock move.
    for line in locked.sales_order.lines.select_related("product").all():
        record_movement(
            actor=actor,
            product=line.product,
            quantity=abs(line.quantity),
            movement_type=StockMovement.Type.RETURN,
            source_document=locked,
            notes=f"Failed delivery of {locked.sales_order.order_number}: {reason}"[:500],
        )

    record_audit(
        action=AuditLog.Action.UPDATE,
        entity_type="delivery",
        entity_id=locked.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"status": Delivery.Status.PENDING},
        after_state={"status": locked.status, "failure_reason": reason},
    )
    logger.info("delivery_failed", extra={"delivery_id": locked.pk, "reason": reason})
    return locked


def _as_uuid(client_uuid: uuid_lib.UUID | str | None) -> uuid_lib.UUID | None:
    """Normalise to a UUID, or ``None``. A blank string is not an identity."""
    if not client_uuid:
        return None
    if isinstance(client_uuid, uuid_lib.UUID):
        return client_uuid
    return uuid_lib.UUID(str(client_uuid))


def _replay_of(client_uuid: uuid_lib.UUID | str | None) -> Delivery | None:
    """The delivery this outcome key already belongs to, if any (TD-39, I-4).

    A fast path, **not the guarantee** — two concurrent first-attempts both miss it. The
    unique constraint is what makes the loser recoverable; this only spares the common
    case a row lock it does not need.
    """
    key = _as_uuid(client_uuid)
    if key is None:
        return None
    return Delivery.objects.filter(outcome_client_uuid=key).first()


def _lock_dispatched(delivery: Delivery) -> Delivery:
    """Lock the delivery row and refuse an outcome before the goods have left."""
    locked = (
        Delivery.objects.select_for_update()
        .select_related("sales_order")
        .filter(pk=delivery.pk)
        .first()
    )
    if locked is None:  # pragma: no cover - the caller just fetched it
        raise ResourceNotFound("That delivery no longer exists.")
    if locked.dispatched_at is None:
        raise ValidationFailed(
            "This delivery has not been dispatched yet.",
            errors=[{"field": "status", "code": "NOT_DISPATCHED", "message": locked.status}],
        )
    return locked
