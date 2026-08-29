"""Stock ledger business rules.

**This module is the only writer of StockMovement** (03 §2.2, N-02). Nothing else in the
codebase may create one — that single constraint is what makes BR-004 and BR-007
enforceable rather than aspirational.

Three decisions from `M2_Design_Review.md` are implemented here and are load-bearing:

* **D-1** — the default lot is created lazily, select-then-upsert: one query on the hot
  path, no savepoint, race-free under the ``uq_stock_lot`` constraint.
* **D-2** — no locks. Negative on hand is permitted and reported, never blocked. M2 has
  no deadlock surface because it takes no locks at all.
* **D-3** — a movement is audited **if and only if** its type is ``ADJUSTMENT``.
  Receipts, issues, returns and opening balances are routine: the movement row already
  carries actor, timestamp, reason and immutability, so an audit row would duplicate it.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db import models, transaction
from django.utils import timezone

from core.exceptions import ValidationFailed
from core.fields import to_quantity
from core.models import AuditLog
from core.permissions import Role, require_roles
from core.services import record_audit
from inventory.models import ReasonCode, StockLocation, StockLot, StockMovement

logger = logging.getLogger("districore.inventory")

# --------------------------------------------------------------------------------
# R-2 — permitted source documents.
#
# 04 T-13 relaxes D-06: source_document_type/id carry no foreign key, because they point
# at four different tables. The compensating control is this registry plus the rule that
# services accept a validated model INSTANCE, never a raw (type, id) pair. A typo cannot
# produce an orphan the database is unable to catch.
#
# EMPTY IN M2 BY DESIGN. Stock enters V1 through reason-coded receipts (DV-6); deliveries
# arrive in M5 and register `fulfilment.Delivery` here. Until then every movement is
# explained by a reason code, and any source_document is rejected.
# --------------------------------------------------------------------------------
SOURCE_DOCUMENT_REGISTRY: dict[type[models.Model], str] = {}


def _resolve_source(document: Any) -> tuple[str, int | None]:
    """Validate a source document instance and return its (type, id) pair.

    Refuses anything that is not a persisted instance of a registered model. This is the
    whole of R-2: the caller must possess the thing, not merely name it.
    """
    if document is None:
        return "", None
    model = type(document)
    if model not in SOURCE_DOCUMENT_REGISTRY:
        raise ValidationFailed(
            f"{model.__name__} is not a permitted stock source document.",
            errors=[
                {
                    "field": "source_document",
                    "code": "UNREGISTERED_SOURCE",
                    "message": model.__name__,
                }
            ],
        )
    if getattr(document, "pk", None) is None:
        raise ValidationFailed(
            "A stock source document must be saved before it can be referenced.",
            errors=[{"field": "source_document", "code": "UNSAVED", "message": model.__name__}],
        )
    return SOURCE_DOCUMENT_REGISTRY[model], document.pk


# --------------------------------------------------------------------------- structure
def default_location() -> StockLocation:
    """The single seeded location (M2-1). V1 exposes no selection."""
    location = StockLocation.objects.filter(is_default=True, is_active=True).first()
    if location is None:  # pragma: no cover - migration 0004 guarantees this
        raise ValidationFailed("No default stock location is configured.")
    return location


def default_lot_for(product: Any) -> StockLot:
    """The implicit default lot for a product, created on demand (D-1, M2-2).

    Select first — after the product's first movement this is one query and always hits.
    On miss, upsert: ``update_conflicts`` compiles to ``ON CONFLICT ... DO UPDATE ...
    RETURNING``, which is race-free without a savepoint and returns the row even when a
    concurrent writer won.
    """
    lot = StockLot.objects.filter(product=product, lot_code="DEFAULT").first()
    if lot is not None:
        return lot

    (lot,) = StockLot.objects.bulk_create(
        [StockLot(product=product, lot_code="DEFAULT", is_default=True)],
        update_conflicts=True,
        update_fields=["is_default"],
        unique_fields=["product", "lot_code"],
    )
    return lot


# --------------------------------------------------------------------------- writers
@transaction.atomic
def record_movement(
    *,
    actor: Any,
    product: Any,
    quantity: Decimal | str | int,
    movement_type: str,
    reason_code: ReasonCode | None = None,
    source_document: Any = None,
    occurred_at: Any = None,
    notes: str = "",
    location: StockLocation | None = None,
) -> StockMovement:
    """Append one movement to the ledger. The single write path.

    Deliberately takes **no lock** (D-2). Two concurrent movements on the same product do
    not contend: appends never conflict, and ``SUM`` sees both. That is why the ledger is
    concurrency-safe by construction rather than by defence.
    """
    quantity = to_quantity(quantity)
    if quantity == 0:
        raise ValidationFailed(
            "A stock movement cannot be zero.",
            errors=[{"field": "quantity", "code": "ZERO", "message": "0"}],
        )
    if movement_type not in StockMovement.Type.values:
        raise ValidationFailed(
            "Unknown movement type.",
            errors=[{"field": "movement_type", "code": "INVALID", "message": str(movement_type)}],
        )

    source_type, source_id = _resolve_source(source_document)

    # BR-007 / M2-8, checked here so the caller gets a usable error rather than an
    # IntegrityError. The database constraint remains the guarantee.
    if source_id is None and reason_code is None:
        raise ValidationFailed(
            "A stock movement needs a source document or a reason code.",
            errors=[{"field": "reason_code", "code": "REQUIRED", "message": "BR-007"}],
        )
    if reason_code is not None and not reason_code.is_active:
        raise ValidationFailed(
            "That reason code is no longer active.",
            errors=[{"field": "reason_code", "code": "INACTIVE", "message": reason_code.code}],
        )
    _check_direction(reason_code, quantity)

    movement = StockMovement(
        product=product,
        location=location or default_location(),
        lot=default_lot_for(product),
        quantity=quantity,
        movement_type=movement_type,
        source_document_type=source_type,
        source_document_id=source_id,
        reason_code=reason_code,
        occurred_at=occurred_at or timezone.now(),
        notes=notes,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    movement.save()

    # D-3, Option A: audit if and only if the movement is discretionary.
    if movement_type == StockMovement.Type.ADJUSTMENT:
        record_audit(
            action=AuditLog.Action.STOCK_ADJUST,
            entity_type="stock_movement",
            entity_id=movement.pk,
            actor=actor,
            surface=AuditLog.Surface.WEB,
            after_state={
                "product": product.code,
                "quantity": quantity,
                "reason": reason_code.code if reason_code else None,
                "notes": notes,
            },
        )

    logger.info(
        "stock_movement",
        extra={
            "movement_id": movement.pk,
            "product": product.code,
            "quantity": str(quantity),
            "type": movement_type,
        },
    )
    return movement


def receive_stock(
    *,
    actor: Any,
    product: Any,
    quantity: Decimal | str | int,
    reason_code: ReasonCode | None = None,
    **kw: Any,
) -> StockMovement:
    """Goods in. Always positive (M2-11).

    Owner only in V1: there is no separate warehouse role (05 §8 defines four roles, and
    the client confirmed one person does everything).

    **`reason_code` became optional at D5 Stage 3 (D-PUR-10), and this is a seam correction
    rather than a new feature.** BR-007 has always been *"a stock movement needs a source
    document **or** a reason code"*, and `record_movement` below has always enforced exactly
    that. This wrapper was narrower than the thing it wraps: with a required `ReasonCode` a
    document-backed receipt could not be expressed through it at all, so a goods receipt would
    have had to call `record_movement` directly and skip the owner check above.

    **Every existing caller is unaffected** — all of them pass a reason code. Callers that
    pass neither still fail, in `record_movement`, with BR-007's own message.
    """
    require_roles(actor, Role.OWNER)
    quantity = abs(to_quantity(quantity))
    return record_movement(
        actor=actor,
        product=product,
        quantity=quantity,
        movement_type=StockMovement.Type.RECEIPT,
        reason_code=reason_code,
        **kw,
    )


def issue_stock(
    *, actor: Any, product: Any, quantity: Decimal | str | int, **kw: Any
) -> StockMovement:
    """Goods out. Always negative (M2-11).

    Takes no lock and does not check availability: negative on hand is permitted and
    reported (D-2, ADR-0006).
    """
    require_roles(actor, Role.OWNER)
    quantity = -abs(to_quantity(quantity))
    return record_movement(
        actor=actor,
        product=product,
        quantity=quantity,
        movement_type=StockMovement.Type.ISSUE,
        **kw,
    )


def adjust_stock(
    *,
    actor: Any,
    product: Any,
    quantity: Decimal | str | int,
    reason_code: ReasonCode,
    notes: str = "",
    **kw: Any,
) -> StockMovement:
    """A discretionary correction. Signed either way, reason code mandatory, **audited**."""
    require_roles(actor, Role.OWNER)
    return record_movement(
        actor=actor,
        product=product,
        quantity=quantity,
        movement_type=StockMovement.Type.ADJUSTMENT,
        reason_code=reason_code,
        notes=notes,
        **kw,
    )


# The movement types a human may write directly. RETURN and OPENING are produced by
# other milestones' services, never by a manual API call.
WRITABLE_MOVEMENT_TYPES: tuple[str, ...] = (
    StockMovement.Type.RECEIPT,
    StockMovement.Type.ISSUE,
    StockMovement.Type.ADJUSTMENT,
)


def record_manual_movement(
    *,
    actor: Any,
    product: Any,
    quantity: Decimal | str | int,
    movement_type: str,
    reason_code: ReasonCode,
    notes: str = "",
) -> StockMovement:
    """Dispatch a manually entered movement to the correct writer.

    The sign rule per type (M2-11) belongs here, not in a view: a delivery layer that
    decides which service to call is a delivery layer holding a business rule (N-01).
    """
    if movement_type not in WRITABLE_MOVEMENT_TYPES:
        raise ValidationFailed(
            "That movement type cannot be entered manually.",
            errors=[{"field": "movement_type", "code": "NOT_WRITABLE", "message": movement_type}],
        )
    common = {
        "actor": actor,
        "product": product,
        "quantity": quantity,
        "reason_code": reason_code,
        "notes": notes,
    }
    if movement_type == StockMovement.Type.RECEIPT:
        return receive_stock(**common)
    if movement_type == StockMovement.Type.ISSUE:
        return issue_stock(**common)
    return adjust_stock(**common)


def _check_direction(reason_code: ReasonCode | None, quantity: Decimal) -> None:
    """A reason code declares which way it may move stock (04 T-08)."""
    if reason_code is None:
        return
    if reason_code.direction == ReasonCode.Direction.IN and quantity < 0:
        raise ValidationFailed(
            f"Reason '{reason_code.code}' can only increase stock.",
            errors=[{"field": "reason_code", "code": "DIRECTION", "message": "IN"}],
        )
    if reason_code.direction == ReasonCode.Direction.OUT and quantity > 0:
        raise ValidationFailed(
            f"Reason '{reason_code.code}' can only decrease stock.",
            errors=[{"field": "reason_code", "code": "DIRECTION", "message": "OUT"}],
        )


# --------------------------------------------------------------------------- lookups
@transaction.atomic
def create_reason_code(
    *,
    actor: Any,
    code: str,
    name: str,
    direction: str = ReasonCode.Direction.BOTH,
    is_restockable: bool = True,
) -> ReasonCode:
    require_roles(actor, Role.OWNER)
    code = code.strip().upper()
    if ReasonCode.objects.filter(code=code).exists():
        raise ValidationFailed(
            "That reason code already exists.",
            errors=[{"field": "code", "code": "DUPLICATE", "message": code}],
        )
    reason = ReasonCode.objects.create(
        code=code, name=name.strip(), direction=direction, is_restockable=is_restockable
    )
    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type="reason_code",
        entity_id=reason.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={"code": reason.code},
    )
    return reason


@transaction.atomic
def deactivate_reason_code(*, actor: Any, reason: ReasonCode) -> ReasonCode:
    """System codes are referenced by name in code and cannot be removed (04 T-08)."""
    require_roles(actor, Role.OWNER)
    if reason.is_system:
        raise ValidationFailed(
            "System reason codes cannot be deactivated.",
            errors=[{"field": "code", "code": "SYSTEM", "message": reason.code}],
        )
    reason.is_active = False
    reason.save(update_fields=["is_active"])
    record_audit(
        action=AuditLog.Action.DEACTIVATE,
        entity_type="reason_code",
        entity_id=reason.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={"is_active": False},
    )
    return reason
