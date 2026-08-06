"""**The M2/M3 boundary, proven rather than trusted.**

M3_Design_Review §1.1 and M3-6: an order is commercial intent. Stock is issued at
dispatch, in M5. If an order moved stock, the ledger would begin carrying intention
rather than physical fact, and "what is on the shelf" would no longer be answerable
from it.

Convention would not survive six more milestones. These tests will.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from inventory.models import StockMovement
from inventory.selectors import on_hand_for
from orders.services import (
    amend_order,
    apply_line_discount,
    cancel_order,
    confirm_order,
    place_order,
)

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]


@pytest.fixture
def stocked(owner, product, receipt_reason):
    """100 units on hand before any order exists."""
    from inventory.services import receive_stock

    receive_stock(actor=owner, product=product, quantity=Decimal("100"), reason_code=receipt_reason)
    return product


def _movement_count() -> int:
    return StockMovement.objects.count()


def test_placing_an_order_moves_no_stock(owner, credit_customer, stocked):
    before = _movement_count()
    place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": stocked, "quantity": Decimal("10")}],
    )
    assert _movement_count() == before
    assert on_hand_for(stocked) == Decimal("100.000")


def test_confirming_an_order_moves_no_stock(owner, credit_customer, stocked):
    """Confirmation is agreement, not dispatch — the distinction M3-6 protects."""
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": stocked, "quantity": Decimal("10")}],
    )
    before = _movement_count()
    confirm_order(actor=owner, order=order)
    assert _movement_count() == before
    assert on_hand_for(stocked) == Decimal("100.000")


def test_amending_an_order_moves_no_stock(owner, credit_customer, stocked):
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": stocked, "quantity": Decimal("10")}],
    )
    before = _movement_count()
    amend_order(actor=owner, order=order, lines=[{"product": stocked, "quantity": Decimal("40")}])
    assert _movement_count() == before
    assert on_hand_for(stocked) == Decimal("100.000")


def test_discounting_moves_no_stock(owner, credit_customer, stocked):
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": stocked, "quantity": Decimal("10")}],
    )
    before = _movement_count()
    apply_line_discount(
        actor=owner, order=order, line=order.lines.first(), discount_amount=Decimal("10.00")
    )
    assert _movement_count() == before


def test_cancelling_reverses_nothing_because_nothing_happened(owner, credit_customer, stocked):
    """An order that had moved stock would need compensating movements on cancellation,
    so the ledger would accumulate pairs for events that never physically occurred."""
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": stocked, "quantity": Decimal("10")}],
    )
    confirm_order(actor=owner, order=order)
    before = _movement_count()
    cancel_order(actor=owner, order=order, reason="Retailer changed mind")
    assert _movement_count() == before
    assert on_hand_for(stocked) == Decimal("100.000")


def test_a_full_order_lifecycle_leaves_the_ledger_untouched(owner, credit_customer, stocked):
    """Place, amend, discount, confirm, cancel — one movement count throughout."""
    before = _movement_count()
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": stocked, "quantity": Decimal("5")}],
    )
    amend_order(actor=owner, order=order, lines=[{"product": stocked, "quantity": Decimal("7")}])
    apply_line_discount(
        actor=owner, order=order, line=order.lines.first(), discount_amount=Decimal("5.00")
    )
    confirm_order(actor=owner, order=order)
    cancel_order(actor=owner, order=order, reason="Out of season")
    assert _movement_count() == before
    assert on_hand_for(stocked) == Decimal("100.000")


def _top_level_imports(module_path: Path) -> set[str]:
    """Every package a module imports, parsed from its AST.

    Parsing rather than text-searching: the previous version matched the word
    ``StockMovement`` in a *docstring* explaining that stock is never moved, and failed
    on the very sentence documenting the guarantee. A test that greps prose asserts
    nothing about architecture.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    packages: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            packages.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            packages.add(node.module.split(".")[0])
    return packages


def test_the_orders_package_imports_no_inventory_module():
    """Structural: Edition 1 orders cannot move stock because they cannot see inventory.

    `03` §2.1 *permits* orders -> inventory for Edition 2 allocation, so this is a
    tripwire rather than a contract — it is deliberately not an import-linter rule,
    because a contract stricter than the architecture eventually blocks correct work
    (M2 report §4.2). It asserts today's fact so that adding the import is a deliberate
    act with a failing test to acknowledge.
    """
    import orders

    package_root = Path(orders.__file__).parent
    offenders = {
        module.relative_to(package_root).as_posix(): sorted(_top_level_imports(module))
        for module in package_root.rglob("*.py")
        if "inventory" in _top_level_imports(module)
    }
    assert offenders == {}, f"orders now imports inventory: {offenders}"


def test_orders_write_no_ledger_entry(owner, credit_customer, stocked):
    """The receivable begins at the invoice (M5), not when a customer asks for goods.

    **This assertion changed in M5, and the change is a strengthening.** It previously
    read ``the ledger table should not exist`` — a proxy that was only ever true because
    no milestone had created the table yet. M5 creates it, so the proxy would now fail
    while the guarantee it stood for remained perfectly intact.

    That is the same class of defect as M3's ``OPEN_STATUSES``: a stand-in for a rule,
    correct only until the thing it stood in for arrived. The rule is *orders write no
    ledger entry*, and this now tests exactly that.
    """
    from ledger.models import CustomerLedgerEntry

    before = CustomerLedgerEntry.objects.count()
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": stocked, "quantity": Decimal("10")}],
    )
    amend_order(actor=owner, order=order, lines=[{"product": stocked, "quantity": Decimal("12")}])
    confirm_order(actor=owner, order=order)
    cancel_order(actor=owner, order=order, reason="Retailer changed mind")
    assert CustomerLedgerEntry.objects.count() == before


def test_the_orders_package_cannot_write_the_ledger():
    """Structural counterpart to the inventory tripwire above.

    ``orders`` *may* read the ledger — D-9 makes ``settled_balance`` the settled term of
    credit exposure, and that is a read. It must never import the **writer**:
    ``ledger.services.record_entry`` is the single path a ledger row can be created by,
    and only ``billing`` is entitled to call it.

    Distinguishing read from write is the whole point. A blanket "orders must not import
    ledger" would have been simpler and wrong — it would forbid the exposure query the
    architecture requires.
    """
    import orders

    package_root = Path(orders.__file__).parent
    offenders = {}
    for module in package_root.rglob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported = ""
            if isinstance(node, ast.ImportFrom) and node.module:
                imported = node.module
            elif isinstance(node, ast.Import):
                imported = ",".join(alias.name for alias in node.names)
            if "ledger.services" in imported:
                offenders[module.relative_to(package_root).as_posix()] = imported
    assert offenders == {}, f"orders imports the ledger writer: {offenders}"
