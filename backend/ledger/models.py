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
            # M6-11 / D-10: **a customer has exactly one opening balance.** It is the
            # balance at go-live, so two of them is not a duplicate record but a
            # meaningless one — which is why the natural key is the customer itself and
            # no `client_uuid` is needed.
            #
            # This makes the ACT-E bulk load idempotent: re-running the whole import
            # after a partial failure is a no-op, whatever mix of loaded and unloaded
            # customers it left behind. That import is the most financially sensitive
            # write the system performs, and "be careful" is not a control.
            #
            # Added at M6. No OPENING row exists — M5's only callers write INVOICE,
            # CREDIT_NOTE and ADJUSTMENT — so nothing can violate it.
            models.UniqueConstraint(
                fields=["customer"],
                condition=models.Q(entry_type="OPENING"),
                name="uq_cle_one_opening_per_customer",
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


class SupplierLedgerEntryQuerySet(models.QuerySet["SupplierLedgerEntry"]):
    def update(self, **kwargs: Any) -> int:
        raise LedgerEntryImmutable("supplier_ledger_entry is append-only (BR-005, D-PUR-3)")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise LedgerEntryImmutable("supplier_ledger_entry is append-only (BR-005, D-PUR-3)")


class SupplierLedgerEntry(models.Model):
    """The supplier ledger — every event that changes what the distributor owes (`04` T-34).

    **The payables sibling of `CustomerLedgerEntry`**, ported field for field because BR-005
    requires it *"on the same terms as the customer ledger"*. The architecture's own analogy,
    extended by one line:

        catalogue  → Product   is to  inventory → StockMovement
        customers  → Customer  is to  ledger    → CustomerLedgerEntry
        purchasing → Supplier  is to  ledger    → SupplierLedgerEntry

    **It lives here, not in `purchasing`,** for the reason ADR-0008 gives for the customer
    side: `ledger` owns immutability, the derived-balance rule and the opening constraint, and
    a second module implementing them again would be a second answer to a settled question.

    **A balance is not stored. It is `SUM(amount)`** filtered by supplier (N-03, E-01). There
    is deliberately no `outstanding_balance` column on `supplier`, and adding one is forbidden.

    **Sign convention — D-PUR-3, and the reason it is stated rather than implied:** a positive
    amount **increases** the distributor's liability. `GOODS_RECEIPT` is positive, `PAYMENT`
    negative. An instruction to "mirror the customer ledger" would have left two developers
    free to invert a debit, which is a defect that reads as a plausible number.
    """

    class Type(models.TextChoices):
        GOODS_RECEIPT = "GOODS_RECEIPT", "Goods receipt"
        PAYMENT = "PAYMENT", "Payment"
        OPENING = "OPENING", "Opening balance"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        DEBIT_NOTE = "DEBIT_NOTE", "Debit note"

    #: Types that must carry a positive amount — they increase what is owed.
    DEBIT_TYPES = (Type.GOODS_RECEIPT,)
    #: Types that must carry a negative amount — they reduce what is owed.
    CREDIT_TYPES = (Type.PAYMENT, Type.DEBIT_NOTE)
    #: **`OPENING` is deliberately in neither**, which is where this diverges from
    #: `CustomerLedgerEntry` (`04` T-34: *"signed as the opening position requires"*). A
    #: retailer's opening balance is money owed to us or nothing at all; an opening position
    #: with a supplier can legitimately be a credit — an advance paid, or goods returned
    #: before the system went live. Forcing it positive would make an operator record a real
    #: position backwards to get it in.
    UNSIGNED_TYPES = (Type.OPENING, Type.ADJUSTMENT)

    supplier = models.ForeignKey(
        "purchasing.Supplier", on_delete=models.RESTRICT, related_name="ledger_entries"
    )
    entry_date = models.DateField()
    entry_type = models.CharField(max_length=20, choices=Type.choices)
    amount = MoneyField()
    # Validated against `ledger.services.SOURCE_DOCUMENT_REGISTRY` — a **different** registry
    # from `inventory.services`', which governs `stock_movement`. `GoodsReceipt` is the first
    # document registered in both, because a receipt moves stock and raises a liability.
    source_document_type = models.CharField(max_length=30, blank=True)
    source_document_id = models.BigIntegerField(null=True, blank=True)
    # Written once and shown on the statement, so a statement never depends on joining to
    # documents that may have been superseded.
    narration = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplier_ledger_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects: ClassVar[models.Manager[SupplierLedgerEntry]] = (
        SupplierLedgerEntryQuerySet.as_manager()
    )

    class Meta:
        db_table = "supplier_ledger_entry"
        ordering = ["supplier", "entry_date", "id"]
        indexes = [
            # THE balance and statement query.
            models.Index(fields=["supplier", "entry_date", "id"], name="ix_sle_supplier_date"),
            models.Index(
                fields=["source_document_type", "source_document_id"], name="ix_sle_source"
            ),
            models.Index(fields=["entry_type", "entry_date"], name="ix_sle_entry_type_date"),
        ]
        constraints = [
            # A zero entry is a bug, not a record.
            models.CheckConstraint(condition=~models.Q(amount=0), name="ck_sle_amount_non_zero"),
            # Half a reference is worse than none.
            models.CheckConstraint(
                condition=(
                    models.Q(source_document_type="", source_document_id__isnull=True)
                    | (
                        ~models.Q(source_document_type="")
                        & models.Q(source_document_id__isnull=False)
                    )
                ),
                name="ck_sle_source_pair",
            ),
            # **The accounting direction, in the database.** A service-layer sign error is
            # rejected rather than silently halving what we owe someone.
            models.CheckConstraint(
                condition=(
                    (models.Q(entry_type="GOODS_RECEIPT") & models.Q(amount__gt=0))
                    | (models.Q(entry_type__in=["PAYMENT", "DEBIT_NOTE"]) & models.Q(amount__lt=0))
                    | models.Q(entry_type__in=["OPENING", "ADJUSTMENT"])
                ),
                name="ck_sle_sign",
            ),
            # **One opening balance per supplier** — the same partial unique index the
            # customer side carries as `uq_cle_one_opening_per_customer`. A second opening
            # balance is not a second fact; it is a duplicate of one.
            models.UniqueConstraint(
                fields=["supplier"],
                condition=models.Q(entry_type="OPENING"),
                name="uq_sle_one_opening_per_supplier",
            ),
        ]
        verbose_name = "supplier ledger entry"
        verbose_name_plural = "supplier ledger entries"

    def __str__(self) -> str:
        return f"{self.entry_type} {self.amount} for supplier {self.supplier_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise LedgerEntryImmutable("supplier_ledger_entry is append-only (BR-005, D-PUR-3)")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise LedgerEntryImmutable("supplier_ledger_entry is append-only (BR-005, D-PUR-3)")
