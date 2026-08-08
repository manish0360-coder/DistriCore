"""Receivables business rules — the only writer of Payment.

**A payment reduces what a customer owes. It does not pay an invoice** (M6-1). Nothing
here allocates, and nothing here stores a balance.

Three properties are load-bearing and each is the subject of an irreversible decision:

* **M6-2** — ``payment_number`` comes from ``nextval`` *before* the insert, so a payment
  row is written in **one statement**. An ``UPDATE`` to set the number would touch a
  column outside ``Payment._mutable_fields`` and the immutability trigger would refuse it.
* **M6-3 / §6.1** — reversal takes ``SELECT … FOR UPDATE`` on the payment row. It is the
  **only lock in M6**, and it is real because the row it locks is the row it mutates.
* **M6-11 / D-10** — the opening-balance load is idempotent on a natural key: one
  ``OPENING`` entry per customer, enforced by a partial unique index.

**No other path here takes a lock.** A lock serialises only the writers that take it, and
every other ledger writer — ``issue_invoice``, ``issue_credit_note``, ``record_payment`` —
appends without one by design since M2. A lock that a single writer acquires excludes
nobody and reads to the next maintainer as protection that exists (§6.2).
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from core.exceptions import ResourceNotFound, ValidationFailed
from core.fields import to_money
from core.models import AuditLog
from core.permissions import Role, require_roles
from core.services import record_audit
from ledger.models import CustomerLedgerEntry
from ledger.selectors import settled_balance
from ledger.services import record_entry
from receivables.models import PAYMENT_NUMBER_SEQUENCE, Payment

logger = logging.getLogger("districore.receivables")


def _next_payment_number() -> str:
    """Allocate the next receipt reference (M6-2).

    ``nextval`` is lock-free and concurrency-safe, and it is read **before** the insert so
    the row is written once. Gaps are permitted: a rolled-back collection consumes a
    number, which is correct behaviour for a reference and would be a defect only for a
    statutory series (contrast ``billing.services.allocate_number``, which locks a counter
    row precisely because invoices must be gapless — M5-4).
    """
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT nextval('{PAYMENT_NUMBER_SEQUENCE}')")
        value = cursor.fetchone()[0]
    return f"PAY-{value:08d}"


# --------------------------------------------------------------------------- payment
@transaction.atomic
def record_payment(
    *,
    actor: Any,
    customer: Any,
    amount: Decimal | str | int,
    method: str,
    payment_date: date | None = None,
    reference_number: str = "",
    notes: str = "",
    device_id: str = "",
    client_uuid: uuid_lib.UUID | str | None = None,
) -> Payment:
    """Record a collection. Owner, salesman and delivery staff may all collect (05 §8).

    Idempotent on ``client_uuid``: replaying an accepted key returns the original payment
    rather than crediting the customer twice.
    """
    require_roles(actor, Role.OWNER, Role.SALESMAN, Role.DELIVERY)

    if client_uuid:
        existing = Payment.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing

    amount = to_money(amount)
    if amount <= 0:
        raise ValidationFailed(
            "A payment must be greater than zero.",
            errors=[{"field": "amount", "code": "MIN_VALUE", "message": str(amount)}],
        )
    if method not in Payment.Method.values:
        raise ValidationFailed(
            "Unknown payment method.",
            errors=[{"field": "method", "code": "INVALID", "message": str(method)}],
        )
    if not customer.is_active:
        raise ValidationFailed(
            "That customer is deactivated.",
            errors=[{"field": "customer", "code": "INACTIVE", "message": customer.code}],
        )

    on = payment_date or timezone.localdate()

    try:
        # The savepoint matters: a check-then-insert on client_uuid races, and
        # uq_payment_client_uuid is the guarantee. Without the savepoint an IntegrityError
        # would abort the whole transaction and a legitimate retry would become a 500
        # instead of the original receipt.
        with transaction.atomic():
            payment = Payment.objects.create(
                payment_number=_next_payment_number(),
                client_uuid=client_uuid or None,
                customer=customer,
                amount=amount,
                method=method,
                reference_number=reference_number[:100],
                payment_date=on,
                received_by=actor if getattr(actor, "pk", None) else None,
                device_id=device_id[:64],
                notes=notes,
            )
    except IntegrityError:
        if not client_uuid:
            raise
        existing = Payment.objects.filter(client_uuid=client_uuid).first()
        if existing is None:  # pragma: no cover - the constraint that fired was another
            raise
        return existing

    record_entry(
        actor=actor,
        customer=customer,
        entry_type=CustomerLedgerEntry.Type.PAYMENT,
        amount=-amount,
        narration=f"Payment {payment.payment_number} ({payment.get_method_display()})",
        entry_date=on,
        source_document=payment,
    )

    logger.info(
        "payment_recorded",
        extra={
            "payment_id": payment.pk,
            "payment_number": payment.payment_number,
            "customer": customer.code,
            "amount": str(amount),
            "method": method,
        },
    )
    return payment


@transaction.atomic
def reverse_payment(*, actor: Any, payment: Payment, reason: str) -> Payment:
    """Reverse a collection (FR-REC-007). **The only lock in M6.**

    The original entry is never edited. A compensating ``ADJUSTMENT`` is appended, because
    ``ck_cle_sign`` requires a ``PAYMENT`` entry to be negative and a reversal increases
    what is owed — the same path M5's ``cancel_invoice`` takes, for the same reason.

    **The lock is real, unlike the one §6.2 removed from ``write_off``.** It locks the
    ``payment`` row, which is the row this function mutates, and ``reverse_payment`` is
    the only writer of ``is_reversed`` — so every writer of that state contends on it.
    Without it, two concurrent reversals both read ``is_reversed = False`` and both write a
    compensating entry, crediting the customer twice.
    """
    require_roles(actor, Role.OWNER)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed(
            "A reversal needs a reason.",
            errors=[{"field": "reason", "code": "REQUIRED", "message": ""}],
        )

    locked = Payment.objects.select_for_update().filter(pk=payment.pk).first()
    if locked is None:  # pragma: no cover - the caller just fetched it
        raise ResourceNotFound("That payment no longer exists.")
    if locked.is_reversed:
        return locked  # idempotent: a second reversal is a no-op, not a second credit

    record_entry(
        actor=actor,
        customer=locked.customer,
        entry_type=CustomerLedgerEntry.Type.ADJUSTMENT,
        amount=locked.amount,
        narration=f"Reversal of payment {locked.payment_number}",
        entry_date=timezone.localdate(),
        source_document=locked,
    )

    locked.is_reversed = True
    locked.reversed_reason = reason
    locked.reversed_at = timezone.now()
    locked.reversed_by = actor if getattr(actor, "pk", None) else None
    locked.save(
        update_fields=["is_reversed", "reversed_reason", "reversed_at", "reversed_by"]
    )

    record_audit(
        action=AuditLog.Action.PAYMENT_REVERSE,
        entity_type="payment",
        entity_id=locked.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"is_reversed": False},
        after_state={
            "payment_number": locked.payment_number,
            "amount": locked.amount,
            "reason": reason,
        },
    )
    logger.info(
        "payment_reversed", extra={"payment_id": locked.pk, "amount": str(locked.amount)}
    )
    return locked


# --------------------------------------------------------------------------- ledger acts
@transaction.atomic
def write_off(
    *,
    actor: Any,
    customer: Any,
    amount: Decimal | str | int,
    reason: str,
    entry_date: date | None = None,
) -> CustomerLedgerEntry:
    """Write off bad debt (FR-REC-015). Owner only, reason mandatory, audited.

    **The caller supplies an explicit amount, and this function takes no lock.**

    Both follow from the same fact. A write-off appends a ledger entry and mutates
    nothing, so there is nothing for a lock to serialise — and locking the customer row
    would exclude nobody, because ``record_payment``, ``issue_invoice`` and
    ``issue_credit_note`` all append without taking it (§6.2).

    Had the amount been derived from the current balance instead, this function would
    carry a genuine read-then-write that **no lock could fix**, precisely because the
    other ledger writers are lock-free. An explicit amount removes the race rather than
    pretending to guard it — and a write-off is a deliberate decision about a specific
    sum, not "whatever the balance happens to be at this instant".
    """
    require_roles(actor, Role.OWNER)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed(
            "A write-off needs a reason.",
            errors=[{"field": "reason", "code": "REQUIRED", "message": ""}],
        )
    amount = to_money(amount)
    if amount <= 0:
        raise ValidationFailed(
            "A write-off must be greater than zero.",
            errors=[{"field": "amount", "code": "MIN_VALUE", "message": str(amount)}],
        )

    on = entry_date or timezone.localdate()
    entry = record_entry(
        actor=actor,
        customer=customer,
        entry_type=CustomerLedgerEntry.Type.WRITE_OFF,
        amount=-amount,
        narration=f"Write-off: {reason}"[:255],
        entry_date=on,
    )
    record_audit(
        action=AuditLog.Action.UPDATE,
        entity_type="customer_ledger_entry",
        entity_id=entry.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={
            "customer": customer.code,
            "entry_type": entry.entry_type,
            "amount": entry.amount,
            "reason": reason,
        },
    )
    logger.info(
        "write_off", extra={"customer": customer.code, "amount": str(amount)}
    )
    return entry


@transaction.atomic
def load_opening_balance(
    *,
    actor: Any,
    customer: Any,
    amount: Decimal | str | int,
    entry_date: date | None = None,
) -> CustomerLedgerEntry:
    """Load a customer's balance at go-live (ACT-E). **Idempotent** (D-10, M6-11).

    The deterministic identifier is the customer itself: a partial unique index permits at
    most one ``OPENING`` entry per customer, because *a customer has exactly one opening
    balance* — it is the balance at go-live, and two of them is not a duplicate record but
    a meaningless one.

    Re-running the whole import is therefore a no-op, whatever mix of already-loaded and
    not-yet-loaded customers a partial failure left behind. This is the most financially
    sensitive write the system performs, and it goes through the same single writer as
    everything else so the sign rules and the audit apply to it too (D-8).
    """
    require_roles(actor, Role.OWNER)
    amount = to_money(amount)
    if amount <= 0:
        raise ValidationFailed(
            "An opening balance must be greater than zero. A customer who owes nothing "
            "needs no entry.",
            errors=[{"field": "amount", "code": "MIN_VALUE", "message": str(amount)}],
        )

    existing = CustomerLedgerEntry.objects.filter(
        customer=customer, entry_type=CustomerLedgerEntry.Type.OPENING
    ).first()
    if existing is not None:
        return existing

    on = entry_date or timezone.localdate()
    try:
        # The database is the guarantee, not the check above: two concurrent import runs
        # would both pass that check. The savepoint keeps the losing run recoverable.
        with transaction.atomic():
            entry = record_entry(
                actor=actor,
                customer=customer,
                entry_type=CustomerLedgerEntry.Type.OPENING,
                amount=amount,
                narration="Opening balance carried at go-live",
                entry_date=on,
            )
    except IntegrityError:
        already = CustomerLedgerEntry.objects.filter(
            customer=customer, entry_type=CustomerLedgerEntry.Type.OPENING
        ).first()
        if already is None:  # pragma: no cover - a different constraint fired
            raise
        return already

    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type="customer_ledger_entry",
        entity_id=entry.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={"customer": customer.code, "opening_balance": entry.amount},
    )
    logger.info(
        "opening_balance_loaded",
        extra={"customer": customer.code, "amount": str(amount)},
    )
    return entry


def balance_after(customer: Any) -> Decimal:
    """The figure `05` §10.4 returns on a collection.

    The salesman is standing in front of the retailer and the next question is always
    *"toh ab kitna baaki?"* — one field that removes a follow-up round trip on a
    connection that may not survive one.
    """
    return settled_balance(customer)
