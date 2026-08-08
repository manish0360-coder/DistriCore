"""**The system must be able to reach its own first authorised user** (FR-IAM-014).

The defect this suite exists for: `grant_role` requires an OWNER to act, a fresh database
has none, and no other supported path writes `user_role`. A freshly created superuser
authenticated correctly and was then refused by `has_role` with "This account cannot sign
in here" — authentication succeeded, authorisation had nothing to read.

Test 7 is the load-bearing one. Without it a later reader sees that `grant_role` "already
does this", deletes `bootstrap_owner` as redundant, and restores the deadlock — with a green
suite, because every other test here would still pass.
"""

from __future__ import annotations

import pytest
from django.core.management import CommandError, call_command

from core.exceptions import PermissionDenied, ValidationFailed
from core.models import AuditLog
from core.permissions import Role, has_role
from identity.models import Role as RoleModel
from identity.models import User, UserRole
from identity.services import (
    BOOTSTRAP_FIRST_BOOT,
    BOOTSTRAP_RECOVERY,
    bootstrap_owner,
    grant_role,
)

pytestmark = pytest.mark.django_db

PHONE = "7903324153"
CANONICAL = "+917903324153"
PASSWORD = "Manish.0360"


def _audit_rows():
    return AuditLog.objects.filter(action=AuditLog.Action.OWNER_BOOTSTRAP)


# ----------------------------------------------------------------- 7. the deadlock
def test_grant_role_cannot_produce_the_first_owner(seeded_roles):
    """**Why `bootstrap_owner` must exist.** Delete this and the next reader deletes it too.

    With an empty `user_role` table nobody holds OWNER, so `require_roles(actor, OWNER)`
    refuses every actor — including a superuser, because `is_superuser` is a framework flag
    that `has_role` deliberately does not consult (ADR-0003).
    """
    assert not UserRole.objects.exists()
    candidate = User.objects.create_superuser(
        phone=PHONE, password=PASSWORD, full_name="Mack"
    )
    with pytest.raises(PermissionDenied):
        grant_role(actor=candidate, user=candidate, role_code=Role.OWNER)
    assert not UserRole.objects.exists(), "the deadlock is the premise of this milestone"


# ------------------------------------------------------------------- 1. current policy
def test_create_superuser_alone_cannot_reach_the_admin(seeded_roles, client):
    """Pinned as correct-by-policy, so nobody "fixes" it by granting OWNER implicitly.

    A login is not an authorisation. `createsuperuser` writes `app_user`; the admin asks
    `user_role`.
    """
    User.objects.create_superuser(phone=PHONE, password=PASSWORD, full_name="Mack")
    response = client.post("/login/", {"phone": PHONE, "password": PASSWORD})
    assert response.status_code == 200
    assert b"cannot sign in here" in response.content


# ------------------------------------------------------------------------ 2. first boot
def test_bootstrap_creates_the_owner_and_grants_the_role(seeded_roles):
    result = bootstrap_owner(phone=PHONE, full_name="Mack", password=PASSWORD)
    assert result.mode == BOOTSTRAP_FIRST_BOOT
    assert result.created_user is True
    assert result.user.phone == CANONICAL
    assert has_role(result.user, Role.OWNER)


def test_bootstrap_promotes_a_user_that_already_exists(seeded_roles):
    existing = User.objects.create_superuser(
        phone=PHONE, password=PASSWORD, full_name="Mack"
    )
    result = bootstrap_owner(phone=PHONE)
    assert result.created_user is False
    assert result.user.pk == existing.pk
    assert has_role(result.user, Role.OWNER)


def test_the_owner_can_then_sign_in_to_the_admin(seeded_roles, client):
    """`00` §20.3 criterion 2, executable for the first time.

    "A user can log in by OTP on mobile and by password on web" has never been satisfiable
    on a clean machine through the supported path — the suite reached it only through
    `UserFactory(roles=[...])`, which is a creation path production does not use (TD-30).
    """
    bootstrap_owner(phone=PHONE, full_name="Mack", password=PASSWORD)
    response = client.post(
        "/login/", {"phone": PHONE, "password": PASSWORD}, follow=True
    )
    assert response.status_code == 200
    assert b"Mack" in response.content


# ------------------------------------------------------------------------- 3. refusal
def test_bootstrap_refuses_while_an_active_owner_exists(seeded_roles):
    """The property that stops this becoming an escalation tool."""
    bootstrap_owner(phone=PHONE, full_name="Mack", password=PASSWORD)
    with pytest.raises(PermissionDenied):
        bootstrap_owner(phone="9000000001", full_name="Impostor", password=PASSWORD)
    assert _audit_rows().count() == 1, "a refused bootstrap must write nothing"


# ------------------------------------------------------------------------ 4. recovery
def test_bootstrap_proceeds_when_the_only_owner_is_inactive(seeded_roles):
    """*Active*, not *any* — otherwise a deactivated owner locks the business out forever."""
    first = bootstrap_owner(phone=PHONE, full_name="Mack", password=PASSWORD).user
    first.is_active = False
    first.save(update_fields=["is_active"])

    result = bootstrap_owner(
        phone="9000000002", full_name="Deputy", password=PASSWORD, reason="owner locked out"
    )
    assert result.mode == BOOTSTRAP_RECOVERY
    assert has_role(result.user, Role.OWNER)


def test_a_deactivated_target_is_refused_rather_than_silently_granted(seeded_roles):
    """Granting a role to a deactivated account is a no-op the operator cannot see.

    `has_role` checks `is_active` before roles, so the grant would succeed and the login
    would still fail. Reactivation is a separate, deliberate act (FR-IAM-011).
    """
    dormant = User.objects.create_user(
        phone=PHONE, password=PASSWORD, full_name="Mack", is_active=False
    )
    with pytest.raises(PermissionDenied):
        bootstrap_owner(phone=PHONE)
    assert not UserRole.objects.filter(app_user=dormant).exists()


# --------------------------------------------------------------------------- 5. audit
def test_the_grant_is_audited_as_a_distinct_high_severity_event(seeded_roles):
    """FR-IAM-014's second clause — the half that gets forgotten.

    `audit_log` has no severity column, so a distinct action code is the only way this is
    findable without a JSON containment query.
    """
    result = bootstrap_owner(
        phone=PHONE, full_name="Mack", password=PASSWORD, reason="first install"
    )
    row = _audit_rows().get()

    assert row.actor_user is None, "nobody authorised this; naming an actor would invent one"
    assert row.surface == AuditLog.Surface.SYSTEM
    assert row.entity_type == "user_role"
    assert row.occurred_at is not None

    state = row.after_state
    assert state["mode"] == BOOTSTRAP_FIRST_BOOT
    assert state["role"] == Role.OWNER
    assert state["user_id"] == result.user.pk
    assert state["reason"] == "first install"
    assert UserRole.objects.get(pk=row.entity_id).granted_by is None


def test_the_audit_row_carries_the_facts_the_mode_was_derived_from(seeded_roles):
    """§7.1. Recording a conclusion without its evidence is what makes a trail unfalsifiable.

    One case makes `mode` debatable rather than wrong: OWNER granted, revoked (the row is
    deleted), then bootstrapped — that reads as FIRST_BOOT. A reviewer who distrusts the
    label can re-derive it from these counts.
    """
    User.objects.create_user(phone="9000000003", password=PASSWORD, full_name="Staff")
    bootstrap_owner(phone=PHONE, full_name="Mack", password=PASSWORD)

    state = _audit_rows().get().after_state
    assert state["users_existing"] == 1, "counted before the grant, excluding the new owner"
    assert state["owner_rows_existing"] == 0
    assert state["inactive_owners"] == 0


def test_a_recovery_records_the_counts_that_made_it_a_recovery(seeded_roles):
    first = bootstrap_owner(phone=PHONE, full_name="Mack", password=PASSWORD).user
    first.is_active = False
    first.save(update_fields=["is_active"])
    bootstrap_owner(phone="9000000004", full_name="Deputy", password=PASSWORD)

    state = _audit_rows().order_by("-id").first().after_state
    assert state["mode"] == BOOTSTRAP_RECOVERY
    assert state["owner_rows_existing"] == 1
    assert state["inactive_owners"] == 1


def test_a_missing_reason_never_blocks_a_recovery(seeded_roles):
    """The ruling: the audit trail is the control, not mandatory free-text."""
    first = bootstrap_owner(phone=PHONE, full_name="Mack", password=PASSWORD).user
    first.is_active = False
    first.save(update_fields=["is_active"])

    result = bootstrap_owner(phone="9000000005", full_name="Deputy", password=PASSWORD)
    assert result.mode == BOOTSTRAP_RECOVERY
    assert _audit_rows().order_by("-id").first().after_state["reason"] == ""


# ------------------------------------------------------------------- 6. FR-IAM-005
def test_a_user_who_can_reach_the_admin_holds_at_least_one_role(seeded_roles):
    """FR-IAM-005: "a user MUST hold at least one role." `create_superuser` holds none."""
    result = bootstrap_owner(phone=PHONE, full_name="Mack", password=PASSWORD)
    assert result.user.role_codes(), "an admin-capable user with no role violates FR-IAM-005"
    assert has_role(result.user, *Role.INTERNAL)


# ------------------------------------------------------------------ the command surface
def test_the_command_bootstraps_and_reports_the_mode(seeded_roles, monkeypatch, capsys):
    monkeypatch.setenv("DISTRICORE_OWNER_PASSWORD", PASSWORD)
    call_command("bootstrap_owner", "--phone", PHONE, "--full-name", "Mack", "--noinput")

    assert "first boot" in capsys.readouterr().out
    assert has_role(User.objects.get(phone=CANONICAL), Role.OWNER)


def test_the_command_refuses_with_one_readable_line(seeded_roles, monkeypatch):
    """A domain refusal is an expected outcome, not a traceback."""
    monkeypatch.setenv("DISTRICORE_OWNER_PASSWORD", PASSWORD)
    call_command("bootstrap_owner", "--phone", PHONE, "--full-name", "Mack", "--noinput")

    with pytest.raises(CommandError, match="active owner already exists"):
        call_command(
            "bootstrap_owner", "--phone", "9000000006", "--full-name", "X", "--noinput"
        )


def test_the_command_needs_a_name_for_a_user_it_must_create(seeded_roles, monkeypatch):
    monkeypatch.setenv("DISTRICORE_OWNER_PASSWORD", PASSWORD)
    with pytest.raises(CommandError):
        call_command("bootstrap_owner", "--phone", PHONE, "--noinput")


def test_bootstrap_needs_the_roles_to_be_seeded(db):
    """No `seeded_roles`: migrations create the four roles, and this says so out loud."""
    RoleModel.objects.filter(code=Role.OWNER).delete()
    with pytest.raises(ValidationFailed):
        bootstrap_owner(phone=PHONE, full_name="Mack", password=PASSWORD)
