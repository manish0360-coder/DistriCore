"""Read queries for identity."""

from __future__ import annotations

from django.db.models import QuerySet

from identity.models import User


def active_users_with_role(role_code: str) -> QuerySet[User]:
    return User.objects.filter(is_active=True, roles__code=role_code).distinct()


def get_active_user_by_phone(phone: str) -> User | None:
    return User.objects.filter(phone=phone, is_active=True).first()


def get_active_user(user_id: int) -> User | None:
    """Fetch a usable account by id.

    Exists so a delivery layer never imports the model (N-02) — the same reason
    ``inventory.selectors.get_active_reason_code`` exists.
    """
    return User.objects.filter(pk=user_id, is_active=True).first()
