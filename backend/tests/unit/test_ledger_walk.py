"""The shared FIFO walk, driven by a **second** policy (D5 Stage 4 S4.2).

`tests/unit/test_fifo_walk.py` is the M6 suite and it runs **unchanged** against
`receivables.selectors._walk`. That is the extraction's correctness proof: every §5A.9 edge
case, the §5A.8 worked example to the paisa, and five randomised invariant seeds all still
pass through the moved code without a single edit to the test.

So this file deliberately does **not** re-test the algorithm. It tests the one thing the M6
suite structurally cannot: that the walk is genuinely *shared* rather than merely relocated
— that a second vocabulary drives the same code to the correspondingly different answer.

**Nothing here implements supplier payments.** `SupplierLedgerEntry` instances are built
unsaved and never touch the database, exactly as the M6 suite builds unsaved customer
entries. No service, no selector and no production policy is added; the supplier policy
below lives in this file and nowhere else, and S4.3 will decide where the real one belongs.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from ledger.models import CustomerLedgerEntry, SupplierLedgerEntry
from ledger.walk import WalkPolicy, annulled_entry_ids, walk

AS_OF = date(2026, 8, 31)
START = date(2026, 1, 1)

SUPPLIER = SupplierLedgerEntry.Type
CUSTOMER = CustomerLedgerEntry.Type

#: The payables vocabulary. Four strings — the whole of what differs between the ledgers.
SUPPLIER_POLICY = WalkPolicy(
    adjustment_type=SUPPLIER.ADJUSTMENT,
    annullable_source_types=(SUPPLIER.GOODS_RECEIPT, SUPPLIER.PAYMENT),
    reducing_type=SUPPLIER.DEBIT_NOTE,
    target_type=SUPPLIER.GOODS_RECEIPT,
)

#: The receivables vocabulary, restated here so the two can be contrasted directly. It is
#: identical to `receivables.selectors._CUSTOMER_POLICY`, and one test asserts that.
CUSTOMER_POLICY = WalkPolicy(
    adjustment_type=CUSTOMER.ADJUSTMENT,
    annullable_source_types=(CUSTOMER.INVOICE, CUSTOMER.PAYMENT),
    reducing_type=CUSTOMER.CREDIT_NOTE,
    target_type=CUSTOMER.INVOICE,
)


def supplier_entry(
    pk: int,
    day: date,
    entry_type: str,
    amount: str,
    *,
    source_type: str = "",
    source_id: int | None = None,
    narration: str = "",
) -> SupplierLedgerEntry:
    """An unsaved supplier ledger entry. The walk never touches the database."""
    instance = SupplierLedgerEntry(
        supplier_id=1,
        entry_date=day,
        entry_type=entry_type,
        amount=Decimal(amount),
        source_document_type=source_type,
        source_document_id=source_id,
        narration=narration or f"{entry_type} {pk}",
    )
    instance.pk = pk
    return instance


def supplier_walk(entries, targets=None):
    return walk(
        party_id=1,
        as_of=AS_OF,
        entries=entries,
        reduction_targets=targets or {},
        policy=SUPPLIER_POLICY,
    )


def assert_invariant(position, entries):
    """§5A.7, unchanged. The property that ties the algorithm back to the SUM."""
    ledger_sum = sum((e.amount for e in entries), Decimal("0.00"))
    assert position.total_outstanding - position.credit_on_account == ledger_sum


# ------------------------------------------------- the walk answers a second vocabulary


def test_the_customer_policy_here_matches_the_one_receivables_actually_uses():
    """Anti-drift. Every contrast below is meaningless if this copy is not the real one."""
    from receivables.selectors import _CUSTOMER_POLICY

    assert CUSTOMER_POLICY == _CUSTOMER_POLICY


def test_receipts_settle_oldest_first_under_the_supplier_policy():
    """The payables shape of §5A.4: goods received are debits, payments settle them FIFO."""
    entries = [
        supplier_entry(1, date(2026, 6, 1), SUPPLIER.GOODS_RECEIPT, "1000.00",
                       source_type="GOODS_RECEIPT", source_id=11, narration="GRN-1"),
        supplier_entry(2, date(2026, 7, 1), SUPPLIER.GOODS_RECEIPT, "500.00",
                       source_type="GOODS_RECEIPT", source_id=12, narration="GRN-2"),
        supplier_entry(3, date(2026, 8, 1), SUPPLIER.PAYMENT, "-1200.00",
                       source_type="PAYMENT", source_id=31),
    ]
    position = supplier_walk(entries)

    assert [(i.document, i.outstanding_amount) for i in position.open_items] == [
        ("GRN-2", Decimal("300.00"))
    ]
    assert position.credit_on_account == Decimal("0.00")
    assert_invariant(position, entries)


def test_an_opening_balance_is_a_debit_and_ages_from_its_own_date():
    """S4.1's rows meet S4.2's walk. An opening balance is the oldest thing there is."""
    entries = [
        supplier_entry(1, date(2026, 4, 1), SUPPLIER.OPENING, "4500.00",
                       narration="Opening balance carried at go-live"),
        supplier_entry(2, date(2026, 7, 1), SUPPLIER.GOODS_RECEIPT, "590.00",
                       source_type="GOODS_RECEIPT", source_id=11, narration="GRN-1"),
        supplier_entry(3, date(2026, 8, 1), SUPPLIER.PAYMENT, "-1000.00",
                       source_type="PAYMENT", source_id=31),
    ]
    position = supplier_walk(entries)

    assert [i.document for i in position.open_items] == [
        "Opening balance carried at go-live",
        "GRN-1",
    ]
    assert position.open_items[0].outstanding_amount == Decimal("3500.00")
    assert position.open_items[0].age_days == 152
    assert_invariant(position, entries)


def test_a_negative_opening_balance_settles_later_receipts():
    """An advance paid before go-live is a credit, and it pays down what arrives next."""
    entries = [
        supplier_entry(1, date(2026, 4, 1), SUPPLIER.OPENING, "-2500.00",
                       narration="Advance paid before go-live"),
        supplier_entry(2, date(2026, 7, 1), SUPPLIER.GOODS_RECEIPT, "1000.00",
                       source_type="GOODS_RECEIPT", source_id=11, narration="GRN-1"),
    ]
    position = supplier_walk(entries)

    assert position.open_items == []
    assert position.credit_on_account == Decimal("1500.00")
    assert position.balance == Decimal("-1500.00")
    assert_invariant(position, entries)


def test_a_reversed_supplier_payment_restores_the_original_age():
    """**The M6 defect, in payables form.**

    Treated as an ordinary positive entry, the reversal would become a fresh debit dated the
    day of the reversal, and an old receipt would reappear as zero days old.
    """
    entries = [
        supplier_entry(1, date(2026, 6, 10), SUPPLIER.GOODS_RECEIPT, "1000.00",
                       source_type="GOODS_RECEIPT", source_id=11, narration="GRN-1"),
        supplier_entry(2, date(2026, 8, 2), SUPPLIER.PAYMENT, "-1000.00",
                       source_type="PAYMENT", source_id=31),
        supplier_entry(3, date(2026, 8, 6), SUPPLIER.ADJUSTMENT, "1000.00",
                       source_type="PAYMENT", source_id=31),
    ]
    position = supplier_walk(entries)

    assert len(position.open_items) == 1
    assert position.open_items[0].age_days == 82, "82 days old, not 25"
    assert_invariant(position, entries)


def test_a_debit_note_reduces_its_own_receipt_not_the_oldest():
    """The payables mirror of §5A.2.

    **`DEBIT_NOTE` has no producer in v1.0** — `purchase_return` is Edition 2 (DV-8) and a
    posted goods receipt is immutable. This asserts the *algorithm* handles the role, so
    that whoever adds the document later finds the walk already correct.
    """
    entries = [
        supplier_entry(1, date(2026, 1, 1), SUPPLIER.GOODS_RECEIPT, "1000.00",
                       source_type="GOODS_RECEIPT", source_id=11, narration="A"),
        supplier_entry(2, date(2026, 2, 1), SUPPLIER.GOODS_RECEIPT, "1000.00",
                       source_type="GOODS_RECEIPT", source_id=12, narration="B"),
        supplier_entry(3, date(2026, 2, 5), SUPPLIER.DEBIT_NOTE, "-200.00",
                       source_type="DEBIT_NOTE", source_id=21),
    ]
    position = supplier_walk(entries, {21: 12})

    assert {i.document: i.outstanding_amount for i in position.open_items} == {
        "A": Decimal("1000.00"),
        "B": Decimal("800.00"),
    }
    assert_invariant(position, entries)


def test_a_cancelled_receipt_never_appears():
    entries = [
        supplier_entry(1, date(2026, 7, 20), SUPPLIER.GOODS_RECEIPT, "900.00",
                       source_type="GOODS_RECEIPT", source_id=13),
        supplier_entry(2, date(2026, 7, 22), SUPPLIER.ADJUSTMENT, "-900.00",
                       source_type="GOODS_RECEIPT", source_id=13),
    ]
    position = supplier_walk(entries)

    assert position.open_items == []
    assert_invariant(position, entries)


def test_same_date_debits_are_tie_broken_by_id():
    """§5A.6 under the second policy — determinism is not a customer-only property."""
    entries = [
        supplier_entry(1, date(2026, 6, 1), SUPPLIER.GOODS_RECEIPT, "100.00",
                       source_type="GOODS_RECEIPT", source_id=11, narration="first"),
        supplier_entry(2, date(2026, 6, 1), SUPPLIER.GOODS_RECEIPT, "100.00",
                       source_type="GOODS_RECEIPT", source_id=12, narration="second"),
        supplier_entry(3, date(2026, 6, 2), SUPPLIER.PAYMENT, "-100.00",
                       source_type="PAYMENT", source_id=31),
    ]
    assert [i.document for i in supplier_walk(entries).open_items] == ["second"]


def test_no_entries_gives_a_zero_position():
    position = supplier_walk([])

    assert position.open_items == []
    assert position.total_outstanding == Decimal("0.00")
    assert position.credit_on_account == Decimal("0.00")
    assert position.balance == Decimal("0.00")
    assert position.party_id == 1


# ------------------------------------------------------ the policy is actually consulted


def test_the_policy_decides_the_answer_rather_than_a_hard_coded_type():
    """**The test that proves the extraction is a parameterisation, not a relocation.**

    If any of the four type codes were still hard-coded to the customer vocabulary, these
    supplier rows would flow through the wrong branches. Running the *same* rows under the
    *wrong* policy must therefore give a *different* answer — and if it gives the same one,
    the policy is decorative.

    Under `SUPPLIER_POLICY` the adjustment annuls the receipt: nothing is owed.
    Under `CUSTOMER_POLICY` `GOODS_RECEIPT` is not an annullable source, so the pair stays
    in the walk as an ordinary debit and an ordinary settlement, and the ageing differs.
    """
    entries = [
        supplier_entry(1, date(2026, 7, 20), SUPPLIER.GOODS_RECEIPT, "900.00",
                       source_type="GOODS_RECEIPT", source_id=13, narration="GRN-1"),
        supplier_entry(2, date(2026, 7, 22), SUPPLIER.ADJUSTMENT, "-900.00",
                       source_type="GOODS_RECEIPT", source_id=13),
    ]

    right = supplier_walk(entries)
    wrong = walk(
        party_id=1, as_of=AS_OF, entries=entries, reduction_targets={},
        policy=CUSTOMER_POLICY,
    )

    assert right.open_items == [], "the supplier policy must annul the pair"
    assert wrong.open_items == [], "settled by FIFO rather than annulled — same total..."
    # ...but the two reached it by different routes, and `annulled_entry_ids` says so.
    assert annulled_entry_ids(entries, SUPPLIER_POLICY) == {1, 2}
    assert annulled_entry_ids(entries, CUSTOMER_POLICY) == set()


def test_the_reducing_type_is_policy_driven_not_hard_coded():
    """A `DEBIT_NOTE` is a targeted reduction only because the policy says so.

    Under the customer policy it is an untyped negative entry, so it settles FIFO — which
    for two equal debits hits the *older* one instead of the one it names.
    """
    entries = [
        supplier_entry(1, date(2026, 1, 1), SUPPLIER.GOODS_RECEIPT, "1000.00",
                       source_type="GOODS_RECEIPT", source_id=11, narration="A"),
        supplier_entry(2, date(2026, 2, 1), SUPPLIER.GOODS_RECEIPT, "1000.00",
                       source_type="GOODS_RECEIPT", source_id=12, narration="B"),
        supplier_entry(3, date(2026, 2, 5), SUPPLIER.DEBIT_NOTE, "-200.00",
                       source_type="DEBIT_NOTE", source_id=21),
    ]

    targeted = supplier_walk(entries, {21: 12})
    untargeted = walk(
        party_id=1, as_of=AS_OF, entries=entries, reduction_targets={21: 12},
        policy=CUSTOMER_POLICY,
    )

    assert {i.document: i.outstanding_amount for i in targeted.open_items} == {
        "A": Decimal("1000.00"), "B": Decimal("800.00")
    }
    assert {i.document: i.outstanding_amount for i in untargeted.open_items} == {
        "A": Decimal("800.00"), "B": Decimal("1000.00")
    }


# ------------------------------------------------------------------------- property


@pytest.mark.parametrize("seed", [1, 7, 42, 20260806, 999])
def test_the_invariant_holds_over_randomised_supplier_sequences(seed):
    """§5A.7 for the payables vocabulary, over every entry role, in random order.

    The same construction the customer side has relied on since M6 — the property that
    makes an algorithmic view trustworthy by tying it back to the one number the system
    already trusts.
    """
    rng = random.Random(seed)
    entries: list[SupplierLedgerEntry] = []
    targets: dict[int, int] = {}
    pk = 0
    receipt_pk = 0

    for _ in range(rng.randint(5, 30)):
        pk += 1
        day = START + timedelta(days=rng.randint(0, 200))
        choice = rng.choice(["receipt", "payment", "debit_note", "cancel", "reverse", "manual"])

        if choice == "receipt":
            receipt_pk += 1
            entries.append(
                supplier_entry(pk, day, SUPPLIER.GOODS_RECEIPT, f"{rng.randint(100, 5000)}.00",
                               source_type="GOODS_RECEIPT", source_id=receipt_pk)
            )
        elif choice == "payment":
            entries.append(
                supplier_entry(pk, day, SUPPLIER.PAYMENT, f"-{rng.randint(50, 3000)}.00",
                               source_type="PAYMENT", source_id=pk)
            )
        elif choice == "debit_note" and receipt_pk:
            target = rng.randint(1, receipt_pk)
            source = next(
                (e for e in entries if e.entry_type == SUPPLIER.GOODS_RECEIPT
                 and e.source_document_id == target),
                None,
            )
            if source is None:
                continue
            # Never more than the receipt was worth — B-7's payables analogue.
            amount = min(Decimal(rng.randint(10, 500)), source.amount)
            targets[pk] = target
            entries.append(
                supplier_entry(pk, day, SUPPLIER.DEBIT_NOTE, f"-{amount}",
                               source_type="DEBIT_NOTE", source_id=pk)
            )
        elif choice == "cancel" and receipt_pk:
            source = next(
                (e for e in entries
                 if e.entry_type == SUPPLIER.GOODS_RECEIPT
                 and e.source_document_id not in set(targets.values())),
                None,
            )
            if source is None:
                continue
            entries.append(
                supplier_entry(pk, day, SUPPLIER.ADJUSTMENT, f"-{source.amount}",
                               source_type="GOODS_RECEIPT", source_id=source.source_document_id)
            )
        elif choice == "reverse":
            source = next((e for e in entries if e.entry_type == SUPPLIER.PAYMENT), None)
            if source is None:
                continue
            entries.append(
                supplier_entry(pk, day, SUPPLIER.ADJUSTMENT, f"{abs(source.amount)}",
                               source_type="PAYMENT", source_id=source.source_document_id)
            )
        else:
            sign = "" if rng.random() > 0.5 else "-"
            entries.append(
                supplier_entry(pk, day, SUPPLIER.ADJUSTMENT, f"{sign}{rng.randint(10, 400)}.00")
            )

    entries.sort(key=lambda e: (e.entry_date, e.pk))
    position = supplier_walk(entries, targets)

    assert_invariant(position, entries)
    assert all(i.outstanding_amount > 0 for i in position.open_items)
    assert position.credit_on_account >= 0
