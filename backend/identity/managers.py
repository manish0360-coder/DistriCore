"""User manager.

Phone number is the login identity (04 T-01). There is no username and no email
field: the client's users are identified by mobile number, and inventing an unused
identifier would be a field that is always wrong.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import BaseUserManager

from identity.phone import normalise_phone


class UserManager(BaseUserManager["Any"]):
    use_in_migrations = True

    def _create(self, phone: str, password: str | None, **extra: Any) -> Any:
        if not phone:
            raise ValueError("A phone number is required.")
        # **The write path must store what the read path will look for.** Every lookup —
        # `authenticate_password`, `request_otp`, `verify_otp` — normalises first, so a
        # row written verbatim is a row that can never be found. A superuser created as
        # "7903324153" could not log in with any spelling of their own number.
        #
        # The empty check stays above this line: it is the contract `createsuperuser`
        # already relies on, and `normalise_phone` raises a different exception type.
        phone = normalise_phone(phone)
        user = self.model(phone=phone, **extra)
        if password:
            user.set_password(password)
        else:
            # Retailers authenticate by OTP only. An unusable placeholder hash would
            # be a lie in the data (04 T-01).
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, phone: str, password: str | None = None, **extra: Any) -> Any:
        extra.setdefault("is_superuser", False)
        return self._create(phone, password, **extra)

    def create_superuser(self, phone: str, password: str | None = None, **extra: Any) -> Any:
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        if extra.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        if not password:
            raise ValueError("A superuser must have a password.")
        return self._create(phone, password, **extra)
