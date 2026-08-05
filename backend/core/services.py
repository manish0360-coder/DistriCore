"""Audit recording — the only way an audit row is written.

N-01: business rules live in services. This module is the service for the audit
concern; no view, serialiser or template writes ``AuditLog`` directly.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.http import HttpRequest

from core.context import get_request_id
from core.models import AuditLog, BusinessProfile

logger = logging.getLogger("districore.audit")

# Stripped before anything is written to an audit row (SEC-3, FR-AUD-006).
_SENSITIVE = {
    "password",
    "password_hash",
    "code",
    "code_hash",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "session",
    "csrf",
}


def _canonical(value: Any) -> Any:
    """Canonical JSON form of an audited value.

    A Decimal is written as its own fixed-scale string. JSON has no decimal type, so
    without this a Decimal would be coerced to a float by the encoder — importing
    exactly the error N-07 forbids — or rendered inconsistently by whatever str() the
    call site happened to apply.

    The scale comes from the value itself, because it was fixed when the value entered
    the domain (core.fields.to_money / to_quantity). This is defence in depth, not the
    place where canonical form is decided.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def _scrub(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        k: ("[redacted]" if k.lower() in _SENSITIVE else _canonical(v)) for k, v in state.items()
    }


def record_audit(
    *,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    actor: Any = None,
    surface: str = AuditLog.Surface.SYSTEM,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    device_id: str = "",
    ip_address: str = "",
) -> AuditLog:
    """Write one audit row.

    Called inside the same transaction as the change it records. An audit row that can
    be lost independently of its change is not an audit row.
    """
    actor_role = ""
    if actor is not None and getattr(actor, "pk", None):
        codes = getattr(actor, "role_codes", None)
        if callable(codes):
            actor_role = ",".join(sorted(codes()))

    entry = AuditLog(
        actor_user=actor if getattr(actor, "pk", None) else None,
        actor_role_code=actor_role[:32],
        surface=surface,
        device_id=device_id[:64],
        entity_type=entity_type[:50],
        entity_id=entity_id,
        action=action,
        before_state=_scrub(before_state),
        after_state=_scrub(after_state),
        request_id=get_request_id()[:64],
        ip_address=ip_address[:45],
    )
    entry.save()
    logger.info(
        "audit",
        extra={
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "actor_id": getattr(actor, "pk", None),
        },
    )
    return entry


def client_ip(request: HttpRequest | None) -> str:
    """Best-effort client IP.

    Behind Caddy the real address arrives in X-Real-IP. Used for audit and abuse
    investigation only — never for an authorisation decision, because it is spoofable
    without a trusted proxy chain.
    """
    if request is None:
        return ""
    forwarded = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return (request.META.get("REMOTE_ADDR") or "")[:45]


# --------------------------------------------------------------------------- config
SINGLETON_ID = 1


def get_business_profile() -> BusinessProfile:
    """The single tier-3 configuration row (04 T-05, M3-10).

    Created on demand rather than assumed: a fresh database, a restored backup and a
    test database must all behave identically, and a missing profile would otherwise be
    a 500 on the first order.
    """
    profile = BusinessProfile.objects.filter(pk=SINGLETON_ID).first()
    if profile is None:
        profile, _ = BusinessProfile.objects.get_or_create(
            pk=SINGLETON_ID, defaults={"legal_name": "DistriCore"}
        )
    return profile


def update_business_profile(*, actor: Any, **fields: Any) -> BusinessProfile:
    """Owner-only. Every change is audited: this row governs discounts and credit."""
    from core.permissions import Role, require_roles

    require_roles(actor, Role.OWNER)
    profile = get_business_profile()
    editable = {
        "legal_name",
        "trade_name",
        "gstin",
        "state_code",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "pin_code",
        "phone",
        "email",
        "invoice_footer",
        "max_manual_discount_percent",
        "credit_limit_mode",
        "otp_expiry_minutes",
    }
    payload = {k: v for k, v in fields.items() if k in editable}
    if not payload:
        return profile
    before = {k: getattr(profile, k) for k in payload}
    for key, value in payload.items():
        setattr(profile, key, value)
    profile.updated_by = actor if getattr(actor, "pk", None) else None
    profile.save()
    record_audit(
        action=AuditLog.Action.UPDATE,
        entity_type="business_profile",
        entity_id=profile.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state=before,
        after_state=payload,
    )
    return profile
