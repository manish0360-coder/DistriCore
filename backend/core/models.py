"""Base models and the audit log.

``AuditLog`` is append-only. That is enforced in three places, because it is the one
table whose mutability would make every historical record unprovable (N-04, I-12):

1. Python — ``save()`` refuses an update, ``delete()`` raises.
2. Database — a trigger rejects UPDATE and DELETE (migration 0002).
3. Tests — ``tests/adversarial/test_audit_immutability.py`` attempts both.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar

from django.db import models

from core.fields import PercentField


class TimeStampedModel(models.Model):
    """Creation and modification timestamps. Both timestamptz, both UTC (N-08)."""

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class BusinessProfile(TimeStampedModel):
    """The distributor's own details and the tunables the owner may change (04 T-05).

    **Exactly one row, enforced by the database** (M3-10). A second row would make
    "which profile?" a question every reader has to answer.

    This is FD-12 tier-3 configuration: values the owner changes without a developer.
    Seller identity is snapshotted onto each invoice at issue (M5, D-02), so editing it
    here never rewrites a document already issued.
    """

    class CreditMode(models.TextChoices):
        WARN = "WARN", "Warn and allow override"
        BLOCK = "BLOCK", "Refuse the order"

    legal_name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=200, blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    state_code = models.CharField(max_length=2, blank=True)
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pin_code = models.CharField(max_length=10, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.CharField(max_length=200, blank=True)
    logo_media = models.ForeignKey(
        "core.MediaFile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    invoice_footer = models.TextField(blank=True)

    # --- tunables ---------------------------------------------------------
    max_manual_discount_percent = PercentField(default=Decimal("10.00"))
    credit_limit_mode = models.CharField(
        max_length=10, choices=CreditMode.choices, default=CreditMode.WARN
    )
    otp_expiry_minutes = models.SmallIntegerField(default=10)

    updated_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "business_profile"
        constraints = [
            # M3-10: singleton, enforced by the database rather than by convention.
            models.CheckConstraint(condition=models.Q(id=1), name="ck_business_profile_singleton"),
            models.CheckConstraint(
                condition=models.Q(
                    max_manual_discount_percent__gte=0, max_manual_discount_percent__lte=100
                ),
                name="ck_business_profile_discount",
            ),
            models.CheckConstraint(
                condition=models.Q(otp_expiry_minutes__gt=0), name="ck_business_profile_otp"
            ),
        ]

    def __str__(self) -> str:
        return self.legal_name or "DistriCore"


class MediaFile(models.Model):
    """Every uploaded file (04 T-25).

    One table, so there is one upload path, one validation routine, one authorisation
    check and one retention policy — instead of four of each (NFR-MNT-001).

    ``storage_path`` is always RELATIVE. An absolute path would break the moment the
    media root moves or object storage arrives (EP-J).
    """

    class Purpose(models.TextChoices):
        PRODUCT_IMAGE = "PRODUCT_IMAGE", "Product image"
        DELIVERY_PHOTO = "DELIVERY_PHOTO", "Delivery photo"
        VISIT_PHOTO = "VISIT_PHOTO", "Visit photo"
        INVOICE_PDF = "INVOICE_PDF", "Invoice PDF"
        OFFER_IMAGE = "OFFER_IMAGE", "Offer image"
        LOGO = "LOGO", "Business logo"

    storage_path = models.CharField(max_length=500)
    original_filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=100)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64, blank=True)
    purpose = models.CharField(max_length=30, choices=Purpose.choices)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_media",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "media_file"
        indexes = [
            models.Index(fields=["purpose", "-uploaded_at"], name="ix_media_purpose_uploaded"),
            models.Index(fields=["sha256"], name="ix_media_sha256"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(size_bytes__gt=0), name="ck_media_size"),
        ]

    def __str__(self) -> str:
        return f"{self.purpose}:{self.storage_path}"


class AuditLogQuerySet(models.QuerySet["AuditLog"]):
    def update(self, **kwargs: Any) -> int:
        raise AuditLogImmutable("audit_log is append-only (N-04, I-12)")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise AuditLogImmutable("audit_log is append-only (N-04, I-12)")


class AuditLogImmutable(RuntimeError):
    """Raised on any attempt to modify an audit record."""


class AuditLog(models.Model):
    """Who changed what, when (04 T-27).

    Version 1 scope is financial and stock events only — the irreversible subset
    (02A §13.2). It is not a general activity feed.
    """

    class Surface(models.TextChoices):
        WEB = "WEB", "Web admin"
        API = "API", "API"
        SYSTEM = "SYSTEM", "System"

    class Action(models.TextChoices):
        CREATE = "CREATE", "Create"
        ISSUE = "ISSUE", "Issue"
        CANCEL = "CANCEL", "Cancel"
        CREDIT_LIMIT_CHANGE = "CREDIT_LIMIT_CHANGE", "Credit limit change"
        CREDIT_OVERRIDE = "CREDIT_OVERRIDE", "Credit override"
        UPDATE = "UPDATE", "Update"
        CONFIRM = "CONFIRM", "Confirm"
        DISCOUNT_APPLIED = "DISCOUNT_APPLIED", "Manual discount applied"
        DEACTIVATE = "DEACTIVATE", "Deactivate"
        PRICE_CHANGE = "PRICE_CHANGE", "Price change"
        STOCK_ADJUST = "STOCK_ADJUST", "Stock adjustment"
        PAYMENT_REVERSE = "PAYMENT_REVERSE", "Payment reversal"
        ROLE_GRANT = "ROLE_GRANT", "Role granted"
        ROLE_REVOKE = "ROLE_REVOKE", "Role revoked"
        LOGIN_SUCCESS = "LOGIN_SUCCESS", "Login succeeded"
        LOGIN_FAILED = "LOGIN_FAILED", "Login failed"

    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True, editable=False)
    actor_user = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,  # deactivating a user must never erase their trail
        related_name="audit_entries",
    )
    # Snapshot: roles change, and "who was allowed to do this at the time" is the
    # question an audit answers.
    actor_role_code = models.CharField(max_length=32, blank=True)
    surface = models.CharField(max_length=20, choices=Surface.choices)
    device_id = models.CharField(max_length=64, blank=True)
    entity_type = models.CharField(max_length=50)
    entity_id = models.BigIntegerField(null=True, blank=True)
    action = models.CharField(max_length=30, choices=Action.choices)
    before_state = models.JSONField(null=True, blank=True)
    after_state = models.JSONField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    ip_address = models.CharField(max_length=45, blank=True)

    # as_manager() returns a Manager built FROM the queryset, not the queryset itself.
    objects: ClassVar[models.Manager[AuditLog]] = AuditLogQuerySet.as_manager()

    class Meta:
        db_table = "audit_log"
        indexes = [
            models.Index(
                fields=["entity_type", "entity_id", "-occurred_at"], name="ix_audit_entity"
            ),
            models.Index(fields=["actor_user", "-occurred_at"], name="ix_audit_actor_date"),
            models.Index(fields=["action", "-occurred_at"], name="ix_audit_action_date"),
        ]
        verbose_name = "audit entry"
        verbose_name_plural = "audit entries"

    def __str__(self) -> str:
        return f"{self.action} {self.entity_type}#{self.entity_id} @ {self.occurred_at:%Y-%m-%d}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise AuditLogImmutable("audit_log is append-only (N-04, I-12)")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise AuditLogImmutable("audit_log is append-only (N-04, I-12)")
