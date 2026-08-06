"""The customer ledger — every event that changes what a customer owes (04 T-22).

**A balance is not stored. It is SUM(customer_ledger_entry.amount)** filtered by customer
(N-03, E-01, BR-005). There is deliberately no balance column anywhere, and adding one is
forbidden (M5-3). ``customer.opening_balance_amount`` is documentation; an ``OPENING``
entry here is the truth.

**Why this is its own module and not part of `customers` (ADR-0008, M5-6).** The
architecture already answered this question once:

    catalogue → Product      is to  inventory → StockMovement
    customers → Customer     is to  ledger    → CustomerLedgerEntry

``StockMovement`` does not live inside ``catalogue``, and for the same reasons a
high-volume append-only financial fact table does not live inside a master-data module.
It is also written by three modules above it — ``billing`` (invoices, credit notes) and
``receivables`` (payments, M6) — and a table with three writers belongs beneath all of
them rather than inside any one of them.

Append-only, like ``stock_movement`` and ``audit_log``, for the same reason: a balance
derived from an editable ledger proves nothing.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from core.fields import MoneyField


class LedgerEntryImmutable(RuntimeError):
    """Raised on any attempt to modify or remove a ledger entry."""


class CustomerLedgerEntryQuerySet(models.QuerySet["CustomerLedgerEntry"]):
    def update(self, **kwargs: Any) -> int:
        raise LedgerEntryImmutable("customer_ledger_entry is append-only (M5-3, BR-005)")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise LedgerEntryImmutable("customer_ledger_entry is append-only (M5-3, BR-005)")


class CustomerLedgerEntry(models.Model):
    """One movement in what a customer owes (04 T-22).

    ``amount`` is **signed**: positive increases debt. One signed column rather than
    debit and credit columns, because formal double-entry is explicitly out of scope
    (`01` §8, O1) and a signed ledger already gives an exact balance, a chronological
    statement and full auditability from one ``SUM``.
    """

    class Type(models.TextChoices):
        INVOICE = "INVOICE", "Invoice"
        CREDIT_NOTE = "CREDIT_NOTE", "Credit note"
        PAYMENT = "PAYMENT", "Payment"
        OPENING = "OPENING", "Opening balance"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        WRITE_OFF = "WRITE_OFF", "Write off"

    #: Types that must carry a positive amount — they increase what is owed.
    DEBIT_TYPES = (Type.INVOICE, Type.OPENING)
    #: Types that must carry a negative amount — they reduce what is owed.
    CREDIT_TYPES = (Type.PAYMENT, Type.CREDIT_NOTE, Type.WRITE_OFF)

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.RESTRICT, related_name="ledger_entries"
    )
    entry_date = models.DateField()
    entry_type = models.CharField(max_length=20, choices=Type.choices)
    amount = MoneyField()

    # D-9: which order this entry settles, when it settles one.
    #
    # `orders` may import `ledger` (it sits below); it may not import `billing` (above),
    # so joining Invoice -> SalesOrder is not available to the exposure query. This
    # column is what lets the two exposure terms partition on ledger presence instead of
    # on order status, which is the only way they can be mutually exclusive by
    # construction. Nullable because payments and opening balances settle no single
    # order.
    sales_order = models.ForeignKey(
        "orders.SalesOrder",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="ledger_entries",
    )

    # R-2: polymorphic, no foreign key — it points at three different tables. The
    # compensating control is that services accept a validated model INSTANCE, never a
    # raw (type, id) pair, exactly as inventory does.
    source_document_type = models.CharField(max_length=30, blank=True)
    source_document_id = models.BigIntegerField(null=True, blank=True)

    # Written once and shown on the statement, so a statement never depends on joining
    # to documents that may since have been superseded.
    narration = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ledger_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects: ClassVar[models.Manager[CustomerLedgerEntry]] = (
        CustomerLedgerEntryQuerySet.as_manager()
    )

    class Meta:
        db_table = "customer_ledger_entry"
        ordering = ["customer", "entry_date", "id"]
        indexes = [
            # THE balance and statement query.
            models.Index(fields=["customer", "entry_date", "id"], name="ix_cle_customer_date"),
            models.Index(
                fields=["source_document_type", "source_document_id"], name="ix_cle_source"
            ),
            models.Index(fields=["entry_type", "entry_date"], name="ix_cle_entry_type_date"),
            models.Index(
                fields=["sales_order"],
                name="ix_cle_sales_order",
                condition=models.Q(sales_order__isnull=False),
            ),
        ]
        constraints = [
            # A zero entry is a bug, not a record.
            models.CheckConstraint(condition=~models.Q(amount=0), name="ck_cle_amount_nonzero"),
            # Half a reference is worse than none.
            models.CheckConstraint(
                condition=(
                    models.Q(source_document_type="", source_document_id__isnull=True)
                    | (
                        ~models.Q(source_document_type="")
                        & models.Q(source_document_id__isnull=False)
                    )
                ),
                name="ck_cle_source_pair",
            ),
            # The accounting direction, encoded in the database. A service-layer sign
            # error is then rejected outright rather than silently halving a balance.
            models.CheckConstraint(
                condition=(
                    (models.Q(entry_type__in=["INVOICE", "OPENING"]) & models.Q(amount__gt=0))
                    | (
                        models.Q(entry_type__in=["PAYMENT", "CREDIT_NOTE", "WRITE_OFF"])
                        & models.Q(amount__lt=0)
                    )
                    # ADJUSTMENT is legitimately bidirectional.
                    | models.Q(entry_type="ADJUSTMENT")
                ),
                name="ck_cle_sign",
            ),
        ]
        verbose_name = "customer ledger entry"
        verbose_name_plural = "customer ledger entries"

    def __str__(self) -> str:
        return f"{self.entry_type} {self.amount} for customer {self.customer_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise LedgerEntryImmutable("customer_ledger_entry is append-only (M5-3, BR-005)")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise LedgerEntryImmutable("customer_ledger_entry is append-only (M5-3, BR-005)")
