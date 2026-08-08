"""The seven reports and the four dashboard numbers, against the worked scenario.

M7 §5.1 is reproduced exactly — same customer, same four documents, same expected figure —
so that the design review's arithmetic and the code's arithmetic are checked against each
other rather than each against itself.

The invariants I-1 … I-7 live in ``tests/adversarial/test_report_invariants.py``. This file
asserts the figures; that one asserts the properties.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from billing.selectors import invoice_lines
from billing.services import cancel_invoice, issue_credit_note, issue_invoice
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.services import receive_stock
from orders.services import confirm_order, place_order
from reporting import selectors as reports

pytestmark = pytest.mark.django_db

TODAY = date(2026, 8, 8)
MONTH_START = date(2026, 8, 1)
MONTH_END = date(2026, 8, 31)


# --------------------------------------------------------------------------- scaffolding
def _invoice(owner, customer, product, *, units: str, invoice_date: date = TODAY):
    """One order, dispatched and invoiced. A new order each time: delivery is 1:1 (M5)."""
    order = place_order(
        actor=owner, customer=customer, lines=[{"product": product, "quantity": units}]
    )
    confirm_order(actor=owner, order=order)
    delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
    dispatch_delivery(actor=owner, delivery=delivery)
    return issue_invoice(actor=owner, order=order, invoice_date=invoice_date)


@pytest.fixture
def stocked(owner, product, receipt_reason):
    receive_stock(
        actor=owner, product=product, quantity=Decimal("1000"), reason_code=receipt_reason
    )
    return product


@pytest.fixture
def august(owner, credit_customer, stocked, damage_reason):
    """M7 §5.1 — August 2026, customer C-0142, product at 100.00 plus 18% GST.

    | INV/00001 | 24 units | issued    | taxable 2,400 |
    | INV/00002 | 10 units | issued    | taxable 1,000 |
    | INV/00003 |  5 units | CANCELLED | taxable   500 |
    | CN/00001  |  2 units | against INV/00002 | (200) |

    Sales under D-1 option C: 2,400 + 1,000 - 200 = 3,200.00
    """
    first = _invoice(owner, credit_customer, stocked, units="24")
    second = _invoice(owner, credit_customer, stocked, units="10")
    third = _invoice(owner, credit_customer, stocked, units="5")
    cancel_invoice(actor=owner, invoice=third, reason="Raised against the wrong shop.")
    credit = issue_credit_note(
        actor=owner,
        invoice=second,
        lines=[{"invoice_line": invoice_lines(second).first(), "quantity": Decimal("2")}],
        reason="Two cases damaged in transit.",
        reason_code=damage_reason,
        credit_note_date=TODAY,
    )
    return {"first": first, "second": second, "cancelled": third, "credit": credit}


def _total(table, key="sales"):
    return table.total[key]


# --------------------------------------------------------------------------------- sales
def test_the_worked_scenario_produces_the_documented_figure(owner, august):
    """M7 §5.1. 2,400 + 1,000 - 200 = 3,200.00, and not the 3,776.00 option A would give."""
    table = reports.sales_report(owner, date_from=MONTH_START, date_to=MONTH_END)
    assert _total(table) == Decimal("3200.00")


def test_a_cancelled_invoice_is_absent_from_both_halves(owner, august):
    """D-1: a cancelled invoice records a sale that did not happen.

    It is not a negative in the month of cancellation — that is what a credit note is for.
    500.00 must appear in neither the invoiced column nor the credited one.
    """
    table = reports.sales_report(owner, date_from=MONTH_START, date_to=MONTH_END)
    assert _total(table, "invoiced") == Decimal("3400.00")
    assert _total(table, "credited") == Decimal("200.00")


def test_gst_is_excluded(owner, august):
    """Tax is collected on behalf of the government; it was never the distributor's money."""
    table = reports.sales_report(owner, date_from=MONTH_START, date_to=MONTH_END)
    assert _total(table) == Decimal("3200.00")
    assert _total(table) != Decimal("3776.00")


def test_the_definition_travels_with_the_report(owner, august):
    table = reports.sales_report(owner, date_from=MONTH_START, date_to=MONTH_END)
    assert "ISSUED" in table.definition
    assert "GST and round-off are excluded" in table.definition


def test_a_credit_note_counts_in_the_period_it_was_issued(
    owner, credit_customer, stocked, damage_reason
):
    """§4.1.1, and the reason is I-6.

    A credit note raised in August against a July invoice reduces August. Restating July
    would make a closed period's figure change after the fact, and a figure that can change
    after the fact cannot be reconciled by hand.
    """
    july = date(2026, 7, 15)
    invoice = _invoice(owner, credit_customer, stocked, units="10", invoice_date=july)
    issue_credit_note(
        actor=owner,
        invoice=invoice,
        lines=[{"invoice_line": invoice_lines(invoice).first(), "quantity": Decimal("2")}],
        reason="Returned in August.",
        reason_code=damage_reason,
        credit_note_date=TODAY,
    )

    july_table = reports.sales_report(
        owner, date_from=date(2026, 7, 1), date_to=date(2026, 7, 31)
    )
    august_table = reports.sales_report(owner, date_from=MONTH_START, date_to=MONTH_END)

    assert _total(july_table) == Decimal("1000.00"), "July must not be restated"
    assert _total(august_table) == Decimal("-200.00"), "August carries the credit"


def test_a_period_whose_only_activity_is_a_credit_is_not_dropped(
    owner, credit_customer, stocked, damage_reason
):
    """A month with negative sales is a real month, and the one the owner needs to see."""
    invoice = _invoice(owner, credit_customer, stocked, units="10", invoice_date=date(2026, 7, 1))
    issue_credit_note(
        actor=owner,
        invoice=invoice,
        lines=[{"invoice_line": invoice_lines(invoice).first(), "quantity": Decimal("1")}],
        reason="Late return.",
        credit_note_date=TODAY,
    )
    table = reports.sales_report(owner, date_from=MONTH_START, date_to=MONTH_END)
    assert table.rows, "the credit-only period produced no rows"
    assert _total(table) == Decimal("-100.00")


def test_an_unknown_grouping_falls_back_rather_than_failing(owner, august):
    table = reports.sales_report(owner, group_by="category")
    assert table.group_by == "day"


# ------------------------------------------------------------------------------- returns
def test_the_returns_report_is_the_financial_trace(owner, august):
    """D-2. Credit notes, at taxable value — 200.00 from the worked scenario."""
    table = reports.returns_report(owner, date_from=MONTH_START, date_to=MONTH_END)
    assert table.total["credited"] == Decimal("200.00")
    assert table.total["documents"] == 1


def test_an_uncategorised_credit_is_shown_not_hidden(
    owner, credit_customer, stocked
):
    """`credit_note.reason_code` is nullable — it drives no behaviour, so M5 left it optional.

    A returns total that silently excluded uncategorised credits would be wrong in a
    direction the reader cannot see.
    """
    invoice = _invoice(owner, credit_customer, stocked, units="10")
    issue_credit_note(
        actor=owner,
        invoice=invoice,
        lines=[{"invoice_line": invoice_lines(invoice).first(), "quantity": Decimal("3")}],
        reason="No reason code recorded.",
        credit_note_date=TODAY,
    )
    table = reports.returns_report(owner, date_from=MONTH_START, date_to=MONTH_END)
    labels = [row["label"] for row in table.rows]
    assert reports.UNCATEGORISED in labels
    assert table.total["credited"] == Decimal("300.00")


def test_the_returns_report_states_what_it_reduced(owner, august):
    """The reconciliation that is *true* — I-7, rendered (§17.1 layer 2)."""
    table = reports.returns_report(owner, date_from=MONTH_START, date_to=MONTH_END)
    assert "reduced Sales for this period by 200.00" in table.definition


def test_returns_can_be_grouped_by_customer(owner, august):
    table = reports.returns_report(
        owner, date_from=MONTH_START, date_to=MONTH_END, group_by="customer"
    )
    assert table.group_by == "customer"
    assert table.total["credited"] == Decimal("200.00")


# --------------------------------------------------------------------------------- stock
def test_the_stock_reports_carry_no_money_column(owner, august):
    """C-7. There is no cost basis; a valuation would be wrong rather than missing."""
    for table in (
        reports.stock_position(owner),
        reports.stock_variance(owner, date_from=MONTH_START, date_to=MONTH_END),
    ):
        labels = " ".join(column.label for column in table.columns).lower()
        assert "value" not in labels
        assert "valuation" not in labels
        assert any("cost basis" in note for note in table.notes)


def test_stock_position_reports_quantity_on_hand(owner, august, stocked):
    """1000 received, 39 dispatched across three orders."""
    table = reports.stock_position(owner)
    row = next(r for r in table.rows if r["code"] == stocked.code)
    assert row["on_hand"] == Decimal("961.000")


def test_stock_variance_reports_units_and_reasons(owner, august, stocked, receipt_reason):
    table = reports.stock_variance(owner, date_from=MONTH_START, date_to=MONTH_END)
    codes = {row["code"] for row in table.rows}
    assert receipt_reason.code in codes


def test_stock_variance_can_be_filtered_to_one_reason(owner, august, receipt_reason):
    table = reports.stock_variance(
        owner, date_from=MONTH_START, date_to=MONTH_END, reason_code=receipt_reason.code
    )
    assert {row["code"] for row in table.rows} == {receipt_reason.code}


def test_the_last_day_of_a_period_is_included(owner, credit_customer, stocked, receipt_reason):
    """M7-3 against a timestamp column.

    ``occurred_at`` is an instant and the bound is a date. Comparing them naively drops
    everything after midnight on the closing day — a whole day, silently, every time.
    """
    table = reports.stock_variance(owner, date_from=TODAY, date_to=TODAY)
    assert table.rows, "movements recorded today fell outside a period that includes today"


# --------------------------------------------------------------------------- receivables
def test_receivables_ageing_reuses_m6s_walk_and_buckets(owner, august, credit_customer):
    table = reports.receivables_ageing(owner)
    row = next(r for r in table.rows if r["code"] == credit_customer.code)
    assert row["bucket"] == "0-30"
    assert row["outstanding"] > Decimal("0.00")


# -------------------------------------------------------------------------- top customers
def test_top_customers_ranks_on_the_net_figure(owner, august, credit_customer):
    table = reports.top_customers(owner, date_from=MONTH_START, date_to=MONTH_END)
    assert table.rows[0]["rank"] == 1
    assert table.rows[0]["sales"] == Decimal("3200.00")


def test_the_limit_is_bounded(owner, august):
    """A caller-supplied limit is a size hint, not a licence to page the whole table."""
    assert len(reports.top_customers(owner, limit=10_000).rows) <= 100
    assert reports.top_customers(owner, limit=0).title.startswith("Top 1 ")


# ------------------------------------------------------------------------------- pipeline
def test_the_order_pipeline_counts_every_visible_order_once(owner, august):
    table = reports.order_pipeline(owner)
    assert table.total["orders"] == 3


# ------------------------------------------------------------------------------ dashboard
def test_the_dashboard_shows_exactly_four_numbers(owner, august):
    """D-4 / M7-8. Four questions; adding a fifth is a design change, not a tweak."""
    board = reports.dashboard(owner, today=TODAY)
    assert len(board.metrics) == 4
    assert [m.key for m in board.metrics] == [
        "sales_today",
        "collected_today",
        "total_outstanding",
        "awaiting_dispatch",
    ]


def test_sales_and_collections_are_separate_numbers(owner, august):
    """M5 split dispatch from invoicing and M6 split payment from invoice.

    One merged "revenue" figure would undo both, on the one screen the owner reads daily.
    """
    board = reports.dashboard(owner, today=TODAY)
    values = {m.key: m.value for m in board.metrics}
    assert values["sales_today"] == Decimal("3200.00")
    assert values["collected_today"] == Decimal("0.00")


def test_the_live_figures_are_marked_as_live(owner, august):
    """I-6 does not apply to them, and the screen must say so."""
    board = reports.dashboard(owner, today=TODAY)
    live = {m.key for m in board.metrics if m.is_live}
    assert live == {"sales_today", "collected_today"}


def test_awaiting_dispatch_counts_confirmed_orders_only(
    owner, credit_customer, stocked, august
):
    board = reports.dashboard(owner, today=TODAY)
    awaiting = next(m for m in board.metrics if m.key == "awaiting_dispatch")
    assert awaiting.value == 0, "every order in the fixture has already been dispatched"

    place_order(
        actor=owner, customer=credit_customer, lines=[{"product": stocked, "quantity": "1"}]
    )
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": stocked, "quantity": "2"}]
    )
    confirm_order(actor=owner, order=order)

    board = reports.dashboard(owner, today=TODAY)
    awaiting = next(m for m in board.metrics if m.key == "awaiting_dispatch")
    assert awaiting.value == 1, "PLACED is not yet agreed and must not be counted"


# ------------------------------------------------------------------------------ statement
def test_the_statement_exports_through_the_same_mechanism(owner, august, credit_customer):
    """C-6: the sixth report, delivered at M6. M7 adds only the export."""
    table = reports.statement_table(credit_customer)
    assert table.rows
    assert table.total["narration"] == "Closing balance"


def test_an_empty_period_is_an_answer_not_an_error(owner, august):
    """Reports are read constantly and often over quiet periods."""
    quiet = date(2020, 1, 1)
    table = reports.sales_report(owner, date_from=quiet, date_to=quiet)
    assert table.rows == ()
    assert _total(table) == Decimal("0.00")
