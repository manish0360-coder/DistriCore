"""Role x capability matrix, issued DIRECTLY against the API (00 §6.4, 02 §25.2).

Every client is bypassed. A test that exercises authorisation through a UI does not
verify FR-IAM-007 — the Flutter binary is public and must be assumed modified.

M0 exposes only the auth surface, so the matrix is small. It grows with every
milestone, and this file is where it grows.
"""

from __future__ import annotations

import pytest

from core.exceptions import PermissionDenied
from core.permissions import Role, has_role, require_roles, role_codes
from identity.services import grant_role, revoke_role

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]

PROTECTED = "/api/v1/auth/me"


def test_no_token_is_rejected(api):
    assert api.get(PROTECTED).status_code == 401


def test_garbage_token_is_rejected(api):
    api.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
    assert api.get(PROTECTED).status_code == 401


def test_tampered_token_is_rejected(api, salesman, auth):
    client = auth(salesman)
    header = client._credentials["HTTP_AUTHORIZATION"]
    forged = header[:-4] + ("aaaa" if not header.endswith("aaaa") else "bbbb")
    api.credentials(HTTP_AUTHORIZATION=forged)
    assert api.get(PROTECTED).status_code == 401


def test_deactivated_user_cannot_use_an_existing_token(api, salesman, auth):
    client = auth(salesman)
    assert client.get(PROTECTED).status_code == 200
    salesman.is_active = False
    salesman.save(update_fields=["is_active"])
    # A token issued before deactivation must stop working immediately.
    assert client.get(PROTECTED).status_code == 401


@pytest.mark.parametrize(
    ("holds", "required", "allowed"),
    [
        ([Role.OWNER], Role.OWNER, True),
        ([Role.SALESMAN], Role.OWNER, False),
        ([Role.RETAILER], Role.OWNER, False),
        ([Role.DELIVERY], Role.OWNER, False),
        ([Role.SALESMAN, Role.DELIVERY], Role.DELIVERY, True),
        ([Role.RETAILER], Role.SALESMAN, False),
    ],
)
def test_role_gate_is_exhaustive(holds, required, allowed):
    from tests.factories import UserFactory

    user = UserFactory(roles=holds)
    assert has_role(user, required) is allowed
    if allowed:
        require_roles(user, required)
    else:
        with pytest.raises(PermissionDenied):
            require_roles(user, required)


def test_inactive_user_holds_no_effective_role(salesman):
    salesman.is_active = False
    salesman.save(update_fields=["is_active"])
    assert has_role(salesman, Role.SALESMAN) is False


def test_anonymous_holds_no_role():
    assert has_role(None, Role.OWNER) is False


def test_only_owner_may_grant_roles(owner, salesman, retailer):
    grant_role(actor=owner, user=retailer, role_code=Role.SALESMAN)
    assert Role.SALESMAN in retailer.role_codes()

    with pytest.raises(PermissionDenied):
        grant_role(actor=salesman, user=retailer, role_code=Role.OWNER)
    with pytest.raises(PermissionDenied):
        revoke_role(actor=retailer, user=salesman, role_code=Role.SALESMAN)


def test_role_changes_are_audited(owner, retailer):
    from core.models import AuditLog

    grant_role(actor=owner, user=retailer, role_code=Role.SALESMAN)
    revoke_role(actor=owner, user=retailer, role_code=Role.SALESMAN)
    actions = set(AuditLog.objects.filter(entity_type="user_role").values_list("action", flat=True))
    assert actions == {AuditLog.Action.ROLE_GRANT, AuditLog.Action.ROLE_REVOKE}


def test_role_codes_helper_narrows_safely(salesman, retailer):
    """The helper a delivery layer uses instead of importing the model (N-02)."""
    assert role_codes(salesman) == ["DELIVERY", "SALESMAN"]
    assert role_codes(None) == []
    salesman.is_active = False
    salesman.save(update_fields=["is_active"])
    assert role_codes(salesman) == []
