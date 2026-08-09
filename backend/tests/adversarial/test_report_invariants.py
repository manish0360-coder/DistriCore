"""**The M7 invariants, and one deliberate non-invariant** (M7 §5.2, §5.3).

I-1 … I-4 guard against a report re-deriving a figure a domain already owns (AR-3). I-5 and
I-6 are the two that would rot silently: nothing fails loudly when a CSV drifts from its
screen, or when a closed period quietly starts answering differently.

**I-7 is the one that earns its place.** It ties the returns report to the sales report, so
the credit-note half of D-1 cannot be implemented twice with two different answers — the
exact failure §1.1 says destroys trust in every other number.

§5.3's non-invariant is asserted here as a *comment with teeth*: a test that documents why
returns and stock variance must never be asserted equal.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

import pytest
from django.utils import timezone

from billing.selectors import invoice_lines
from billing.services import issue_credit_note, issue_invoice
from fulfilment.services import assign_delivery, dispatch_delivery, fail_delivery
from inventory.services import receive_stock
from ledger.selectors import settled_balance
from orders.services import confirm_order, place_order
from receivables import selectors as receivable_selectors
from reporting import csv as report_csv
from reporting import selectors as reports

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]

TODAY = date(2026, 8, 8)
MONTH_START = date(2026, 8, 1)
MONTH_END = date(2026, 8, 31)


@pytest.fixture
def stocked(owner, product, receipt_reason):
    """Goods received at a **pinned** instant (see `test_report_selectors.py`).

    ``receive_stock`` defaults ``occurred_at`` to ``timezone.now()``, and
    ``test_returns_and_variance_are_allowed_to_disagree`` bounds its period with hard-coded
    August dates. Unpinned, that assertion would have started failing on 1 September while
    the code under test had not changed at all.
    """
    receive_stock(
        actor=owner,
        product=product,
        quantity=Decimal("1000"),
        reason_code=receipt_reason,
        occurred_at=timezone.make_aware(datetime.combine(TODAY, time.min)),
    )
    return product


def _dispatched_order(owner, customer, product, units: str):
    order = place_order(
        actor=owner, customer=customer, lines=[{"product": product, "quantity": units}]
    )
    confirm_order(actor=owner, order=order)
    delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
    dispatch_delivery(actor=owner, delivery=delivery)
    return order, delivery


@pytest.fixture
def trading(owner, credit_customer, stocked, damage_reason):
    """Two invoices and one credit note, all inside August."""
    first, _ = _dispatched_order(owner, credit_customer, stocked, "24")
    second, _ = _dispatched_order(owner, credit_customer, stocked, "10")
    issue_invoice(actor=owner, order=first, invoice_date=TODAY)
    invoice = issue_invoice(actor=owner, order=second, invoice_date=TODAY)
    issue_credit_note(
        actor=owner,
        invoice=invoice,
        lines=[{"invoice_line": invoice_lines(invoice).first(), "quantity": Decimal("2")}],
        reason="Damaged in transit.",
        reason_code=damage_reason,
        credit_note_date=TODAY,
    )
    return invoice


# ----------------------------------------------------------------------------------- I-1
@pytest.mark.parametrize("group_by", reports.SALES_GROUPINGS)
def test_i1_the_sales_total_is_the_same_under_every_grouping(owner, trading, group_by):
    """A ``group_by`` that changes the answer is a join defect, and joins are where they hide.

    Grouping by product goes through the invoice *lines*; the other three go through the
    documents. That the two paths agree is the whole point of asserting this per grouping
    rather than once.
    """
    table = reports.sales_report(
        owner, date_from=MONTH_START, date_to=MONTH_END, group_by=group_by
    )
    assert table.total["sales"] == Decimal("3200.00"), group_by
    assert sum(row["sales"] for row in table.rows) == table.total["sales"], group_by


# ----------------------------------------------------------------------------------- I-2
def test_i2_the_receivables_report_agrees_with_the_ledger(owner, trading, credit_customer):
    """The report and M6's walk must not disagree — §5A.7 surfacing at the read layer."""
    table = reports.receivables_ageing(owner)
    positions = receivable_selectors.receivables_position(owner)
    assert table.total["balance"] == sum(p.balance for p in positions)
    assert table.total["balance"] == settled_balance(credit_customer)


# ----------------------------------------------------------------------------------- I-3
def test_i3_the_stock_report_adds_no_arithmetic(owner, trading, stocked):
    from inventory.selectors import on_hand_for

    table = reports.stock_position(owner)
    row = next(r for r in table.rows if r["code"] == stocked.code)
    assert row["on_hand"] == on_hand_for(stocked)


# ----------------------------------------------------------------------------------- I-4
def test_i4_every_order_appears_in_exactly_one_state(owner, trading):
    from orders.selectors import visible_orders

    table = reports.order_pipeline(owner)
    assert table.total["orders"] == visible_orders(owner).count()


# ----------------------------------------------------------------------------------- I-5
@pytest.mark.parametrize(
    "build",
    [
        lambda actor: reports.sales_report(actor, date_from=MONTH_START, date_to=MONTH_END),
        lambda actor: reports.stock_position(actor),
        lambda actor: reports.stock_variance(actor, date_from=MONTH_START, date_to=MONTH_END),
        lambda actor: reports.returns_report(actor, date_from=MONTH_START, date_to=MONTH_END),
        lambda actor: reports.receivables_ageing(actor),
        lambda actor: reports.top_customers(actor, date_from=MONTH_START, date_to=MONTH_END),
        lambda actor: reports.order_pipeline(actor),
    ],
)
def test_i5_csv_content_is_screen_content(owner, trading, build):
    """One query, two renderings.

    Asserted per report rather than in general, because the failure mode is *one* report
    growing its own exporter — and a general test would still pass while it did.
    """
    table = build(owner)
    lines = report_csv.render(table).splitlines()
    # The renderer owns the definition of "this line is prose"; the test reads it rather
    # than restating it, so the two cannot disagree about where the data starts.
    body = [line for line in lines if not line.startswith(report_csv.COMMENT_PREFIX)]

    assert body[0] == ",".join(column.label for column in table.columns)
    data = body[1:-1] if table.total else body[1:]
    assert len(data) == len(table.rows), f"{table.key}: CSV row count differs from the screen"
    for row, rendered in zip(table.rows, data, strict=True):
        for column in table.columns:
            value = row.get(column.key)
            if value not in (None, ""):
                assert str(value) in rendered, f"{table.key}.{column.key} missing from the CSV"


# ----------------------------------------------------------------------------------- I-6
def test_i6_a_closed_period_answers_the_same_on_any_later_day(
    owner, credit_customer, stocked, trading, damage_reason
):
    """Append-only inputs plus an explicit period.

    July is closed. Trading in August — including a credit note against a July invoice —
    must not move July's figure, or every reconciliation the owner has already performed
    becomes unverifiable.
    """
    july = (date(2026, 7, 1), date(2026, 7, 31))
    order, _ = _dispatched_order(owner, credit_customer, stocked, "5")
    july_invoice = issue_invoice(actor=owner, order=order, invoice_date=date(2026, 7, 10))

    before = reports.sales_report(owner, date_from=july[0], date_to=july[1]).total["sales"]

    later, _ = _dispatched_order(owner, credit_customer, stocked, "7")
    issue_invoice(actor=owner, order=later, invoice_date=TODAY)
    issue_credit_note(
        actor=owner,
        invoice=july_invoice,
        lines=[{"invoice_line": invoice_lines(july_invoice).first(), "quantity": Decimal("1")}],
        reason="Returned in August, against a July invoice.",
        reason_code=damage_reason,
        credit_note_date=TODAY,
    )

    after = reports.sales_report(owner, date_from=july[0], date_to=july[1]).total["sales"]
    assert after == before, "a closed period was restated"


# ----------------------------------------------------------------------------------- I-7
def test_i7_the_returns_total_is_the_credit_deduction_inside_sales(owner, trading):
    """The load-bearing tie between two reports that read the same documents.

    If these diverge, one of them reads credit notes wrongly — and the owner has two
    figures for one question, which §1.1 says is the failure that costs trust in all of
    them.
    """
    sales = reports.sales_report(owner, date_from=MONTH_START, date_to=MONTH_END)
    returns = reports.returns_report(owner, date_from=MONTH_START, date_to=MONTH_END)
    assert returns.total["credited"] == sales.total["credited"]
    assert sales.total["sales"] == sales.total["invoiced"] - returns.total["credited"]


@pytest.mark.parametrize("group_by", ["reason", "customer"])
def test_i7_holds_under_either_returns_grouping(owner, trading, group_by):
    sales = reports.sales_report(owner, date_from=MONTH_START, date_to=MONTH_END)
    returns = reports.returns_report(
        owner, date_from=MONTH_START, date_to=MONTH_END, group_by=group_by
    )
    assert returns.total["credited"] == sales.total["credited"]


# ------------------------------------------------------------------- the NON-invariant
def test_returns_and_variance_are_allowed_to_disagree(
    owner, credit_customer, stocked, trading, sales_return_reason
):
    """**§5.3. This test exists so that nobody writes its opposite.**

    A credit note writes no stock movement (ADR-0009) and a failed delivery writes no
    credit note. Here both happen: goods come back on an uninvoiced order, and a separate
    credit note is issued against a different invoice.

    Asserting these two totals equal would encode the join ADR-0009 removed on purpose. It
    would then fail — correctly — on the first uninvoiced delivery failure, at which point
    someone would "fix" the reports to satisfy the test. Recording the non-invariant is
    cheaper than recovering from that.
    """
    _, delivery = _dispatched_order(owner, credit_customer, stocked, "6")
    fail_delivery(actor=owner, delivery=delivery, reason="Shop shut; goods returned to van.")

    variance = reports.stock_variance(owner, date_from=MONTH_START, date_to=MONTH_END)
    returns = reports.returns_report(owner, date_from=MONTH_START, date_to=MONTH_END)

    # The physical trace saw the failed delivery.
    assert any(row["quantity"] != Decimal("0.000") for row in variance.rows)
    # The financial trace did not: no invoice existed, so nothing was credited for it.
    assert returns.total["credited"] == Decimal("200.00")
    # And each report says which trace it is, because this is exactly the moment the
    # owner asks why they differ (AR-7).
    assert any("PHYSICAL" in note for note in variance.notes)
    assert any("FINANCIAL" in note for note in returns.notes)
