"""**Tests of the test infrastructure** (TD-30).

Unusual, and earned. `UserFactory` built users through `Manager.create()` for eight
milestones, which never reaches `UserManager._create`. Two defects hid there in a row:

* phone numbers stored uncanonicalised — invisible, because factory phones were already
  canonical;
* the owner-bootstrap deadlock — invisible, because factory users already had roles.

Neither was a failure of the code under test. Both were failures of the scaffolding, and
scaffolding that lies is worse than scaffolding that is missing, because it is counted.

Test 1 is the load-bearing one: it is the smallest statement of *"the factory takes the
production path"*, and it fails the moment anyone reverts `_create`.
"""

from __future__ import annotations

import pytest

from core.permissions import Role, has_role
from identity.models import User
from identity.phone import normalise_phone
from identity.services import authenticate_password
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PASSWORD = "factory-password-123"


# ------------------------------------------------------------------ 1. the creation path
def test_the_factory_normalises_a_phone_like_production_does(seeded_roles):
    """**The test that would have caught the first defect.**

    `_create` must route through `UserManager.create_user`. A factory that calls
    `Manager.create()` stores "7903324153" verbatim and this fails.
    """
    user = UserFactory(phone="7903324153")
    assert user.phone == "+917903324153"
    user.refresh_from_db()
    assert user.phone == "+917903324153"


@pytest.mark.parametrize("spelling", ["7903324153", "917903324153", "+917903324153"])
def test_the_factory_and_create_user_agree_on_the_stored_form(seeded_roles, spelling):
    """Not "both normalise" — *the same string*. Two implementations could drift."""
    user = UserFactory(phone=spelling)
    assert user.phone == normalise_phone(spelling)


def test_the_factory_reaches_the_manager_not_the_queryset(seeded_roles):
    """Stated at the seam itself, so the reason for the override cannot be mistaken.

    `User.objects.create` would bypass `_create`; `create_user` is the production entry
    point and the only one that applies the write-path rules.
    """
    bypassed = User.objects.create(phone="9000000001", full_name="Bypassed")
    built = UserFactory(phone="9000000002")

    assert bypassed.phone == "9000000001", "the ORM shortcut still stores verbatim"
    assert built.phone == "+919000000002", "the factory must not take that shortcut"


# ---------------------------------------------------------------------- 2-3. passwords
def test_a_user_built_without_a_password_cannot_be_logged_into(seeded_roles):
    """`create_user` gives an unusable hash, not an empty string.

    That is production's contract for a retailer who authenticates by OTP alone — an
    unusable placeholder would be a lie in the data (`04` T-01).
    """
    user = UserFactory()
    assert not user.has_usable_password()


def test_a_user_built_with_a_password_can_authenticate(seeded_roles):
    """The `password=` kwarg must survive the move from post_generation to declaration."""
    user = UserFactory(password=PASSWORD)
    assert authenticate_password(phone=user.phone, password=PASSWORD).pk == user.pk


# --------------------------------------------------------------- 4. the roles shortcut
def test_roles_is_a_fixture_shortcut_and_is_pinned_as_one(seeded_roles, client):
    """`roles=` writes `UserRole` directly. Production uses `grant_role` / `bootstrap_owner`.

    Recorded here rather than routed, because routing would make every fixture needing a
    salesman carry an owner, and would make fixtures order-dependent
    (`docs/TD-30_Factory_Creation_Path_Note.md` §3). A factory user with **no** roles must
    therefore behave exactly like the `createsuperuser` account that started all this.
    """
    user = UserFactory(password=PASSWORD)
    assert not user.role_codes()
    assert not has_role(user, *Role.INTERNAL)

    response = client.post("/login/", {"phone": user.phone, "password": PASSWORD})
    assert response.status_code == 200
    assert b"cannot sign in here" in response.content


def test_the_roles_shortcut_still_produces_a_usable_internal_user(seeded_roles):
    """The convenience must keep working, or 703 tests change meaning at once."""
    user = UserFactory(roles=[Role.SALESMAN, Role.DELIVERY])
    assert user.role_codes() == {Role.SALESMAN, Role.DELIVERY}
    assert has_role(user, *Role.INTERNAL)
