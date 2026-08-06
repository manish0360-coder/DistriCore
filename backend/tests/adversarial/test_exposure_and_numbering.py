"""A-3, A-4, A-12, A-13, A-14 — numbering, the credit cap, and exposure continuity.

The exposure tests are the ones that matter most here. D-9 exists because M5 makes
``DISPATCHED`` reachable for the first time, and M3's status-based open term would have
let a dispatched-but-uninvoiced order fall out of **both** exposure terms — invisible at
the exact moment the distributor is most exposed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from billing.models import Invoice, NumberSeries, financial_year_for
from billing.services import allocate_number, credited_total, issue_credit_note, issue_invoice
from core.exceptions import ValidationFailed
from core.models import BusinessProfile
from core.services import update_business_profile
from customers.services import set_credit_limit
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.services import receive_stock
from orders.selectors import credit_exposure, open_order_value, settled_balance
from orders.services import CreditLimitExceeded, confirm_order, place_order

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]


@pytest.fixture
def stocked(owner, product, receipt_reason):
    receive_stock(
        actor=owner, product=product, quantity=Decimal("5000"), reason_code=receipt_reason
    )
    return product


def _order(owner, customer, product, quantity="24"):
    order = place_order(
        actor=owner, customer=customer, lines=[{"product": product, "quantity": quantity}]
    )
    confirm_order(actor=owner, order=order)
    return order


def _dispatch(owner, order):
    return dispatch_delivery(
        actor=owner, delivery=assign_delivery(actor=owner, order=order, assigned_user=owner)
    )


# --------------------------------------------------------------------------- A-13 / D-9
def test_exposure_never_dips_across_the_full_lifecycle(owner, credit_customer, stocked):
    """**The defect D-9 fixes.** Sampled after every state change; it must not drop.

    The dangerous window is dispatched-but-uninvoiced: wrong status for the open term,
    no ledger entry for the settled term. Under M3's ``OPEN_STATUSES`` the order would
    have vanished from exposure entirely while the goods were already gone.
    """
    order = _order(owner, credit_customer, stocked)
    total = order.total_amount
    assert credit_exposure(credit_customer) == total, "confirmed and unbilled"

    _dispatch(owner, order)
    assert credit_exposure(credit_customer) == total, (
        "dispatched but uninvoiced is the MOST exposed state, not an invisible one"
    )

    invoice = issue_invoice(actor=owner, order=order)
    assert credit_exposure(credit_customer) == invoice.total_amount, (
        "invoicing moves the value between terms; it does not remove it"
    )
    # The invoice rounds to the rupee (M5-11) and the order does not, so the two agree
    # to within the round-off and no further. Asserting equality would be asserting that
    # rounding does not happen.
    assert abs(invoice.total_amount - total) <= Decimal("1.00")


def test_the_two_exposure_terms_partition(owner, credit_customer, stocked):
    """An order contributes to exactly one term, never both and never neither (B-15)."""
    order = _order(owner, credit_customer, stocked)
    total = order.total_amount

    assert open_order_value(credit_customer) == total
    assert settled_balance(credit_customer) == Decimal("0.00")

    _dispatch(owner, order)
    assert open_order_value(credit_customer) == total
    assert settled_balance(credit_customer) == Decimal("0.00")

    invoice = issue_invoice(actor=owner, order=order)
    assert open_order_value(credit_customer) == Decimal("0.00"), "left the open term"
    assert settled_balance(credit_customer) == invoice.total_amount, "entered the settled term"
    assert credit_exposure(credit_customer) == invoice.total_amount, "counted once, never twice"


def test_a_cancelled_order_leaves_exposure_entirely(owner, credit_customer, stocked):
    from orders.services import cancel_order

    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": stocked, "quantity": "24"}]
    )
    assert credit_exposure(credit_customer) > Decimal("0.00")
    cancel_order(actor=owner, order=order, reason="Retailer changed mind")
    assert credit_exposure(credit_customer) == Decimal("0.00")


def test_a_customer_with_no_ledger_entries_shows_zero_not_none(credit_customer):
    """R-1, in the module its own text predicted would need it."""
    from ledger.selectors import outstanding_balances

    assert settled_balance(credit_customer) == Decimal("0.00")
    balances = {c.pk: c.balance for c in outstanding_balances()}
    assert balances[credit_customer.pk] == Decimal("0.00"), "must not vanish from the report"


# --------------------------------------------------------------------------- A-14 / D-8
def test_credit_is_re_evaluated_at_dispatch(owner, credit_customer, stocked, profile):
    """D-8. The limit is lowered after confirmation; dispatch must notice."""
    update_business_profile(actor=owner, credit_limit_mode=BusinessProfile.CreditMode.BLOCK)
    order = _order(owner, credit_customer, stocked, quantity="24")

    # Approved at confirmation against a 10,000 limit.
    set_credit_limit(actor=owner, customer=credit_customer, amount=Decimal("100.00"))
    credit_customer.refresh_from_db()

    delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
    with pytest.raises(CreditLimitExceeded):
        dispatch_delivery(actor=owner, delivery=delivery)


def test_a_blocked_dispatch_writes_no_stock(owner, credit_customer, stocked, profile):
    """The check runs before anything is written, so a refusal leaves no partial state."""
    from inventory.selectors import on_hand_for

    update_business_profile(actor=owner, credit_limit_mode=BusinessProfile.CreditMode.BLOCK)
    order = _order(owner, credit_customer, stocked)
    set_credit_limit(actor=owner, customer=credit_customer, amount=Decimal("1.00"))
    credit_customer.refresh_from_db()

    before = on_hand_for(stocked)
    delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
    with pytest.raises(CreditLimitExceeded):
        dispatch_delivery(actor=owner, delivery=delivery)
    assert on_hand_for(stocked) == before


def test_the_owner_may_override_a_blocked_dispatch_with_a_reason(
    owner, credit_customer, stocked, profile
):
    """Refusing outright teaches staff to dispatch and record nothing (ADR-0006)."""
    from core.models import AuditLog

    update_business_profile(actor=owner, credit_limit_mode=BusinessProfile.CreditMode.BLOCK)
    order = _order(owner, credit_customer, stocked)
    set_credit_limit(actor=owner, customer=credit_customer, amount=Decimal("1.00"))
    credit_customer.refresh_from_db()

    delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
    dispatch_delivery(
        actor=owner, delivery=delivery, override_reason="Long-standing customer, owner approved"
    )

    order.refresh_from_db()
    assert order.credit_override_at is not None
    assert AuditLog.objects.filter(
        action=AuditLog.Action.CREDIT_OVERRIDE, entity_id=order.pk
    ).exists()


def test_warn_mode_lets_dispatch_proceed(owner, credit_customer, stocked, profile):
    update_business_profile(actor=owner, credit_limit_mode=BusinessProfile.CreditMode.WARN)
    order = _order(owner, credit_customer, stocked)
    set_credit_limit(actor=owner, customer=credit_customer, amount=Decimal("1.00"))
    credit_customer.refresh_from_db()

    delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
    dispatched = dispatch_delivery(actor=owner, delivery=delivery)
    assert dispatched.dispatched_at is not None


def test_dispatch_uses_the_same_function_as_capture():
    """PO-6 applied to credit: one measurement, two call sites, no second implementation."""
    import ast
    from pathlib import Path

    import fulfilment

    source = (Path(fulfilment.__file__).parent / "services.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "orders.services"
        for alias in node.names
    }
    assert "evaluate_credit" in imported
    assert "credit_exposure" not in source, "fulfilment must not recompute exposure itself"


# --------------------------------------------------------------------------- A-3
def test_numbers_are_gapless_and_unique(owner, credit_customer, stocked):
    numbers = []
    for _ in range(5):
        order = _order(owner, credit_customer, stocked, quantity="1")
        _dispatch(owner, order)
        numbers.append(issue_invoice(actor=owner, order=order).invoice_number)

    assert len(set(numbers)) == 5, "no duplicates"
    tail = [int(n.rsplit("/", 1)[-1]) for n in numbers]
    assert tail == list(range(1, 6)), f"gapless: {tail}"


def test_a_rolled_back_document_releases_its_number(owner, credit_customer, stocked):
    """Gapless and never-reused are in tension; the resolution releases both together."""
    from django.db import transaction

    order = _order(owner, credit_customer, stocked)
    _dispatch(owner, order)

    with pytest.raises(RuntimeError), transaction.atomic():
        issue_invoice(actor=owner, order=order)
        raise RuntimeError("simulated failure after allocation")

    assert not Invoice.objects.exists()
    invoice = issue_invoice(actor=owner, order=order)
    assert invoice.invoice_number.endswith("00001"), "the released number is reused, unissued"


def test_each_financial_year_starts_a_new_series(db):
    """April to March. Series do not continue across years (04 T-06)."""
    assert financial_year_for(date(2026, 4, 1)) == "2026-2027"
    assert financial_year_for(date(2027, 3, 31)) == "2026-2027"
    assert financial_year_for(date(2027, 4, 1)) == "2027-2028"

    _, first = allocate_number(series_key=NumberSeries.Key.INVOICE, on=date(2026, 6, 1))
    _, second = allocate_number(series_key=NumberSeries.Key.INVOICE, on=date(2027, 6, 1))
    assert first.endswith("00001")
    assert second.endswith("00001"), "a new year restarts at one"
    assert first != second, "but the prefix differs, so the numbers do not collide"


def test_invoice_and_credit_note_have_independent_series(db):
    _, invoice_number = allocate_number(series_key=NumberSeries.Key.INVOICE, on=date(2026, 6, 1))
    _, note_number = allocate_number(series_key=NumberSeries.Key.CREDIT_NOTE, on=date(2026, 6, 1))
    assert invoice_number.startswith("INV/")
    assert note_number.startswith("CN/")


def test_an_unknown_series_is_refused(db):
    with pytest.raises(ValidationFailed):
        allocate_number(series_key="NOT_A_SERIES", on=date(2026, 6, 1))


# --------------------------------------------------------------------------- A-4
def test_total_credited_never_exceeds_the_invoice(owner, credit_customer, stocked):
    """B-7 / FR-BIL-016 — an aggregate invariant, enforced under a row lock."""
    order = _order(owner, credit_customer, stocked, quantity="24")
    _dispatch(owner, order)
    invoice = issue_invoice(actor=owner, order=order)
    line = invoice.lines.first()

    issue_credit_note(
        actor=owner,
        invoice=invoice,
        lines=[{"invoice_line": line, "quantity": Decimal("20")}],
        reason="Twenty returned",
    )
    with pytest.raises(ValidationFailed, match="exceed the invoice value"):
        issue_credit_note(
            actor=owner,
            invoice=invoice,
            lines=[{"invoice_line": line, "quantity": Decimal("20")}],
            reason="Twenty more, which do not exist",
        )
    assert credited_total(invoice) < invoice.total_amount


def test_cannot_credit_more_units_than_were_invoiced(owner, credit_customer, stocked):
    order = _order(owner, credit_customer, stocked, quantity="24")
    _dispatch(owner, order)
    invoice = issue_invoice(actor=owner, order=order)
    with pytest.raises(ValidationFailed, match="more than was invoiced"):
        issue_credit_note(
            actor=owner,
            invoice=invoice,
            lines=[{"invoice_line": invoice.lines.first(), "quantity": Decimal("25")}],
            reason="Impossible",
        )


def test_a_credit_note_line_must_belong_to_its_invoice(owner, credit_customer, stocked):
    first = _order(owner, credit_customer, stocked, quantity="5")
    second = _order(owner, credit_customer, stocked, quantity="5")
    _dispatch(owner, first)
    _dispatch(owner, second)
    invoice_one = issue_invoice(actor=owner, order=first)
    invoice_two = issue_invoice(actor=owner, order=second)

    with pytest.raises(ValidationFailed, match="does not belong"):
        issue_credit_note(
            actor=owner,
            invoice=invoice_one,
            lines=[{"invoice_line": invoice_two.lines.first(), "quantity": Decimal("1")}],
            reason="Wrong invoice",
        )
