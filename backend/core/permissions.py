"""Role constants and the server-side authorisation primitive.

N-06 / BR-003: authorisation is evaluated in CORE on every request, independently of
the client. The Flutter binary is public and must be assumed decompiled (DV-4), so a
client-side check is a usability feature and never a control.
"""

from __future__ import annotations

from typing import Any

from core.exceptions import PermissionDenied


class Role:
    """The four seeded roles (04 T-02). Codes are stable and referenced by code."""

    OWNER = "OWNER"
    SALESMAN = "SALESMAN"
    DELIVERY = "DELIVERY"
    RETAILER = "RETAILER"

    ALL = (OWNER, SALESMAN, DELIVERY, RETAILER)
    INTERNAL = (OWNER, SALESMAN, DELIVERY)
    FIELD = (SALESMAN, DELIVERY)


def role_codes(user: Any) -> list[str]:
    """Roles held by an authenticated, active user. Empty otherwise.

    Exists so a delivery layer can render a user's roles without importing the model
    (N-02). The narrowing is the same one has_role() performs.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    if not user.is_active:
        return []
    return sorted(user.role_codes())


def has_role(user: Any, *codes: str) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not user.is_active:
        return False
    return bool(set(codes) & user.role_codes())


def require_roles(user: Any, *codes: str) -> None:
    """Raise unless ``user`` holds at least one of ``codes``.

    Called from service functions, not from views — so that a rule cannot be bypassed
    by reaching a service through a different delivery layer (N-01).
    """
    if not has_role(user, *codes):
        raise PermissionDenied(f"This action requires one of: {', '.join(sorted(codes))}.")
