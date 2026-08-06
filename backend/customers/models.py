"""Zones and customers (04 T-07, T-09)."""

from __future__ import annotations

from django.db import models

from core.fields import CoordinateField, MoneyField
from core.models import TimeStampedModel


class Zone(TimeStampedModel):
    """The geographic area a customer belongs to and a salesman serves (04 T-07).

    All five client-named fields are nullable because rural addressing is inconsistent:
    a shop may have a ward but no panchayat, or a road name but no PIN. Requiring all
    five would make the form unfillable, and an unfillable form is how a salesman ends
    up entering rubbish.
    """

    name = models.CharField(max_length=150)
    road_name = models.CharField(max_length=200, blank=True)
    pin_code = models.CharField(max_length=10, blank=True)
    panchayat = models.CharField(max_length=150, blank=True)
    # VARCHAR, not INT: wards are labelled "12A" as often as "12".
    ward_number = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=150, blank=True)
    assigned_user = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,  # a salesman may leave; the zone must survive
        related_name="zones",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "zone"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["assigned_user"], name="ix_zone_assigned_user"),
            models.Index(fields=["pin_code"], name="ix_zone_pin_code"),
            models.Index(fields=["updated_at"], name="ix_zone_updated_at"),
        ]

    def __str__(self) -> str:
        return self.name


class Customer(TimeStampedModel):
    """The retailer the distributor sells to (04 T-09)."""

    code = models.CharField(max_length=32, unique=True)
    shop_name = models.CharField(max_length=200)
    owner_name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20)
    alt_phone = models.CharField(max_length=20, blank=True)
    # Many small retailers are unregistered, so this must be nullable.
    gstin = models.CharField(max_length=15, blank=True)
    # D-3 / M5-7: drives CGST+SGST versus IGST at invoice issue.
    #
    # An Indian GSTIN encodes the state in its first two characters, so for a registered
    # buyer this is derivable and normally left blank. It exists as an explicit override
    # because unregistered retailers have no GSTIN and **a wrong tax split is a legal
    # defect, not a cosmetic one** — the derivation must be correctable by hand.
    state_code = models.CharField(max_length=2, blank=True)
    zone = models.ForeignKey(
        Zone, null=True, blank=True, on_delete=models.SET_NULL, related_name="customers"
    )
    billing_address = models.TextField()
    delivery_address = models.TextField(blank=True)  # blank means "same as billing"
    # The owner sets this. Only the owner may change it (FR-CUS-005).
    credit_limit_amount = MoneyField(default=0)
    credit_days = models.SmallIntegerField(default=0)
    # Documentation only. The balance that counts comes from an OPENING ledger entry
    # created at go-live (ACT-E); there is deliberately NO outstanding_balance column.
    opening_balance_amount = MoneyField(default=0)
    latitude = CoordinateField(null=True, blank=True)
    longitude = CoordinateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="customers_created",
    )

    class Meta:
        db_table = "customer"
        ordering = ["shop_name"]
        indexes = [
            models.Index(fields=["zone"], name="ix_customer_zone"),
            models.Index(fields=["phone"], name="ix_customer_phone"),
            models.Index(fields=["shop_name"], name="ix_customer_shop_name"),
            models.Index(fields=["updated_at"], name="ix_customer_updated_at"),
            models.Index(
                fields=["is_active"], name="ix_customer_active", condition=models.Q(is_active=True)
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(credit_limit_amount__gte=0), name="ck_customer_credit_limit"
            ),
            models.CheckConstraint(
                condition=models.Q(credit_days__gte=0), name="ck_customer_credit_days"
            ),
            # Coordinates are captured together or not at all. Q == Q is a Python
            # bool, not an expression — this is the correct spelling.
            models.CheckConstraint(
                condition=(
                    models.Q(latitude__isnull=True, longitude__isnull=True)
                    | models.Q(latitude__isnull=False, longitude__isnull=False)
                ),
                name="ck_customer_coords_paired",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.shop_name}"
