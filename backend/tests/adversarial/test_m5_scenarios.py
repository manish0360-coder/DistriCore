"""The M5 worked scenarios, executed.

`M5_Design_Review.md` §4 describes four business scenarios in prose. These run them. A
design document that executes cannot silently diverge from the system it describes —
which is exactly how `04` T-16 came to say delivery writes the stock issue while `02`
FR-FUL-003 said dispatch does (C-1).

**Scenario F is the one that matters most.** It is the case an independent review found
in the frozen database design: a failed delivery followed by a credit note, which under
`04` T-19's ``restocked`` flag would restock the same physical goods twice.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from billing.services import issue_credit_note, issue_invoice
from fulfilment.models import Delivery
from fulfilment.services import (
    assign_delivery,
    complete_delivery,
    dispatch_delivery,
    fail_delivery,
)
from inventory.models import StockMovement
from inventory.selectors import on_hand_for
from inventory.services import receive_stock, record_movement
from ledger.models import CustomerLedgerEntry
from ledger.selectors import settled_balance
from orders.models import SalesOrder
from orders.services import confirm_order, place_order

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]


@pytest.fixture
def stocked(owner, product, receipt_reason):
    """1,200 units on hand — the design review's opening position."""
    receive_stock(
        actor=owner, product=product, quantity=Decimal("1200"), reason_code=receipt_reason
    )
    return product


@pytest.fixture
def confirmed_order(owner, credit_customer, stocked):
    """24 units of P-1001, confirmed and awaiting dispatch."""
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": stocked, "quantity": Decimal("24")}],
    )
    confirm_order(actor=owner, order=order)
    return order


@pytest.fixture
def dispatched(owner, confirmed_order):
    delivery = assign_delivery(actor=owner, order=confirmed_order, assigned_user=owner)
    return dispatch_delivery(actor=owner, delivery=delivery)


# --------------------------------------------------------------------------- A
def test_scenario_a_happy_path(owner, credit_customer, stocked, confirmed_order):
    """Assign, dispatch, invoice, deliver — stock falls once, the ledger rises once."""
    assert on_hand_for(stocked) == Decimal("1200.000")

    delivery = assign_delivery(actor=owner, order=confirmed_order, assigned_user=owner)
    assert on_hand_for(stocked) == Decimal("1200.000"), "assignment moves nothing"

    dispatch_delivery(actor=owner, delivery=delivery)
    confirmed_order.refresh_from_db()
    assert confirmed_order.status == SalesOrder.Status.DISPATCHED
    assert on_hand_for(stocked) == Decimal("1176.000"), "the goods left at dispatch (M5-1)"
    assert settled_balance(credit_customer) == Decimal("0.00"), "nothing is owed yet"

    invoice = issue_invoice(actor=owner, order=confirmed_order)
    assert on_hand_for(stocked) == Decimal("1176.000"), "invoicing moves no stock"
    assert settled_balance(credit_customer) == invoice.total_amount

    complete_delivery(actor=owner, delivery=delivery, recipient_name="Shop owner")
    confirmed_order.refresh_from_db()
    assert confirmed_order.status == SalesOrder.Status.DELIVERED
    assert on_hand_for(stocked) == Decimal("1176.000"), "delivery moves nothing either"


def test_dispatch_is_the_first_movement_to_carry_a_source_document(owner, dispatched, stocked):
    """R-2's accept path, in production for the first time — this closes TD-16."""
    issue = StockMovement.objects.filter(movement_type=StockMovement.Type.ISSUE).get()
    assert issue.source_document_type == "DELIVERY"
    assert issue.source_document_id == dispatched.pk
    assert issue.reason_code is None, "a document-driven movement needs no reason code"


# --------------------------------------------------------------------------- B
def test_scenario_b_failed_delivery_returns_the_goods(owner, dispatched, stocked):
    """The ISSUE is not deleted and not edited. Two rows record what happened."""
    assert on_hand_for(stocked) == Decimal("1176.000")

    fail_delivery(actor=owner, delivery=dispatched, reason="Shop shut")

    assert on_hand_for(stocked) == Decimal("1200.000")
    assert StockMovement.objects.filter(movement_type=StockMovement.Type.ISSUE).count() == 1
    assert StockMovement.objects.filter(movement_type=StockMovement.Type.RETURN).count() == 1
    dispatched.refresh_from_db()
    assert dispatched.status == Delivery.Status.FAILED


# --------------------------------------------------------------------------- C
def test_scenario_c_physical_return_and_credit_are_separate_events(
    owner, credit_customer, dispatched, stocked, sales_return_reason
):
    """12 units come back and 12 units are credited — two events, two documents.

    The reason code is ``SALES_RETURN`` (direction ``IN``), not ``DAMAGE`` (``OUT``).
    Goods coming back from a customer increase stock, and the direction rule refuses to
    let an outbound code express an inbound movement.
    """
    invoice = issue_invoice(actor=owner, order=dispatched.sales_order)
    complete_delivery(actor=owner, delivery=dispatched, recipient_name="Shop owner")

    # C1 — the physical event, recorded by the warehouse.
    record_movement(
        actor=owner,
        product=stocked,
        quantity=Decimal("12"),
        movement_type=StockMovement.Type.RETURN,
        reason_code=sales_return_reason,
    )
    assert on_hand_for(stocked) == Decimal("1188.000")

    # C2 — the financial event. It must move no stock.
    before = StockMovement.objects.count()
    note = issue_credit_note(
        actor=owner,
        invoice=invoice,
        lines=[{"invoice_line": invoice.lines.first(), "quantity": Decimal("12")}],
        reason="Twelve units returned damaged",
    )
    assert StockMovement.objects.count() == before, "a credit note writes no stock (D-7)"
    assert on_hand_for(stocked) == Decimal("1188.000")
    assert settled_balance(credit_customer) == invoice.total_amount - note.total_amount


# --------------------------------------------------------------------------- E
def test_scenario_e_dispatch_proceeds_when_stock_is_short(
    owner, credit_customer, product, receipt_reason
):
    """Negative on hand is permitted and reported, never blocked (D-2, ADR-0006).

    Blocking would teach the warehouse to send goods and record nothing, and an
    unrecorded movement is the failure the ledger exists to prevent.
    """
    receive_stock(actor=owner, product=product, quantity=Decimal("10"), reason_code=receipt_reason)
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "24"}]
    )
    confirm_order(actor=owner, order=order)
    delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)

    dispatch_delivery(actor=owner, delivery=delivery)

    assert on_hand_for(product) == Decimal("-14.000")


# --------------------------------------------------------------------------- F
def test_scenario_f_failed_delivery_then_credit_note_restocks_once(
    owner, credit_customer, dispatched, stocked
):
    """**The double-restock trap.** The defect an independent review found in `04` T-19.

    Under the frozen schema the owner, asked "were these restocked?", would honestly
    answer *yes* — the goods really are back on the shelf after the failed delivery —
    and inflate stock by 24 units that do not exist. A field whose correct answer
    produces an incorrect result is a design defect, not a training problem.

    D-7 removes the second writer entirely rather than refereeing between two.
    """
    invoice = issue_invoice(actor=owner, order=dispatched.sales_order)
    assert on_hand_for(stocked) == Decimal("1176.000")

    fail_delivery(actor=owner, delivery=dispatched, reason="Shop shut")
    assert on_hand_for(stocked) == Decimal("1200.000"), "the goods came back once"

    issue_credit_note(
        actor=owner,
        invoice=invoice,
        lines=[{"invoice_line": invoice.lines.first(), "quantity": Decimal("24")}],
        reason="Never received — delivery failed",
    )

    assert on_hand_for(stocked) == Decimal("1200.000"), (
        "the credit note must not restock goods the failed delivery already returned"
    )
    assert StockMovement.objects.filter(movement_type=StockMovement.Type.RETURN).count() == 1
    assert settled_balance(credit_customer) == Decimal("0.00"), "and nothing is owed"


def test_no_credit_note_field_can_trigger_a_stock_movement():
    """Structural: ``billing`` cannot write stock, so no future call site can either."""
    import ast
    from pathlib import Path

    import billing

    package_root = Path(billing.__file__).parent
    offenders = {}
    for module in package_root.rglob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = ""
            if isinstance(node, ast.ImportFrom) and node.module:
                name = node.module
            elif isinstance(node, ast.Import):
                name = ",".join(alias.name for alias in node.names)
            if "inventory.services" in name or "inventory.models" in name:
                offenders[module.relative_to(package_root).as_posix()] = name
    assert offenders == {}, f"billing reached into inventory: {offenders}"


def test_the_restocked_flag_does_not_exist():
    """`04` T-19's ``restocked`` boolean is removed by ADR-0009, not merely unused.

    Leaving it in place unused would be worse than removing it: a future developer would
    reasonably wire it up.
    """
    from billing.models import CreditNote

    fields = {f.name for f in CreditNote._meta.get_fields()}
    assert "restocked" not in fields


# --------------------------------------------------------------------------- ledger shape
def test_every_document_writes_exactly_one_ledger_entry(owner, credit_customer, dispatched):
    invoice = issue_invoice(actor=owner, order=dispatched.sales_order)
    entries = CustomerLedgerEntry.objects.filter(customer=credit_customer)
    assert entries.count() == 1
    assert entries.get().entry_type == CustomerLedgerEntry.Type.INVOICE
    assert entries.get().sales_order_id == dispatched.sales_order_id

    issue_credit_note(
        actor=owner,
        invoice=invoice,
        lines=[{"invoice_line": invoice.lines.first(), "quantity": Decimal("24")}],
        reason="Full credit",
    )
    assert entries.count() == 2
    assert settled_balance(credit_customer) == Decimal("0.00")
