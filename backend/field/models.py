"""Visit — proof that a salesman called on a shop (04 T-23).

**Append only.** A visit is an observation, not a record anyone edits: it is evidence of
where a person was and what happened. That is why there is no update path in
``services.py`` and no mutable status column here.

Its own module rather than a member of ``customers`` (D-M9.1-2): a visit stands to
``customer`` as ``stock_movement`` stands to ``catalogue`` and ``customer_ledger_entry``
stands to ``customers`` — an append-only fact table over master data (ADR-0008).
"""

from __future__ import annotations

from django.db import models

from core.fields import CoordinateField
from core.models import TimeStampedModel


class Visit(TimeStampedModel):
    class Outcome(models.TextChoices):
        ORDER_TAKEN = "ORDER_TAKEN", "Order taken"
        NO_ORDER = "NO_ORDER", "No order"
        SHOP_CLOSED = "SHOP_CLOSED", "Shop closed"

    #: AD-09 / BR-012. Nullable because Edition 2 may create visits server-side, unique
    #: because the device's replay must resolve to the original row rather than a second
    #: one. `sync_operation` catches the replay first; this is the constraint that catches
    #: any path which bypasses it (04 T-26, "defence in depth").
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.RESTRICT, related_name="visits"
    )
    app_user = models.ForeignKey(
        "identity.User", on_delete=models.RESTRICT, related_name="visits"
    )

    #: **Device time** (04 T-23), and metadata only. P-4: it labels, it never orders.
    visited_at = models.DateTimeField()

    latitude = CoordinateField(null=True, blank=True)
    longitude = CoordinateField(null=True, blank=True)
    accuracy_metres = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    photo_media = models.ForeignKey(
        "core.MediaFile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    notes = models.TextField(blank=True)
    outcome = models.CharField(
        max_length=20, choices=Outcome.choices, blank=True, default=""
    )
    device_id = models.CharField(max_length=64, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "visit"
        constraints = [
            models.CheckConstraint(
                # 04 T-23 `ck_visit_outcome`. Blank is the "" default rather than NULL,
                # so the frozen `outcome IS NULL OR ...` becomes an empty-string branch.
                condition=models.Q(outcome="")
                | models.Q(
                    outcome__in=["ORDER_TAKEN", "NO_ORDER", "SHOP_CLOSED"]
                ),
                name="ck_visit_outcome",
            ),
            models.CheckConstraint(
                # 04 T-23 `ck_visit_coords`. GPS genuinely fails inside shops, and a
                # half-fix is worse than none: a latitude with no longitude is not a place.
                condition=models.Q(latitude__isnull=True, longitude__isnull=True)
                | models.Q(latitude__isnull=False, longitude__isnull=False),
                name="ck_visit_coords",
            ),
        ]
        indexes = [
            models.Index(
                fields=["app_user", "-visited_at"], name="ix_visit_user_date"
            ),
            models.Index(
                fields=["customer", "-visited_at"], name="ix_visit_customer_date"
            ),
        ]

    def __str__(self) -> str:
        return f"Visit {self.customer_id} by {self.app_user_id} at {self.visited_at:%Y-%m-%d}"
