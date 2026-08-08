"""Identity business rules.

N-01: every rule in this module and nowhere else. Views call these functions; they do
not reimplement any part of them.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.exceptions import (
    AccountInactive,
    DomainError,
    InvalidCredentials,
    OtpAttemptsExceeded,
    OtpExpired,
    OtpInvalid,
    OtpRateLimited,
    PermissionDenied,
    ValidationFailed,
)
from core.models import AuditLog
from core.permissions import Role, require_roles
from core.services import get_business_profile, record_audit
from identity.models import OtpRequest, User, UserRole
from identity.models import Role as RoleModel
from identity.phone import normalise_phone as _normalise_phone
from identity.sms import get_sms_provider

logger = logging.getLogger("districore.identity")

# `_normalise_phone` is re-exported under its historical private name so every call site
# here — and `tests/unit/test_otp_services.py` — keeps importing the same function it
# always did. The definition moved to `identity.phone` so `UserManager` can WRITE the
# canonical form this module READS, without a manager importing a service (see 0004).

_MAX_OTP_PER_WINDOW = 3
_OTP_WINDOW = timedelta(minutes=15)


@dataclass(frozen=True)
class OtpChallenge:
    """What the client is told after requesting a code. Never includes the code."""

    expires_in_seconds: int
    attempts_allowed: int


# --------------------------------------------------------------------------- OTP
def request_otp(
    *,
    phone: str,
    ip_address: str = "",
    purpose: str = OtpRequest.Purpose.LOGIN,
) -> OtpChallenge:
    """Issue a one-time code.

    Deliberately does not reveal whether the number is registered (FR-IAM-004). An
    unregistered number receives the same response and the same delay; verification
    fails later, at which point an attacker has learned nothing.
    """
    phone = _normalise_phone(phone)

    recent = OtpRequest.objects.filter(
        phone=phone, created_at__gte=timezone.now() - _OTP_WINDOW
    ).count()
    if recent >= _MAX_OTP_PER_WINDOW:
        # SMS costs real money; an unthrottled OTP endpoint is both a security hole
        # and a bill (05 §13).
        raise OtpRateLimited("Too many code requests. Try again in a few minutes.")

    code = _generate_code(settings.OTP_LENGTH)
    otp = OtpRequest.objects.create(
        phone=phone,
        code_hash=make_password(code),
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=_otp_expiry_minutes()),
        requested_ip=ip_address[:45],
    )

    if User.objects.filter(phone=phone, is_active=True).exists():
        get_sms_provider().send_otp(phone, code)
    else:
        # Same shape of response, no SMS sent, no information disclosed.
        logger.info("otp_requested_unknown_phone", extra={"phone_suffix": phone[-4:]})

    return OtpChallenge(
        expires_in_seconds=int((otp.expires_at - timezone.now()).total_seconds()),
        attempts_allowed=settings.OTP_MAX_ATTEMPTS,
    )


def verify_otp(*, phone: str, code: str, device_id: str = "", ip_address: str = "") -> User:
    """Exchange a code for a verified user.

    **The whole function is deliberately NOT wrapped in a single atomic block.**

    It was, and that was a security defect, not merely a failing test: a wrong code
    incremented ``attempt_count``, then raised ``OtpInvalid`` *inside* the same
    transaction — so Django rolled the increment back. The counter never advanced, the
    cap in FR-IAM-004 never engaged, and an OTP could be brute-forced indefinitely.

    A failed attempt must therefore be **committed** and the rejection raised
    afterwards, outside the block. The same applies to consuming a used code.
    """
    phone = _normalise_phone(phone)

    failure: DomainError | None = None
    user: User | None = None

    with transaction.atomic():
        otp = (
            OtpRequest.objects.select_for_update()
            .filter(phone=phone, consumed_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        # These three raise having written nothing, so a rollback costs nothing.
        if otp is None:
            raise OtpInvalid("No active code for this number.")
        if otp.attempt_count >= settings.OTP_MAX_ATTEMPTS:
            raise OtpAttemptsExceeded("Too many incorrect attempts. Request a new code.")
        if otp.is_expired:
            raise OtpExpired("This code has expired. Request a new one.")

        if check_password(code, otp.code_hash):
            # Single use: consume it before deciding whether the account can sign in,
            # so a rejected account cannot replay the same code.
            OtpRequest.objects.filter(pk=otp.pk).update(consumed_at=timezone.now())

            user = User.objects.filter(phone=phone).first()
            if user is None:
                failure = InvalidCredentials("Could not sign in.")
            elif not user.is_active:
                failure = AccountInactive("This account has been deactivated.")
            else:
                user.last_login_at = timezone.now()
                user.save(update_fields=["last_login_at", "updated_at"])
                record_audit(
                    action=AuditLog.Action.LOGIN_SUCCESS,
                    entity_type="app_user",
                    entity_id=user.pk,
                    actor=user,
                    surface=AuditLog.Surface.API,
                    device_id=device_id,
                    ip_address=ip_address,
                    after_state={"method": "OTP"},
                )
        else:
            # F() rather than read-modify-write: two concurrent wrong guesses must
            # count as two, not one.
            OtpRequest.objects.filter(pk=otp.pk).update(attempt_count=F("attempt_count") + 1)
            failure = OtpInvalid("Incorrect code.")

    # Raised only after the block has COMMITTED the attempt or the consumption.
    if failure is not None:
        raise failure

    assert user is not None  # narrowed: no failure implies a signed-in user
    return user


# --------------------------------------------------------------------------- password
def authenticate_password(*, phone: str, password: str, ip_address: str = "") -> User:
    """Password authentication for staff on the web admin."""
    phone = _normalise_phone(phone)
    user = User.objects.filter(phone=phone).first()

    if user is None or not user.check_password(password):
        record_audit(
            action=AuditLog.Action.LOGIN_FAILED,
            entity_type="app_user",
            entity_id=getattr(user, "pk", None),
            surface=AuditLog.Surface.WEB,
            ip_address=ip_address,
            after_state={"phone_suffix": phone[-4:]},
        )
        # Identical message whether the number is unknown or the password is wrong.
        raise InvalidCredentials("Incorrect phone number or password.")
    if not user.is_active:
        raise AccountInactive("This account has been deactivated.")

    user.last_login_at = timezone.now()
    user.save(update_fields=["last_login_at", "updated_at"])
    record_audit(
        action=AuditLog.Action.LOGIN_SUCCESS,
        entity_type="app_user",
        entity_id=user.pk,
        actor=user,
        surface=AuditLog.Surface.WEB,
        ip_address=ip_address,
        after_state={"method": "PASSWORD"},
    )
    return user


# --------------------------------------------------------------------------- roles
@transaction.atomic
def grant_role(*, actor: User, user: User, role_code: str) -> UserRole:
    """Give a user a role. Owner only, and audited (BR-002)."""
    require_roles(actor, Role.OWNER)
    role = RoleModel.objects.filter(code=role_code).first()
    if role is None:
        raise ValidationFailed(
            "Unknown role.",
            errors=[{"field": "role_code", "code": "NOT_FOUND", "message": role_code}],
        )
    link, created = UserRole.objects.get_or_create(
        app_user=user, role=role, defaults={"granted_by": actor}
    )
    if created:
        user.__dict__.pop("_role_codes", None)
        record_audit(
            action=AuditLog.Action.ROLE_GRANT,
            entity_type="user_role",
            entity_id=link.pk,
            actor=actor,
            surface=AuditLog.Surface.WEB,
            after_state={"user_id": user.pk, "role": role_code},
        )
    return link


@transaction.atomic
def revoke_role(*, actor: User, user: User, role_code: str) -> None:
    require_roles(actor, Role.OWNER)
    link = UserRole.objects.filter(app_user=user, role__code=role_code).first()
    if link is None:
        return
    link_id = link.pk
    link.delete()
    user.__dict__.pop("_role_codes", None)
    record_audit(
        action=AuditLog.Action.ROLE_REVOKE,
        entity_type="user_role",
        entity_id=link_id,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"user_id": user.pk, "role": role_code},
    )


# ----------------------------------------------------------------------- bootstrap
#: How the system reached the state that made a bootstrap necessary. Classified **here,
#: from the database** — never accepted from the caller, because a security record must
#: not assert whatever an operator typed.
BOOTSTRAP_FIRST_BOOT = "FIRST_BOOT"
BOOTSTRAP_RECOVERY = "RECOVERY"


@dataclass(frozen=True)
class BootstrapResult:
    """What the bootstrap did, so the caller need not re-derive it.

    The command surface must report the mode without reading a model (N-02) and without
    computing it a second time — two derivations of one fact can disagree, and this one
    ends up on a security record.
    """

    user: User
    mode: str
    created_user: bool


@transaction.atomic
def bootstrap_owner(
    *,
    phone: str,
    full_name: str = "",
    password: str | None = None,
    reason: str = "",
) -> BootstrapResult:
    """Grant the first — or the recovering — OWNER. FR-IAM-014's break-glass procedure.

    **Why this exists.** ``grant_role`` requires an OWNER to act, and a fresh database has
    none, so no user can ever be granted the first role through any other supported path.
    The only alternative today is a raw ``INSERT`` into ``user_role``: an unaudited write
    into authorisation data, which is exactly what ADR-0003 exists to prevent.

    **It is not an escalation tool.** It refuses while any *active* OWNER exists — the
    ordinary path is then ``grant_role``, which is audited against a named actor. *Active*
    rather than *any*: if the sole owner has been deactivated, that **is** the recovery
    case FR-IAM-014 describes, and a stricter guard would lock the business out of its own
    system permanently.

    Someone with shell access could deactivate the owner and then run this. Shell access
    already implies database access, so the guard prevents accident; **the audit row is the
    control.**

    ``reason`` is optional by ruling. A mandatory field on a break-glass path fails closed
    at the worst possible moment, and is defeated within a week by a constant string in a
    saved command — at which point the audit row looks explained and is not.
    """
    phone = _normalise_phone(phone)

    # Serialises two concurrent bootstraps against each other: the second waits, then sees
    # the first's UserRole and refuses. The Role row is the only row that exists to lock —
    # the absence of a UserRole is the whole problem. Readers are unaffected, so
    # `grant_role`'s plain lookup never blocks on this.
    owner_role = RoleModel.objects.select_for_update().filter(code=Role.OWNER).first()
    if owner_role is None:
        raise ValidationFailed(
            "The OWNER role is not seeded. Run migrations first.",
            errors=[{"field": "role", "code": "NOT_FOUND", "message": Role.OWNER}],
        )

    owner_links = UserRole.objects.filter(role=owner_role)
    if owner_links.filter(app_user__is_active=True).exists():
        raise PermissionDenied(
            "An active owner already exists. Use the ordinary role-grant path, which "
            "records who granted it."
        )

    # Facts first, conclusion second — and both are recorded (§7.1). A reviewer who
    # distrusts `mode` can re-derive it from the counts.
    owner_rows_existing = owner_links.count()
    users_existing = User.objects.count()
    mode = BOOTSTRAP_FIRST_BOOT if owner_rows_existing == 0 else BOOTSTRAP_RECOVERY

    user = User.objects.filter(phone=phone).first()
    created_user = user is None
    if user is None:
        if not full_name:
            raise ValidationFailed(
                "A new owner needs a full name.",
                errors=[{"field": "full_name", "code": "REQUIRED", "message": ""}],
            )
        user = User.objects.create_user(phone=phone, password=password, full_name=full_name)
    elif not user.is_active:
        # Granting a role to a deactivated account produces a user who still cannot log
        # in — a silent no-op from the operator's point of view. Refuse loudly instead.
        # Reactivation is a separate, deliberate act (FR-IAM-011).
        raise PermissionDenied(
            "That account is deactivated. Reactivate it first, then bootstrap."
        )

    link, created = UserRole.objects.get_or_create(
        app_user=user,
        role=owner_role,
        # Nobody granted this. The truthful actor is an operator with shell access, who
        # is unidentifiable — naming one would invent them.
        defaults={"granted_by": None},
    )
    user.__dict__.pop("_role_codes", None)

    record_audit(
        action=AuditLog.Action.OWNER_BOOTSTRAP,
        entity_type="user_role",
        entity_id=link.pk,
        actor=None,
        surface=AuditLog.Surface.SYSTEM,
        after_state={
            "mode": mode,
            "role": Role.OWNER,
            "user_id": user.pk,
            "phone_suffix": phone[-4:],
            "users_existing": users_existing,
            "owner_rows_existing": owner_rows_existing,
            "inactive_owners": owner_rows_existing,
            "reason": reason,
            "granted": created,
        },
    )
    return BootstrapResult(user=user, mode=mode, created_user=created_user)


# --------------------------------------------------------------------------- helpers
def _otp_expiry_minutes() -> int:
    """D-5: the owner-editable value wins; the environment variable is the fallback.

    04 T-05 places this on business_profile. M0 read it from settings, which made the
    document untrue. Reading the profile with a settings fallback keeps a fresh database
    working before anyone has opened the configuration screen.
    """
    try:
        return int(get_business_profile().otp_expiry_minutes)
    except Exception:
        return int(settings.OTP_EXPIRY_MINUTES)


def _generate_code(length: int) -> str:
    """Cryptographically random numeric code. ``secrets``, never ``random``."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def user_payload(user: User) -> dict[str, Any]:
    """The user object returned by /auth/* and /auth/me (05 §10.1).

    ``roles`` is an array: one person may be both SALESMAN and DELIVERY, and a client
    that assumes a single role hides delivery screens from a salesman who delivers
    (05 §12, C-12).
    """
    return {
        "id": user.pk,
        "full_name": user.full_name,
        "phone": user.phone,
        "language": user.language,
        "roles": sorted(user.role_codes()),
        "customer_id": user.customer_id,
    }
