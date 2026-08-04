"""Audit recording — the only way an audit row is written.

N-01: business rules live in services. This module is the service for the audit
concern; no view, serialiser or template writes ``AuditLog`` directly.
"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest

from core.context import get_request_id
from core.models import AuditLog

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


def _scrub(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {k: ("[redacted]" if k.lower() in _SENSITIVE else v) for k, v in state.items()}


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
