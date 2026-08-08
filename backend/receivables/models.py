"""Receivables — money received from a customer (04 T-21).

**A payment reduces what a customer owes. It does not pay an invoice** (M6 §1). There is
no allocation table and no allocation column: which invoices are consequently settled is
derived FIFO at read time (`receivables.selectors`, M6 §5A) and never written down.

``payment`` is **mutable in exactly four columns** — the reversal fields — and immutable in
every other. That is the same shape M5 built for ``invoice``, so it reuses the same
machinery rather than growing a second copy of it (M6 D-7, deferred to M10 as TD-24).

``payment_number`` is a **reference, not a statutory series** (M6 D-4). It is allocated by
``nextval`` on a dedicated sequence *before* the insert, so the row is written in one
statement and the immutability trigger is never engaged. Gaps are permitted and expected;
a rolled-back collection consumes a receipt number and that is correct.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

# M6 D-7 is DEFERRED (TD-24): the immutability machinery stays in `billing` until M10
# hardening rather than being moved into `core` while M5 is freshly verified.
# `receivables` sits above `billing` in the layer graph, so this import is legal — it is
# one import of shared behaviour, chosen over duplicating a financial guard.
from billing.models import DocumentImmutable, _ImmutableDocument, _ImmutableQuerySet
from core.fields import MoneyField

#: Read by ``nextval`` before every insert. Created by a RunSQL migration — Django's
#: autodetector does not generate bare sequences.
PAYMENT_NUMBER_SEQUENCE = "payment_number_seq"


class PaymentQuerySet(_ImmutableQuerySet):
    document_name = "payment"


class Payment(_ImmutableDocument):
    """A collection from a customer (04 T-21).

    Recorded against the **customer**, never against an invoice (M6-1). Reversal is a
    compensating ledger entry; the original is never edited (M6-3).
    """

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        UPI = "UPI", "UPI"
        BANK = "BANK", "Bank transfer"
        CHEQUE = "CHEQUE", "Cheque"

    _document_name: ClassVar[str] = "payment"
    #: The only columns any UPDATE may touch. Must match the trigger exactly.
    _mutable_fields: ClassVar[frozenset[str]] = frozenset(
        {"is_reversed", "reversed_reason", "reversed_at", "reversed_by"}
    )

    payment_number = models.CharField(max_length=32, unique=True)
    # M6-5: **the most important constraint in this milestone.** A salesman on a weak
    # connection retrying a collection is the exact scenario that double-credits a
    # customer, and "who owes what" is the client's founding problem.
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.RESTRICT, related_name="payments"
    )
    amount = MoneyField()
    method = models.CharField(max_length=20, choices=Method.choices)
    reference_number = models.CharField(max_length=100, blank=True)
    payment_date = models.DateField()

    received_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments_received",
    )
    # M6-9: structural enabler (E-06). Field collection is FR-REC-010, v1.1, M8 — but
    # adding a column to a financial table later is a migration of live money records.
    device_id = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)

    # --- the only mutable state ------------------------------------------
    is_reversed = models.BooleanField(default=False)
    reversed_reason = models.TextField(blank=True)
    # M6 C-3: `04` T-21 omitted these. "Who reversed this payment" is a question asked of
    # the payment, and answering it should not require joining to the audit subsystem.
    # M5's invoice carries cancelled_at / cancelled_by for the identical shape of event.
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects: ClassVar[models.Manager[Payment]] = PaymentQuerySet.as_manager()

    class Meta:
        db_table = "payment"
        ordering = ["-payment_date", "-id"]
        indexes = [
            models.Index(fields=["customer", "-payment_date"], name="ix_payment_customer_date"),
            # The Cash/UPI split report (M7).
            models.Index(fields=["method", "-payment_date"], name="ix_payment_method_date"),
            # Collections by collector (FR-REC-012, v1.1). Free now.
            models.Index(fields=["received_by"], name="ix_payment_received_by"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="ck_payment_amount"),
            # A reversal without a reason is not auditable.
            models.CheckConstraint(
                condition=~models.Q(is_reversed=True) | ~models.Q(reversed_reason=""),
                name="ck_payment_reversed",
            ),
            # Half a reversal record is worse than none — the same rule M1 applied to
            # coordinates and M3 to the credit override.
            models.CheckConstraint(
                condition=(
                    models.Q(is_reversed=False, reversed_at__isnull=True)
                    | models.Q(is_reversed=True, reversed_at__isnull=False)
                ),
                name="ck_payment_reversed_pair",
            ),
        ]

    def __str__(self) -> str:
        return self.payment_number

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise DocumentImmutable("payment is never deleted. Reverse it instead (M6-3).")
