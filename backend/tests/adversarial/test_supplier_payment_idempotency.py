"""**E3 — accidental duplicate submission must not pay a supplier twice** (D5 S4.3 §3).

The four rules this suite asserts, from the frozen design §3.7:

* **S-1** the same `submission_id` is the same logical payment attempt;
* **S-2** a separate form render gets a new id and may be a legitimate second payment;
* **S-3** an identical replay returns the original payment;
* **S-4** the same id with a changed business payload is rejected explicitly.

**Why this is adversarial rather than a unit test.** The guarantee is a database unique
index, and the failure it prevents happens *between* two requests. A sequential test proves
only the service's pre-check; the index is proven by two connections racing, and by removing
the index and requiring the race test to fail.

**The identity is a form render, not a payload.** Two ₹50,000 payments to one supplier on
one day are ordinary — a distributor settling two invoices in a morning — so any natural key
over `(supplier, amount, payment_date)` would refuse a real payment. `test_..._different_
submission_ids_are_two_real_payments` is the test that fails such a key.
"""

from __future__ import annotations

import threading
import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.db import connection, connections, transaction

from core.exceptions import ValidationFailed
from core.models import AuditLog
from ledger.models import SupplierLedgerEntry
from ledger.selectors import supplier_balance
from purchasing.models import SupplierPayment
from purchasing.services import (
    create_supplier,
    load_supplier_opening_balance,
    record_supplier_payment,
)

pytestmark = pytest.mark.adversarial

GO_LIVE = date(2026, 4, 1)
PAID_ON = date(2026, 8, 2)


@pytest.fixture
def supplier(owner):
    return create_supplier(
        actor=owner,
        code="acme",
        name="Acme Distributors",
        phone="+919876500011",
        billing_address="Industrial Estate",
    )


@pytest.fixture
def owing(owner, supplier):
    load_supplier_opening_balance(
        actor=owner, supplier=supplier, amount="500000.00", entry_date=GO_LIVE
    )
    return supplier


def _payload(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "amount": "50000.00",
        "method": SupplierPayment.Method.BANK,
        "payment_date": PAID_ON,
        "reference_number": "UTR-9911",
        "notes": "August settlement",
    }
    fields.update(overrides)
    return fields


# ------------------------------------------------------------------ S-1 / S-3 sequential


@pytest.mark.django_db
def test_a_sequential_identical_replay_returns_the_original_and_pays_once(owner, owing):
    """S-3. The double-click, the Back-then-resubmit, the refresh on the POST result."""
    submission_id = uuid.uuid4()

    first = record_supplier_payment(
        actor=owner, supplier=owing, submission_id=submission_id, **_payload()
    )
    second = record_supplier_payment(
        actor=owner, supplier=owing, submission_id=submission_id, **_payload()
    )

    assert first.pk == second.pk
    assert SupplierPayment.objects.count() == 1
    assert (
        SupplierLedgerEntry.objects.filter(
            entry_type=SupplierLedgerEntry.Type.PAYMENT
        ).count()
        == 1
    ), "a replay must not write a second ledger entry"
    assert supplier_balance(owing) == Decimal("450000.00"), "the balance moved once"
    assert (
        AuditLog.objects.filter(entity_type="supplier_payment").count() == 1
    ), "nothing happened the second time, so nothing is audited"


@pytest.mark.django_db
def test_ten_replays_still_pay_once(owner, owing):
    """A held-down key, or a client retrying on a timeout it never saw resolve."""
    submission_id = uuid.uuid4()
    results = [
        record_supplier_payment(
            actor=owner, supplier=owing, submission_id=submission_id, **_payload()
        )
        for _ in range(10)
    ]

    assert len({p.pk for p in results}) == 1
    assert SupplierPayment.objects.count() == 1
    assert supplier_balance(owing) == Decimal("450000.00")


# ------------------------------------------------------------------------- S-2 legitimate


@pytest.mark.django_db
def test_same_supplier_amount_and_date_with_different_submission_ids_are_two_payments(
    owner, owing
):
    """**S-2, and the test that disqualifies a naive natural key.**

    Identical supplier, identical amount, identical date, identical everything — except the
    form was loaded twice. That is two payments, and any deduplication keyed on
    `(supplier, amount, payment_date)` would silently refuse the second one.
    """
    first = record_supplier_payment(
        actor=owner, supplier=owing, submission_id=uuid.uuid4(), **_payload()
    )
    second = record_supplier_payment(
        actor=owner, supplier=owing, submission_id=uuid.uuid4(), **_payload()
    )

    assert first.pk != second.pk
    assert first.payment_number != second.payment_number
    assert SupplierPayment.objects.count() == 2
    assert supplier_balance(owing) == Decimal("400000.00"), "both payments landed"


# --------------------------------------------------------------------- S-4 changed payload


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", "60000.00"),
        ("payment_date", date(2026, 8, 3)),
        ("method", SupplierPayment.Method.CHEQUE),
        ("reference_number", "UTR-0000"),
        ("notes", "September settlement"),
    ],
)
def test_a_replay_with_any_changed_field_is_rejected(owner, owing, field, value):
    """S-4, one case per caller-supplied field — `notes` included.

    A replay whose only change is a note would otherwise succeed while silently discarding
    the note. Ignoring is a quieter failure than refusing, not a smaller one.
    """
    submission_id = uuid.uuid4()
    original = record_supplier_payment(
        actor=owner, supplier=owing, submission_id=submission_id, **_payload()
    )

    with pytest.raises(ValidationFailed) as exc:
        record_supplier_payment(
            actor=owner,
            supplier=owing,
            submission_id=submission_id,
            **_payload(**{field: value}),
        )

    assert exc.value.errors[0]["code"] == "SUBMISSION_REPLAYED_WITH_CHANGES"
    assert field in exc.value.errors[0]["message"] or field == "payment_date"

    original.refresh_from_db()
    assert original.amount == Decimal("50000.00"), "the original is never altered"
    assert SupplierPayment.objects.count() == 1
    assert supplier_balance(owing) == Decimal("450000.00")


@pytest.mark.django_db
def test_a_replay_against_a_different_supplier_is_rejected(owner, owing):
    """The id belongs to one attempt, and an attempt names one supplier."""
    other = create_supplier(
        actor=owner,
        code="brio",
        name="Brio Traders",
        phone="+919876500022",
        billing_address="Market Road",
    )
    submission_id = uuid.uuid4()
    record_supplier_payment(
        actor=owner, supplier=owing, submission_id=submission_id, **_payload()
    )

    with pytest.raises(ValidationFailed) as exc:
        record_supplier_payment(
            actor=owner, supplier=other, submission_id=submission_id, **_payload()
        )

    assert exc.value.errors[0]["code"] == "SUBMISSION_REPLAYED_WITH_CHANGES"
    assert supplier_balance(other) == Decimal("0.00")


@pytest.mark.django_db
def test_an_equivalent_amount_written_differently_is_still_the_same_submission(owner, owing):
    """`50000` and `50000.00` are one figure. `to_money` decides, not the string."""
    submission_id = uuid.uuid4()
    first = record_supplier_payment(
        actor=owner, supplier=owing, submission_id=submission_id, **_payload(amount="50000")
    )
    second = record_supplier_payment(
        actor=owner, supplier=owing, submission_id=submission_id, **_payload(amount="50000.00")
    )
    assert first.pk == second.pk


# ------------------------------------------------------ a failed attempt is reusable


@pytest.mark.django_db
def test_a_validation_failure_leaves_the_submission_id_reusable(owner, owing):
    """The quiet advantage of holding the identity on the payment row itself.

    No row is written when validation fails, so the id is unconsumed and the owner may
    correct the form and submit the same render again. A separate idempotency table would
    have needed an explicit state for this; here it falls out of the absence of a row.
    """
    submission_id = uuid.uuid4()

    with pytest.raises(ValidationFailed):
        record_supplier_payment(
            actor=owner, supplier=owing, submission_id=submission_id, **_payload(amount="0")
        )
    assert not SupplierPayment.objects.exists()

    payment = record_supplier_payment(
        actor=owner, supplier=owing, submission_id=submission_id, **_payload()
    )
    assert payment.submission_id == submission_id
    assert supplier_balance(owing) == Decimal("450000.00")


# --------------------------------------------------------------------- concurrency


@pytest.mark.django_db(transaction=True)
def test_concurrent_identical_submissions_pay_once(owner, owing):
    """**The case a sequential test cannot reach.**

    Two real connections, both past the service's pre-check before either inserts. Only
    `uq_supplier_payment_submission` can decide this, and the loser must recover through the
    `IntegrityError` path and return the winner's payment rather than raising.

    `transaction=True` is required: the default `django_db` fixture wraps each test in one
    transaction on one connection, so a second thread would never see the first thread's
    uncommitted row and the race could not be reproduced.
    """
    submission_id = uuid.uuid4()
    barrier = threading.Barrier(2)
    results: list[object] = []
    failures: list[BaseException] = []

    def submit() -> None:
        try:
            barrier.wait(timeout=10)
            payment = record_supplier_payment(
                actor=owner, supplier=owing, submission_id=submission_id, **_payload()
            )
            results.append(payment.pk)
        except BaseException as exc:  # reported, never swallowed
            failures.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not failures, f"a concurrent duplicate raised instead of recovering: {failures}"
    assert len(results) == 2, "both callers must get an answer"
    assert len(set(results)) == 1, "and it must be the same payment"

    assert SupplierPayment.objects.count() == 1
    assert (
        SupplierLedgerEntry.objects.filter(
            entry_type=SupplierLedgerEntry.Type.PAYMENT
        ).count()
        == 1
    ), "the loser must not have written a ledger entry"
    assert supplier_balance(owing) == Decimal("450000.00")


@pytest.mark.django_db(transaction=True)
def test_concurrent_submissions_with_different_ids_both_pay(owner, owing):
    """The mirror image: concurrency must not suppress two genuine payments."""
    barrier = threading.Barrier(2)
    results: list[int] = []
    failures: list[BaseException] = []

    def submit() -> None:
        try:
            barrier.wait(timeout=10)
            payment = record_supplier_payment(
                actor=owner, supplier=owing, submission_id=uuid.uuid4(), **_payload()
            )
            results.append(payment.pk)
        except BaseException as exc:  # reported, never swallowed
            failures.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not failures, f"a legitimate concurrent payment was refused: {failures}"
    assert len(set(results)) == 2
    assert SupplierPayment.objects.count() == 2
    assert supplier_balance(owing) == Decimal("400000.00")


@pytest.mark.django_db(transaction=True)
def test_concurrent_reversals_credit_the_supplier_once(owner, owing):
    """`select_for_update` is the guard, and this is what it guards.

    Without the row lock both callers read `is_reversed = False` and both append a
    compensating entry, crediting the supplier twice.
    """
    from purchasing.services import reverse_supplier_payment

    payment = record_supplier_payment(
        actor=owner, supplier=owing, submission_id=uuid.uuid4(), **_payload()
    )
    barrier = threading.Barrier(2)
    failures: list[BaseException] = []

    def reverse() -> None:
        try:
            barrier.wait(timeout=10)
            reverse_supplier_payment(
                actor=owner,
                payment=payment,
                reason="Cheque bounced",
                reversal_date=date(2026, 8, 6),
            )
        except BaseException as exc:  # reported, never swallowed
            failures.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=reverse) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not failures, f"a concurrent reversal raised: {failures}"
    assert (
        SupplierLedgerEntry.objects.filter(
            entry_type=SupplierLedgerEntry.Type.ADJUSTMENT
        ).count()
        == 1
    ), "one reversal, one compensating entry"
    assert supplier_balance(owing) == Decimal("500000.00")


# ----------------------------------------------------- the index is the guarantee


@pytest.mark.django_db
def test_the_unique_index_exists_and_covers_submission_id(owner, owing):
    """Anti-vacuity for everything above.

    Every sequential test would still pass if the guarantee were only the service's
    pre-check. This asserts the constraint the concurrency tests actually rely on, by asking
    the database rather than the model.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM pg_index i
            JOIN pg_class t ON t.oid = i.indrelid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY (i.indkey)
            WHERE t.relname = 'supplier_payment'
              AND i.indisunique
              AND a.attname = 'submission_id'
            """
        )
        assert cursor.fetchone()[0] == 1, (
            "supplier_payment.submission_id has no unique index — E3's guarantee is gone "
            "and every duplicate test above is passing on the pre-check alone"
        )


@pytest.mark.django_db
def test_submission_id_is_not_nullable(owner, owing):
    """A nullable identity could not enforce anything at the boundary."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'supplier_payment' AND column_name = 'submission_id'"
        )
        assert cursor.fetchone()[0] == "NO"


@pytest.mark.django_db
def test_the_database_refuses_a_duplicate_submission_id_directly(owner, owing):
    """Past the service entirely. The index, on its own."""
    payment = record_supplier_payment(
        actor=owner, supplier=owing, submission_id=uuid.uuid4(), **_payload()
    )

    from django.db import IntegrityError

    with pytest.raises(IntegrityError), transaction.atomic():
        SupplierPayment.objects.create(
            submission_id=payment.submission_id,
            payment_number="SPY-99999999",
            supplier=owing,
            amount=Decimal("1.00"),
            method=SupplierPayment.Method.CASH,
            payment_date=PAID_ON,
        )
