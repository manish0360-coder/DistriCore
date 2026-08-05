"""Product master (04 T-10)."""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from core.fields import MoneyField, PercentField, to_quantity
from core.models import TimeStampedModel


class Product(TimeStampedModel):
    """What is sold.

    ``pack_size`` replaces a unit-of-measure model: the client sells cases and pieces,
    which is one conversion and one integer (02A §13.2). All stock is held in the base
    unit; the pack is a capture convenience.
    """

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    # Required on a GST invoice; nullable so a product can exist before the code is
    # looked up.
    hsn_code = models.CharField(max_length=8, blank=True)
    tax_rate_percent = PercentField(default=0)
    selling_price = MoneyField()
    unit_name = models.CharField(max_length=20, default="PCS")
    pack_size = models.IntegerField(default=1)
    pack_name = models.CharField(max_length=20, blank=True, default="CASE")
    image_media = models.ForeignKey(
        "core.MediaFile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,  # a missing image must not break the row
        related_name="products",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "product"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="ix_product_name"),
            models.Index(fields=["updated_at"], name="ix_product_updated_at"),
            models.Index(
                fields=["is_active"], name="ix_product_active", condition=models.Q(is_active=True)
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(selling_price__gte=0), name="ck_product_selling_price"
            ),
            models.CheckConstraint(
                condition=models.Q(tax_rate_percent__gte=0, tax_rate_percent__lte=100),
                name="ck_product_tax_rate",
            ),
            models.CheckConstraint(
                condition=models.Q(pack_size__gte=1), name="ck_product_pack_size"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"

    def to_base_units(self, quantity: Decimal | str | int, *, in_packs: bool = False) -> Decimal:
        """Convert an entered quantity to base units.

        Returns a **Decimal at quantity scale**, never an int. The previous signature
        returned ``int`` and truncated: ordering 2.5 kg stored 2. ``QuantityField`` is
        NUMERIC(14,3) exactly so fractional units work (M3-2, N-07).

        Lives on the model because it is a property OF the product, and because every
        caller must use the same conversion — mixed units in the ledger would make every
        aggregate wrong.
        """
        entered = to_quantity(quantity)
        return to_quantity(entered * self.pack_size) if in_packs else entered
