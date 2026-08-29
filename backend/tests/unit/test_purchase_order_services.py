"""Purchase order and lifecycle rules (D5 Stage 2 — FR-PUR-003, FR-PUR-005).

Stage 2 is a commercial intention. Nothing here moves stock or money; goods receipt, the
supplier ledger and supplier payments arrive at Stages 3 and 4.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db.utils import IntegrityError

from catalogue.services import create_product
from core.exceptions import PermissionDenied, ValidationFailed
from core.models import AuditLog
from purchasing.models import PurchaseOrder, PurchaseOrderLine
from purchasing.selectors import lines_for, search_purchase_orders
from purchasing.services import (
    ALLOWED_TRANSITIONS,
    amend_purchase_order,
    cancel_purchase_order,
    create_purchase_order,
    create_supplier,
    deactivate_supplier,
    issue_purchase_order,
)

pytestmark = pytest.mark.django_db

ORDER_DATE = date(2026, 8, 26)


@pytest.fixture
def supplier(owner):
    return create_supplier(
        actor=owner,
        code="acme",
        name="Acme Distributors",
        phone="+919876500011",
        billing_address="Industrial Estate",
        payment_terms_days=30,
    )


@pytest.fixture
def widget(owner):
    return create_product(
        actor=owner,
        code="w-1",
        name="Widget",
        selling_price=Decimal("100.00"),
        tax_rate_percent=Decimal("18.00"),
    )


def _po(owner, supplier, widget, **kw):
    fields = {
        "actor": owner,
        "supplier": supplier,
        "order_date": ORDER_DATE,
        "lines": [
            {"product": widget, "quantity_ordered": Decimal("10"), "unit_cost": Decimal("50.00")}
        ],
    }
    fields.update(kw)
    return create_purchase_order(**fields)


# ------------------------------------------------------------- FR-PUR-003 order + lines


def test_owner_creates_a_purchase_order(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    assert po.status == PurchaseOrder.Status.DRAFT
    assert po.supplier_id == supplier.pk
    assert po.order_date == ORDER_DATE
    assert po.created_by_id == owner.pk
    assert lines_for(po).count() == 1


def test_the_number_is_allocated_at_creation(owner, supplier, widget):
    """D-PUR-8. A draft is already a business document and needs a stable reference."""
    po = _po(owner, supplier, widget)
    assert po.po_number.startswith("PO-")
    assert len(po.po_number) == 11  # PO- plus eight digits


def test_two_orders_get_different_numbers(owner, supplier, widget):
    first, second = _po(owner, supplier, widget), _po(owner, supplier, widget)
    assert first.po_number != second.po_number


def test_line_snapshots_survive_a_rename_and_a_reprice(owner, supplier, widget):
    """The snapshots freeze the commercial agreement, as `SalesOrderLine`'s do for a sale."""
    from catalogue.services import update_product

    po = _po(owner, supplier, widget)
    update_product(actor=owner, product=widget, name="Renamed", selling_price=Decimal("999.00"))

    line = lines_for(po).get()
    assert line.product_name == "Widget"
    assert line.product_code == "W-1"
    assert line.unit_cost == Decimal("50.00")


def test_unit_cost_is_a_purchase_price_not_the_selling_price(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    assert lines_for(po).get().unit_cost == Decimal("50.00")
    assert widget.selling_price == Decimal("100.00")


def test_line_money_is_rounded_at_line_level_and_summed_onto_the_header(owner, supplier, widget):
    """M3-8. 10 x 50.00 = 500.00 taxable, 18% = 90.00 tax, 590.00 total."""
    po = _po(owner, supplier, widget)
    line = lines_for(po).get()
    assert line.taxable_amount == Decimal("500.00")
    assert line.tax_rate_percent == Decimal("18.00")
    assert line.tax_amount == Decimal("90.00")
    assert line.line_total == Decimal("590.00")

    po.refresh_from_db()
    assert po.subtotal_amount == Decimal("500.00")
    assert po.tax_amount == Decimal("90.00")
    assert po.total_amount == Decimal("590.00")


def test_totals_are_decimal_never_float(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    po.refresh_from_db()
    for value in (po.subtotal_amount, po.tax_amount, po.total_amount):
        assert isinstance(value, Decimal)


def test_a_second_line_is_numbered_and_summed(owner, supplier, widget):
    other = create_product(
        actor=owner,
        code="w-2",
        name="Other",
        selling_price=Decimal("10.00"),
        tax_rate_percent=Decimal("0.00"),
    )
    po = _po(
        owner,
        supplier,
        widget,
        lines=[
            {"product": widget, "quantity_ordered": Decimal("1"), "unit_cost": Decimal("50.00")},
            {"product": other, "quantity_ordered": Decimal("2"), "unit_cost": Decimal("25.00")},
        ],
    )
    assert [line.line_number for line in lines_for(po)] == [1, 2]
    po.refresh_from_db()
    assert po.total_amount == Decimal("109.00")  # 59.00 + 50.00


def test_a_zero_line_order_is_refused(owner, supplier, widget):
    with pytest.raises(ValidationFailed):
        _po(owner, supplier, widget, lines=[])


def test_a_non_positive_quantity_is_refused(owner, supplier, widget):
    with pytest.raises(ValidationFailed):
        _po(
            owner,
            supplier,
            widget,
            lines=[
                {"product": widget, "quantity_ordered": Decimal("0"), "unit_cost": Decimal("1")}
            ],
        )


def test_a_negative_unit_cost_is_refused(owner, supplier, widget):
    with pytest.raises(ValidationFailed):
        _po(
            owner,
            supplier,
            widget,
            lines=[
                {"product": widget, "quantity_ordered": Decimal("1"), "unit_cost": Decimal("-1")}
            ],
        )


def test_free_goods_are_permitted(owner, supplier, widget):
    """A zero cost is legitimate; only a negative one is not."""
    po = _po(
        owner,
        supplier,
        widget,
        lines=[{"product": widget, "quantity_ordered": Decimal("1"), "unit_cost": Decimal("0")}],
    )
    assert lines_for(po).get().line_total == Decimal("0.00")


def test_the_database_refuses_a_non_positive_quantity(owner, supplier, widget):
    """Proved able to fail at the constraint, not only in the service."""
    po = _po(owner, supplier, widget)
    with pytest.raises(IntegrityError):
        PurchaseOrderLine.objects.create(
            purchase_order=po,
            line_number=99,
            product=widget,
            product_code="X",
            product_name="X",
            unit_name="PCS",
            pack_size_snapshot=1,
            quantity_ordered=Decimal("0"),
            unit_cost=Decimal("1.00"),
            tax_rate_percent=Decimal("0.00"),
            taxable_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            line_total=Decimal("0.00"),
        )


def test_the_line_number_is_unique_per_order(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    with pytest.raises(IntegrityError):
        PurchaseOrderLine.objects.create(
            purchase_order=po,
            line_number=1,
            product=widget,
            product_code="X",
            product_name="X",
            unit_name="PCS",
            pack_size_snapshot=1,
            quantity_ordered=Decimal("1"),
            unit_cost=Decimal("1.00"),
            tax_rate_percent=Decimal("0.00"),
            taxable_amount=Decimal("1.00"),
            tax_amount=Decimal("0.00"),
            line_total=Decimal("1.00"),
        )


def test_an_inactive_supplier_cannot_be_ordered_from(owner, supplier, widget):
    deactivate_supplier(actor=owner, supplier=supplier)
    with pytest.raises(ValidationFailed):
        _po(owner, supplier, widget)


def test_an_expected_date_before_the_order_date_is_refused(owner, supplier, widget):
    with pytest.raises(ValidationFailed):
        _po(owner, supplier, widget, expected_date=ORDER_DATE - timedelta(days=1))


def test_the_order_date_is_caller_supplied_not_today(owner, supplier, widget):
    """P-4's reasoning: a machine clock may suggest a business fact, never decide one."""
    po = _po(owner, supplier, widget, order_date=date(2020, 1, 1))
    assert po.order_date == date(2020, 1, 1)


# ---------------------------------------------------------------------------- amend


def test_a_draft_may_be_amended(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    amend_purchase_order(
        actor=owner,
        purchase_order=po,
        lines=[
            {"product": widget, "quantity_ordered": Decimal("2"), "unit_cost": Decimal("50.00")}
        ],
    )
    po.refresh_from_db()
    assert lines_for(po).count() == 1
    assert lines_for(po).get().quantity_ordered == Decimal("2.000")
    assert po.total_amount == Decimal("118.00")


def test_an_issued_order_cannot_be_amended(owner, supplier, widget):
    """Narrower than `SalesOrder`: an issued PO has been sent to a supplier."""
    po = _po(owner, supplier, widget)
    issue_purchase_order(actor=owner, purchase_order=po)
    with pytest.raises(ValidationFailed):
        amend_purchase_order(
            actor=owner,
            purchase_order=po,
            lines=[
                {"product": widget, "quantity_ordered": Decimal("1"), "unit_cost": Decimal("1")}
            ],
        )


def test_amending_keeps_the_same_number(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    before = po.po_number
    amend_purchase_order(
        actor=owner,
        purchase_order=po,
        lines=[
            {"product": widget, "quantity_ordered": Decimal("3"), "unit_cost": Decimal("50.00")}
        ],
    )
    po.refresh_from_db()
    assert po.po_number == before


# ------------------------------------------------------------- FR-PUR-005 lifecycle


def test_issue_moves_a_draft_and_stamps_who_and_when(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    issue_purchase_order(actor=owner, purchase_order=po)
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.ISSUED
    assert po.issued_by_id == owner.pk
    assert po.issued_at is not None


def test_issue_never_allocates_a_second_number(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    before = po.po_number
    issue_purchase_order(actor=owner, purchase_order=po)
    po.refresh_from_db()
    assert po.po_number == before


def test_re_issue_is_refused_by_the_lifecycle(owner, supplier, widget):
    """The double-submit guard is the state machine, not the number."""
    po = _po(owner, supplier, widget)
    issue_purchase_order(actor=owner, purchase_order=po)
    with pytest.raises(ValidationFailed):
        issue_purchase_order(actor=owner, purchase_order=po)


def test_a_line_less_order_cannot_be_issued(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    po.lines.all().delete()
    with pytest.raises(ValidationFailed):
        issue_purchase_order(actor=owner, purchase_order=po)


def test_cancel_requires_a_reason(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    with pytest.raises(ValidationFailed):
        cancel_purchase_order(actor=owner, purchase_order=po, reason="  ")


def test_a_draft_may_be_cancelled(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    cancel_purchase_order(actor=owner, purchase_order=po, reason="Supplier out of stock")
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.CANCELLED
    assert po.cancelled_reason == "Supplier out of stock"
    assert po.cancelled_by_id == owner.pk


def test_an_issued_order_may_be_cancelled(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    issue_purchase_order(actor=owner, purchase_order=po)
    cancel_purchase_order(actor=owner, purchase_order=po, reason="Changed our mind")
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.CANCELLED


def test_a_cancelled_order_is_terminal(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    cancel_purchase_order(actor=owner, purchase_order=po, reason="No longer needed")
    with pytest.raises(ValidationFailed):
        issue_purchase_order(actor=owner, purchase_order=po)


@pytest.mark.parametrize(
    ("from_status", "to_status", "allowed"),
    [
        (PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.ISSUED, True),
        (PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CANCELLED, True),
        (PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.RECEIVED, False),
        (PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CLOSED, False),
        (PurchaseOrder.Status.ISSUED, PurchaseOrder.Status.PARTIALLY_RECEIVED, True),
        (PurchaseOrder.Status.ISSUED, PurchaseOrder.Status.RECEIVED, True),
        (PurchaseOrder.Status.ISSUED, PurchaseOrder.Status.CANCELLED, True),
        (PurchaseOrder.Status.ISSUED, PurchaseOrder.Status.CLOSED, False),
        (PurchaseOrder.Status.ISSUED, PurchaseOrder.Status.DRAFT, False),
        # FR-PUR-013: the self-edge is what makes multiple receipts work.
        (
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
            True,
        ),
        (PurchaseOrder.Status.PARTIALLY_RECEIVED, PurchaseOrder.Status.RECEIVED, True),
        (PurchaseOrder.Status.PARTIALLY_RECEIVED, PurchaseOrder.Status.CLOSED, True),
        # Once stock has arrived an order is short-closed, never cancelled.
        (PurchaseOrder.Status.PARTIALLY_RECEIVED, PurchaseOrder.Status.CANCELLED, False),
        (PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.CLOSED, True),
        (PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.CANCELLED, False),
        (PurchaseOrder.Status.CLOSED, PurchaseOrder.Status.ISSUED, False),
        (PurchaseOrder.Status.CANCELLED, PurchaseOrder.Status.ISSUED, False),
    ],
)
def test_the_transition_map_is_the_specification(from_status, to_status, allowed):
    """Asserted against the map itself, so every cell is covered whether or not Stage 2 has
    a service that walks it. The receipt edges are declared now and reachable at Stage 3."""
    assert (to_status in ALLOWED_TRANSITIONS[from_status]) is allowed


def test_every_status_appears_in_the_map(owner):
    """Anti-vacuity: a status missing from the map would be a state nothing could leave."""
    assert set(ALLOWED_TRANSITIONS) == set(PurchaseOrder.Status.values)


# -------------------------------------------------------------------------- audit


def test_creation_is_audited(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    entry = AuditLog.objects.filter(
        entity_type="purchase_order", entity_id=po.pk, action=AuditLog.Action.CREATE
    ).get()
    assert entry.after_state["po_number"] == po.po_number
    assert entry.after_state["supplier_code"] == supplier.code


def test_issue_is_audited_as_ISSUE_not_a_new_action(owner, supplier, widget):
    """D5 adds no `AuditLog.Action` values; `ISSUE` already serves invoices."""
    po = _po(owner, supplier, widget)
    issue_purchase_order(actor=owner, purchase_order=po)
    entry = AuditLog.objects.filter(
        entity_type="purchase_order", action=AuditLog.Action.ISSUE
    ).get()
    assert entry.before_state["status"] == PurchaseOrder.Status.DRAFT
    assert entry.after_state["status"] == PurchaseOrder.Status.ISSUED


def test_cancel_is_audited_as_CANCEL_with_the_reason(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    cancel_purchase_order(actor=owner, purchase_order=po, reason="Out of stock")
    entry = AuditLog.objects.filter(
        entity_type="purchase_order", action=AuditLog.Action.CANCEL
    ).get()
    assert entry.after_state["reason"] == "Out of stock"


def test_amend_is_audited_with_both_totals(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    amend_purchase_order(
        actor=owner,
        purchase_order=po,
        lines=[
            {"product": widget, "quantity_ordered": Decimal("20"), "unit_cost": Decimal("50.00")}
        ],
    )
    entry = AuditLog.objects.filter(
        entity_type="purchase_order", action=AuditLog.Action.UPDATE
    ).get()
    assert entry.before_state["total_amount"] == "590.00"
    assert entry.after_state["total_amount"] == "1180.00"


# ------------------------------------------------------------------- authorization


@pytest.mark.parametrize(
    "call",
    [
        lambda actor, po, s, w: create_purchase_order(
            actor=actor,
            supplier=s,
            order_date=ORDER_DATE,
            lines=[{"product": w, "quantity_ordered": Decimal("1"), "unit_cost": Decimal("1")}],
        ),
        lambda actor, po, s, w: amend_purchase_order(
            actor=actor,
            purchase_order=po,
            lines=[{"product": w, "quantity_ordered": Decimal("1"), "unit_cost": Decimal("1")}],
        ),
        lambda actor, po, s, w: issue_purchase_order(actor=actor, purchase_order=po),
        lambda actor, po, s, w: cancel_purchase_order(actor=actor, purchase_order=po, reason="no"),
    ],
)
def test_only_the_owner_may_touch_purchase_orders(owner, salesman, supplier, widget, call):
    po = _po(owner, supplier, widget)
    with pytest.raises(PermissionDenied):
        call(salesman, po, supplier, widget)


# ---------------------------------------------------------------------- selectors


def test_search_matches_number_and_supplier(owner, supplier, widget):
    po = _po(owner, supplier, widget)
    assert search_purchase_orders(term=po.po_number).count() == 1
    assert search_purchase_orders(term="Acme").count() == 1
    assert search_purchase_orders(term="nothing").count() == 0


def test_search_filters_by_status(owner, supplier, widget):
    _po(owner, supplier, widget)
    issued = _po(owner, supplier, widget)
    issue_purchase_order(actor=owner, purchase_order=issued)
    assert search_purchase_orders(status=PurchaseOrder.Status.DRAFT).count() == 1
    assert search_purchase_orders(status=PurchaseOrder.Status.ISSUED).count() == 1
