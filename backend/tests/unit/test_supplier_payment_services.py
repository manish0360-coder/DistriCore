"""Supplier payment and reversal (FR-PUR-012, D5 Stage 4 S4.3).

Money leaving the building. Every test here exists because something writes to a table that
cannot be edited afterwards: `supplier_payment` and `supplier_ledger_entry`.

**E3 — duplicate-payment protection — lives in
`tests/adversarial/test_supplier_payment_idempotency.py`**, including the concurrency case,
because it needs two real database connections and is a different kind of proof.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from core.exceptions import PermissionDenied, ValidationFailed
from core.models import AuditLog
from ledger.models import SupplierLedgerEntry
from ledger.selectors import supplier_balance, supplier_statement_for
from ledger.services import record_supplier_entry
from purchasing.models import SupplierPayment, SupplierPaymentImmutable
from purchasing.selectors import supplier_position
from purchasing.services import (
    create_supplier,
    load_supplier_opening_balance,
    record_supplier_payment,
    reverse_supplier_payment,
)

pytestmark = pytest.mark.django_db

GO_LIVE = date(2026, 4, 1)
PAID_ON = date(2026, 8, 2)
REVERSED_ON = date(2026, 8, 6)


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
def owing(owner, supplier):
    """12,500 owed since go-live. Gives the payments something to settle."""
    load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="12500.00", entry_date=GO_LIVE
    )
    return supplier


def _pay(owner, supplier, amount="1000.00", **kw):
    fields = {
        "actor": owner,
        "supplier": supplier,
        "submission_id": uuid.uuid4(),
        "amount": amount,
        "method": SupplierPayment.Method.BANK,
        "payment_date": PAID_ON,
    }
    fields.update(kw)
    return record_supplier_payment(**fields)


# --------------------------------------------------------------------------- the happy path


def test_a_payment_reduces_what_we_owe(owner, owing):
    payment = _pay(owner, owing, "2500.00")

    assert payment.payment_number.startswith("SPY-")
    assert payment.amount == Decimal("2500.00")
    assert payment.payment_date == PAID_ON
    assert supplier_balance(owing) == Decimal("10000.00")


def test_the_ledger_entry_is_negative_and_points_back_at_the_payment(owner, owing):
    """Constraint 8, and the source type that `ledger.walk` depends on (U-1)."""
    payment = _pay(owner, owing, "2500.00")
    entry = supplier_statement_for(owing).filter(
        entry_type=SupplierLedgerEntry.Type.PAYMENT
    ).get()

    assert entry.amount == Decimal("-2500.00")
    assert entry.entry_date == PAID_ON
    assert entry.source_document_id == payment.pk
    # **Exactly "PAYMENT", not "SUPPLIER_PAYMENT".** `annulled_entry_ids` only accepts a
    # target where `entry_type == source_document_type`; any other spelling would make
    # reversal silently stop annulling and resurrect settled debt as new debt.
    assert entry.source_document_type == "PAYMENT"
    assert entry.entry_type == entry.source_document_type


def test_a_payment_settles_the_oldest_liability_first(owner, supplier):
    """FIFO through the shared `ledger.walk`. Nothing about it is stored."""
    load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="1000.00", entry_date=GO_LIVE
    )
    record_supplier_entry(
        actor=owner,
        supplier=supplier,
        entry_type=SupplierLedgerEntry.Type.GOODS_RECEIPT,
        amount=Decimal("500.00"),
        narration="GRN-00000001",
        entry_date=date(2026, 7, 1),
    )
    _pay(owner, supplier, "1200.00")

    position = supplier_position(supplier)
    assert [(i.document, i.outstanding_amount) for i in position.open_items] == [
        ("GRN-00000001", Decimal("300.00"))
    ]
    assert position.total_outstanding == Decimal("300.00")


def test_overpaying_leaves_credit_on_account(owner, supplier):
    load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="500.00", entry_date=GO_LIVE
    )
    _pay(owner, supplier, "800.00")

    position = supplier_position(supplier)
    assert position.open_items == []
    assert position.credit_on_account == Decimal("300.00")
    assert supplier_balance(supplier) == Decimal("-300.00")


# ------------------------------------------------------------------------------ refusals


def test_only_the_owner_may_pay(salesman, owing):
    with pytest.raises(PermissionDenied):
        _pay(salesman, owing)
    assert not SupplierPayment.objects.exists()


def test_a_zero_or_negative_payment_is_refused(owner, owing):
    for amount in ("0.00", "-5.00"):
        with pytest.raises(ValidationFailed) as exc:
            _pay(owner, owing, amount)
        assert exc.value.errors[0]["code"] == "MIN_VALUE"
    assert not SupplierPayment.objects.exists()


def test_an_unknown_method_is_refused(owner, owing):
    with pytest.raises(ValidationFailed) as exc:
        _pay(owner, owing, method="BARTER")
    assert exc.value.errors[0]["code"] == "INVALID"


def test_a_payment_date_is_required(owner, owing):
    """Constraint 12. There is no `date.today()` fallback, and its absence is the rule."""
    with pytest.raises(ValidationFailed) as exc:
        _pay(owner, owing, payment_date=None)
    assert exc.value.errors[0]["code"] == "REQUIRED"


def test_a_submission_id_is_required(owner, owing):
    """E3 is enforced at the service boundary, not by the form."""
    with pytest.raises(ValidationFailed) as exc:
        _pay(owner, owing, submission_id=None)
    assert exc.value.errors[0]["code"] == "REQUIRED"
    assert not SupplierPayment.objects.exists()


# ------------------------------------------------------------------------- atomicity


def test_a_ledger_failure_leaves_no_payment(owner, owing, monkeypatch):
    """Constraint 2. Money that left the building with no entry behind it is unrecoverable.

    The ledger write is forced to fail *after* the payment row exists, which is the only
    ordering where a non-atomic implementation would leave one behind.
    """
    from purchasing import services

    def boom(**kwargs):
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(services, "record_supplier_entry", boom)

    with pytest.raises(RuntimeError):
        _pay(owner, owing, "2500.00")

    assert not SupplierPayment.objects.exists()
    assert supplier_balance(owing) == Decimal("12500.00")


# ------------------------------------------------------------------------ immutability


def test_a_recorded_payment_cannot_be_edited_or_deleted(owner, owing):
    payment = _pay(owner, owing)

    payment.amount = Decimal("1.00")
    with pytest.raises(SupplierPaymentImmutable):
        payment.save()
    with pytest.raises(SupplierPaymentImmutable):
        payment.delete()
    with pytest.raises(SupplierPaymentImmutable):
        SupplierPayment.objects.filter(pk=payment.pk).update(amount=Decimal("1.00"))
    with pytest.raises(SupplierPaymentImmutable):
        SupplierPayment.objects.filter(pk=payment.pk).delete()

    payment.refresh_from_db()
    assert payment.amount == Decimal("1000.00")


def _raw(sql: str, *params: object) -> None:
    """Straight to the database, past every Python guard."""
    with connection.cursor() as cursor:
        cursor.execute(sql, list(params))


def test_the_database_trigger_refuses_an_edit_that_bypasses_python(owner, owing):
    """The second of three layers. The Python guard can be worked around; this cannot."""
    payment = _pay(owner, owing)

    with pytest.raises(IntegrityError), transaction.atomic():
        _raw("UPDATE supplier_payment SET amount = 1.00 WHERE id = %s", payment.pk)

    payment.refresh_from_db()
    assert payment.amount == Decimal("1000.00")


def test_the_database_trigger_refuses_a_delete(owner, owing):
    payment = _pay(owner, owing)

    with pytest.raises(IntegrityError), transaction.atomic():
        _raw("DELETE FROM supplier_payment WHERE id = %s", payment.pk)

    assert SupplierPayment.objects.filter(pk=payment.pk).exists()


def test_the_database_trigger_refuses_un_reversing(owner, owing):
    """A reversal is one-way. Un-reversing would re-debit with no compensating entry."""
    payment = _pay(owner, owing)
    reverse_supplier_payment(
        actor=owner, payment=payment, reason="Cheque bounced", reversal_date=REVERSED_ON
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        _raw("UPDATE supplier_payment SET is_reversed = false WHERE id = %s", payment.pk)


def test_the_database_trigger_refuses_a_reversal_with_no_reason(owner, owing):
    payment = _pay(owner, owing)

    with pytest.raises(IntegrityError), transaction.atomic():
        _raw(
            "UPDATE supplier_payment SET is_reversed = true, reversed_at = now() "
            "WHERE id = %s",
            payment.pk,
        )


# -------------------------------------------------------------------------- reversal


def test_a_reversal_appends_an_adjustment_and_edits_no_history(owner, owing):
    """Constraint 3. The original entry is untouched; a compensating one is added."""
    payment = _pay(owner, owing, "2500.00")
    reverse_supplier_payment(
        actor=owner, payment=payment, reason="Cheque bounced", reversal_date=REVERSED_ON
    )

    entries = list(supplier_statement_for(owing))
    kinds = [e.entry_type for e in entries]
    assert kinds == [
        SupplierLedgerEntry.Type.OPENING,
        SupplierLedgerEntry.Type.PAYMENT,
        SupplierLedgerEntry.Type.ADJUSTMENT,
    ]

    original = entries[1]
    reversal = entries[2]
    assert original.amount == Decimal("-2500.00"), "the original is not edited"
    assert reversal.amount == Decimal("2500.00")
    assert reversal.entry_date == REVERSED_ON
    assert reversal.source_document_type == "PAYMENT"
    assert reversal.source_document_id == payment.pk
    assert supplier_balance(owing) == Decimal("12500.00")


def test_a_reversal_restores_the_original_age_through_the_walk(owner, supplier):
    """**Constraint 10, and the defect M6 §5A was written to prevent.**

    Treated as an ordinary positive entry, the reversal would become a fresh debit dated the
    day of the reversal, and the 123-day-old liability would reappear as 4 days old. That
    launders aged debt into new debt in a tool whose only purpose is to show which debt is
    oldest. `ledger.walk` annuls the pair instead, and both leave the walk.
    """
    load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="1000.00", entry_date=GO_LIVE
    )
    payment = _pay(owner, supplier, "1000.00")
    assert supplier_position(supplier, as_of=REVERSED_ON).open_items == []

    reverse_supplier_payment(
        actor=owner, payment=payment, reason="Cheque bounced", reversal_date=REVERSED_ON
    )

    position = supplier_position(supplier, as_of=REVERSED_ON)
    assert len(position.open_items) == 1
    item = position.open_items[0]
    assert item.outstanding_amount == Decimal("1000.00")
    assert item.entry_date == GO_LIVE
    assert item.age_days == (REVERSED_ON - GO_LIVE).days == 127, (
        "the liability is as old as it always was, not as old as the reversal"
    )


def test_an_as_of_view_before_the_reversal_still_shows_the_payment_settling(owner, supplier):
    """Why `reversal_date` is caller-supplied (U-4). It decides this, and only this."""
    load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="1000.00", entry_date=GO_LIVE
    )
    payment = _pay(owner, supplier, "1000.00")
    reverse_supplier_payment(
        actor=owner, payment=payment, reason="Cheque bounced", reversal_date=REVERSED_ON
    )

    before = supplier_position(supplier, as_of=date(2026, 8, 4))
    after = supplier_position(supplier, as_of=REVERSED_ON)
    assert before.open_items == [], "settled, as it was on that day"
    assert after.total_outstanding == Decimal("1000.00")


def test_a_reversal_is_idempotent(owner, owing):
    payment = _pay(owner, owing, "2500.00")
    first = reverse_supplier_payment(
        actor=owner, payment=payment, reason="Cheque bounced", reversal_date=REVERSED_ON
    )
    second = reverse_supplier_payment(
        actor=owner, payment=first, reason="Again", reversal_date=REVERSED_ON
    )

    assert first.pk == second.pk
    assert (
        SupplierLedgerEntry.objects.filter(
            entry_type=SupplierLedgerEntry.Type.ADJUSTMENT
        ).count()
        == 1
    ), "a second reversal is a no-op, not a second credit"
    assert supplier_balance(owing) == Decimal("12500.00")


def test_a_reversal_needs_a_reason_and_a_date(owner, owing):
    payment = _pay(owner, owing)
    with pytest.raises(ValidationFailed) as exc:
        reverse_supplier_payment(
            actor=owner, payment=payment, reason="  ", reversal_date=REVERSED_ON
        )
    assert exc.value.errors[0]["field"] == "reason"

    with pytest.raises(ValidationFailed) as exc:
        reverse_supplier_payment(
            actor=owner, payment=payment, reason="Bounced", reversal_date=None
        )
    assert exc.value.errors[0]["field"] == "reversal_date"


def test_only_the_owner_may_reverse(owner, salesman, owing):
    payment = _pay(owner, owing)
    with pytest.raises(PermissionDenied):
        reverse_supplier_payment(
            actor=salesman, payment=payment, reason="Nope", reversal_date=REVERSED_ON
        )


def test_a_reversal_does_not_prevent_another_legitimate_payment(owner, owing):
    """A bounced cheque is not the end of paying a supplier."""
    first = _pay(owner, owing, "2500.00")
    reverse_supplier_payment(
        actor=owner, payment=first, reason="Cheque bounced", reversal_date=REVERSED_ON
    )
    second = _pay(owner, owing, "2500.00", payment_date=date(2026, 8, 10))

    assert second.pk != first.pk
    assert SupplierPayment.objects.count() == 2
    assert supplier_balance(owing) == Decimal("10000.00")


# ----------------------------------------------------------------------------- audit


def test_the_payment_is_audited_and_the_ledger_entry_is_not(owner, owing):
    """R-3, unchanged since Stage 3 and S4.1."""
    payment = _pay(owner, owing)

    assert (
        AuditLog.objects.filter(entity_type="supplier_payment", entity_id=payment.pk).count()
        == 1
    )
    assert not AuditLog.objects.filter(entity_type="supplier_ledger_entry").exists()


def test_a_reversal_is_audited_once_under_its_own_action(owner, owing):
    payment = _pay(owner, owing)
    reverse_supplier_payment(
        actor=owner, payment=payment, reason="Cheque bounced", reversal_date=REVERSED_ON
    )

    entries = AuditLog.objects.filter(entity_type="supplier_payment").order_by("id")
    assert [e.action for e in entries] == [
        AuditLog.Action.CREATE,
        AuditLog.Action.PAYMENT_REVERSE,
    ]
    assert entries[1].after_state["reason"] == "Cheque bounced"


def test_the_audit_payload_survives_redaction(owner, owing):
    """`supplier_code`, never `code` — `core.services._SENSITIVE` matches `code` exactly."""
    payment = _pay(owner, owing)
    entry = AuditLog.objects.get(entity_type="supplier_payment", entity_id=payment.pk)

    assert entry.after_state["supplier_code"] == "ACME"
    assert entry.after_state["payment_number"] == payment.payment_number
    assert "[redacted]" not in str(entry.after_state)
