"""Goods receipt rules (D5 Stage 3 — FR-PUR-006/007/008/009/010/011/013).

Stage 3 is where a purchase order stops being an intention. Every test below exists because
something here writes to a table that cannot be edited afterwards: `stock_movement`,
`supplier_ledger_entry` and `goods_receipt` itself.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from catalogue.services import create_product
from core.exceptions import PermissionDenied, ValidationFailed
from core.models import AuditLog
from inventory.models import StockMovement
from inventory.selectors import on_hand_for
from ledger.models import LedgerEntryImmutable, SupplierLedgerEntry
from ledger.selectors import supplier_balance, supplier_statement_for
from ledger.services import record_supplier_entry
from purchasing.models import GoodsReceipt, GoodsReceiptImmutable, PurchaseOrder
from purchasing.selectors import outstanding_lines, received_quantities
from purchasing.services import (
    close_purchase_order,
    create_goods_receipt,
    create_purchase_order,
    create_supplier,
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


@pytest.fixture
def issued_po(owner, supplier, widget):
    """Ten widgets at 50.00 + 18% — subtotal 500.00, tax 90.00, total 590.00."""
    purchase_order = create_purchase_order(
        actor=owner,
        supplier=supplier,
        order_date=ORDER_DATE,
        lines=[
            {"product": widget, "quantity_ordered": Decimal("10"), "unit_cost": Decimal("50.00")}
        ],
    )
    return issue_purchase_order(actor=owner, purchase_order=purchase_order)


def _receive(owner, purchase_order, quantity, **kw):
    fields = {
        "actor": owner,
        "purchase_order": purchase_order,
        "receipt_date": ORDER_DATE,
        "lines": [
            {
                "purchase_order_line": purchase_order.lines.first(),
                "quantity_received": Decimal(quantity),
            }
        ],
    }
    fields.update(kw)
    return create_goods_receipt(**fields)


# --------------------------------------------------------------------------- the happy path


def test_a_full_receipt_moves_stock_raises_a_payable_and_completes_the_order(
    owner, issued_po, widget, supplier, profile
):
    """FR-PUR-006/007/010/011 in one assertion set, because they happen in one transaction."""
    receipt = _receive(owner, issued_po, "10")

    assert receipt.grn_number.startswith("GRN-")
    assert receipt.subtotal_amount == Decimal("500.00")
    assert receipt.tax_amount == Decimal("90.00")
    assert receipt.total_amount == Decimal("590.00")

    # FR-PUR-007: the stock moved, and it resolves in both directions.
    assert on_hand_for(widget) == Decimal("10.000")
    line = receipt.lines.get()
    assert line.stock_movement.movement_type == StockMovement.Type.RECEIPT
    assert line.stock_movement.quantity == Decimal("10.000")
    assert line.stock_movement.source_document_type == "GOODS_RECEIPT"
    assert line.stock_movement.source_document_id == receipt.pk

    # FR-PUR-010/011: the payable, positive, for the receipt total.
    assert supplier_balance(supplier) == Decimal("590.00")
    entry = supplier_statement_for(supplier).get()
    assert entry.entry_type == SupplierLedgerEntry.Type.GOODS_RECEIPT
    assert entry.amount == Decimal("590.00")
    assert entry.source_document_type == "GOODS_RECEIPT"
    assert entry.source_document_id == receipt.pk

    issued_po.refresh_from_db()
    assert issued_po.status == PurchaseOrder.Status.RECEIVED


def test_the_receipt_is_audited_and_the_ledger_entry_is_not(owner, issued_po, profile):
    """R-3. An immutable row carrying actor, amount, narration and source needs no audit of it."""
    receipt = _receive(owner, issued_po, "10")

    assert AuditLog.objects.filter(entity_type="goods_receipt", entity_id=receipt.pk).count() == 1
    assert not AuditLog.objects.filter(entity_type="supplier_ledger_entry").exists()


def test_the_audit_payload_survives_redaction(owner, issued_po, profile):
    """`supplier_code`, never `code` — `core.services._SENSITIVE` matches `code` exactly."""
    receipt = _receive(owner, issued_po, "10")
    entry = AuditLog.objects.get(entity_type="goods_receipt", entity_id=receipt.pk)

    assert entry.after_state["supplier_code"] == "ACME"
    assert entry.after_state["grn_number"] == receipt.grn_number
    assert "[redacted]" not in str(entry.after_state)


# --------------------------------------------------------------- partial receipts (FR-PUR-013)


def test_a_short_receipt_leaves_the_order_partially_received(owner, issued_po, profile):
    _receive(owner, issued_po, "4")

    issued_po.refresh_from_db()
    assert issued_po.status == PurchaseOrder.Status.PARTIALLY_RECEIVED
    assert received_quantities(issued_po) == {issued_po.lines.get().pk: Decimal("4.000")}


def test_a_second_receipt_completes_the_order_and_the_payables_accumulate(
    owner, issued_po, supplier, widget, profile
):
    _receive(owner, issued_po, "4")
    issued_po.refresh_from_db()
    _receive(owner, issued_po, "6")

    issued_po.refresh_from_db()
    assert issued_po.status == PurchaseOrder.Status.RECEIVED
    assert on_hand_for(widget) == Decimal("10.000")
    # 4 x 50 x 1.18 = 236.00, 6 x 50 x 1.18 = 354.00.
    assert supplier_balance(supplier) == Decimal("590.00")
    assert GoodsReceipt.objects.filter(purchase_order=issued_po).count() == 2


def test_the_variance_is_derived_from_what_has_arrived(owner, issued_po, profile):
    """FR-PUR-008. Nothing is stored; the figure is a subtraction."""
    _receive(owner, issued_po, "4")
    issued_po.refresh_from_db()

    row = outstanding_lines(issued_po)[0]
    assert row["received"] == Decimal("4.000")
    assert row["outstanding"] == Decimal("6.000")


# ------------------------------------------------------ the over-receipt tolerance (FR-PUR-009)


def test_an_unconfigured_system_refuses_every_over_receipt(owner, issued_po, profile):
    """BD-2 / D-PUR-4. The default is `0.00`, and the default is the decision."""
    assert profile.over_receipt_tolerance_percent == Decimal("0.00")

    with pytest.raises(ValidationFailed) as exc:
        _receive(owner, issued_po, "11")
    assert exc.value.errors[0]["code"] == "OVER_RECEIPT"


def test_a_configured_tolerance_admits_exactly_that_much_and_no_more(owner, issued_po, profile):
    """The figure comes from `BusinessProfile`; nothing in the service hard-codes one."""
    profile.over_receipt_tolerance_percent = Decimal("5.00")
    profile.save(update_fields=["over_receipt_tolerance_percent"])

    # 10 ordered, 5% tolerance -> 10.5 permitted.
    with pytest.raises(ValidationFailed):
        _receive(owner, issued_po, "11")

    receipt = _receive(owner, issued_po, "10.5")
    assert receipt.lines.get().quantity_received == Decimal("10.500")


def test_the_tolerance_is_cumulative_not_per_receipt(owner, issued_po, profile):
    """Three receipts of 40% each must not each pass and overshoot together (D-PUR-4)."""
    profile.over_receipt_tolerance_percent = Decimal("10.00")
    profile.save(update_fields=["over_receipt_tolerance_percent"])

    _receive(owner, issued_po, "8")
    issued_po.refresh_from_db()
    # 8 already in; 11 permitted in total; 4 more would make 12.
    with pytest.raises(ValidationFailed) as exc:
        _receive(owner, issued_po, "4")
    assert exc.value.errors[0]["code"] == "OVER_RECEIPT"

    # 3 more makes exactly 11, which is the limit and is therefore accepted.
    _receive(owner, issued_po, "3")


def test_a_shortfall_on_one_line_does_not_finance_an_overage_on_another(
    owner, supplier, widget, profile
):
    """Per line, not per order — the other half of D-PUR-4."""
    other = create_product(
        actor=owner,
        code="w-2",
        name="Gadget",
        selling_price=Decimal("80.00"),
        tax_rate_percent=Decimal("18.00"),
    )
    purchase_order = issue_purchase_order(
        actor=owner,
        purchase_order=create_purchase_order(
            actor=owner,
            supplier=supplier,
            order_date=ORDER_DATE,
            lines=[
                {
                    "product": widget,
                    "quantity_ordered": Decimal("10"),
                    "unit_cost": Decimal("50.00"),
                },
                {
                    "product": other,
                    "quantity_ordered": Decimal("10"),
                    "unit_cost": Decimal("40.00"),
                },
            ],
        ),
    )
    first, second = purchase_order.lines.order_by("line_number")

    with pytest.raises(ValidationFailed):
        create_goods_receipt(
            actor=owner,
            purchase_order=purchase_order,
            receipt_date=ORDER_DATE,
            lines=[
                {"purchase_order_line": first, "quantity_received": Decimal("2")},
                {"purchase_order_line": second, "quantity_received": Decimal("18")},
            ],
        )


# ------------------------------------------------------------------------------ refusals


def test_only_the_owner_may_receive(salesman, issued_po, profile):
    with pytest.raises(PermissionDenied):
        _receive(salesman, issued_po, "10")


def test_goods_cannot_be_received_against_a_draft(owner, supplier, widget, profile):
    draft = create_purchase_order(
        actor=owner,
        supplier=supplier,
        order_date=ORDER_DATE,
        lines=[
            {"product": widget, "quantity_ordered": Decimal("10"), "unit_cost": Decimal("50.00")}
        ],
    )
    with pytest.raises(ValidationFailed) as exc:
        _receive(owner, draft, "10")
    assert exc.value.errors[0]["code"] == "NOT_RECEIVABLE"


def test_goods_cannot_be_received_against_a_completed_order(owner, issued_po, profile):
    _receive(owner, issued_po, "10")
    issued_po.refresh_from_db()

    with pytest.raises(ValidationFailed) as exc:
        _receive(owner, issued_po, "1")
    assert exc.value.errors[0]["code"] == "NOT_RECEIVABLE"


def test_goods_cannot_be_received_against_a_closed_order(owner, issued_po, profile):
    _receive(owner, issued_po, "4")
    issued_po.refresh_from_db()
    close_purchase_order(actor=owner, purchase_order=issued_po, reason="Supplier discontinued it")
    issued_po.refresh_from_db()

    with pytest.raises(ValidationFailed):
        _receive(owner, issued_po, "1")


def test_a_receipt_needs_at_least_one_line(owner, issued_po, profile):
    with pytest.raises(ValidationFailed) as exc:
        create_goods_receipt(
            actor=owner, purchase_order=issued_po, receipt_date=ORDER_DATE, lines=[]
        )
    assert exc.value.errors[0]["code"] == "REQUIRED"


def test_a_zero_quantity_is_not_a_receipt(owner, issued_po, profile):
    with pytest.raises(ValidationFailed) as exc:
        _receive(owner, issued_po, "0")
    assert exc.value.errors[0]["code"] == "MIN_VALUE"


def test_the_same_line_twice_in_one_receipt_is_refused(owner, issued_po, profile):
    """A data-entry error, not a partial delivery. Partials are separate receipts."""
    line = issued_po.lines.get()
    with pytest.raises(ValidationFailed) as exc:
        create_goods_receipt(
            actor=owner,
            purchase_order=issued_po,
            receipt_date=ORDER_DATE,
            lines=[
                {"purchase_order_line": line, "quantity_received": Decimal("2")},
                {"purchase_order_line": line, "quantity_received": Decimal("3")},
            ],
        )
    assert exc.value.errors[0]["code"] == "DUPLICATE_LINE"


def test_a_line_from_another_order_is_refused(owner, supplier, widget, issued_po, profile):
    other = issue_purchase_order(
        actor=owner,
        purchase_order=create_purchase_order(
            actor=owner,
            supplier=supplier,
            order_date=ORDER_DATE,
            lines=[
                {"product": widget, "quantity_ordered": Decimal("5"), "unit_cost": Decimal("50.00")}
            ],
        ),
    )
    with pytest.raises(ValidationFailed) as exc:
        create_goods_receipt(
            actor=owner,
            purchase_order=issued_po,
            receipt_date=ORDER_DATE,
            lines=[
                {
                    "purchase_order_line": other.lines.get(),
                    "quantity_received": Decimal("1"),
                }
            ],
        )
    assert exc.value.errors[0]["code"] == "WRONG_ORDER"


def test_goods_cannot_be_received_before_the_order_was_placed(owner, issued_po, profile):
    with pytest.raises(ValidationFailed) as exc:
        _receive(owner, issued_po, "10", receipt_date=ORDER_DATE - timedelta(days=1))
    assert exc.value.errors[0]["code"] == "BEFORE_ORDER_DATE"


# ------------------------------------------------------------------------- atomicity


def test_a_refused_line_leaves_no_stock_no_payable_and_no_receipt(
    owner, supplier, widget, profile
):
    """The one outcome the business cannot absorb: stock with no payable, or the reverse.

    The second line is refused, so the first line's movement — already written by then — must
    roll back with it.
    """
    other = create_product(
        actor=owner,
        code="w-2",
        name="Gadget",
        selling_price=Decimal("80.00"),
        tax_rate_percent=Decimal("18.00"),
    )
    purchase_order = issue_purchase_order(
        actor=owner,
        purchase_order=create_purchase_order(
            actor=owner,
            supplier=supplier,
            order_date=ORDER_DATE,
            lines=[
                {
                    "product": widget,
                    "quantity_ordered": Decimal("10"),
                    "unit_cost": Decimal("50.00"),
                },
                {
                    "product": other,
                    "quantity_ordered": Decimal("10"),
                    "unit_cost": Decimal("40.00"),
                },
            ],
        ),
    )
    first, second = purchase_order.lines.order_by("line_number")

    with pytest.raises(ValidationFailed):
        create_goods_receipt(
            actor=owner,
            purchase_order=purchase_order,
            receipt_date=ORDER_DATE,
            lines=[
                {"purchase_order_line": first, "quantity_received": Decimal("5")},
                {"purchase_order_line": second, "quantity_received": Decimal("99")},
            ],
        )

    assert on_hand_for(widget) == Decimal("0.000")
    assert not GoodsReceipt.objects.exists()
    assert supplier_balance(supplier) == Decimal("0.00")
    assert not StockMovement.objects.filter(source_document_type="GOODS_RECEIPT").exists()


# ------------------------------------------------------------------------ immutability


def test_a_posted_receipt_cannot_be_edited(owner, issued_po, profile):
    receipt = _receive(owner, issued_po, "10")

    receipt.notes = "changed my mind"
    with pytest.raises(GoodsReceiptImmutable):
        receipt.save()
    with pytest.raises(GoodsReceiptImmutable):
        receipt.delete()
    with pytest.raises(GoodsReceiptImmutable):
        GoodsReceipt.objects.filter(pk=receipt.pk).update(notes="changed my mind")
    with pytest.raises(GoodsReceiptImmutable):
        GoodsReceipt.objects.filter(pk=receipt.pk).delete()


def test_a_supplier_ledger_entry_cannot_be_edited(owner, issued_po, profile):
    _receive(owner, issued_po, "10")
    entry = SupplierLedgerEntry.objects.get()

    entry.amount = Decimal("1.00")
    with pytest.raises(LedgerEntryImmutable):
        entry.save()
    with pytest.raises(LedgerEntryImmutable):
        entry.delete()
    with pytest.raises(LedgerEntryImmutable):
        SupplierLedgerEntry.objects.filter(pk=entry.pk).update(amount=Decimal("1.00"))
    with pytest.raises(LedgerEntryImmutable):
        SupplierLedgerEntry.objects.filter(pk=entry.pk).delete()


# ------------------------------------------------------------------- the supplier ledger


def test_a_payment_reduces_the_balance(owner, supplier, issued_po, profile):
    """`04` T-34, testable as written: 1,000 in, 400 out, 600 left. Here: 590 - 400 = 190."""
    _receive(owner, issued_po, "10")
    record_supplier_entry(
        actor=owner,
        supplier=supplier,
        entry_type=SupplierLedgerEntry.Type.PAYMENT,
        amount=Decimal("-400.00"),
        narration="Part payment",
        entry_date=ORDER_DATE,
    )
    assert supplier_balance(supplier) == Decimal("190.00")


def test_a_supplier_with_no_entries_has_a_zero_balance_not_none(supplier, db):
    """R-1's trap, in its scalar form."""
    assert supplier_balance(supplier) == Decimal("0.00")


def test_the_sign_of_a_supplier_entry_must_match_its_type(owner, supplier, db):
    """The service refuses before the CHECK does, so the caller gets a usable message."""
    with pytest.raises(ValidationFailed) as exc:
        record_supplier_entry(
            actor=owner,
            supplier=supplier,
            entry_type=SupplierLedgerEntry.Type.PAYMENT,
            amount=Decimal("400.00"),
            narration="Backwards",
        )
    assert exc.value.errors[0]["code"] == "SIGN"

    with pytest.raises(ValidationFailed):
        record_supplier_entry(
            actor=owner,
            supplier=supplier,
            entry_type=SupplierLedgerEntry.Type.GOODS_RECEIPT,
            amount=Decimal("-1.00"),
            narration="Backwards",
        )


def test_a_supplier_opening_balance_may_be_a_credit(owner, supplier, db):
    """Where this diverges from the customer ledger, deliberately (`04` T-34).

    An advance paid before go-live is a real opening position and must be recordable as one.
    """
    record_supplier_entry(
        actor=owner,
        supplier=supplier,
        entry_type=SupplierLedgerEntry.Type.OPENING,
        amount=Decimal("-250.00"),
        narration="Advance paid before go-live",
    )
    assert supplier_balance(supplier) == Decimal("-250.00")


def test_an_unregistered_source_document_is_refused(owner, supplier, widget, db):
    """R-2: the caller must possess the thing, not merely name it."""
    with pytest.raises(ValidationFailed) as exc:
        record_supplier_entry(
            actor=owner,
            supplier=supplier,
            entry_type=SupplierLedgerEntry.Type.GOODS_RECEIPT,
            amount=Decimal("100.00"),
            narration="Not a document",
            source_document=widget,
        )
    assert exc.value.errors[0]["code"] == "UNREGISTERED_SOURCE"
