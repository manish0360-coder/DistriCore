"""Reason code read queries."""

from __future__ import annotations

from django.db.models import QuerySet

from inventory.models import ReasonCode


def active_reason_codes(*, direction: str | None = None) -> QuerySet[ReasonCode]:
    qs = ReasonCode.objects.filter(is_active=True)
    if direction:
        qs = qs.filter(direction__in=[direction, ReasonCode.Direction.BOTH])
    return qs
