"""Inventory — the stock ledger.

**Stock on hand is not stored. It is SUM(stock_movement.quantity)** filtered by product,
location and lot (N-03, E-01, BR-004). There is deliberately no quantity column on any
table in this module, and adding one is forbidden (M2-3).

The corollary is that ``StockMovement`` is append-only: a correction is a compensating
movement, never an edit. Enforced in Python here, by a database trigger in migration
0004, and by the adversarial suite.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from core.fields import QuantityField


class StockLocation(models.Model):
    """A physical place stock is held (04 T-11).

    **A structural enabler (N-10, E-06, M2-1).** Version 1 seeds exactly one row and
    exposes no location selection anywhere. Adding this column after a year of movements
    would re-key the largest table in the system and every balance query over it.
    """

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=150)
    address = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "stock_location"
        ordering = ["code"]
        constraints = [
            # The database guarantees exactly one default, not a convention.
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True),
                name="uq_stock_location_default",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class StockLot(models.Model):
    """An identified quantity of a product within a location (04 T-12).

    **A structural enabler (N-10, E-06, M2-2).** Version 1 creates one implicit default
    lot per product, on first movement, and never surfaces lots in the interface.

    ``manufactured_date`` and ``expiry_date`` exist and are unused. They are columns on a
    table being created anyway; omitting them saves nothing and adding them later is
    another migration touching the movement path.
    """

    product = models.ForeignKey(
        "catalogue.Product", on_delete=models.RESTRICT, related_name="stock_lots"
    )
    lot_code = models.CharField(max_length=64, default="DEFAULT")
    manufactured_date = models.DateField(null=True, blank=True)  # unused until Edition 2
    expiry_date = models.DateField(null=True, blank=True)  # unused until Edition 2
    is_default = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_lot"
        constraints = [
            models.UniqueConstraint(fields=["product", "lot_code"], name="uq_stock_lot"),
        ]
        indexes = [
            models.Index(fields=["product"], name="ix_stock_lot_product"),
            # Unused in V1, free now, and exactly what expiry reporting needs at Edition 2.
            models.Index(
                fields=["expiry_date"],
                name="ix_stock_lot_expiry",
                condition=models.Q(expiry_date__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_id}:{self.lot_code}"


class StockMovementImmutable(RuntimeError):
    """Raised on any attempt to modify or remove a stock movement."""


class StockMovementQuerySet(models.QuerySet["StockMovement"]):
    def update(self, **kwargs: Any) -> int:
        raise StockMovementImmutable("stock_movement is append-only (M2-4, BR-004)")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise StockMovementImmutable("stock_movement is append-only (M2-4, BR-004)")


class StockMovement(models.Model):
    """Every change in stock, ever. **The single source of truth for inventory** (04 T-13).

    Append-only. A correction is a compensating movement (FR-STK-003).
    """

    class Type(models.TextChoices):
        RECEIPT = "RECEIPT", "Goods received"
        ISSUE = "ISSUE", "Goods issued"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        RETURN = "RETURN", "Return"
        OPENING = "OPENING", "Opening stock"

    product = models.ForeignKey(
        "catalogue.Product", on_delete=models.RESTRICT, related_name="movements"
    )
    # M2-1 / M2-2: structural. Defaulted to the seeded rows; no UI in V1.
    location = models.ForeignKey(StockLocation, on_delete=models.RESTRICT, related_name="movements")
    lot = models.ForeignKey(StockLot, on_delete=models.RESTRICT, related_name="movements")

    # M2-5: ONE signed column. Positive in, negative out. Separate in/out columns would
    # be assumed by every query, index and aggregate thereafter.
    quantity = QuantityField()
    movement_type = models.CharField(max_length=20, choices=Type.choices)

    # M2-9: polymorphic, no foreign key — it points at four different tables. The
    # compensating control is R-2: services accept a validated model INSTANCE, never a
    # raw (type, id) pair, so a typo cannot produce an orphan.
    source_document_type = models.CharField(max_length=30, blank=True)
    source_document_id = models.BigIntegerField(null=True, blank=True)

    reason_code = models.ForeignKey(
        "inventory.ReasonCode",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="movements",
    )

    # M2-10: when it physically happened, distinct from when the server recorded it.
    # Offline capture (M9) records events hours before sync.
    occurred_at = models.DateTimeField(db_index=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects: ClassVar[models.Manager[StockMovement]] = StockMovementQuerySet.as_manager()

    class Meta:
        db_table = "stock_movement"
        indexes = [
            # THE balance query.
            models.Index(fields=["product", "location", "lot"], name="ix_stock_mv_prod_loc_lot"),
            models.Index(fields=["-occurred_at"], name="ix_stock_mv_occurred"),
            models.Index(
                fields=["source_document_type", "source_document_id"], name="ix_stock_mv_source"
            ),
            models.Index(
                fields=["reason_code"],
                name="ix_stock_mv_reason",
                condition=models.Q(reason_code__isnull=False),
            ),
        ]
        constraints = [
            # M2-8 / BR-007 / N-05: every movement is explained. This is the database
            # enforcement of "every divergence is explained" (PO-5).
            models.CheckConstraint(
                condition=(
                    models.Q(source_document_id__isnull=False) | models.Q(reason_code__isnull=False)
                ),
                name="ck_stock_movement_has_source",
            ),
            # A zero movement is a bug, not a record.
            models.CheckConstraint(
                condition=~models.Q(quantity=0), name="ck_stock_movement_qty_nonzero"
            ),
            # Half a reference is worse than none.
            models.CheckConstraint(
                condition=(
                    models.Q(source_document_type="", source_document_id__isnull=True)
                    | (
                        ~models.Q(source_document_type="")
                        & models.Q(source_document_id__isnull=False)
                    )
                ),
                name="ck_stock_movement_source_pair",
            ),
            # M2-11: sign must agree with type. ADJUSTMENT, RETURN and OPENING are
            # legitimately bidirectional — a sales return is inbound, a purchase return
            # outbound — so they stay unconstrained.
            models.CheckConstraint(
                condition=(
                    (models.Q(movement_type="RECEIPT") & models.Q(quantity__gt=0))
                    | (models.Q(movement_type="ISSUE") & models.Q(quantity__lt=0))
                    | models.Q(movement_type__in=["ADJUSTMENT", "RETURN", "OPENING"])
                ),
                name="ck_stock_movement_sign_per_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.movement_type} {self.quantity} of product {self.product_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise StockMovementImmutable("stock_movement is append-only (M2-4, BR-004)")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise StockMovementImmutable("stock_movement is append-only (M2-4, BR-004)")


class ReasonCode(models.Model):
    """The owner-maintained explanation attached to every stock adjustment (04 T-08).

    BR-007 requires a source document OR one of these on every movement. This table is
    what makes "every divergence is explained" (PO-5) enforceable rather than aspirational.
    """

    class Direction(models.TextChoices):
        IN = "IN", "Increase only"
        OUT = "OUT", "Decrease only"
        BOTH = "BOTH", "Either"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=150)
    direction = models.CharField(max_length=10, choices=Direction.choices, default=Direction.BOTH)
    is_restockable = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "reason_code"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code
