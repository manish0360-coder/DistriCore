"""M6 service rules: payments, reversal, write-off, opening balances."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.exceptions import PermissionDenied, ValidationFailed
from core.models import AuditLog
from ledger.models import CustomerLedgerEntry
from ledger.selectors import settled_balance
from receivables.models import Payment
from receivables.selectors import collected_total, customer_statement, outstanding_for
from receivables.services import (
    load_opening_balance,
    record_payment,
    reverse_payment,
    write_off,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def paid(owner, credit_customer):
    return record_payment(
        actor=owner, customer=credit_customer, amount=Decimal("500.00"), method="CASH"
    )


class TestRecordPayment:
    def test_a_payment_writes_one_row_and_one_ledger_entry(self, owner, credit_customer, paid):
        assert Payment.objects.count() == 1
        entries = CustomerLedgerEntry.objects.filter(customer=credit_customer)
        assert entries.count() == 1
        assert entries.get().entry_type == CustomerLedgerEntry.Type.PAYMENT
        assert entries.get().amount == Decimal("-500.00")
        assert settled_balance(credit_customer) == Decimal("-500.00")

    def test_the_receipt_number_is_allocated_from_a_sequence(self, owner, credit_customer):
        """M6-2. Written in ONE statement — an UPDATE would hit the immutability trigger."""
        first = record_payment(
            actor=owner, customer=credit_customer, amount="100.00", method="CASH"
        )
        second = record_payment(
            actor=owner, customer=credit_customer, amount="100.00", method="UPI"
        )
        assert first.payment_number.startswith("PAY-")
        assert first.payment_number != second.payment_number

    def test_replaying_a_client_uuid_returns_the_original(self, owner, credit_customer):
        """M6-5 — the founding problem inverted. A retry must never double-credit."""
        key = "44444444-4444-4444-4444-444444444444"
        first = record_payment(
            actor=owner, customer=credit_customer, amount="500.00", method="UPI", client_uuid=key
        )
        second = record_payment(
            actor=owner, customer=credit_customer, amount="500.00", method="UPI", client_uuid=key
        )
        assert first.pk == second.pk
        assert Payment.objects.count() == 1
        assert settled_balance(credit_customer) == Decimal("-500.00")

    def test_a_salesman_may_collect(self, salesman, credit_customer):
        """05 §8 gives payment creation to O, S and D — not to retailers."""
        payment = record_payment(
            actor=salesman, customer=credit_customer, amount="100.00", method="CASH"
        )
        assert payment.received_by == salesman

    def test_a_retailer_may_not_collect(self, retailer, credit_customer):
        with pytest.raises(PermissionDenied):
            record_payment(
                actor=retailer, customer=credit_customer, amount="100.00", method="CASH"
            )

    @pytest.mark.parametrize("amount", ["0.00", "-10.00"])
    def test_a_payment_must_be_positive(self, owner, credit_customer, amount):
        with pytest.raises(ValidationFailed, match="greater than zero"):
            record_payment(
                actor=owner, customer=credit_customer, amount=amount, method="CASH"
            )

    def test_an_unknown_method_is_refused(self, owner, credit_customer):
        with pytest.raises(ValidationFailed, match="Unknown payment method"):
            record_payment(
                actor=owner, customer=credit_customer, amount="100.00", method="BARTER"
            )

    def test_a_deactivated_customer_cannot_pay(self, owner, credit_customer):
        credit_customer.is_active = False
        credit_customer.save(update_fields=["is_active"])
        with pytest.raises(ValidationFailed, match="deactivated"):
            record_payment(
                actor=owner, customer=credit_customer, amount="100.00", method="CASH"
            )

    def test_a_payment_is_not_audited(self, owner, credit_customer, paid):
        """D-5: routine and already self-describing. Reversal is the discretionary act."""
        assert not AuditLog.objects.filter(entity_type="payment").exists()


class TestReversePayment:
    def test_reversal_appends_and_never_edits(self, owner, credit_customer, paid):
        reverse_payment(actor=owner, payment=paid, reason="Wrong customer")
        entries = CustomerLedgerEntry.objects.filter(customer=credit_customer)
        assert entries.count() == 2
        assert settled_balance(credit_customer) == Decimal("0.00")
        assert entries.filter(entry_type=CustomerLedgerEntry.Type.ADJUSTMENT).exists()

    def test_reversal_is_idempotent(self, owner, credit_customer, paid):
        reverse_payment(actor=owner, payment=paid, reason="Wrong customer")
        reverse_payment(actor=owner, payment=paid, reason="Again")
        assert CustomerLedgerEntry.objects.count() == 2, "one compensating entry, not two"
        paid.refresh_from_db()
        assert paid.reversed_reason == "Wrong customer"

    def test_reversal_records_who_and_when(self, owner, credit_customer, paid):
        """M6 C-3 — `04` T-21 omitted these columns; M5's invoice had them."""
        reverse_payment(actor=owner, payment=paid, reason="Wrong customer")
        paid.refresh_from_db()
        assert paid.reversed_by == owner
        assert paid.reversed_at is not None

    def test_reversal_needs_a_reason(self, owner, paid):
        with pytest.raises(ValidationFailed, match="needs a reason"):
            reverse_payment(actor=owner, payment=paid, reason="   ")

    def test_only_the_owner_may_reverse(self, salesman, paid):
        with pytest.raises(PermissionDenied):
            reverse_payment(actor=salesman, payment=paid, reason="nope")

    def test_reversal_is_audited(self, owner, paid):
        reverse_payment(actor=owner, payment=paid, reason="Wrong customer")
        assert AuditLog.objects.filter(
            action=AuditLog.Action.PAYMENT_REVERSE, entity_id=paid.pk
        ).exists()


class TestWriteOff:
    def test_a_write_off_reduces_the_balance(self, owner, credit_customer):
        load_opening_balance(actor=owner, customer=credit_customer, amount="1000.00")
        write_off(actor=owner, customer=credit_customer, amount="400.00", reason="Shop closed")
        assert settled_balance(credit_customer) == Decimal("600.00")

    def test_the_amount_is_explicit_and_must_be_positive(self, owner, credit_customer):
        with pytest.raises(ValidationFailed, match="greater than zero"):
            write_off(actor=owner, customer=credit_customer, amount="0.00", reason="x")

    def test_a_write_off_needs_a_reason(self, owner, credit_customer):
        with pytest.raises(ValidationFailed, match="needs a reason"):
            write_off(actor=owner, customer=credit_customer, amount="100.00", reason=" ")

    def test_only_the_owner_may_write_off(self, salesman, credit_customer):
        with pytest.raises(PermissionDenied):
            write_off(actor=salesman, customer=credit_customer, amount="100.00", reason="x")

    def test_a_write_off_is_audited(self, owner, credit_customer):
        write_off(actor=owner, customer=credit_customer, amount="100.00", reason="Bad debt")
        assert AuditLog.objects.filter(entity_type="customer_ledger_entry").exists()


class TestOpeningBalance:
    def test_the_import_is_idempotent(self, owner, credit_customer):
        """D-10 / M6-11. Re-running the go-live load must not double the balance."""
        first = load_opening_balance(actor=owner, customer=credit_customer, amount="4500.00")
        second = load_opening_balance(actor=owner, customer=credit_customer, amount="4500.00")
        assert first.pk == second.pk
        assert (
            CustomerLedgerEntry.objects.filter(
                customer=credit_customer, entry_type=CustomerLedgerEntry.Type.OPENING
            ).count()
            == 1
        )
        assert settled_balance(credit_customer) == Decimal("4500.00")

    def test_rerunning_with_a_different_amount_still_does_not_duplicate(
        self, owner, credit_customer
    ):
        """The natural key is the customer, not the amount. A second load is a no-op."""
        load_opening_balance(actor=owner, customer=credit_customer, amount="4500.00")
        load_opening_balance(actor=owner, customer=credit_customer, amount="9999.00")
        assert settled_balance(credit_customer) == Decimal("4500.00")

    def test_only_the_owner_may_load(self, salesman, credit_customer):
        with pytest.raises(PermissionDenied):
            load_opening_balance(actor=salesman, customer=credit_customer, amount="100.00")

    def test_a_zero_opening_balance_is_refused(self, owner, credit_customer):
        with pytest.raises(ValidationFailed, match="greater than zero"):
            load_opening_balance(actor=owner, customer=credit_customer, amount="0.00")


class TestReads:
    def test_collected_total_ignores_reversed_payments(self, owner, credit_customer, paid):
        assert collected_total(credit_customer) == Decimal("500.00")
        reverse_payment(actor=owner, payment=paid, reason="Wrong customer")
        assert collected_total(credit_customer) == Decimal("0.00")

    def test_a_customer_who_never_paid_returns_zero_not_none(self, customer):
        assert collected_total(customer) == Decimal("0.00")

    def test_a_statements_closing_figure_is_the_next_periods_opening(
        self, owner, credit_customer
    ):
        load_opening_balance(
            actor=owner, customer=credit_customer, amount="1000.00",
            entry_date=date(2026, 4, 1),
        )
        record_payment(
            actor=owner, customer=credit_customer, amount="300.00", method="CASH",
            payment_date=date(2026, 5, 10),
        )
        april = customer_statement(
            credit_customer, date_from=date(2026, 4, 1), date_to=date(2026, 4, 30)
        )
        may = customer_statement(
            credit_customer, date_from=date(2026, 5, 1), date_to=date(2026, 5, 31)
        )
        assert april.closing_balance == may.opening_balance == Decimal("1000.00")
        assert may.closing_balance == Decimal("700.00")

    def test_outstanding_reflects_an_opening_balance_and_a_payment(
        self, owner, credit_customer
    ):
        load_opening_balance(
            actor=owner, customer=credit_customer, amount="1000.00",
            entry_date=date(2026, 4, 1),
        )
        record_payment(
            actor=owner, customer=credit_customer, amount="400.00", method="UPI",
            payment_date=date(2026, 5, 1),
        )
        position = outstanding_for(credit_customer, as_of=date(2026, 5, 31))
        assert position.total_outstanding == Decimal("600.00")
        assert position.outstanding[0].age_days == 60
        assert position.credit_on_account == Decimal("0.00")
