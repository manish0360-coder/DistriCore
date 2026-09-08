"""**M10.6b — the bulk position path must answer exactly what the per-customer path does.**

`receivables_position` stopped materialising `CustomerLedgerEntry` instances. At the DR-8
envelope it was building **373,000** Django models — field descriptors, `_state`, deferred
loading, a `from_db_value` per `Decimal` and per date — to read the seven attributes
`ledger.walk.LedgerRow` declares. `receivables ageing` took **17.139 s** against
FR-RPT-015's ten-second budget, and `dashboard` inherited 16.874 s of it
(`docs/M10.6_Performance_Report.md` §3, §7).

**A performance change to a money path needs an oracle, not a plausibility argument.**

`outstanding_for` is deliberately **not** optimised: it walks one customer, it is small, and
it still fetches real model instances. That makes it an independent implementation of the
same question, and the equivalence below is the strongest guard available — stronger than
any assertion about expected numbers, because it compares two code paths rather than a code
path against a constant somebody typed.

The query-count contracts are the regression guard for the *second* defect: two consumers
were each re-fetching every visible `Customer` that `receivables_position` had already
fetched and thrown away.

**BR-005 is untouched.** Nothing is stored, nothing is cached, and every figure below is
still derived by walking immutable entries on each call.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from billing.services import issue_credit_note, issue_invoice
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.services import receive_stock
from ledger.models import CustomerLedgerEntry
from ledger.walk import LedgerRow, LedgerRowTuple
from orders.services import confirm_order, place_order
from receivables import selectors as receivable_selectors
from receivables.services import record_payment, reverse_payment
from reporting import selectors as reports

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]


@pytest.fixture
def trading_ledger(owner, credit_customer, product, receipt_reason, damage_reason):
    """One customer with all four entry roles present: invoice, credit note, payment, reversal.

    Every branch of the walk has to be reachable, or the equivalence below would prove only
    that two paths agree on the easy case. A reversal is included because annulment removes
    a **pair** and is the branch most sensitive to what an entry object is.
    """
    receive_stock(actor=owner, product=product, quantity=Decimal("500"), reason_code=receipt_reason)

    def invoice(units: str):
        order = place_order(
            actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": units}]
        )
        confirm_order(actor=owner, order=order)
        delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
        dispatch_delivery(actor=owner, delivery=delivery)
        return issue_invoice(actor=owner, order=order)

    first = invoice("10")
    second = invoice("4")
    issue_credit_note(
        actor=owner,
        invoice=second,
        lines=[{"invoice_line": second.lines.first(), "quantity": Decimal("1")}],
        reason="One case damaged in transit.",
        reason_code=damage_reason,
    )
    record_payment(actor=owner, customer=credit_customer, amount=Decimal("100.00"), method="CASH")
    reversed_payment = record_payment(
        actor=owner, customer=credit_customer, amount=Decimal("50.00"), method="CASH"
    )
    reverse_payment(actor=owner, payment=reversed_payment, reason="Cheque bounced.")
    return {"first": first, "second": second}


# ------------------------------------------------------- the equivalence, against an oracle
def test_the_bulk_path_agrees_with_the_per_customer_path(owner, trading_ledger, credit_customer):
    """**The oracle.** `outstanding_for` is untouched and answers the same question.

    Field by field, including the open items in order: FIFO is an *ordering* rule, so two
    paths agreeing on totals while disagreeing on which document is oldest would satisfy a
    weaker test and break the only screen this report exists for.
    """
    bulk = {
        position.customer_id: position
        for position in receivable_selectors.receivables_position(owner, include_settled=True)
    }
    oracle = receivable_selectors.outstanding_for(credit_customer)
    position = bulk[credit_customer.pk]

    assert position.total_outstanding == oracle.total_outstanding
    assert position.credit_on_account == oracle.credit_on_account
    assert position.balance == oracle.balance
    assert position.as_of == oracle.as_of
    assert [
        (
            item.entry_id,
            item.entry_date,
            item.entry_type,
            item.document,
            item.original_amount,
            item.outstanding_amount,
            item.age_days,
        )
        for item in position.outstanding
    ] == [
        (
            item.entry_id,
            item.entry_date,
            item.entry_type,
            item.document,
            item.original_amount,
            item.outstanding_amount,
            item.age_days,
        )
        for item in oracle.outstanding
    ], "the two paths disagree on the open items or their FIFO order"


def test_the_two_paths_agree_at_a_historical_as_of(owner, trading_ledger, credit_customer):
    """`as_of` filters the rows the walk sees. Both paths must filter identically."""
    as_of = date.today()
    bulk = next(
        position
        for position in receivable_selectors.receivables_position(
            owner, as_of=as_of, include_settled=True
        )
        if position.customer_id == credit_customer.pk
    )
    oracle = receivable_selectors.outstanding_for(credit_customer, as_of=as_of)
    assert bulk.total_outstanding == oracle.total_outstanding
    assert bulk.balance == oracle.balance


# ----------------------------------------------------------------- the row type itself
def test_the_lightweight_row_satisfies_the_walk_protocol():
    """Anti-vacuity. If `LedgerRowTuple` lost a field the walk would fail at a distance.

    **Read from the properties, not from `__annotations__`.** `LedgerRow`'s members are
    read-only `@property` declarations — a bare `pk: int` in a `Protocol` is PEP 544's
    *settable* variable, which a `NamedTuple` cannot satisfy and which the walk never uses.
    A property-based Protocol has an empty `__annotations__`, so the original spelling of
    this contract would have passed over nothing at all.

    `vars()` preserves declaration order on every supported version, unlike
    `__protocol_attrs__` — which is a set, and does not exist before 3.12.
    """
    declared = tuple(name for name, value in vars(LedgerRow).items() if isinstance(value, property))
    assert declared, "`LedgerRow` declares no property members — this contract would be vacuous"
    assert LedgerRowTuple._fields == declared, (
        f"`LedgerRowTuple` no longer mirrors `LedgerRow`: {LedgerRowTuple._fields} vs {declared}"
    )
    assert declared == (
        "pk",
        "entry_date",
        "entry_type",
        "amount",
        "narration",
        "source_document_type",
        "source_document_id",
    ), "the walk's Protocol changed; the row that feeds it must change with it"

    # The property is what makes a NamedTuple acceptable, and what stops the walk assigning
    # to a caller's row. A member that reverts to a settable variable must fail here.
    for name in declared:
        assert isinstance(vars(LedgerRow)[name], property), (
            f"`LedgerRow.{name}` is no longer read-only. A settable member demands an "
            "assignment the walk never performs, and would refuse every NamedTuple row."
        )


def test_the_row_carries_decimal_not_float(owner, trading_ledger):
    """**P-3, and it is unrecoverable.** A float that has been sent cannot be un-sent.

    `values_list` returns whatever the field adapter builds. Asserting the type here rather
    than trusting it is the difference between a property and an assumption — money that
    round-trips through `float` is wrong in a way no later test would notice.
    """
    row = (
        CustomerLedgerEntry.objects.values_list(
            "id",
            "entry_date",
            "entry_type",
            "amount",
            "narration",
            "source_document_type",
            "source_document_id",
        )
        .order_by("id")
        .first()
    )
    assert row is not None, "no ledger entry to inspect — this contract would be vacuous"
    entry = LedgerRowTuple._make(row)
    assert isinstance(entry.amount, Decimal), f"amount arrived as {type(entry.amount).__name__}"
    assert not isinstance(entry.amount, float)
    assert isinstance(entry.entry_date, date)


# ------------------------------------------------------ the duplicate fetch must stay gone
def test_the_bulk_position_stays_at_three_queries(owner, trading_ledger, django_assert_num_queries):
    """*"Three queries for the whole set"* — customers, entries, credit-note map (§5A.11).

    A fourth would mean something became per-customer, which is the failure mode the M6
    design named in advance and the one that would not show up until the envelope.
    """
    with django_assert_num_queries(3):
        receivable_selectors.receivables_position(owner)


def test_the_ageing_report_does_not_refetch_the_customers(
    owner, trading_ledger, django_assert_num_queries
):
    """The report labels its rows from two `CharField`s, not from 10,000 model instances.

    Before M10.6b it called `visible_customers_for_receivables` a second time, materialising
    every visible `Customer` that `receivables_position` had already fetched and discarded.
    Four queries: the position's three, plus one for the labels.
    """
    with django_assert_num_queries(4):
        reports.receivables_ageing(owner)


def test_the_labels_come_from_the_visibility_selector(owner, trading_ledger, credit_customer):
    """BR-003 / `05` §8. Scoping is decided in one place and the labels inherit it."""
    labels = receivable_selectors.visible_customer_labels(owner)
    assert labels[credit_customer.pk].code == credit_customer.code
    assert labels[credit_customer.pk].shop_name == credit_customer.shop_name
    assert set(labels) == set(
        receivable_selectors.visible_customers_for_receivables(owner).values_list("pk", flat=True)
    ), "the label map and the visibility selector disagree about who is visible"
