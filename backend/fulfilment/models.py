"""Delivery — the physical handover (04 T-16).

**Dispatch is the moment commercial intent becomes physical fact.** M5's governing
principle is that this is a *different* boundary from the one the invoice crosses:
dispatch makes stock physical, the invoice makes money owed. Each is reversed on its own
terms — a failed delivery by a RETURN movement, a wrong invoice by a credit note.

A delivery is **mutable** (PENDING → DELIVERED or FAILED), so under R-3 every state
change is audited. The stock movements it causes are immutable and audit themselves.
"""

from __future__ import annotations

from django.db import models

from core.fields import CoordinateField
from core.models import TimeStampedModel


class Delivery(TimeStampedModel):
    """One physical delivery of one order.

    One per order in Edition 1, enforced by ``uq_delivery_sales_order``. Partial
    delivery is Edition 2 (`02A` §7.7); dropping a unique constraint then is a one-line
    migration, whereas splitting delivery data out of ``sales_order`` would have been a
    migration of live operational records.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"

    sales_order = models.OneToOneField(
        "orders.SalesOrder", on_delete=models.RESTRICT, related_name="delivery"
    )
    # M5-10: idempotency from the first migration. This row causes stock to move, and a
    # retried request that moved stock twice would be indistinguishable from two real
    # dispatches. The M8 app retries on a flaky rural connection by design.
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    assigned_user = models.ForeignKey(
        "identity.User", on_delete=models.RESTRICT, related_name="deliveries"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    dispatched_at = models.DateTimeField(null=True, blank=True)
    # Physical time, from the device. May precede synced_at by hours when captured
    # offline (M9), which is why it is not auto_now_add.
    delivered_at = models.DateTimeField(null=True, blank=True)
    recipient_name = models.CharField(max_length=200, blank=True)
    photo_media = models.ForeignKey(
        "core.MediaFile", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    latitude = CoordinateField(null=True, blank=True)
    longitude = CoordinateField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    device_id = models.CharField(max_length=64, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "delivery"
        ordering = ["-id"]
        indexes = [
            # The app's delivery list — its most frequent query from M8.
            models.Index(fields=["assigned_user", "status"], name="ix_delivery_user_status"),
            models.Index(fields=["-delivered_at"], name="ix_delivery_delivered_at"),
            models.Index(fields=["status"], name="ix_delivery_status"),
            models.Index(fields=["updated_at"], name="ix_delivery_updated_at"),
        ]
        constraints = [
            # A failure without a reason is not actionable and not auditable.
            models.CheckConstraint(
                condition=~models.Q(status="FAILED") | ~models.Q(failure_reason=""),
                name="ck_delivery_failed_reason",
            ),
            # "Delivered" with no time is not a delivery record.
            models.CheckConstraint(
                condition=~models.Q(status="DELIVERED") | models.Q(delivered_at__isnull=False),
                name="ck_delivery_delivered_at",
            ),
            # Coordinates are captured together or not at all.
            models.CheckConstraint(
                condition=(
                    models.Q(latitude__isnull=True, longitude__isnull=True)
                    | models.Q(latitude__isnull=False, longitude__isnull=False)
                ),
                name="ck_delivery_coords_paired",
            ),
        ]
        verbose_name_plural = "deliveries"

    def __str__(self) -> str:
        return f"Delivery for order {self.sales_order_id} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.PENDING
