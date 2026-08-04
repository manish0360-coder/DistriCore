"""Authentication backend.

Delegates to ``identity.services`` rather than reimplementing the rules, so that the
web login and the API login cannot diverge (N-01, BR-001).
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.backends import BaseBackend
from django.http import HttpRequest

from core.exceptions import DomainError
from core.services import client_ip
from identity.models import User


class PhoneBackend(BaseBackend):
    def authenticate(
        self,
        request: HttpRequest | None = None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> User | None:
        from identity.services import authenticate_password

        phone = username or kwargs.get("phone")
        if not phone or not password:
            return None
        try:
            return authenticate_password(
                phone=phone, password=password, ip_address=client_ip(request)
            )
        except DomainError:
            return None

    def get_user(self, user_id: int) -> User | None:
        return User.objects.filter(pk=user_id, is_active=True).first()
