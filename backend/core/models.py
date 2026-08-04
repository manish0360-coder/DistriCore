"""Base models and the audit log.

``AuditLog`` is append-only. That is enforced in three places, because it is the one
table whose mutability would make every historical record unprovable (N-04, I-12):

1. Python — ``save()`` refuses an update, ``delete()`` raises.
2. Database — a trigger rejects UPDATE and DELETE (migration 0002).
3. Tests — ``tests/adversarial/test_audit_immutability.py`` attempts both.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models


class TimeStampedModel(models.Model):
    """Creation and modification timestamps. Both timestamptz, both UTC (N-08)."""

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


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
