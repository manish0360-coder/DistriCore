"""Stock ledger rules (04 T-11..T-13, M2_Design_Review).

The scenario in §1.1 of the design review is executed end to end in
``test_worked_scenario_from_the_design_review``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from core.exceptions import PermissionDenied, ValidationFailed
from core.models import AuditLog
from inventory.models import ReasonCode, StockLot, StockMovement
from inventory.selectors import negative_stock, on_hand_for, stock_on_hand, variance_by_reason
from inventory.services import (
    adjust_stock,
    default_location,
    default_lot_for,
    issue_stock,
    receive_stock,
    record_movement,
)

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- structure
def test_migration_seeds_exactly_one_default_location(location):
    from inventory.models import StockLocation

    assert location.code == "MAIN"
    assert StockLocation.objects.filter(is_default=True).count() == 1
    assert default_location() == location


def test_lot_is_created_lazily_not_at_product_creation(product):
    """D-1: a product that has never been stocked has nothing to say about stock."""
    assert StockLot.objects.filter(product=product).count() == 0
    lot = default_lot_for(product)
    assert lot.lot_code == "DEFAULT"
    assert StockLot.objects.filter(product=product).count() == 1


def test_default_lot_is_idempotent(product):
    """Select-then-upsert: repeated calls return the same row, never a duplicate."""
    first = default_lot_for(product)
    second = default_lot_for(product)
    assert first.pk == second.pk
    assert StockLot.objects.filter(product=product).count() == 1


# --------------------------------------------------------------------------- scenario
def test_worked_scenario_from_the_design_review(owner, product, receipt_reason, damage_reason):
    """Design review §1.1, executed. 100 cases in, 12 out, 2 damaged."""
    assert on_hand_for(product) == Decimal("0.000")

    receive_stock(
        actor=owner,
        product=product,
        quantity=product.to_base_units(100, in_packs=True),  # 100 cases x 12
        reason_code=receipt_reason,
    )
    assert on_hand_for(product) == Decimal("1200.000")

    issue_stock(
        actor=owner,
        product=product,
        quantity=product.to_base_units(12, in_packs=True),  # 12 cases
        reason_code=ReasonCode.objects.get(code="COUNT_ADJ"),
    )
    assert on_hand_for(product) == Decimal("1056.000")

    adjust_stock(
        actor=owner,
        product=product,
        quantity=Decimal("-2"),
        reason_code=damage_reason,
        notes="Torn packs, rack 3",
    )
    assert on_hand_for(product) == Decimal("1054.000")

    # Three rows, three facts, nothing overwritten.
    assert StockMovement.objects.filter(product=product).count() == 3


# --------------------------------------------------------------------------- sign rules
def test_receipt_is_always_positive(owner, product, receipt_reason):
    movement = receive_stock(
        actor=owner, product=product, quantity=Decimal("-50"), reason_code=receipt_reason
    )
    assert movement.quantity == Decimal("50.000")


def test_issue_is_always_negative(owner, product):
    movement = issue_stock(
        actor=owner,
        product=product,
        quantity=Decimal("50"),
        reason_code=ReasonCode.objects.get(code="COUNT_ADJ"),
    )
    assert movement.quantity == Decimal("-50.000")


def test_adjustment_may_go_either_way(owner, product):
    both = ReasonCode.objects.get(code="COUNT_ADJ")
    up = adjust_stock(actor=owner, product=product, quantity=Decimal("5"), reason_code=both)
    down = adjust_stock(actor=owner, product=product, quantity=Decimal("-3"), reason_code=both)
    assert up.quantity == Decimal("5.000")
    assert down.quantity == Decimal("-3.000")
    assert on_hand_for(product) == Decimal("2.000")


# --------------------------------------------------------------------------- BR-007
def test_movement_without_source_or_reason_is_refused(owner, product):
    """BR-007 / M2-8 — every divergence is explained."""
    with pytest.raises(ValidationFailed) as exc:
        record_movement(
            actor=owner,
            product=product,
            quantity=Decimal("1"),
            movement_type=StockMovement.Type.ADJUSTMENT,
        )
    assert exc.value.errors[0]["code"] == "REQUIRED"


def test_zero_movement_is_refused(owner, product, damage_reason):
    with pytest.raises(ValidationFailed):
        adjust_stock(actor=owner, product=product, quantity=0, reason_code=damage_reason)


def test_reason_direction_is_enforced(owner, product, damage_reason, receipt_reason):
    """DAMAGE is OUT-only; PURCHASE_IN is IN-only (04 T-08)."""
    with pytest.raises(ValidationFailed) as exc:
        adjust_stock(actor=owner, product=product, quantity=Decimal("5"), reason_code=damage_reason)
    assert exc.value.errors[0]["code"] == "DIRECTION"

    with pytest.raises(ValidationFailed):
        adjust_stock(
            actor=owner, product=product, quantity=Decimal("-5"), reason_code=receipt_reason
        )


def test_inactive_reason_is_refused(owner, product, damage_reason):
    damage_reason.is_active = False
    damage_reason.save(update_fields=["is_active"])
    with pytest.raises(ValidationFailed):
        adjust_stock(
            actor=owner, product=product, quantity=Decimal("-1"), reason_code=damage_reason
        )


# --------------------------------------------------------------------------- D-3 audit
def test_adjustment_is_audited(owner, product, damage_reason):
    """D-3 Option A: discretionary movements are audited."""
    movement = adjust_stock(
        actor=owner, product=product, quantity=Decimal("-2"), reason_code=damage_reason
    )
    entry = AuditLog.objects.get(entity_type="stock_movement", entity_id=movement.pk)
    assert entry.action == AuditLog.Action.STOCK_ADJUST
    assert entry.after_state["quantity"] == "-2.000"  # canonical scale
    assert entry.after_state["reason"] == "DAMAGE"


@pytest.mark.parametrize("kind", ["receipt", "issue"])
def test_routine_movements_are_not_audited(owner, product, receipt_reason, kind):
    """D-3 Option A: the movement row already carries actor, time, reason and
    immutability. A parallel audit row would duplicate it and double the write volume
    of the largest table in the system."""
    if kind == "receipt":
        receive_stock(
            actor=owner, product=product, quantity=Decimal("10"), reason_code=receipt_reason
        )
    else:
        issue_stock(
            actor=owner,
            product=product,
            quantity=Decimal("10"),
            reason_code=ReasonCode.objects.get(code="COUNT_ADJ"),
        )
    assert not AuditLog.objects.filter(entity_type="stock_movement").exists()


# --------------------------------------------------------------------------- R-2
def test_unregistered_source_document_is_refused(owner, product, customer):
    """R-2: the registry is empty in M2, so any source document is rejected."""
    with pytest.raises(ValidationFailed) as exc:
        record_movement(
            actor=owner,
            product=product,
            quantity=Decimal("1"),
            movement_type=StockMovement.Type.ISSUE,
            source_document=customer,
        )
    assert exc.value.errors[0]["code"] == "UNREGISTERED_SOURCE"


def test_unsaved_source_document_is_refused(owner, product, monkeypatch):
    """A caller must possess a persisted object, not merely name one."""
    from customers.models import Customer
    from inventory import services

    monkeypatch.setitem(services.SOURCE_DOCUMENT_REGISTRY, Customer, "CUSTOMER")
    with pytest.raises(ValidationFailed) as exc:
        record_movement(
            actor=owner,
            product=product,
            quantity=Decimal("1"),
            movement_type=StockMovement.Type.ISSUE,
            source_document=Customer(),
        )
    assert exc.value.errors[0]["code"] == "UNSAVED"


def test_registered_saved_source_document_is_accepted(owner, product, customer, monkeypatch):
    """The M5 path, proven now: a registered persisted instance sets the pair."""
    from customers.models import Customer
    from inventory import services

    monkeypatch.setitem(services.SOURCE_DOCUMENT_REGISTRY, Customer, "CUSTOMER")
    movement = record_movement(
        actor=owner,
        product=product,
        quantity=Decimal("-1"),
        movement_type=StockMovement.Type.ISSUE,
        source_document=customer,
    )
    assert movement.source_document_type == "CUSTOMER"
    assert movement.source_document_id == customer.pk
    assert movement.reason_code is None  # BR-007 satisfied by the document side


# --------------------------------------------------------------------------- authority
@pytest.mark.parametrize("role_fixture", ["salesman", "retailer", "delivery_only"])
def test_stock_writes_are_owner_only(request, product, damage_reason, role_fixture):
    actor = request.getfixturevalue(role_fixture)
    with pytest.raises(PermissionDenied):
        adjust_stock(
            actor=actor, product=product, quantity=Decimal("-1"), reason_code=damage_reason
        )


# --------------------------------------------------------------------------- R-1
def test_product_with_no_movements_returns_zero_not_missing(product):
    """R-1: the sharpest failure mode. A silently shorter stock report is worse than a
    visibly wrong None, because the owner believes it and orders against it."""
    rows = list(stock_on_hand())
    assert len(rows) == 1
    assert rows[0].on_hand == Decimal("0.000")
    assert isinstance(rows[0].on_hand, Decimal)  # typed zero, not int (M1 §4.3)


def test_every_active_product_appears_regardless_of_movements(owner, product, receipt_reason):
    from tests.factories import ProductFactory

    stocked = product
    unstocked = ProductFactory()
    receive_stock(actor=owner, product=stocked, quantity=Decimal("5"), reason_code=receipt_reason)
    by_code = {p.code: p.on_hand for p in stock_on_hand()}
    assert by_code[stocked.code] == Decimal("5.000")
    assert by_code[unstocked.code] == Decimal("0.000")


def test_balance_as_of_a_past_instant(owner, product, receipt_reason, damage_reason):
    """Something a stored quantity could never answer: it only knows now."""
    receive_stock(actor=owner, product=product, quantity=Decimal("100"), reason_code=receipt_reason)
    midpoint = timezone.now()
    adjust_stock(actor=owner, product=product, quantity=Decimal("-10"), reason_code=damage_reason)
    assert on_hand_for(product) == Decimal("90.000")
    assert on_hand_for(product, as_of=midpoint) == Decimal("100.000")


def test_negative_stock_is_permitted_and_reported(owner, product):
    """D-2 / ADR-0006: a signal that paperwork lags, not a corruption."""
    issue_stock(
        actor=owner,
        product=product,
        quantity=Decimal("5"),
        reason_code=ReasonCode.objects.get(code="COUNT_ADJ"),
    )
    assert on_hand_for(product) == Decimal("-5.000")
    assert product in negative_stock()


def test_variance_by_reason(owner, product, damage_reason):
    adjust_stock(actor=owner, product=product, quantity=Decimal("-2"), reason_code=damage_reason)
    adjust_stock(actor=owner, product=product, quantity=Decimal("-3"), reason_code=damage_reason)
    rows = {r["reason_code__code"]: r["total_quantity"] for r in variance_by_reason()}
    assert rows["DAMAGE"] == Decimal("-5.000")
