"""Supplier opening balances (BD-5, D5 Stage 4 S4.1).

What the distributor already owed a supplier on the day the system went live.

**Stage 3 built the schema; S4.1 adds one service.** The partial unique index
`uq_sle_one_opening_per_supplier`, the `ck_sle_sign` CHECK that deliberately omits
`OPENING`, and `ck_sle_amount_non_zero` all shipped with the supplier ledger. These tests
therefore assert two different kinds of thing, and the distinction matters: some prove the
new service behaves, and some prove the **database** would refuse the same mistake if the
service were bypassed.

**Three divergences from `receivables.services.load_opening_balance` are asserted here
explicitly**, because a reader comparing the two functions must be able to tell a deliberate
difference from an oversight:

1. no audit row (R-3, `D5_Stage4_Design_Review` v2.0.0 §4.1 D1);
2. a duplicate is refused rather than returned (D2);
3. `entry_date` is required, with no server-clock fallback (D3).

The last class of test guards the other direction: **the customer ledger is unchanged.**
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from core.exceptions import PermissionDenied, ValidationFailed
from core.models import AuditLog
from ledger.models import LedgerEntryImmutable, SupplierLedgerEntry
from ledger.selectors import supplier_balance, supplier_statement_for
from ledger.services import record_supplier_entry
from purchasing.services import create_supplier, load_supplier_opening_balance

pytestmark = pytest.mark.django_db

GO_LIVE = date(2026, 4, 1)


@pytest.fixture
def supplier(owner):
    return create_supplier(
        actor=owner,
        code="acme",
        name="Acme Distributors",
        phone="+919876500011",
        billing_address="Industrial Estate",
        payment_terms_days=30,
    )


@pytest.fixture
def other_supplier(owner):
    return create_supplier(
        actor=owner,
        code="brio",
        name="Brio Traders",
        phone="+919876500022",
        billing_address="Market Road",
    )


# --------------------------------------------------------------------- the two good cases


def test_a_positive_opening_balance_is_what_we_owed_at_go_live(owner, supplier):
    entry = load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="12500.00", entry_date=GO_LIVE
    )

    assert entry.entry_type == SupplierLedgerEntry.Type.OPENING
    assert entry.amount == Decimal("12500.00")
    assert entry.entry_date == GO_LIVE
    assert supplier_balance(supplier) == Decimal("12500.00")


def test_a_negative_opening_balance_records_an_advance_already_paid(owner, supplier):
    """**Where this diverges from the customer ledger, and why Stage 3 made room for it.**

    `load_opening_balance` refuses anything `<= 0` — *"a customer who owes nothing needs no
    entry"*. A supplier position can legitimately be a credit: money paid in advance, or
    goods returned, before go-live. `ck_sle_sign` omits `OPENING` from both the debit and
    the credit lists precisely so this row is representable.
    """
    entry = load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="-2500.00", entry_date=GO_LIVE
    )

    assert entry.amount == Decimal("-2500.00")
    assert supplier_balance(supplier) == Decimal("-2500.00")


def test_the_entry_date_is_the_callers_and_may_precede_go_live(owner, supplier):
    """D3 / P-4. A machine clock must not decide a business fact.

    The balance ages from this date, so dating it when the debt arose — not when it was
    keyed — is what makes the first ageing report correct rather than uniformly zero days
    old.
    """
    backdated = date(2026, 1, 15)
    entry = load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="900.00", entry_date=backdated
    )

    assert entry.entry_date == backdated


# ----------------------------------------------------------------------------- refusals


def test_a_zero_opening_balance_is_refused(owner, supplier):
    with pytest.raises(ValidationFailed) as exc:
        load_supplier_opening_balance(
            actor=owner, supplier=supplier, amount="0.00", entry_date=GO_LIVE
        )

    assert exc.value.errors[0]["code"] == "ZERO"
    assert not SupplierLedgerEntry.objects.exists()


def test_a_second_opening_balance_is_refused_not_returned(owner, supplier):
    """D2. The divergence from the customer import, asserted rather than assumed.

    `load_opening_balance` is idempotent and returns the existing entry. Here a second load
    raises, because opening balances are entered one supplier at a time and quietly
    returning the old row would report success for a change that did not happen.
    """
    first = load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="4500.00", entry_date=GO_LIVE
    )

    with pytest.raises(ValidationFailed) as exc:
        load_supplier_opening_balance(
            actor=owner, supplier=supplier, amount="9999.00", entry_date=GO_LIVE
        )

    assert exc.value.errors[0]["code"] == "DUPLICATE_OPENING"
    assert SupplierLedgerEntry.objects.get().pk == first.pk
    assert supplier_balance(supplier) == Decimal("4500.00")


def test_the_database_refuses_a_second_opening_even_if_the_service_is_bypassed(
    owner, supplier
):
    """**The database is the guarantee, not the pre-check.**

    Two concurrent loads would both pass the service's lookup. This asserts what stops the
    loser: `uq_sle_one_opening_per_supplier`, the partial unique index Stage 3 shipped.
    """
    load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="4500.00", entry_date=GO_LIVE
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        record_supplier_entry(
            actor=owner,
            supplier=supplier,
            entry_type=SupplierLedgerEntry.Type.OPENING,
            amount=Decimal("1.00"),
            narration="Second opening, straight through the service layer",
            entry_date=GO_LIVE,
        )


def test_one_opening_per_supplier_is_per_supplier_not_global(owner, supplier, other_supplier):
    """The index is partial *and* keyed. A second supplier is not a duplicate."""
    load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="4500.00", entry_date=GO_LIVE
    )
    load_supplier_opening_balance(
        actor=owner, supplier=other_supplier, amount="700.00", entry_date=GO_LIVE
    )

    assert supplier_balance(supplier) == Decimal("4500.00")
    assert supplier_balance(other_supplier) == Decimal("700.00")


def test_only_the_owner_may_load_an_opening_balance(salesman, supplier):
    with pytest.raises(PermissionDenied):
        load_supplier_opening_balance(
            actor=salesman, supplier=supplier, amount="100.00", entry_date=GO_LIVE
        )

    assert not SupplierLedgerEntry.objects.exists()


def test_an_entry_date_is_required(owner, supplier):
    """D3. There is no fallback to `date.today()`, and its absence is the rule."""
    with pytest.raises(ValidationFailed) as exc:
        load_supplier_opening_balance(
            actor=owner, supplier=supplier, amount="100.00", entry_date=None
        )

    assert exc.value.errors[0]["code"] == "REQUIRED"
    assert not SupplierLedgerEntry.objects.exists()


# -------------------------------------------------------------------------- immutability


def test_an_opening_balance_cannot_be_edited_or_removed(owner, supplier):
    """Four layers, the same four the supplier ledger enforces on every entry."""
    entry = load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="4500.00", entry_date=GO_LIVE
    )

    entry.amount = Decimal("1.00")
    with pytest.raises(LedgerEntryImmutable):
        entry.save()
    with pytest.raises(LedgerEntryImmutable):
        entry.delete()
    with pytest.raises(LedgerEntryImmutable):
        SupplierLedgerEntry.objects.filter(pk=entry.pk).update(amount=Decimal("1.00"))
    with pytest.raises(LedgerEntryImmutable):
        SupplierLedgerEntry.objects.filter(pk=entry.pk).delete()

    entry.refresh_from_db()
    assert entry.amount == Decimal("4500.00")


# ------------------------------------------------------------- provenance and the ledger


def test_the_entry_carries_its_own_provenance_and_no_source_document(owner, supplier):
    """**Why no audit row is needed** — everything an audit row would hold is on the row.

    An opening balance predates the system, so there is no document to point at.
    `ck_sle_source_pair` requires both halves of a reference or neither; this is the
    "neither" case, and leaving half of it would be refused by the database.
    """
    entry = load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="4500.00", entry_date=GO_LIVE
    )

    assert entry.created_by == owner
    assert entry.created_at is not None
    assert entry.narration == "Opening balance carried at go-live"
    assert entry.source_document_type == ""
    assert entry.source_document_id is None


def test_no_audit_row_is_written_for_the_ledger_entry(owner, supplier):
    """R-3, and divergence D1 from `D5_Stage4_Design_Review` v2.0.0 §4.2.

    The design specified one `record_audit` here, copying the customer version. The S4.1
    ruling reversed it: *"no separate AuditLog row for ledger entry"*, *"preserve existing
    R-3 ledger behavior"*. The supplier ledger is therefore strictly R-3-consistent — an
    immutable row carrying actor, timestamp, amount and narration is not audited again.
    """
    load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="4500.00", entry_date=GO_LIVE
    )

    assert not AuditLog.objects.filter(entity_type="supplier_ledger_entry").exists()


def test_the_derived_balance_sums_the_opening_with_later_activity(owner, supplier):
    """N-03 / E-01: the balance is `SUM(amount)`, computed on every read.

    12,500 owed at go-live, plus a 590.00 receipt, is 13,090.00 — and there is no column
    anywhere holding that figure.
    """
    load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="12500.00", entry_date=GO_LIVE
    )
    record_supplier_entry(
        actor=owner,
        supplier=supplier,
        entry_type=SupplierLedgerEntry.Type.GOODS_RECEIPT,
        amount=Decimal("590.00"),
        narration="GRN-00000001",
        entry_date=date(2026, 5, 2),
    )

    assert supplier_balance(supplier) == Decimal("13090.00")
    assert supplier_balance(supplier, as_of=GO_LIVE) == Decimal("12500.00")
    assert [entry.entry_type for entry in supplier_statement_for(supplier)] == [
        SupplierLedgerEntry.Type.OPENING,
        SupplierLedgerEntry.Type.GOODS_RECEIPT,
    ]


def test_a_supplier_with_no_opening_balance_is_complete_not_incomplete(supplier):
    """The ruling's own words: values are go-live data, and many suppliers will have none."""
    assert supplier_balance(supplier) == Decimal("0.00")
    assert not supplier_statement_for(supplier).exists()


# ------------------------------------------------- the customer ledger is unchanged (S4.1)


class TestCustomerLedgerInvariantsUnchanged:
    """S4.1 diverges from the customer conventions on purpose. It must not *alter* them.

    Every divergence above is a property of the new supplier service. These assert that the
    M6 behaviour it diverges from is still exactly what it was — otherwise "divergence"
    would be a euphemism for a regression on the customer side.
    """

    def test_the_customer_import_is_still_idempotent(self, owner, credit_customer):
        from ledger.models import CustomerLedgerEntry
        from receivables.services import load_opening_balance

        first = load_opening_balance(actor=owner, customer=credit_customer, amount="4500.00")
        second = load_opening_balance(actor=owner, customer=credit_customer, amount="9999.00")

        assert first.pk == second.pk
        assert (
            CustomerLedgerEntry.objects.filter(
                customer=credit_customer, entry_type=CustomerLedgerEntry.Type.OPENING
            ).count()
            == 1
        )

    def test_the_customer_opening_balance_still_writes_its_audit_row(
        self, owner, credit_customer
    ):
        """The legacy anomaly, pinned. If it is ever removed that must be a ruling, not drift."""
        from receivables.services import load_opening_balance

        load_opening_balance(actor=owner, customer=credit_customer, amount="4500.00")

        assert AuditLog.objects.filter(entity_type="customer_ledger_entry").exists()

    def test_a_customer_opening_balance_must_still_be_positive(self, owner, credit_customer):
        """The supplier side permits a credit. The customer side must still not."""
        from receivables.services import load_opening_balance

        with pytest.raises(ValidationFailed, match="greater than zero"):
            load_opening_balance(actor=owner, customer=credit_customer, amount="-100.00")

    def test_the_two_ledgers_do_not_share_an_opening_entry(
        self, owner, supplier, credit_customer
    ):
        """Two tables, two constraints. Loading one must not satisfy or block the other."""
        from ledger.models import CustomerLedgerEntry
        from ledger.selectors import settled_balance
        from receivables.services import load_opening_balance

        load_supplier_opening_balance(
            actor=owner, supplier=supplier, amount="4500.00", entry_date=GO_LIVE
        )
        load_opening_balance(actor=owner, customer=credit_customer, amount="700.00")

        assert supplier_balance(supplier) == Decimal("4500.00")
        assert settled_balance(credit_customer) == Decimal("700.00")
        assert SupplierLedgerEntry.objects.count() == 1
        assert (
            CustomerLedgerEntry.objects.filter(
                entry_type=CustomerLedgerEntry.Type.OPENING
            ).count()
            == 1
        )
