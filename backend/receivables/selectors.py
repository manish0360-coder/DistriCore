"""Receivables read queries, including **the FIFO application walk** (M6 §5A, D-9).

Nothing here is stored. Which invoices are outstanding is a *view*, recomputed from
immutable inputs whenever someone asks — the third derived quantity in the system after
stock on hand (M2) and the settled balance (M5).

**Three roles, not two.** The walk classifies every ledger entry as *reducing*,
*settling* or **annulling**, and the third is the one that is easy to miss:

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

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Q, QuerySet, Sum
from django.db.models.functions import Coalesce

from core.fields import MoneyField
from core.permissions import Role, has_role
from customers.models import Customer
from ledger.models import CustomerLedgerEntry
from ledger.selectors import settled_balance
from receivables.models import Payment

ZERO = Decimal("0.00")

#: Display constants, not configuration (M6 C-2). `02A` §13.2 demoted a configurable
#: bucket engine to Edition 2; OI-4's boundaries live here as three integers.
AGING_BUCKET_DAYS: tuple[int, int, int] = (30, 60, 90)


# --------------------------------------------------------------------------- the walk
@dataclass
class _Debit:
    """One open item during the walk. Mutable only inside ``_walk``."""

    entry_id: int
    entry_date: date
    entry_type: str
    narration: str
    source_document_id: int | None
    original_amount: Decimal
    remaining: Decimal


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


#: An ADJUSTMENT annuls its target when it points at one of these. In both cases the
#: pointed-at document's type is *also* the target entry's ``entry_type``, which is what
#: makes the lookup in ``_annulled_entry_ids`` a single dictionary hit.
_ANNULLABLE_SOURCES = (
    CustomerLedgerEntry.Type.INVOICE,  # invoice cancellation
    CustomerLedgerEntry.Type.PAYMENT,  # payment reversal
)


def _annulled_entry_ids(entries: list[CustomerLedgerEntry]) -> set[int]:
    """Primary keys of every entry that annuls another, plus every entry annulled.

    An invoice cancellation and its ``INVOICE`` entry sum to zero; so do a payment
    reversal and its ``PAYMENT`` entry. Both members of each pair leave the walk, which is
    what restores the settled invoices to outstanding **at their original ages** rather
    than as a fresh debt dated the day of the reversal.

    **Annulment is a PAIR, and this function is where that is enforced** (§5A.3).

    Two properties are required, and §5A.7's proof depends on both — it excludes annulled
    entries from *both* sides of the invariant, which is only sound when what leaves is
    exactly a matched, offsetting couple:

    * **One annuller claims one target.** A target is consumed when matched, so a second
      annuller pointing at the same document finds nothing and stays in the walk as an
      ordinary entry. Without this, two annullers and one target — three entries — leave
      together, and the walk silently loses one amount.
    * **The pair must offset.** If the amounts do not sum to zero it is not a reversal of
      that entry, and removing both would discard a net figure the balance still contains.

    Neither malformed shape is reachable through the services: ``cancel_invoice`` and
    ``reverse_payment`` each lock the row, return early if already done, and write a
    compensating entry of exactly the original amount — and the database triggers refuse a
    second transition independently. **The guards are here anyway**, because a read model
    that produces a wrong number on input it did not expect is worse than one that
    produces a defensible number on any input at all.
    """
    unclaimed: dict[tuple[str, int], CustomerLedgerEntry] = {
        (entry.source_document_type, entry.source_document_id): entry
        for entry in entries
        # The target of an annulment is the entry *created by* that document — an INVOICE
        # entry for an invoice, a PAYMENT entry for a payment.
        if entry.source_document_id is not None
        and entry.entry_type == entry.source_document_type
    }

    annulled: set[int] = set()
    for entry in entries:
        if entry.entry_type != CustomerLedgerEntry.Type.ADJUSTMENT:
            continue
        if entry.source_document_type not in _ANNULLABLE_SOURCES:
            continue  # a manual adjustment annuls nothing
        if entry.source_document_id is None:
            # An annulment with no document to point at annuls nothing. Previously this
            # fell through to the lookup below and missed, because every key in
            # `unclaimed` carries a non-null id — same outcome, one branch later. Stated
            # here so the key is provably `tuple[str, int]`, which is what the dict holds.
            continue
        key = (entry.source_document_type, entry.source_document_id)
        target = unclaimed.get(key)
        if target is None:
            continue  # already claimed by an earlier annuller, or no such document
        if entry.amount + target.amount != ZERO:
            continue  # does not offset, so it is not an annulment of this entry
        del unclaimed[key]  # claimed: one annuller, one target
        annulled.add(entry.pk)
        annulled.add(target.pk)
    return annulled


def _walk(
    *,
    customer_id: int,
    as_of: date,
    entries: list[CustomerLedgerEntry],
    credit_note_targets: dict[int, int],
) -> CustomerPosition:
    """Apply credits to debits per M6 §5A.4. **Pure** — no database access.

    ``entries`` must already be filtered to ``entry_date <= as_of`` and ordered by
    ``(entry_date, id)``. ``credit_note_targets`` maps a credit note's primary key to the
    invoice it references.
    """
    # --- 1. ANNUL ------------------------------------------------------------
    # **Computed once, deliberately.** A comprehension re-evaluates its condition for every
    # element, so calling `_annulled_entry_ids(entries)` inside the `if` ran it once per
    # entry — O(n²), with a fresh dict and set allocated each time. At the DR-8 envelope
    # that was ~10.6 million entry-visits across 1,000 customers and **11.7 seconds**,
    # breaching FR-RPT-015 (M7 §10.1). The suite never saw it: at tens of entries a
    # quadratic and a linear walk are indistinguishable.
    #
    # The function is pure — it reads `entries` and builds only local structures — so
    # hoisting cannot change the answer. §5A.7's invariant holds unchanged.
    #
    # Do not inline this again.
    annulled = _annulled_entry_ids(entries)
    live = [e for e in entries if e.pk not in annulled]

    # --- 2. DEBITS -----------------------------------------------------------
    debits = [
        _Debit(
            entry_id=e.pk,
            entry_date=e.entry_date,
            entry_type=e.entry_type,
            narration=e.narration,
            source_document_id=e.source_document_id,
            original_amount=e.amount,
            remaining=e.amount,
        )
        for e in live
        if e.amount > ZERO
    ]
    debit_by_invoice: dict[int, _Debit] = {
        d.source_document_id: d
        for d in debits
        if d.entry_type == CustomerLedgerEntry.Type.INVOICE and d.source_document_id is not None
    }

    # --- 3. REDUCE (targeted) — before any settling --------------------------
    # A credit note establishes what an invoice was ever worth; a payment settles what is
    # owed. Reducing first fixes the net value before money is applied to it.
    #
    # **A credit reduces its target by at most what the target is worth; the rest spills
    # into the settling pool.** Every rupee is accounted for either way, so a debit's
    # `remaining` is never driven negative — which matters because step 5 keeps only
    # positive remainders, and a negative one would be silently discarded from the total
    # while still sitting in the ledger SUM.
    #
    # M5's B-7 caps *total* credited against an invoice at its value under a row lock, so
    # in production the spill is always zero and this is arithmetically identical to a
    # plain subtraction (§5A.5 property 1). The spill is here because a read model must
    # hold its own invariant rather than trust one enforced in another module — the same
    # reason `_annulled_entry_ids` claims its targets instead of merely looking them up.
    #
    # It is also the right answer when it does fire: crediting more than a document is
    # worth leaves the customer in credit on account, which is what `pool` becomes.
    pool = ZERO
    for entry in live:
        if entry.entry_type != CustomerLedgerEntry.Type.CREDIT_NOTE:
            continue
        invoice_pk = credit_note_targets.get(entry.source_document_id or 0)
        target_debit = debit_by_invoice.get(invoice_pk) if invoice_pk else None
        credited = abs(entry.amount)
        if target_debit is None:
            # Unresolvable target — an annulled invoice, or a note whose invoice is
            # outside the as_of window. Settle it FIFO rather than lose it.
            pool += credited
            continue
        applied = min(credited, target_debit.remaining)
        target_debit.remaining -= applied
        pool += credited - applied

    # --- 4. SETTLE (untargeted, FIFO) ---------------------------------------
    pool += sum(
        (
            abs(e.amount)
            for e in live
            if e.amount < ZERO and e.entry_type != CustomerLedgerEntry.Type.CREDIT_NOTE
        ),
        ZERO,
    )
    for debit in debits:  # already ordered (entry_date, id) — M6-8
        if pool <= ZERO:
            break
        applied = min(pool, debit.remaining)
        debit.remaining -= applied
        pool -= applied

    # --- 5. RESULT -----------------------------------------------------------
    outstanding = [
        OutstandingItem(
            entry_id=d.entry_id,
            entry_date=d.entry_date,
            entry_type=d.entry_type,
            document=d.narration,
            original_amount=d.original_amount,
            outstanding_amount=d.remaining,
            age_days=(as_of - d.entry_date).days,
        )
        for d in debits
        if d.remaining > ZERO
    ]
    total = sum((item.outstanding_amount for item in outstanding), ZERO)
    return CustomerPosition(
        customer_id=customer_id,
        as_of=as_of,
        outstanding=outstanding,
        total_outstanding=total,
        credit_on_account=pool,
        balance=total - pool,
    )


def _credit_note_targets(entries: list[CustomerLedgerEntry]) -> dict[int, int]:
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
    customers = list(visible_customers_for_receivables(actor))
    if not customers:
        return []

    entries = list(
        CustomerLedgerEntry.objects.filter(
            customer__in=customers, entry_date__lte=as_of
        ).order_by("customer_id", "entry_date", "id")
    )
    targets = _credit_note_targets(entries)

    grouped: dict[int, list[CustomerLedgerEntry]] = {c.pk: [] for c in customers}
    for entry in entries:
        grouped[entry.customer_id].append(entry)

    positions = [
        _walk(
            customer_id=customer.pk,
            as_of=as_of,
            entries=grouped[customer.pk],
            credit_note_targets=targets,
        )
        for customer in customers
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
