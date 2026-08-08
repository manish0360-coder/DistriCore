"""The M6 §5A FIFO application walk.

``_walk`` is **pure** — it takes entries and a target map and returns a position, with no
database access. That is deliberate: this is the least "obviously correct" derived
quantity in the system (M6 §12.2), and an algorithm with ordering, partial consumption
and tie-breaking deserves tests that isolate it from persistence.

The §5A.9 edge cases are covered one per test, by their E-number.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from ledger.models import CustomerLedgerEntry
from receivables.selectors import _walk

AS_OF = date(2026, 8, 31)
#: The randomised sequence spans START .. START + 200 days, comfortably within AS_OF.
START = date(2026, 1, 1)
TYPE = CustomerLedgerEntry.Type


def entry(
    pk: int,
    day: date,
    entry_type: str,
    amount: str,
    *,
    source_type: str = "",
    source_id: int | None = None,
    narration: str = "",
) -> CustomerLedgerEntry:
    """An unsaved ledger entry. ``_walk`` never touches the database."""
    instance = CustomerLedgerEntry(
        customer_id=1,
        entry_date=day,
        entry_type=entry_type,
        amount=Decimal(amount),
        source_document_type=source_type,
        source_document_id=source_id,
        narration=narration or f"{entry_type} {pk}",
    )
    instance.pk = pk
    return instance


def walk(entries, targets=None):
    return _walk(
        customer_id=1, as_of=AS_OF, entries=entries, credit_note_targets=targets or {}
    )


def assert_invariant(position, entries):
    """§5A.7 — the property that ties the algorithm back to the SUM we already trust."""
    ledger_sum = sum((e.amount for e in entries), Decimal("0.00"))
    assert position.total_outstanding - position.credit_on_account == ledger_sum


# --------------------------------------------------------------------------- §5A.8
def test_the_worked_example_reproduces_exactly():
    """M6 §5A.8, to the paisa. A design document that runs cannot silently diverge."""
    entries = [
        entry(1, date(2026, 4, 1), TYPE.OPENING, "4500.00", narration="Opening balance"),
        entry(2, date(2026, 6, 10), TYPE.INVOICE, "2832.00", source_type="INVOICE", source_id=11,
              narration="Invoice INV/00001"),
        entry(3, date(2026, 7, 5), TYPE.INVOICE, "1180.00", source_type="INVOICE", source_id=12,
              narration="Invoice INV/00002"),
        entry(4, date(2026, 7, 8), TYPE.CREDIT_NOTE, "-180.00", source_type="CREDIT_NOTE",
              source_id=21, narration="Credit note CN/00001"),
        entry(5, date(2026, 7, 12), TYPE.PAYMENT, "-5000.00", source_type="PAYMENT", source_id=31,
              narration="Payment PAY-00000001"),
        entry(6, date(2026, 7, 20), TYPE.INVOICE, "900.00", source_type="INVOICE", source_id=13,
              narration="Invoice INV/00003"),
        entry(7, date(2026, 7, 22), TYPE.ADJUSTMENT, "-900.00", source_type="INVOICE",
              source_id=13, narration="Cancellation of INV/00003"),
        entry(8, date(2026, 8, 2), TYPE.PAYMENT, "-1000.00", source_type="PAYMENT", source_id=32,
              narration="Payment PAY-00000002"),
        entry(9, date(2026, 8, 6), TYPE.ADJUSTMENT, "1000.00", source_type="PAYMENT",
              source_id=32, narration="Reversal of PAY-00000002"),
    ]
    position = walk(entries, {21: 12})

    assert [(i.document, i.outstanding_amount, i.age_days) for i in position.outstanding] == [
        ("Invoice INV/00001", Decimal("2332.00"), 82),
        ("Invoice INV/00002", Decimal("1000.00"), 57),
    ]
    assert position.total_outstanding == Decimal("3332.00")
    assert position.credit_on_account == Decimal("0.00")
    assert_invariant(position, entries)


def test_the_cancelled_invoice_never_appears():
    """Not merely settled — absent. It was never owed."""
    entries = [
        entry(1, date(2026, 7, 20), TYPE.INVOICE, "900.00", source_type="INVOICE", source_id=13),
        entry(2, date(2026, 7, 22), TYPE.ADJUSTMENT, "-900.00", source_type="INVOICE",
              source_id=13),
    ]
    position = walk(entries)
    assert position.outstanding == []
    assert_invariant(position, entries)


def test_a_reversed_payment_restores_the_original_age():
    """**The defect writing §5A found.**

    Treated as an ordinary positive entry, the reversal would become a fresh debit dated
    the day of the reversal, and the 82-day-old invoice would reappear as 0 days old.
    That launders aged debt into new debt in a tool whose only purpose is to show which
    debt is oldest.
    """
    entries = [
        entry(1, date(2026, 6, 10), TYPE.INVOICE, "1000.00", source_type="INVOICE", source_id=11,
              narration="Invoice INV/00001"),
        entry(2, date(2026, 8, 2), TYPE.PAYMENT, "-1000.00", source_type="PAYMENT", source_id=31),
        entry(3, date(2026, 8, 6), TYPE.ADJUSTMENT, "1000.00", source_type="PAYMENT",
              source_id=31),
    ]
    position = walk(entries)

    assert len(position.outstanding) == 1
    item = position.outstanding[0]
    assert item.document == "Invoice INV/00001"
    assert item.outstanding_amount == Decimal("1000.00")
    assert item.age_days == 82, "the debt is 82 days old, not 25 days old"
    assert_invariant(position, entries)


# --------------------------------------------------------------------------- §5A.2
def test_a_credit_note_reduces_its_own_invoice_not_the_oldest():
    """§5A.2. Both rules give the right balance; only one gives the right document."""
    entries = [
        entry(1, date(2026, 1, 1), TYPE.INVOICE, "1000.00", source_type="INVOICE", source_id=11,
              narration="A"),
        entry(2, date(2026, 2, 1), TYPE.INVOICE, "1000.00", source_type="INVOICE", source_id=12,
              narration="B"),
        entry(3, date(2026, 2, 5), TYPE.CREDIT_NOTE, "-200.00", source_type="CREDIT_NOTE",
              source_id=21),
    ]
    position = walk(entries, {21: 12})

    outstanding = {i.document: i.outstanding_amount for i in position.outstanding}
    assert outstanding == {"A": Decimal("1000.00"), "B": Decimal("800.00")}
    assert_invariant(position, entries)


# --------------------------------------------------------------------------- §5A.9
def test_e1_no_entries():
    position = walk([])
    assert position.outstanding == []
    assert position.total_outstanding == Decimal("0.00")
    assert position.credit_on_account == Decimal("0.00")
    assert position.balance == Decimal("0.00")


def test_e2_only_an_opening_entry():
    """The view is over *debits*, not invoices. An opening balance is a debit."""
    entries = [entry(1, date(2026, 4, 1), TYPE.OPENING, "4500.00", narration="Opening balance")]
    position = walk(entries)
    assert position.outstanding[0].document == "Opening balance"
    assert position.outstanding[0].entry_type == TYPE.OPENING
    assert_invariant(position, entries)


def test_e3_overpayment_becomes_credit_on_account():
    entries = [
        entry(1, date(2026, 6, 1), TYPE.INVOICE, "500.00", source_type="INVOICE", source_id=11),
        entry(2, date(2026, 6, 2), TYPE.PAYMENT, "-800.00", source_type="PAYMENT", source_id=31),
    ]
    position = walk(entries)
    assert position.outstanding == []
    assert position.credit_on_account == Decimal("300.00")
    assert position.balance == Decimal("-300.00"), "in credit"
    assert_invariant(position, entries)


def test_e4_credit_note_settles_its_invoice_in_full():
    entries = [
        entry(1, date(2026, 6, 1), TYPE.INVOICE, "500.00", source_type="INVOICE", source_id=11),
        entry(2, date(2026, 6, 3), TYPE.CREDIT_NOTE, "-500.00", source_type="CREDIT_NOTE",
              source_id=21),
    ]
    position = walk(entries, {21: 11})
    assert position.outstanding == []
    assert position.credit_on_account == Decimal("0.00")
    assert_invariant(position, entries)


def test_e7_same_date_debits_are_tie_broken_by_id():
    """§5A.6 — without the tie-break the same inputs give different views on different days."""
    entries = [
        entry(1, date(2026, 6, 1), TYPE.INVOICE, "100.00", source_type="INVOICE", source_id=11,
              narration="first"),
        entry(2, date(2026, 6, 1), TYPE.INVOICE, "100.00", source_type="INVOICE", source_id=12,
              narration="second"),
        entry(3, date(2026, 6, 2), TYPE.PAYMENT, "-100.00", source_type="PAYMENT", source_id=31),
    ]
    position = walk(entries)
    assert [i.document for i in position.outstanding] == ["second"]
    assert_invariant(position, entries)


def test_e9_write_off_settles_the_oldest_first():
    entries = [
        entry(1, date(2026, 1, 1), TYPE.INVOICE, "100.00", source_type="INVOICE", source_id=11,
              narration="old"),
        entry(2, date(2026, 6, 1), TYPE.INVOICE, "100.00", source_type="INVOICE", source_id=12,
              narration="new"),
        entry(3, date(2026, 7, 1), TYPE.WRITE_OFF, "-100.00", narration="Write-off: bad debt"),
    ]
    position = walk(entries)
    assert [i.document for i in position.outstanding] == ["new"]
    assert_invariant(position, entries)


def test_e10_and_e11_manual_adjustments_annul_nothing():
    """A manual adjustment has no source document. Positive is a debit, negative settles."""
    entries = [
        entry(1, date(2026, 6, 1), TYPE.ADJUSTMENT, "250.00", narration="manual up"),
        entry(2, date(2026, 6, 2), TYPE.ADJUSTMENT, "-100.00", narration="manual down"),
    ]
    position = walk(entries)
    assert [(i.document, i.outstanding_amount) for i in position.outstanding] == [
        ("manual up", Decimal("150.00"))
    ]
    assert_invariant(position, entries)


def test_e12_entries_after_as_of_are_the_callers_responsibility():
    """``_walk`` trusts its input filter; ``outstanding_for`` applies ``entry_date <= as_of``."""
    entries = [entry(1, AS_OF, TYPE.INVOICE, "100.00", source_type="INVOICE", source_id=11)]
    position = walk(entries)
    assert position.outstanding[0].age_days == 0


def test_an_unresolvable_credit_note_falls_back_to_settling():
    """Defensive branch: §5A.5 property 2 makes this unreachable in production."""
    entries = [
        entry(1, date(2026, 6, 1), TYPE.INVOICE, "500.00", source_type="INVOICE", source_id=11),
        entry(2, date(2026, 6, 3), TYPE.CREDIT_NOTE, "-200.00", source_type="CREDIT_NOTE",
              source_id=99),
    ]
    position = walk(entries, {})  # no target mapping
    assert position.outstanding[0].outstanding_amount == Decimal("300.00")
    assert_invariant(position, entries)


# --------------------------------------------------------------------------- property
@pytest.mark.parametrize("seed", [1, 7, 42, 20260806, 999])
def test_the_invariant_holds_over_randomised_sequences(seed):
    """§5A.7 over every entry role, in random order and quantity.

    This is the test that makes an algorithmic view trustworthy: it ties the walk back to
    the one number the system already trusts — the SUM.
    """
    import random

    rng = random.Random(seed)
    entries: list[CustomerLedgerEntry] = []
    targets: dict[int, int] = {}
    pk = 0
    invoice_pk = 0

    for _ in range(rng.randint(5, 30)):
        pk += 1
        # A date offset, not a day-of-month. The previous line read
        # `date(2026, 1, 1 + rng.randint(0, 200))`, which asks January for its 201st day.
        day = START + timedelta(days=rng.randint(0, 200))
        choice = rng.choice(["invoice", "payment", "credit", "cancel", "reverse", "manual"])

        if choice == "invoice":
            invoice_pk += 1
            entries.append(
                entry(pk, day, TYPE.INVOICE, f"{rng.randint(100, 5000)}.00",
                      source_type="INVOICE", source_id=invoice_pk)
            )
        elif choice == "payment":
            entries.append(
                entry(pk, day, TYPE.PAYMENT, f"-{rng.randint(50, 3000)}.00",
                      source_type="PAYMENT", source_id=pk)
            )
        elif choice == "credit" and invoice_pk:
            target = rng.randint(1, invoice_pk)
            source = next(
                (e for e in entries if e.entry_type == TYPE.INVOICE
                 and e.source_document_id == target),
                None,
            )
            if source is None:
                continue
            # B-7: never more than the invoice.
            amount = min(Decimal(rng.randint(10, 500)), source.amount)
            targets[pk] = target
            entries.append(
                entry(pk, day, TYPE.CREDIT_NOTE, f"-{amount}", source_type="CREDIT_NOTE",
                      source_id=pk)
            )
        elif choice == "cancel" and invoice_pk:
            source = next(
                (e for e in entries
                 if e.entry_type == TYPE.INVOICE
                 and e.source_document_id not in set(targets.values())),
                None,
            )
            if source is None:
                continue
            entries.append(
                entry(pk, day, TYPE.ADJUSTMENT, f"-{source.amount}", source_type="INVOICE",
                      source_id=source.source_document_id)
            )
        elif choice == "reverse":
            source = next((e for e in entries if e.entry_type == TYPE.PAYMENT), None)
            if source is None:
                continue
            entries.append(
                entry(pk, day, TYPE.ADJUSTMENT, f"{abs(source.amount)}", source_type="PAYMENT",
                      source_id=source.source_document_id)
            )
        else:
            sign = "" if rng.random() > 0.5 else "-"
            entries.append(entry(pk, day, TYPE.ADJUSTMENT, f"{sign}{rng.randint(10, 400)}.00"))

    entries.sort(key=lambda e: (e.entry_date, e.pk))
    position = walk(entries, targets)

    assert_invariant(position, entries)
    assert all(i.outstanding_amount > 0 for i in position.outstanding)
    assert position.credit_on_account >= 0
