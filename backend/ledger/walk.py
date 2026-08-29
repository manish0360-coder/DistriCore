"""The FIFO application walk — one algorithm, both ledgers (M6 §5A, D5 Stage 4 S4.2).

**This module is a lift, not a rewrite.** Every line of the algorithm below was moved
verbatim from ``receivables.selectors``, where it was written at M6, verified, and has been
held to a randomised invariant ever since. The only edits were to replace four hard-coded
``CustomerLedgerEntry.Type`` members with the ``WalkPolicy`` that names them, and to rename
``customer_id`` to ``party_id``. Nothing about ordering, pairing, spill, tie-breaking or
ageing was touched, and ``tests/unit/test_fifo_walk.py`` runs unchanged against the customer
side to prove it.

**Why it is here and not in ``receivables``.** The supplier ledger needs the same walk, and
``receivables`` sits two layers above ``purchasing`` — so a supplier consumer could never
import it there. ``ledger`` is beneath both:

    receivables  ─┐
                  ├──▶  ledger.walk
    purchasing   ─┘

**It imports nothing — not even ``ledger.models``.** The rows it reads are described by a
``Protocol``, so both ``CustomerLedgerEntry`` and ``SupplierLedgerEntry`` satisfy it
structurally with no conversion layer and no copying. A module with no imports cannot
acquire an upward dependency by accident.

**Three roles, not two**, and the third is the one that is easy to miss:

* a **reducing** entry (a credit note, or its payables mirror) reduces the *specific*
  document it references — it is a fact about that document's value, so uniform FIFO would
  report the wrong figure against a statutory document;
* a **settling** entry (a payment, a write-off) settles the account oldest-first;
* an **annulling** entry cancels its target, and *both* leave the walk. Treating a payment
  reversal as an ordinary positive entry would create a fresh, zero-day-old debt and launder
  genuinely aged debt into new debt — in a tool whose only purpose is to show which debt is
  oldest.

The invariant that keeps this honest, asserted over randomised sequences for both ledgers:

    Σ open.remaining - credit_on_account ≡ Σ entry.amount
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol

ZERO = Decimal("0.00")


class LedgerRow(Protocol):
    """What the walk reads from an entry, and the whole of it.

    Structural rather than nominal on purpose: ``CustomerLedgerEntry`` and
    ``SupplierLedgerEntry`` both satisfy this already, so neither ledger needs an adapter
    and the walk needs no import from ``ledger.models``. Unsaved instances work too, which
    is what lets the algorithm be tested without a database.
    """

    pk: int
    entry_date: date
    entry_type: str
    amount: Decimal
    narration: str
    source_document_type: str
    source_document_id: int | None


@dataclass(frozen=True)
class WalkPolicy:
    """The four entry-type codes the algorithm needs named, and nothing else.

    **Everything that differs between the two ledgers is here**, which is the point: if a
    third ledger ever appears, it supplies four strings rather than a second algorithm.

    The codes are deliberately *not* inferred from the model enums. Both spell ``PAYMENT``
    and ``ADJUSTMENT`` identically today, and a shared lookup keyed on bare strings would
    silently merge two accounting vocabularies the first time one of them diverged — the
    same hazard ``ledger.services`` records for ``_SUPPLIER_SIGN_RULES``.
    """

    #: The type that can annul another entry. Both ledgers call it ``ADJUSTMENT``.
    adjustment_type: str
    #: Source-document types an adjustment may annul. In each case the pointed-at
    #: document's type is *also* the target entry's ``entry_type``, which is what makes the
    #: lookup in ``annulled_entry_ids`` a single dictionary hit.
    annullable_source_types: tuple[str, ...]
    #: The type that reduces one specific document — ``CREDIT_NOTE`` for receivables.
    reducing_type: str
    #: The debit type a reduction targets — ``INVOICE`` for receivables.
    target_type: str


@dataclass
class _Debit:
    """One open item during the walk. Mutable only inside ``walk``."""

    entry_id: int
    entry_date: date
    entry_type: str
    narration: str
    source_document_id: int | None
    original_amount: Decimal
    remaining: Decimal


@dataclass(frozen=True)
class OpenItem:
    """A document still owed against, with its age.

    **No display concerns.** Ageing *buckets* are presentation and stay with the consumer
    that renders them — `receivables` holds `AGING_BUCKET_DAYS` as three integers because
    `02A` §13.2 demoted a configurable bucket engine to Edition 2 (M6 C-2).
    """

    entry_id: int
    entry_date: date
    entry_type: str
    document: str
    original_amount: Decimal
    outstanding_amount: Decimal
    age_days: int


@dataclass(frozen=True)
class Position:
    """The derived position for one party at one instant.

    ``party_id`` rather than ``customer_id``: the same walk answers the question for a
    supplier, and a field named for one of the two would have to be misread for the other.
    """

    party_id: int
    as_of: date
    open_items: list[OpenItem] = field(default_factory=list)
    total_outstanding: Decimal = ZERO
    credit_on_account: Decimal = ZERO
    balance: Decimal = ZERO


def annulled_entry_ids(entries: Sequence[LedgerRow], policy: WalkPolicy) -> set[int]:
    """Primary keys of every entry that annuls another, plus every entry annulled.

    An invoice cancellation and its ``INVOICE`` entry sum to zero; so do a payment reversal
    and its ``PAYMENT`` entry. Both members of each pair leave the walk, which is what
    restores the settled invoices to outstanding **at their original ages** rather than as a
    fresh debt dated the day of the reversal.

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
    that produces a wrong number on input it did not expect is worse than one that produces
    a defensible number on any input at all.
    """
    unclaimed: dict[tuple[str, int], LedgerRow] = {
        (entry.source_document_type, entry.source_document_id): entry
        for entry in entries
        # The target of an annulment is the entry *created by* that document — an INVOICE
        # entry for an invoice, a PAYMENT entry for a payment.
        if entry.source_document_id is not None
        and entry.entry_type == entry.source_document_type
    }

    annulled: set[int] = set()
    for entry in entries:
        if entry.entry_type != policy.adjustment_type:
            continue
        if entry.source_document_type not in policy.annullable_source_types:
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


def walk(
    *,
    party_id: int,
    as_of: date,
    entries: Sequence[LedgerRow],
    reduction_targets: dict[int, int],
    policy: WalkPolicy,
) -> Position:
    """Apply credits to debits per M6 §5A.4. **Pure** — no database access.

    ``entries`` must already be filtered to ``entry_date <= as_of`` and ordered by
    ``(entry_date, id)``. ``reduction_targets`` maps a reducing document's primary key to
    the debit document it references — for receivables, a credit note to its invoice.
    """
    # --- 1. ANNUL ------------------------------------------------------------
    # **Computed once, deliberately.** A comprehension re-evaluates its condition for every
    # element, so calling `annulled_entry_ids(entries)` inside the `if` ran it once per
    # entry — O(n²), with a fresh dict and set allocated each time. At the DR-8 envelope
    # that was ~10.6 million entry-visits across 1,000 customers and **11.7 seconds**,
    # breaching FR-RPT-015 (M7 §10.1). The suite never saw it: at tens of entries a
    # quadratic and a linear walk are indistinguishable.
    #
    # The function is pure — it reads `entries` and builds only local structures — so
    # hoisting cannot change the answer. §5A.7's invariant holds unchanged.
    #
    # Do not inline this again.
    annulled = annulled_entry_ids(entries, policy)
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
    debit_by_target: dict[int, _Debit] = {
        d.source_document_id: d
        for d in debits
        if d.entry_type == policy.target_type and d.source_document_id is not None
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
    # reason `annulled_entry_ids` claims its targets instead of merely looking them up.
    #
    # It is also the right answer when it does fire: crediting more than a document is
    # worth leaves the party in credit on account, which is what `pool` becomes.
    pool = ZERO
    for entry in live:
        if entry.entry_type != policy.reducing_type:
            continue
        target_pk = reduction_targets.get(entry.source_document_id or 0)
        target_debit = debit_by_target.get(target_pk) if target_pk else None
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
        (abs(e.amount) for e in live if e.amount < ZERO and e.entry_type != policy.reducing_type),
        ZERO,
    )
    for debit in debits:  # already ordered (entry_date, id) — M6-8
        if pool <= ZERO:
            break
        applied = min(pool, debit.remaining)
        debit.remaining -= applied
        pool -= applied

    # --- 5. RESULT -----------------------------------------------------------
    open_items = [
        OpenItem(
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
    total = sum((item.outstanding_amount for item in open_items), ZERO)
    return Position(
        party_id=party_id,
        as_of=as_of,
        open_items=open_items,
        total_outstanding=total,
        credit_on_account=pool,
        balance=total - pool,
    )
