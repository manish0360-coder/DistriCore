"""Inventory.

M1 creates only ReasonCode. StockLocation, StockLot and StockMovement arrive in M2
under the ADR-0004 structural-column gate.
"""

from __future__ import annotations

from django.db import models


class ReasonCode(models.Model):
    """The owner-maintained explanation attached to every stock adjustment (04 T-08).

    This table is what makes "every divergence is explained" (PO-5) enforceable rather
    than aspirational: BR-007 requires a source document OR one of these on every
    stock movement.
    """

    class Direction(models.TextChoices):
        IN = "IN", "Increase only"
        OUT = "OUT", "Decrease only"
        BOTH = "BOTH", "Either"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=150)
    direction = models.CharField(max_length=10, choices=Direction.choices, default=Direction.BOTH)
    # Returned goods that re-enter sellable stock. A DAMAGE return records the event
    # without adding sellable stock — the DV-8 mechanism for V1 returns.
    is_restockable = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "reason_code"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code
