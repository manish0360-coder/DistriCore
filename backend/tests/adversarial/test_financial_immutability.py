"""A-1, A-2 — issued financial documents and the ledger cannot be altered.

Most assertions here go through **raw SQL**, deliberately. A Python guard proves the ORM
refuses; only the database can prove that a management command, a psql session or a
future developer's ``.update()`` refuses too. If an invoice can be edited, no historical
financial claim this system makes is provable.

**Why plain ``django_db`` rather than ``transaction=True``.** A transactional test is torn
down by TRUNCATE, which would destroy the reason codes and the default stock location
that migrations seed — for this test and every one that ran after it. Each refusal is
therefore taken inside its own savepoint instead, which is what ``_refuse`` does.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection, transaction

from billing.models import CreditNote, DocumentImmutable, Invoice, InvoiceLine
from billing.services import cancel_invoice, issue_credit_note, issue_invoice
from catalogue.services import update_product
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.services import receive_stock
from ledger.models import CustomerLedgerEntry, LedgerEntryImmutable
from ledger.selectors import settled_balance
from orders.services import confirm_order, place_order

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]


@pytest.fixture
def invoice(owner, credit_customer, product, receipt_reason):
    receive_stock(
        actor=owner, product=product, quantity=Decimal("1000"), reason_code=receipt_reason
    )
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "24"}]
    )
    confirm_order(actor=owner, order=order)
    delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
    dispatch_delivery(actor=owner, delivery=delivery)
    return issue_invoice(actor=owner, order=order)


def _refuse(statement: str, params: list, match: str) -> None:
    """Run a statement the database must reject, inside its own savepoint.

    A failed statement aborts the enclosing PostgreSQL transaction. ``pytest.raises`` must
    be the OUTER context so the savepoint rolls back before the exception is swallowed —
    the other order leaves an aborted transaction and every later query fails.
    """
    with pytest.raises(Exception, match=match), transaction.atomic(), connection.cursor() as cur:
        cur.execute(statement, params)


# --------------------------------------------------------------------------- A-1
def test_raw_sql_cannot_change_an_invoice_amount(invoice):
    _refuse(
        "UPDATE invoice SET total_amount = 1 WHERE id = %s", [invoice.pk], "immutable once issued"
    )
    invoice.refresh_from_db()
    assert invoice.total_amount > Decimal("1.00")


def test_raw_sql_cannot_delete_an_invoice(invoice):
    _refuse("DELETE FROM invoice WHERE id = %s", [invoice.pk], "never deleted")
    assert Invoice.objects.filter(pk=invoice.pk).exists()


def test_raw_sql_cannot_touch_an_invoice_line(invoice):
    line = invoice.lines.first()
    _refuse(
        "UPDATE invoice_line SET quantity = 999 WHERE id = %s", [line.pk], "immutable once issued"
    )
    _refuse("DELETE FROM invoice_line WHERE id = %s", [line.pk], "immutable once issued")
    assert InvoiceLine.objects.filter(pk=line.pk).exists()


def test_raw_sql_cannot_touch_a_ledger_entry(invoice, credit_customer):
    entry = CustomerLedgerEntry.objects.get(customer=credit_customer)
    _refuse(
        "UPDATE customer_ledger_entry SET amount = 0.01 WHERE id = %s", [entry.pk], "append-only"
    )
    _refuse("DELETE FROM customer_ledger_entry WHERE id = %s", [entry.pk], "append-only")
    assert settled_balance(credit_customer) == invoice.total_amount


def test_raw_sql_cannot_touch_a_credit_note(owner, invoice):
    note = issue_credit_note(
        actor=owner,
        invoice=invoice,
        lines=[{"invoice_line": invoice.lines.first(), "quantity": Decimal("1")}],
        reason="Short supply",
    )
    _refuse(
        "UPDATE credit_note SET total_amount = 1 WHERE id = %s", [note.pk], "immutable once issued"
    )
    _refuse("DELETE FROM credit_note WHERE id = %s", [note.pk], "immutable once issued")
    _refuse(
        "UPDATE credit_note_line SET quantity = 99 WHERE credit_note_id = %s",
        [note.pk],
        "immutable once issued",
    )


def test_the_orm_refuses_before_the_database_has_to(invoice):
    """Both layers hold. The Python guard gives a usable error; the trigger is the proof."""
    with pytest.raises(DocumentImmutable):
        invoice.total_amount = Decimal("1.00")
        invoice.save()
    with pytest.raises(DocumentImmutable):
        Invoice.objects.filter(pk=invoice.pk).update(total_amount=Decimal("1.00"))
    with pytest.raises(DocumentImmutable):
        invoice.delete()
    with pytest.raises(LedgerEntryImmutable):
        CustomerLedgerEntry.objects.all().delete()
    with pytest.raises(LedgerEntryImmutable):
        CustomerLedgerEntry.objects.all().update(amount=Decimal("0.01"))


def test_bulk_mutation_of_lines_and_notes_is_refused(invoice):
    with pytest.raises(DocumentImmutable):
        InvoiceLine.objects.all().update(quantity=Decimal("1.000"))
    with pytest.raises(DocumentImmutable):
        InvoiceLine.objects.all().delete()
    with pytest.raises(DocumentImmutable):
        CreditNote.objects.all().delete()


def test_a_ledger_entry_instance_cannot_be_re_saved(invoice, credit_customer):
    entry = CustomerLedgerEntry.objects.get(customer=credit_customer)
    entry.amount = Decimal("1.00")
    with pytest.raises(LedgerEntryImmutable):
        entry.save()
    with pytest.raises(LedgerEntryImmutable):
        entry.delete()


# --------------------------------------------------------------------------- cancellation
def test_cancellation_is_the_only_permitted_change(owner, invoice):
    cancelled = cancel_invoice(actor=owner, invoice=invoice, reason="Wrong customer")
    assert cancelled.status == Invoice.Status.CANCELLED
    assert cancelled.total_amount == invoice.total_amount, "cancellation changes no value"


def test_raw_sql_cannot_cancel_without_a_reason(invoice):
    _refuse(
        "UPDATE invoice SET status = 'CANCELLED' WHERE id = %s", [invoice.pk], "without a reason"
    )


def test_raw_sql_cannot_uncancel(owner, invoice):
    cancel_invoice(actor=owner, invoice=invoice, reason="Wrong customer")
    _refuse("UPDATE invoice SET status = 'ISSUED' WHERE id = %s", [invoice.pk], "cannot go from")


def test_cancelling_reverses_the_receivable(owner, invoice, credit_customer):
    """The ledger is append-only, so a cancellation compensates rather than erases."""
    assert settled_balance(credit_customer) == invoice.total_amount
    cancel_invoice(actor=owner, invoice=invoice, reason="Wrong customer")
    assert settled_balance(credit_customer) == Decimal("0.00")
    assert CustomerLedgerEntry.objects.filter(customer=credit_customer).count() == 2


def test_a_cancelled_invoice_cannot_be_credited(owner, invoice):
    cancel_invoice(actor=owner, invoice=invoice, reason="Wrong customer")
    with pytest.raises(Exception, match="cancelled invoice cannot be credited"):
        issue_credit_note(
            actor=owner,
            invoice=invoice,
            lines=[{"invoice_line": invoice.lines.first(), "quantity": Decimal("1")}],
            reason="Too late",
        )


def test_an_invoice_with_credit_notes_cannot_be_cancelled(owner, invoice):
    """Two mechanisms for one outcome would be ambiguous. Credit wins once started."""
    issue_credit_note(
        actor=owner,
        invoice=invoice,
        lines=[{"invoice_line": invoice.lines.first(), "quantity": Decimal("1")}],
        reason="Short supply",
    )
    with pytest.raises(Exception, match="cannot be cancelled"):
        cancel_invoice(actor=owner, invoice=invoice, reason="Changed my mind")


# --------------------------------------------------------------------------- A-2
def test_a_price_change_does_not_alter_an_issued_invoice(owner, invoice, product):
    """M5-2 / FR-BIL-008 — the whole reason the document snapshots itself."""
    original_unit_price = invoice.lines.first().unit_price
    original_total = invoice.total_amount

    update_product(actor=owner, product=product, selling_price=Decimal("999.00"))

    invoice.refresh_from_db()
    assert invoice.lines.first().unit_price == original_unit_price
    assert invoice.total_amount == original_total


def test_a_renamed_product_does_not_alter_an_issued_invoice(owner, invoice, product):
    original_name = invoice.lines.first().product_name
    update_product(actor=owner, product=product, name="Completely Different Product")
    invoice.refresh_from_db()
    assert invoice.lines.first().product_name == original_name


# --------------------------------------------------------------------------- constraints
def test_the_database_refuses_a_mixed_gst_split(invoice):
    """M5-7 — the one GST rule worth enforcing in the database."""
    _refuse(
        "INSERT INTO invoice_line (invoice_id, line_number, product_code, product_name, "
        "hsn_code, quantity, unit_name, unit_price, discount_amount, taxable_amount, "
        "tax_rate_percent, cgst_amount, sgst_amount, igst_amount, line_total) "
        "VALUES (%s, 99, 'X', 'X', '', 1, 'pc', 1, 0, 1, 18, 1, 1, 1, 3)",
        [invoice.pk],
        "ck_invoice_line_gst_split",
    )


def test_the_database_refuses_a_wrong_signed_ledger_entry(credit_customer):
    """``ck_cle_sign`` — a service-layer sign error is rejected, not silently absorbed."""
    _refuse(
        "INSERT INTO customer_ledger_entry "
        "(customer_id, entry_date, entry_type, amount, narration, "
        " source_document_type, source_document_id, created_at) "
        "VALUES (%s, CURRENT_DATE, 'PAYMENT', 500.00, 'wrong sign', '', NULL, now())",
        [credit_customer.pk],
        "ck_cle_sign",
    )


def test_the_database_refuses_a_zero_ledger_entry(credit_customer):
    _refuse(
        "INSERT INTO customer_ledger_entry "
        "(customer_id, entry_date, entry_type, amount, narration, "
        " source_document_type, source_document_id, created_at) "
        "VALUES (%s, CURRENT_DATE, 'ADJUSTMENT', 0, 'nothing', '', NULL, now())",
        [credit_customer.pk],
        "ck_cle_amount_nonzero",
    )


def test_the_database_refuses_half_a_source_reference(credit_customer):
    """``ck_cle_source_pair`` — half a polymorphic reference is worse than none (R-2)."""
    _refuse(
        "INSERT INTO customer_ledger_entry "
        "(customer_id, entry_date, entry_type, amount, narration, "
        " source_document_type, source_document_id, created_at) "
        "VALUES (%s, CURRENT_DATE, 'OPENING', 10, 'dangling', 'INVOICE', NULL, now())",
        [credit_customer.pk],
        "ck_cle_source_pair",
    )
