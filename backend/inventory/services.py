"""Reason code administration (N-01).

Stock movement services arrive in M2.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from core.exceptions import ValidationFailed
from core.models import AuditLog
from core.permissions import Role, require_roles
from core.services import record_audit
from inventory.models import ReasonCode


@transaction.atomic
def create_reason_code(
    *,
    actor: Any,
    code: str,
    name: str,
    direction: str = ReasonCode.Direction.BOTH,
    is_restockable: bool = True,
) -> ReasonCode:
    require_roles(actor, Role.OWNER)
    code = code.strip().upper()
    if ReasonCode.objects.filter(code=code).exists():
        raise ValidationFailed(
            "That reason code already exists.",
            errors=[{"field": "code", "code": "DUPLICATE", "message": code}],
        )
    reason = ReasonCode.objects.create(
        code=code, name=name.strip(), direction=direction, is_restockable=is_restockable
    )
    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type="reason_code",
        entity_id=reason.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={"code": reason.code},
    )
    return reason


@transaction.atomic
def deactivate_reason_code(*, actor: Any, reason: ReasonCode) -> ReasonCode:
    """System codes are referenced by name in code and cannot be removed (04 T-08)."""
    require_roles(actor, Role.OWNER)
    if reason.is_system:
        raise ValidationFailed(
            "System reason codes cannot be deactivated.",
            errors=[{"field": "code", "code": "SYSTEM", "message": reason.code}],
        )
    reason.is_active = False
    reason.save(update_fields=["is_active"])
    record_audit(
        action=AuditLog.Action.DEACTIVATE,
        entity_type="reason_code",
        entity_id=reason.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={"is_active": False},
    )
    return reason
