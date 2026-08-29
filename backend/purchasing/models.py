"""Suppliers, what they supply, what we ordered, and what arrived (D5, `04` §11A).

**Stages 1-3.** `supplier_payment` belongs to Stage 4 and is deliberately absent, as is
`supplier_payment_allocation`, which is conditional on business decision BD-1.

**`supplier_ledger_entry` is not here** and will not be: BR-005 requires it on the same terms
as the customer ledger, so it lives in `ledger` alongside `CustomerLedgerEntry`, which already
owns immutability, the derived-balance rule and the one-opening constraint (`04` T-34).

**Where the line between intention and transaction falls.** A purchase order is a commercial
intention — issuing one moves no stock and owes no money. `GoodsReceipt` is the transaction:
creating one moves stock and raises a liability in the same breath, which is why it is
immutable and a `DRAFT` purchase order is not.

**Why a supplier is not a customer with a different name.** `customers.Customer` was the
field-*convention* template — `code` at 32, addresses as `TextField` with the second blank
meaning "same as the first", `gstin` at 15, `state_code` at 2, terms as a `CHECK`-guarded
non-negative small integer. It was **not** the field *list*: `shop_name`, `zone`,
`credit_limit_amount`, `opening_balance_amount` and the visit coordinates are things a
retailer has and a supplier does not.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from core.fields import MoneyField, PercentField, QuantityField
from core.models import TimeStampedModel

#: `PO-00000001`, drawn with `nextval` — a reference, not a statutory series (`04` T-30).
#: Created by `purchasing/migrations/0002`, before the table that uses it.
PURCHASE_ORDER_NUMBER_SEQUENCE = "purchase_order_number_seq"


class Supplier(TimeStampedModel):
    """Who the distributor buys from (FR-PUR-001, `04` §2.1 procurement).

    Deactivated rather than deleted: a supplier with purchase history must remain
    resolvable, and every future foreign key to this table is `PROTECT` for that reason.
    """

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20)
    alt_phone = models.CharField(max_length=20, blank=True)
    # No `Customer` analogue. Suppliers are corporate counterparties and send documents by
    # email; retailers at this scale do not.
    email = models.EmailField(max_length=254, blank=True)
    billing_address = models.TextField()
    # Blank means "same as billing" — the convention `Customer.delivery_address` uses, so a
    # reader who knows one table already knows this one.
    dispatch_address = models.TextField(blank=True)
    # Unregistered suppliers exist, so this is optional (as on `Customer`).
    gstin = models.CharField(max_length=15, blank=True)
    # Carried to satisfy FR-PUR-001's "tax identifiers" (plural) by mirroring the customer
    # side. **It has no consumer in v1.0** — D5 computes no purchase tax — and is retained
    # by ruling of 2026-08-26 rather than by need. One blank-able column.
    state_code = models.CharField(max_length=2, blank=True)
    # FR-PUR-001 "payment terms". The supplier-side counterpart of `Customer.credit_days`,
    # guarded by the same non-negative CHECK.
    payment_terms_days = models.SmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="suppliers_created",
    )

    class Meta:
        db_table = "supplier"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="ix_supplier_name"),
            models.Index(fields=["phone"], name="ix_supplier_phone"),
            models.Index(fields=["updated_at"], name="ix_supplier_updated_at"),
            models.Index(
                fields=["is_active"], name="ix_supplier_active", condition=models.Q(is_active=True)
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(payment_terms_days__gte=0),
                name="ck_supplier_payment_terms",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class ProductSupplier(models.Model):
    """Which suppliers a product can be bought from (FR-PUR-002).

    A plain association, not a `TimeStampedModel`: it carries no lifecycle of its own and
    nothing reports on when a link was made. Both foreign keys are `PROTECT` — a product or
    supplier with purchasing history must not be deletable out from under it.

    **`is_preferred` is enforced by a partial unique index, not by a service check.** A check
    loses the race it exists for; the index is the same construction
    `uq_cle_one_opening_per_customer` uses on the customer ledger.
    """

    product = models.ForeignKey(
        "catalogue.Product", on_delete=models.PROTECT, related_name="supplier_links"
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="product_links")
    # The supplier's own code for this product, as it appears on their documents. Optional:
    # many small suppliers quote against the distributor's description instead.
    supplier_sku = models.CharField(max_length=64, blank=True)
    is_preferred = models.BooleanField(default=False)

    class Meta:
        db_table = "product_supplier"
        ordering = ["product", "supplier"]
        indexes = [
            models.Index(fields=["supplier"], name="ix_prodsup_supplier"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["product", "supplier"], name="uq_product_supplier"),
            # At most one preferred supplier per product. A partial index rather than a
            # unique-together, because "not preferred" must remain unlimited.
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_preferred=True),
                name="uq_product_supplier_one_preferred",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} <- {self.supplier_id}"


class PurchaseOrder(TimeStampedModel):
    """What was ordered from a supplier, and where that order has got to (`04` T-30).

    **Not an `_ImmutableDocument`.** That base blocks every write once a row exists, and a
    `DRAFT` purchase order must be editable. Immutability begins at `ISSUED` and is enforced
    in services through `is_editable` — the construction `orders.services.amend_order` uses.

    **`status` is never written directly.** `purchasing.services._transition` is the only
    writer, and `ALLOWED_TRANSITIONS` is the specification. A caller that could assign
    `status` would hold the state machine.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ISSUED = "ISSUED", "Issued"
        PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Partially received"
        RECEIVED = "RECEIVED", "Received"
        CLOSED = "CLOSED", "Closed"
        CANCELLED = "CANCELLED", "Cancelled"

    # **Allocated at creation, not at issue** (D-PUR-8). A draft is already a business
    # document: it is discussed on the phone and looked up in support, so it needs a stable,
    # human-readable reference before anyone issues it. Gaps from abandoned drafts are
    # acceptable because this is an internal reference, not a statutory series.
    po_number = models.CharField(max_length=32, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    # Caller-supplied, never `date.today()` inside the service. P-4's reasoning applies to any
    # surface: a machine clock must not decide a business fact. The web form defaults it.
    order_date = models.DateField()
    expected_date = models.DateField(null=True, blank=True)
    # Summed from already-rounded line values (M3-8). Rounding once at the end would give a
    # different figure, and the Stage 4 payable must agree to the paisa.
    subtotal_amount = MoneyField(default=0)
    tax_amount = MoneyField(default=0)
    total_amount = MoneyField(default=0)
    notes = models.TextField(blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_orders_issued",
    )
    cancelled_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_orders_cancelled",
    )
    created_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_orders_created",
    )

    class Meta:
        db_table = "purchase_order"
        ordering = ["-order_date", "-id"]
        indexes = [
            models.Index(fields=["supplier"], name="ix_po_supplier"),
            models.Index(fields=["status"], name="ix_po_status"),
            models.Index(fields=["order_date"], name="ix_po_order_date"),
            models.Index(fields=["updated_at"], name="ix_po_updated_at"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(subtotal_amount__gte=0)
                    & models.Q(tax_amount__gte=0)
                    & models.Q(total_amount__gte=0)
                ),
                name="ck_po_totals_non_negative",
            ),
        ]

    @property
    def is_editable(self) -> bool:
        """Only a draft may be amended.

        **Narrower than `SalesOrder.is_editable`, which also permits `CONFIRMED`**, and the
        difference is the counterparty: a confirmed sales order is still ours to change, but
        an issued purchase order has been sent to a supplier. Amending it silently would leave
        the two parties holding different documents.
        """
        return self.status == self.Status.DRAFT

    def __str__(self) -> str:
        return f"{self.po_number} {self.supplier_id}"


class PurchaseOrderLine(models.Model):
    """What was ordered, at the cost that was agreed, with the tax that applied (`04` T-31).

    **The snapshots freeze the commercial agreement**, as `SalesOrderLine`'s do for a sale. A
    product renamed or repriced after issue must not retroactively change what was ordered.

    **`unit_cost` is a purchase price and is unrelated to `product.selling_price`.** There is
    no cost field on `Product` and D5 does not add one: the cost is what this supplier quoted
    on this order, entered per line. That is also what makes FR-PUR-008's receipt variance
    measurable at Stage 3.
    """

    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="lines"
    )
    line_number = models.SmallIntegerField()
    product = models.ForeignKey(
        "catalogue.Product", on_delete=models.PROTECT, related_name="purchase_order_lines"
    )
    product_code = models.CharField(max_length=32)
    product_name = models.CharField(max_length=200)
    unit_name = models.CharField(max_length=20)
    pack_size_snapshot = models.IntegerField()
    quantity_ordered = QuantityField()
    unit_cost = MoneyField()
    tax_rate_percent = PercentField()
    taxable_amount = MoneyField()
    tax_amount = MoneyField()
    line_total = MoneyField()

    class Meta:
        db_table = "purchase_order_line"
        ordering = ["purchase_order", "line_number"]
        indexes = [
            models.Index(fields=["product"], name="ix_po_line_product"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["purchase_order", "line_number"], name="uq_po_line_number"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_ordered__gt=0), name="ck_po_line_quantity_positive"
            ),
            # Free goods are legitimate; a negative cost is not.
            models.CheckConstraint(
                condition=models.Q(unit_cost__gte=0), name="ck_po_line_unit_cost_non_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.purchase_order_id}/{self.line_number} {self.product_code}"


#: `GRN-00000001`, drawn with `nextval` — a reference, not a statutory series (`04` T-32),
#: on the same terms as `po_number` and `payment_number`. Gaps are permitted because nothing
#: statutory is numbered here; the alternative is a row lock on every goods-in.
GOODS_RECEIPT_NUMBER_SEQUENCE = "goods_receipt_number_seq"


class GoodsReceiptImmutable(RuntimeError):
    """Raised on any attempt to modify or remove a posted goods receipt."""


class GoodsReceiptQuerySet(models.QuerySet["GoodsReceipt"]):
    def update(self, **kwargs: Any) -> int:
        raise GoodsReceiptImmutable("goods_receipt is immutable once posted (`04` T-32)")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise GoodsReceiptImmutable("goods_receipt is immutable once posted (`04` T-32)")


class GoodsReceipt(models.Model):
    """What actually arrived against a purchase order, and when (`04` T-32).

    **Immutable once created, and it has no draft phase.** The moment this row exists it has
    moved stock (T-13) and raised a liability (T-34) — both of which are themselves
    append-only — so an editable receipt would be an editable handle on two immutable facts.
    Immutability is enforced the way `CustomerLedgerEntry` enforces it: `save()` refuses an
    update and `delete()` raises, on the queryset as well as the instance.

    **No `updated_at` and no `status`**, deliberately, and `TimeStampedModel` is therefore
    not the base. A column that can never change would be a standing invitation to make it
    change. The lifecycle a receipt drives belongs to `PurchaseOrder`, not here.

    > Correcting a posted receipt is **outside Stage 3** and needs a separately approved
    > design. Nothing in this class may be read as providing one.
    """

    grn_number = models.CharField(max_length=32, unique=True)
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.RESTRICT, related_name="goods_receipts"
    )
    # Caller-supplied, never `date.today()` inside the service (P-4). Goods booked in on
    # Monday for a Saturday delivery must date to Saturday.
    receipt_date = models.DateField()
    supplier_reference = models.CharField(max_length=64, blank=True)
    # Summed from already-rounded line values (M3-8), so the payable in T-34 agrees to the
    # paisa with the sum of the lines that justify it.
    subtotal_amount = MoneyField(default=0)
    tax_amount = MoneyField(default=0)
    total_amount = MoneyField(default=0)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="goods_receipts",
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    objects: ClassVar[models.Manager[GoodsReceipt]] = GoodsReceiptQuerySet.as_manager()

    class Meta:
        db_table = "goods_receipt"
        ordering = ["-receipt_date", "-id"]
        indexes = [
            models.Index(fields=["purchase_order"], name="ix_grn_purchase_order"),
            models.Index(fields=["receipt_date"], name="ix_grn_receipt_date"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(subtotal_amount__gte=0)
                    & models.Q(tax_amount__gte=0)
                    & models.Q(total_amount__gte=0)
                ),
                name="ck_grn_totals_non_negative",
            ),
        ]
        verbose_name = "goods receipt"
        verbose_name_plural = "goods receipts"

    def __str__(self) -> str:
        return f"{self.grn_number} against {self.purchase_order_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise GoodsReceiptImmutable("goods_receipt is immutable once posted (`04` T-32)")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise GoodsReceiptImmutable("goods_receipt is immutable once posted (`04` T-32)")


class GoodsReceiptLine(models.Model):
    """What arrived, per ordered line, and the stock movement it produced (`04` T-33).

    **`stock_movement` is `NOT NULL`, and that is the point.** `StockMovement` carries
    `source_document_type = 'GOODS_RECEIPT'` pointing *forward* to the receipt; this column
    points *back* to the movement. Both directions must resolve, and the `NOT NULL` makes a
    receipt line without a movement **unrepresentable** rather than merely discouraged.
    Together with T-13's existing CHECK forbidding half a reference, that is the whole of
    FR-PUR-007.

    **Variance is derived, never stored** — FR-PUR-008's figure is
    ``quantity_ordered - Σ quantity_received``. A stored variance would be a second source of
    truth for a subtraction, which N-03/E-01 forbid for the reason they forbid a cached
    balance.

    **`unit_cost` and `tax_rate_percent` are snapshots of the PURCHASE ORDER LINE**, not of
    the product. What arrived is priced at what was agreed, even if the product has been
    repriced since — and even if the supplier's own note says something else, because a
    disputed price is a commercial conversation, not a silent overwrite.
    """

    goods_receipt = models.ForeignKey(
        GoodsReceipt, on_delete=models.CASCADE, related_name="lines"
    )
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.RESTRICT, related_name="receipt_lines"
    )
    quantity_received = QuantityField()
    unit_cost = MoneyField()
    tax_rate_percent = PercentField()
    taxable_amount = MoneyField()
    tax_amount = MoneyField()
    line_total = MoneyField()
    stock_movement = models.ForeignKey(
        "inventory.StockMovement", on_delete=models.RESTRICT, related_name="goods_receipt_lines"
    )

    class Meta:
        db_table = "goods_receipt_line"
        ordering = ["goods_receipt", "purchase_order_line"]
        indexes = [
            models.Index(fields=["purchase_order_line"], name="ix_grn_line_po_line"),
        ]
        constraints = [
            # One line per ordered line per receipt. Receiving the same PO line twice **in
            # one receipt** is a data-entry error, not a partial delivery; partials are
            # separate receipts (FR-PUR-013).
            models.UniqueConstraint(
                fields=["goods_receipt", "purchase_order_line"], name="uq_grn_line"
            ),
            # A zero receipt is not a receipt.
            models.CheckConstraint(
                condition=models.Q(quantity_received__gt=0), name="ck_grn_line_quantity_positive"
            ),
        ]
        verbose_name = "goods receipt line"
        verbose_name_plural = "goods receipt lines"

    def __str__(self) -> str:
        return f"{self.goods_receipt_id}/{self.purchase_order_line_id} x{self.quantity_received}"


#: `SPY-00000001`, drawn with `nextval` — a reference, not a statutory series, on the same
#: terms as `po_number`, `grn_number` and `payment_number`. A losing racer in
#: `record_supplier_payment` consumes a number; gaps are permitted and expected.
SUPPLIER_PAYMENT_NUMBER_SEQUENCE = "supplier_payment_number_seq"


class SupplierPaymentImmutable(RuntimeError):
    """Raised on any attempt to edit or remove a recorded supplier payment."""


class SupplierPaymentQuerySet(models.QuerySet["SupplierPayment"]):
    def update(self, **kwargs: Any) -> int:
        raise SupplierPaymentImmutable(
            "supplier_payment is immutable once recorded. Reverse it instead."
        )

    def delete(self) -> tuple[int, dict[str, int]]:
        raise SupplierPaymentImmutable("supplier_payment is never deleted. Reverse it instead.")


class SupplierPayment(models.Model):
    """Money paid to a supplier (FR-PUR-012, D5 Stage 4 S4.3).

    Recorded against the **supplier**, never against a goods receipt. Which receipts it
    consequently settles is derived FIFO at read time through `ledger.walk` and never
    written down — BD-1 Option A, frozen. **There is no allocation table, no allocation
    column and no settled flag**, for the reason N-03/E-01 forbid a cached balance.

    **Mutable in exactly four columns**, the reversal set, and immutable in every other. That
    is the shape `receivables.Payment` and `billing.Invoice` already have.

    **Why it does not inherit `billing._ImmutableDocument`.** It cannot: `billing` sits two
    layers above `purchasing`, so the import would invert the module graph. TD-24 already
    records that the machinery belongs in `core`; consolidating it is deferred (S4.3 ruling
    U-5) because moving an abstract base out of `billing` would edit three verified financial
    tables to enable one new feature. The guards below are therefore local, and deliberately
    identical in behaviour to the base they cannot use.
    """

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        UPI = "UPI", "UPI"
        BANK = "BANK", "Bank transfer"
        CHEQUE = "CHEQUE", "Cheque"

    #: The only columns any UPDATE may touch. Must match the trigger in `0008` exactly.
    _mutable_fields: ClassVar[frozenset[str]] = frozenset(
        {"is_reversed", "reversed_reason", "reversed_at", "reversed_by"}
    )

    # **E3 — the duplicate-payment guarantee, and it is this column** (S4.3 §3).
    #
    # Server-minted `uuid4`, one per rendered payment form, required on submit. A logical
    # payment attempt IS a form render: every real duplicate — double-click, browser Back,
    # refresh on the POST result, a resurrected bfcache page — replays the *same* render,
    # while a legitimate second payment requires loading the form again and therefore
    # carries a different id.
    #
    # **NOT NULL, unlike `Payment.client_uuid`.** That column had to be nullable because
    # M3-era callers predate it. This table has no history, so protection is mandatory from
    # the first row — and a nullable column could not enforce anything at the boundary.
    #
    # **It is idempotency, not authentication** (ruling U-3). `login_required`, CSRF and the
    # `OWNER` check are the security controls; this is not one, is not secret, and must not
    # be named like one — see `core.services._SENSITIVE`, which redacts the key `token`.
    submission_id = models.UUIDField(unique=True)

    payment_number = models.CharField(max_length=32, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.RESTRICT, related_name="payments")
    # Positive here; the ledger entry it produces is negative (D-PUR-3). The sign lives in
    # one place — `ledger.services._SUPPLIER_SIGN_RULES` — and not in two.
    amount = MoneyField()
    method = models.CharField(max_length=20, choices=Method.choices)
    reference_number = models.CharField(max_length=100, blank=True)
    # Caller-supplied, never `date.today()` inside the service. P-4's reasoning: a machine
    # clock must not decide a business fact, and a payment is dated when it left the bank.
    payment_date = models.DateField()
    notes = models.TextField(blank=True)
    paid_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplier_payments_made",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # --- the only mutable state ------------------------------------------
    is_reversed = models.BooleanField(default=False)
    reversed_reason = models.TextField(blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects: ClassVar[models.Manager[SupplierPayment]] = SupplierPaymentQuerySet.as_manager()

    class Meta:
        db_table = "supplier_payment"
        ordering = ["-payment_date", "-id"]
        indexes = [
            models.Index(fields=["supplier", "-payment_date"], name="ix_spay_supplier_date"),
            models.Index(fields=["method", "-payment_date"], name="ix_spay_method_date"),
            models.Index(fields=["paid_by"], name="ix_spay_paid_by"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="ck_supplier_payment_amount"
            ),
            # A reversal without a reason is not auditable.
            models.CheckConstraint(
                condition=~models.Q(is_reversed=True) | ~models.Q(reversed_reason=""),
                name="ck_supplier_payment_reversed",
            ),
            # Half a reversal record is worse than none.
            models.CheckConstraint(
                condition=(
                    models.Q(is_reversed=False, reversed_at__isnull=True)
                    | models.Q(is_reversed=True, reversed_at__isnull=False)
                ),
                name="ck_supplier_payment_reversed_pair",
            ),
        ]
        verbose_name = "supplier payment"
        verbose_name_plural = "supplier payments"

    def __str__(self) -> str:
        return self.payment_number

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            updating = set(kwargs.get("update_fields") or ())
            if not updating or not updating.issubset(self._mutable_fields):
                raise SupplierPaymentImmutable(
                    "supplier_payment is immutable once recorded. Reverse it instead."
                )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise SupplierPaymentImmutable("supplier_payment is never deleted. Reverse it instead.")
