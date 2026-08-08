"""M6 adversarial suite — immutability, boundaries and the scenario the walk exists for.

Raw SQL, deliberately. A Python guard proves the ORM refuses; only the database can prove
that a management command, a psql session or a future `.update()` refuses too.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest
from django.db import connection, transaction

from billing.models import DocumentImmutable
from billing.services import issue_credit_note, issue_invoice
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.models import StockMovement
from inventory.services import receive_stock
from ledger.models import CustomerLedgerEntry
from ledger.selectors import settled_balance
from orders.selectors import credit_exposure
from orders.services import confirm_order, place_order
from receivables.models import Payment
from receivables.selectors import outstanding_for
from receivables.services import load_opening_balance, record_payment, reverse_payment

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]


def _refuse(statement: str, params: list, match: str) -> None:
    """Expect the database to refuse, without poisoning the test's transaction.

    ``pytest.raises`` must be the OUTER context so the savepoint rolls back before the
    exception is swallowed — the M5 pattern.
    """
    with pytest.raises(Exception, match=match), transaction.atomic(), connection.cursor() as cur:
        cur.execute(statement, params)


@pytest.fixture
def invoiced(owner, credit_customer, product, receipt_reason):
    receive_stock(
        actor=owner, product=product, quantity=Decimal("1000"), reason_code=receipt_reason
    )
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "10"}]
    )
    confirm_order(actor=owner, order=order)
    dispatch_delivery(
        actor=owner, delivery=assign_delivery(actor=owner, order=order, assigned_user=owner)
    )
    return issue_invoice(actor=owner, order=order)


@pytest.fixture
def paid(owner, credit_customer):
    return record_payment(
        actor=owner, customer=credit_customer, amount=Decimal("500.00"), method="CASH"
    )


# --------------------------------------------------------------------------- immutability
def test_raw_sql_cannot_change_a_payment_amount(paid):
    _refuse(
        "UPDATE payment SET amount = 1 WHERE id = %s", [paid.pk], "immutable|append-only"
    )
    paid.refresh_from_db()
    assert paid.amount == Decimal("500.00")


def test_raw_sql_cannot_delete_a_payment(paid):
    _refuse("DELETE FROM payment WHERE id = %s", [paid.pk], "immutable|never deleted")
    assert Payment.objects.filter(pk=paid.pk).exists()


def test_the_orm_refuses_before_the_database_has_to(paid):
    with pytest.raises(DocumentImmutable):
        paid.amount = Decimal("1.00")
        paid.save()
    with pytest.raises(DocumentImmutable):
        Payment.objects.filter(pk=paid.pk).update(amount=Decimal("1.00"))
    with pytest.raises(DocumentImmutable):
        paid.delete()


def test_the_database_refuses_a_second_opening_balance(owner, credit_customer):
    """M6-11 / D-10 — the idempotency guarantee, enforced where code cannot bypass it."""
    load_opening_balance(actor=owner, customer=credit_customer, amount="1000.00")
    _refuse(
        "INSERT INTO customer_ledger_entry "
        "(customer_id, entry_date, entry_type, amount, narration, "
        " source_document_type, source_document_id, created_at) "
        "VALUES (%s, CURRENT_DATE, 'OPENING', 500.00, 'second opening', '', NULL, now())",
        [credit_customer.pk],
        "uq_cle_one_opening_per_customer",
    )
    assert settled_balance(credit_customer) == Decimal("1000.00")


def test_the_database_refuses_a_non_positive_payment(credit_customer):
    _refuse(
        "INSERT INTO payment (payment_number, customer_id, amount, method, payment_date, "
        " reference_number, device_id, notes, is_reversed, reversed_reason, created_at) "
        "VALUES ('PAY-X', %s, 0, 'CASH', CURRENT_DATE, '', '', '', false, '', now())",
        [credit_customer.pk],
        "ck_payment_amount",
    )


# --------------------------------------------------------------------------- boundaries
def test_a_payment_moves_no_stock(owner, credit_customer, product, receipt_reason):
    """A payment is money. It moves no goods (M2 boundary)."""
    receive_stock(
        actor=owner, product=product, quantity=Decimal("50"), reason_code=receipt_reason
    )
    before = StockMovement.objects.count()
    payment = record_payment(
        actor=owner, customer=credit_customer, amount="100.00", method="CASH"
    )
    reverse_payment(actor=owner, payment=payment, reason="Wrong customer")
    assert StockMovement.objects.count() == before


def test_a_payment_does_not_modify_the_invoice_it_settles(owner, invoiced, credit_customer):
    """M5-3 — invoices are immutable and "paid" is derived, never a column."""
    before = (invoiced.total_amount, invoiced.status)
    record_payment(
        actor=owner, customer=credit_customer, amount=invoiced.total_amount, method="UPI"
    )
    invoiced.refresh_from_db()
    assert (invoiced.total_amount, invoiced.status) == before


def test_receivables_never_imports_the_billing_writer():
    """Structural. `receivables` reads `billing` for credit-note targeting (§5A.10).

    That read is why the layer graph puts it above `billing`. It must never import
    `billing.services` — the same read/write distinction the M5 boundary suite drew for
    `orders -> ledger`.
    """
    import receivables

    package_root = Path(receivables.__file__).parent
    offenders = {}
    for module in package_root.rglob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = ""
            if isinstance(node, ast.ImportFrom) and node.module:
                name = node.module
            elif isinstance(node, ast.Import):
                name = ",".join(alias.name for alias in node.names)
            if "billing.services" in name or "inventory" in name:
                offenders[module.relative_to(package_root).as_posix()] = name
    assert offenders == {}, f"receivables reached too far: {offenders}"


def test_no_allocation_table_exists():
    """C-1. Allocation is Edition 2. An unused table invites a future developer to fill it.

    **Scoped to `public`.** Unscoped, `information_schema.tables` also returns PostgreSQL's
    own catalogs, and the server ships a system view called `pg_shmem_allocations` — so the
    original assertion was reporting on the database engine rather than on this schema.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name LIKE %s",
            ["%allocation%"],
        )
        assert cursor.fetchone()[0] == 0


# --------------------------------------------------------------------------- scenarios
def test_a_payment_frees_credit_headroom(owner, invoiced, credit_customer):
    """D-9's dividend: exposure reads the ledger, so M6 writes no code to make this work."""
    before = credit_exposure(credit_customer)
    assert before == invoiced.total_amount

    record_payment(
        actor=owner, customer=credit_customer, amount=invoiced.total_amount, method="CASH"
    )
    assert credit_exposure(credit_customer) == Decimal("0.00")


def test_a_credit_note_reduces_its_invoice_end_to_end(owner, invoiced, credit_customer):
    """§5A.2 through the real services, not a constructed ledger."""
    note = issue_credit_note(
        actor=owner,
        invoice=invoiced,
        lines=[{"invoice_line": invoiced.lines.first(), "quantity": Decimal("2")}],
        reason="Two damaged",
    )
    position = outstanding_for(credit_customer)
    assert position.total_outstanding == invoiced.total_amount - note.total_amount
    assert position.total_outstanding - position.credit_on_account == settled_balance(
        credit_customer
    )


def test_a_reversed_payment_restores_the_debt_end_to_end(owner, invoiced, credit_customer):
    """The §5A.3 annulling case, driven by the real services."""
    payment = record_payment(
        actor=owner, customer=credit_customer, amount=invoiced.total_amount, method="CASH"
    )
    assert outstanding_for(credit_customer).total_outstanding == Decimal("0.00")

    reverse_payment(actor=owner, payment=payment, reason="Cheque bounced")

    position = outstanding_for(credit_customer)
    assert position.total_outstanding == invoiced.total_amount
    assert len(position.outstanding) == 1
    assert position.outstanding[0].entry_type == CustomerLedgerEntry.Type.INVOICE, (
        "the debt is the invoice again, not a fresh adjustment"
    )
    assert position.total_outstanding - position.credit_on_account == settled_balance(
        credit_customer
    )
