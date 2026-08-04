"""Read queries for the core module."""

from __future__ import annotations

from django.db.models import QuerySet

from core.models import AuditLog


def audit_for_entity(entity_type: str, entity_id: int) -> QuerySet[AuditLog]:
    """Everything that ever happened to one record (FR-AUD-005)."""
    return AuditLog.objects.filter(entity_type=entity_type, entity_id=entity_id).order_by(
        "-occurred_at"
    )
