"""Sales orders — commercial intent.

**An order is a record of what was agreed, at the moment it was agreed. It changes no
physical fact and no financial fact** (M3_Design_Review §1).

* Lines snapshot product name, unit price, tax rate and pack size (M3-1). An order that
  rendered from current master data would silently rewrite history when a price changed.
* No module here writes a ``StockMovement`` (M3-6). Stock is issued at dispatch, in M5.
* No module here writes a ledger entry. The receivable begins at the invoice, in M5.

An order is the only **mutable** record M3 creates, which is why every state-changing
operation on it is audited (R-3).
"""

from __future__ import annotations

from django.db import models

from core.fields import MoneyField, PercentField, QuantityField
from core.models import TimeStampedModel


class SalesOrder(TimeStampedModel):
    """A retailer's request for goods (04 T-14)."""

    class Status(models.TextChoices):
        PLACED = "PLACED", "Placed"
        CONFIRMED = "CONFIRMED", "Confirmed"
        DISPATCHED = "DISPATCHED", "Dispatched"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"

    class Source(models.TextChoices):
        WEB = "WEB", "Web admin"
        PORTAL = "PORTAL", "Retailer portal"
        APP = "APP", "Field app"

    # D-3: a human reference, NOT a statutory series. Gaps are permitted; the gapless,
    # row-locked series belongs to invoices (04 T-06) because tax authorities require it.
    order_number = models.CharField(max_length=32, unique=True)
    # M3-5: idempotency from the first migration (BR-012, AD-09).
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.RESTRICT, related_name="orders"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLACED)
    source = models.CharField(max_length=20, choices=Source.choices)
    order_date = models.DateField()
    expected_delivery_date = models.DateField(null=True, blank=True)
    assigned_user = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_orders",
    )

    # M3-7: denormalised deliberately. Order lists are the most-read screen in the
    # product; recomputing a sum over lines for every row is an N+1 aggregate. Written in
    # the same transaction as the lines and reconciled by an integrity test.
    subtotal_amount = MoneyField(default=0)
    discount_amount = MoneyField(default=0)
    tax_amount = MoneyField(default=0)
    total_amount = MoneyField(default=0)

    credit_warning_shown = models.BooleanField(default=False)
    credit_override_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="credit_overrides",
    )
    credit_override_at = models.DateTimeField(null=True, blank=True)

    cancelled_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_orders",
    )

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders_created",
    )

    class Meta:
        db_table = "sales_order"
        ordering = ["-order_date", "-id"]
        indexes = [
            models.Index(fields=["customer"], name="ix_order_customer"),
            models.Index(fields=["status"], name="ix_order_status"),
            # The salesman's pending list — the app's most frequent query from M8.
            models.Index(fields=["assigned_user", "status"], name="ix_order_assigned_status"),
            models.Index(fields=["-order_date"], name="ix_order_date"),
            models.Index(fields=["updated_at"], name="ix_order_updated_at"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    subtotal_amount__gte=0,
                    discount_amount__gte=0,
                    tax_amount__gte=0,
                    total_amount__gte=0,
                ),
                name="ck_order_amounts_non_negative",
            ),
            # A cancellation without a reason is not auditable.
            models.CheckConstraint(
                condition=~models.Q(status="CANCELLED") | ~models.Q(cancelled_reason=""),
                name="ck_order_cancel_reason",
            ),
            # Half an override is worse than none.
            models.CheckConstraint(
                condition=(
                    models.Q(credit_override_by__isnull=True, credit_override_at__isnull=True)
                    | models.Q(credit_override_by__isnull=False, credit_override_at__isnull=False)
                ),
                name="ck_order_override_pair",
            ),
        ]

    def __str__(self) -> str:
        return self.order_number

    @property
    def is_editable(self) -> bool:
        """Orders may be amended only before they physically leave (FR-ORD-030)."""
        return self.status in {self.Status.PLACED, self.Status.CONFIRMED}


class SalesOrderLine(models.Model):
    """What was ordered, at the price that was agreed (04 T-15).

    Every ``*_snapshot`` value and ``unit_price`` / ``tax_rate_percent`` is frozen at
    capture (M3-1). Changing a product's price afterwards must not alter this row.
    """

    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="lines")
    line_number = models.SmallIntegerField()
    product = models.ForeignKey(
        "catalogue.Product", on_delete=models.RESTRICT, related_name="order_lines"
    )

    # --- snapshots (M3-1) --------------------------------------------------
    product_code = models.CharField(max_length=32)
    product_name = models.CharField(max_length=200)
    unit_name = models.CharField(max_length=20)
    unit_price = MoneyField()
    tax_rate_percent = PercentField()
    pack_size_snapshot = models.IntegerField()

    # M3-2: quantity is ALWAYS base units. pack_quantity records what the user typed, so
    # a bill can be explained back to them.
    quantity = QuantityField()
    pack_quantity = QuantityField(null=True, blank=True)

    discount_amount = MoneyField(default=0)
    discount_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    taxable_amount = MoneyField()
    tax_amount = MoneyField()
    line_total = MoneyField()

    class Meta:
        db_table = "sales_order_line"
        ordering = ["sales_order", "line_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["sales_order", "line_number"], name="uq_sales_order_line"
            ),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="ck_order_line_qty"),
            models.CheckConstraint(
                condition=models.Q(
                    unit_price__gte=0,
                    discount_amount__gte=0,
                    taxable_amount__gte=0,
                    tax_amount__gte=0,
                ),
                name="ck_order_line_amounts",
            ),
            models.CheckConstraint(
                condition=models.Q(pack_size_snapshot__gte=1), name="ck_order_line_pack_size"
            ),
        ]
        indexes = [
            models.Index(fields=["sales_order"], name="ix_order_line_order"),
            models.Index(fields=["product"], name="ix_order_line_product"),
        ]

    def __str__(self) -> str:
        return f"{self.sales_order_id}:{self.line_number} {self.product_code}"
