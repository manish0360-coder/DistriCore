"""Read queries for the core module."""

from __future__ import annotations

from django.db.models import QuerySet

from core.models import AuditLog, MediaFile


def audit_for_entity(entity_type: str, entity_id: int) -> QuerySet[AuditLog]:
    """Everything that ever happened to one record (FR-AUD-005)."""
    return AuditLog.objects.filter(entity_type=entity_type, entity_id=entity_id).order_by(
        "-occurred_at"
    )


def get_media(media_id: int) -> MediaFile | None:
    """Fetch a stored file by id.

    Exists so the delivery layer never imports the model (N-02). Authorisation is the
    caller's responsibility; retrieval is mediated by an authorised view (04 T-25).
    """
    return MediaFile.objects.filter(pk=media_id).first()
