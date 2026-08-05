"""Identity models (04 T-01 … T-04).

Deviations from 04, both minor and both documented in the M0 report:

* ``customer`` foreign key is added in M1, when the ``customer`` table exists.
  A nullable FK added later is trivially reversible and is not on the irreversible
  list (04 §17.1).
* ``is_superuser`` is added for framework compatibility. ``PermissionsMixin`` is NOT
  used, which avoids the ``auth_group`` / ``user_permissions`` join tables entirely.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel
from identity.managers import UserManager


class Role(models.Model):
    """A named permission set (04 T-02).

    Four rows are seeded. The table exists so Edition 2 can add roles without a
    migration (EP-B). Permissions themselves are code-level, checked in services —
    this table names the role, it does not model a permission matrix.
    """

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        db_table = "role"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class User(AbstractBaseUser, TimeStampedModel):
    """Everyone who can log in (04 T-01)."""

    class Language(models.TextChoices):
        HINDI = "hi", "हिन्दी"
        ENGLISH = "en", "English"

    phone = models.CharField(max_length=20, unique=True)
    alt_phone = models.CharField(max_length=20, blank=True)
    full_name = models.CharField(max_length=200)
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.HINDI)
    # Set ONLY for RETAILER users. On the many side because one shop may later have
    # several logins, while one login always belongs to exactly one shop (04 T-01).
    # Deferred from M0 (TD-5) because the customer table did not exist yet.
    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="logins",
    )
    is_active = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)

    roles: models.ManyToManyField[Role, UserRole] = models.ManyToManyField(
        Role,
        through="UserRole",
        # UserRole has two FKs to User (holder and granter); name the holder.
        through_fields=("app_user", "role"),
        related_name="users",
    )

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "app_user"
        indexes = [
            models.Index(fields=["is_active"], name="ix_app_user_is_active"),
            models.Index(
                fields=["customer"],
                name="ix_app_user_customer",
                condition=models.Q(customer__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.phone}>"

    # -- roles ---------------------------------------------------------------
    def role_codes(self) -> set[str]:
        """Codes of every role this user holds.

        Cached per instance: authorisation is checked several times per request and
        this must not become N queries.
        """
        cached = getattr(self, "_role_codes", None)
        if cached is None:
            cached = set(self.roles.values_list("code", flat=True))
            self._role_codes = cached
        return cached

    # -- framework compatibility --------------------------------------------
    # PermissionsMixin is deliberately not used (see module docstring). These two
    # methods satisfy the framework contract without the extra tables.
    def has_perm(self, perm: str, obj: Any = None) -> bool:
        return self.is_active and self.is_superuser

    def has_module_perms(self, app_label: str) -> bool:
        return self.is_active and self.is_superuser

    @property
    def is_staff(self) -> bool:
        return self.is_superuser


class UserRole(models.Model):
    """Which roles a user holds (04 T-03).

    A join table rather than a single foreign key because one person is both
    SALESMAN and DELIVERY — the client stated delivery is a role inside the salesman
    application. A single FK would force that person to hold two accounts, splitting
    their visits, deliveries and audit trail across two identities.
    """

    app_user = models.ForeignKey(User, on_delete=models.RESTRICT, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.RESTRICT, related_name="user_roles")
    granted_at = models.DateTimeField(default=timezone.now)
    granted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="roles_granted"
    )

    class Meta:
        db_table = "user_role"
        constraints = [
            models.UniqueConstraint(fields=["app_user", "role"], name="uq_user_role"),
        ]
        indexes = [models.Index(fields=["app_user"], name="ix_user_role_app_user")]

    def __str__(self) -> str:
        return f"{self.app_user_id}:{self.role_id}"


class OtpRequest(models.Model):
    """One-time passcodes for mobile login (04 T-04).

    ``phone`` is deliberately not a foreign key: an OTP is requested before identity
    is known, and failing a foreign key for an unregistered number would leak user
    existence (FR-IAM-004).
    """

    class Purpose(models.TextChoices):
        LOGIN = "LOGIN", "Login"
        PHONE_CHANGE = "PHONE_CHANGE", "Phone change"

    phone = models.CharField(max_length=20)
    code_hash = models.CharField(max_length=255)  # hashed — never plaintext
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.LOGIN)
    expires_at = models.DateTimeField()
    attempt_count = models.SmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    requested_ip = models.CharField(max_length=45, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "otp_request"
        indexes = [
            models.Index(fields=["phone", "-created_at"], name="ix_otp_phone_created"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(attempt_count__gte=0), name="ck_otp_request_attempts"
            ),
        ]

    def __str__(self) -> str:
        return f"OTP {self.phone} ({self.purpose})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None
