"""Receivables read queries — **the customer half of the FIFO application walk** (M6 §5A, D-9).

Nothing here is stored. Which invoices are outstanding is a *view*, recomputed from
immutable inputs whenever someone asks — the third derived quantity in the system after
stock on hand (M2) and the settled balance (M5).

**The algorithm moved to `ledger.walk` at D5 Stage 4 (S4.2) and is not duplicated here.**
It was not rewritten: the annulment pairing, the targeted reduce before any settling, the
FIFO order, the spill and the tie-break are the same lines, with four hard-coded type
members replaced by the `WalkPolicy` this module supplies. `tests/unit/test_fifo_walk.py`
runs against `_walk` **unchanged**, which is what proves the customer answer did not move.

It moved because the supplier ledger needs the same walk, and `purchasing` sits two layers
below `receivables` — it could never have imported it from here.

**Three roles, not two.** The walk classifies every ledger entry as *reducing*, *settling*
or **annulling**, and the third is the one that is easy to miss:

* a **credit note** reduces the invoice it references — it is a fact about that document's
  value, so uniform FIFO would report the wrong figure against a statutory document;
* a **payment** settles the account oldest-first;
* a **reversal or cancellation annuls its target**, and *both* leave the walk. Treating a
  payment reversal as an ordinary positive entry would create a fresh, zero-day-old debt
  and launder genuinely aged debt into new debt — in a tool whose only purpose is to show
  which debt is oldest.

The invariant that keeps this honest, asserted over randomised sequences:

    Σ outstanding.remaining - credit_on_account ≡ settled_balance(customer, as_of)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, NamedTuple

from django.db.models import Q, QuerySet, Sum
from django.db.models.functions import Coalesce

from core.fields import MoneyField
from core.permissions import Role, has_role
from customers.models import Customer
from ledger.models import CustomerLedgerEntry
from ledger.selectors import settled_balance
from ledger.walk import LedgerRow, LedgerRowTuple, WalkPolicy
from ledger.walk import walk as ledger_walk
from receivables.models import Payment

ZERO = Decimal("0.00")

#: Display constants, not configuration (M6 C-2). `02A` §13.2 demoted a configurable
#: bucket engine to Edition 2; OI-4's boundaries live here as three integers.
AGING_BUCKET_DAYS: tuple[int, int, int] = (30, 60, 90)


# --------------------------------------------------------------------------- the walk
#
# **The algorithm itself moved to `ledger.walk` at S4.2 and is not reimplemented here.**
# It is unchanged — the same annulment pairing, the same targeted reduce before any
# settling, the same FIFO order, the same spill, the same tie-break. What stayed behind is
# everything specific to *customers*: the four type codes below, the display shapes the API
# and the reports already consume, and the two queries that feed the walk.
#
# It moved because `purchasing` needs the same walk and sits two layers below
# `receivables`, so it could never have imported it from here.


#: The customer vocabulary, handed to a walk that knows none of it.
_CUSTOMER_POLICY = WalkPolicy(
    adjustment_type=CustomerLedgerEntry.Type.ADJUSTMENT,
    # An ADJUSTMENT annuls its target when it points at one of these. In both cases the
    # pointed-at document's type is *also* the target entry's ``entry_type``.
    annullable_source_types=(
        CustomerLedgerEntry.Type.INVOICE,  # invoice cancellation
        CustomerLedgerEntry.Type.PAYMENT,  # payment reversal
    ),
    reducing_type=CustomerLedgerEntry.Type.CREDIT_NOTE,
    target_type=CustomerLedgerEntry.Type.INVOICE,
)


@dataclass(frozen=True)
class OutstandingItem:
    """A document the customer still owes against, with its age."""

    entry_id: int
    entry_date: date
    entry_type: str
    document: str
    original_amount: Decimal
    outstanding_amount: Decimal
    age_days: int

    @property
    def bucket(self) -> str:
        """Which display bucket this age falls in (C-2 — constants, not configuration)."""
        first, second, third = AGING_BUCKET_DAYS
        if self.age_days <= first:
            return f"0-{first}"
        if self.age_days <= second:
            return f"{first + 1}-{second}"
        if self.age_days <= third:
            return f"{second + 1}-{third}"
        return f"{third}+"


@dataclass(frozen=True)
class CustomerPosition:
    """The derived receivables position for one customer at one instant."""

    customer_id: int
    as_of: date
    outstanding: list[OutstandingItem] = field(default_factory=list)
    total_outstanding: Decimal = ZERO
    credit_on_account: Decimal = ZERO
    balance: Decimal = ZERO

    @property
    def oldest(self) -> OutstandingItem | None:
        """What `/reports/receivables` shows beside the balance (05 §9.7)."""
        return self.outstanding[0] if self.outstanding else None


def _walk(
    *,
    customer_id: int,
    as_of: date,
    entries: Sequence[LedgerRow],
    credit_note_targets: dict[int, int],
) -> CustomerPosition:
    """The customer view of the shared walk (M6 §5A).

    **The signature is unchanged from M6 on purpose.** `tests/unit/test_fifo_walk.py` — the
    randomised invariant suite and every §5A.9 edge case — calls this function directly, and
    the extraction is only trustworthy if that suite runs against it **without a single
    edit**. An identical signature is what makes "before and after are identical" a thing
    the existing tests assert rather than a thing this comment claims.

    ``entries`` was annotated ``list[CustomerLedgerEntry]`` until M10.6b and is now
    ``Sequence[LedgerRow]`` — **strictly wider**, and narrower than what it delegates to was
    an accident rather than a rule: ``ledger.walk.walk`` has always taken the Protocol.
    Every existing caller still type-checks and behaves identically, because
    ``CustomerLedgerEntry`` satisfies ``LedgerRow``; parameter names and order are untouched,
    so the suite above still runs without an edit.

    All it does now is name the customer vocabulary and rename the result. The algorithm
    lives in `ledger.walk`, below `purchasing`, so the supplier ledger can reach the same
    code instead of growing a second copy of it.
    """
    position = ledger_walk(
        party_id=customer_id,
        as_of=as_of,
        entries=entries,
        reduction_targets=credit_note_targets,
        policy=_CUSTOMER_POLICY,
    )
    return CustomerPosition(
        customer_id=position.party_id,
        as_of=position.as_of,
        # `OutstandingItem` carries `bucket`, which `ledger.walk` deliberately does not:
        # ageing buckets are display, and M6 C-2 keeps them here as three integers.
        outstanding=[
            OutstandingItem(
                entry_id=item.entry_id,
                entry_date=item.entry_date,
                entry_type=item.entry_type,
                document=item.document,
                original_amount=item.original_amount,
                outstanding_amount=item.outstanding_amount,
                age_days=item.age_days,
            )
            for item in position.open_items
        ],
        total_outstanding=position.total_outstanding,
        credit_on_account=position.credit_on_account,
        balance=position.balance,
    )


def _credit_note_targets(entries: Sequence[LedgerRow]) -> dict[int, int]:
    """Map credit-note primary keys to the invoices they reference.

    **One query for the whole set**, never one per credit note (§5A.11). Resolved through
    ``billing`` rather than through ``sales_order_id``, because that shortcut depends on
    one-invoice-per-order — an Edition 1 constraint Edition 2 drops — and would not
    resolve a credit note against a direct counter sale, whose invoice has no order
    (§5A.10, E-8).
    """
    from billing.models import CreditNote

    ids = {
        e.source_document_id
        for e in entries
        if e.entry_type == CustomerLedgerEntry.Type.CREDIT_NOTE and e.source_document_id
    }
    if not ids:
        return {}
    return dict(CreditNote.objects.filter(pk__in=ids).values_list("pk", "invoice_id"))


def outstanding_for(customer: Customer, *, as_of: date | None = None) -> CustomerPosition:
    """The derived outstanding position for one customer (M6 §5A)."""
    as_of = as_of or date.today()
    entries = list(
        CustomerLedgerEntry.objects.filter(customer=customer, entry_date__lte=as_of).order_by(
            "entry_date", "id"
        )
    )
    return _walk(
        customer_id=customer.pk,
        as_of=as_of,
        entries=entries,
        credit_note_targets=_credit_note_targets(entries),
    )


def visible_customers_for_receivables(actor: Any) -> QuerySet[Customer]:
    """Customers whose balance the caller may see.

    `05` §8 gives ledger and balance to salesmen and delivery staff for **their own
    zones** — a different predicate from payments, which they see only for what **they
    collected**. The two must not be collapsed into one helper.
    """
    base = Customer.objects.filter(is_active=True)
    if has_role(actor, Role.OWNER):
        return base.order_by("shop_name")
    if has_role(actor, Role.SALESMAN, Role.DELIVERY):
        return base.filter(zone__assigned_user=actor).order_by("shop_name")
    if has_role(actor, Role.RETAILER):
        return base.filter(pk=getattr(actor, "customer_id", None) or 0)
    return base.none()


class CustomerLabel(NamedTuple):
    """The two fields a receivables row shows beside a position: code and shop name."""

    code: str
    shop_name: str


def visible_customer_labels(actor: Any) -> dict[int, CustomerLabel]:
    """Codes and shop names for the customers this actor may see, by primary key.

    **Both consumers of ``receivables_position`` need to label its rows**, and both were
    doing it by materialising every visible ``Customer`` a second time — the report and the
    web-admin screen each fetched 10,000 model instances that ``receivables_position`` had
    already fetched and discarded, to read two ``CharField``s.

    One selector rather than two identical dictionary comprehensions: the duplication was
    what let the cost hide in two places at once. Visibility is still decided by
    ``visible_customers_for_receivables`` and nowhere else, so `05` §8's scoping and BR-003
    are unchanged.
    """
    return {
        pk: CustomerLabel(code=code, shop_name=shop_name)
        for pk, code, shop_name in visible_customers_for_receivables(actor).values_list(
            "pk", "code", "shop_name"
        )
    }


def receivables_position(
    actor: Any, *, as_of: date | None = None, include_settled: bool = False
) -> list[CustomerPosition]:
    """Every visible customer's position (FR-REC-008/009).

    **Three queries for the whole set** — customers, their ledger entries, and the
    credit-note mapping — applied in memory. None is per customer and none is per
    document; the only real risk to the <10 s budget was always N+1 (§5A.11).

    R-1: anchored on ``Customer``, so with ``include_settled`` a customer who owes nothing
    appears with a zero position rather than vanishing from a report the owner acts on.
    """
    as_of = as_of or date.today()
    # **Ids, not instances.** Only `pk` is read from a customer here, and the ordering of
    # `visible_customers_for_receivables` — `shop_name` — is preserved by `values_list`, so
    # the positions come back in exactly the order they did before.
    customer_ids = list(visible_customers_for_receivables(actor).values_list("pk", flat=True))
    if not customer_ids:
        return []

    # **`LedgerRowTuple`, not `CustomerLedgerEntry`** (M10.6b). The walk reads seven
    # attributes through `ledger.walk.LedgerRow`; at the DR-8 envelope this query returns
    # 373,000 rows, and building a Django model for each — field descriptors, `_state`,
    # deferred loading, a `from_db_value` per Decimal and per date — was the dominant cost
    # behind `receivables ageing` at 17.139 s (`docs/M10.6_Performance_Report.md` §7).
    #
    # `ORDER BY (customer_id, entry_date, id)` is unchanged and still matches
    # `ix_cle_customer_date`; the M6-8 tie-break inside the walk is untouched.
    #
    # **Not `.iterator()`**, deliberately. It would avoid holding the raw tuples alongside
    # the rows built from them, but it opens a server-side cursor whose chunked `FETCH`es
    # can register as further queries — which would make "three queries for the whole set"
    # depend on the database configuration rather than on this code. The saving is tens of
    # megabytes of transient tuples; the cost would be a contract that means something
    # different in two environments.
    #
    # **This is not a shortcut** (M7-4): the same rows, in the same order, reach the same
    # algorithm. Only the container changed.
    rows = (
        CustomerLedgerEntry.objects.filter(customer_id__in=customer_ids, entry_date__lte=as_of)
        .order_by("customer_id", "entry_date", "id")
        .values_list(
            "customer_id",
            "id",
            "entry_date",
            "entry_type",
            "amount",
            "narration",
            "source_document_type",
            "source_document_id",
        )
    )

    grouped: dict[int, list[LedgerRow]] = {customer_id: [] for customer_id in customer_ids}
    entries: list[LedgerRow] = []
    for customer_id, *values in rows:
        entry = LedgerRowTuple._make(values)
        entries.append(entry)
        grouped[customer_id].append(entry)

    targets = _credit_note_targets(entries)

    positions = [
        _walk(
            customer_id=customer_id,
            as_of=as_of,
            entries=grouped[customer_id],
            credit_note_targets=targets,
        )
        for customer_id in customer_ids
    ]
    if include_settled:
        return positions
    return [p for p in positions if p.outstanding or p.credit_on_account]


# --------------------------------------------------------------------------- statement
@dataclass(frozen=True)
class Statement:
    """Opening, entries, closing — `05` §9.6."""

    customer_id: int
    date_from: date | None
    date_to: date
    opening_balance: Decimal
    entries: list[CustomerLedgerEntry]
    closing_balance: Decimal


def customer_statement(
    customer: Customer, *, date_from: date | None = None, date_to: date | None = None
) -> Statement:
    """A period statement whose closing figure is the next period's opening figure.

    Opening is the balance **strictly before** ``date_from``; closing is the balance as at
    ``date_to``. Both come from the same ``SUM`` over the same immutable rows, so
    successive periods reconcile exactly by construction — there is no separate running
    total that could drift out of step with the ledger.
    """
    date_to = date_to or date.today()
    queryset = CustomerLedgerEntry.objects.filter(
        customer=customer, entry_date__lte=date_to
    ).select_related("created_by")

    opening = ZERO
    if date_from is not None:
        opening = settled_balance(customer, as_of=date_from - timedelta(days=1))
        queryset = queryset.filter(entry_date__gte=date_from)

    return Statement(
        customer_id=customer.pk,
        date_from=date_from,
        date_to=date_to,
        opening_balance=opening,
        entries=list(queryset.order_by("entry_date", "id")),
        closing_balance=settled_balance(customer, as_of=date_to),
    )


# --------------------------------------------------------------------------- payments
def visible_payments(actor: Any) -> QuerySet[Payment]:
    """Payments the caller may see (05 §8).

    **Salesmen and delivery staff see what they collected**, not their whole zone. That is
    a narrower predicate than the ledger's and is deliberate: a collection is money that
    passed through a specific person's hands (FR-REC-012).
    """
    base = Payment.objects.select_related("customer", "received_by")
    if has_role(actor, Role.OWNER):
        return base
    if has_role(actor, Role.SALESMAN, Role.DELIVERY):
        return base.filter(received_by=actor)
    if has_role(actor, Role.RETAILER):
        return base.filter(customer_id=getattr(actor, "customer_id", None) or 0)
    return base.none()


def search_payments(
    actor: Any,
    *,
    customer_id: int | None = None,
    method: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_reversed: bool = True,
) -> QuerySet[Payment]:
    queryset = visible_payments(actor)
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if method:
        queryset = queryset.filter(method=method)
    if date_from is not None:
        queryset = queryset.filter(payment_date__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(payment_date__lte=date_to)
    if not include_reversed:
        queryset = queryset.filter(is_reversed=False)
    return queryset


def get_payment_for(actor: Any, payment_id: int) -> Payment | None:
    """Scope violations look like absence, never like refusal (05 §4.1)."""
    return visible_payments(actor).filter(pk=payment_id).first()


def collections_by_user(
    *, date_from: date | None = None, date_to: date | None = None
) -> QuerySet[Payment]:
    """Collections grouped by collector and method (FR-REC-012, and M7's Cash/UPI split).

    Anchored on the payment deliberately: this reports on collections that *happened*, so
    a user who collected nothing correctly contributes nothing. R-1 governs balances, not
    event counts — the same distinction M2 drew for ``variance_by_reason``.
    """
    queryset = Payment.objects.filter(is_reversed=False)
    if date_from is not None:
        queryset = queryset.filter(payment_date__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(payment_date__lte=date_to)
    return (
        queryset.values("received_by__id", "received_by__full_name", "method")
        .annotate(total=Coalesce(Sum("amount"), ZERO, output_field=MoneyField()))
        .order_by("received_by__full_name", "method")
    )


def collected_total(customer: Customer) -> Decimal:
    """What this customer has actually paid, ignoring reversed collections.

    R-1: anchored on ``Customer`` and coalesced to a typed zero, so a customer who has
    never paid returns ``0.00`` rather than ``None``.
    """
    row = (
        Customer.objects.filter(pk=customer.pk)
        .annotate(
            paid=Coalesce(
                Sum("payments__amount", filter=Q(payments__is_reversed=False)),
                ZERO,
                output_field=MoneyField(),
            )
        )
        .values_list("paid", flat=True)
        .first()
    )
    return row if row is not None else ZERO
