"""Web admin login, logout and shell (ADR-003 surface)."""

from __future__ import annotations

import pytest

from core.models import AuditLog

pytestmark = pytest.mark.django_db

LOGIN = "/login/"
LOGOUT = "/logout/"
DASHBOARD = "/"


def test_login_page_renders(client):
    response = client.get(LOGIN)
    assert response.status_code == 200
    assert b"Sign in" in response.content


def test_dashboard_requires_authentication(client):
    response = client.get(DASHBOARD)
    assert response.status_code == 302
    assert LOGIN in response["Location"]


def test_owner_can_sign_in_and_sees_their_roles(client, owner):
    response = client.post(
        LOGIN, {"phone": owner.phone, "password": "owner-password-123"}, follow=True
    )
    assert response.status_code == 200
    assert owner.full_name.encode() in response.content
    assert b"OWNER" in response.content


@pytest.mark.parametrize("spelling", ["7903324153", "917903324153", "+917903324153"])
def test_sign_in_works_for_every_spelling_of_one_number(client, seeded_roles, spelling):
    """The reported defect, on the surface it was reported from.

    A superuser created as `7903324153` was stored verbatim while every lookup asked for
    `+917903324153`, so the browser reported "Incorrect phone number or password" for a
    correct password. `check_password` was never reached — the `user is None` branch
    short-circuits before it.
    """
    # Created through `create_user`, not `UserFactory`. The factory calls
    # `Manager.create()` and therefore **bypasses `UserManager._create` entirely** — which
    # is precisely why 665 green tests never caught this defect.
    from identity.models import Role as RoleModel
    from identity.models import User, UserRole

    user = User.objects.create_user(
        phone="7903324153", password="Manish.0360", full_name="Mack"
    )
    assert user.phone == "+917903324153", "the manager did not normalise on write"
    UserRole.objects.create(app_user=user, role=RoleModel.objects.get(code="OWNER"))

    response = client.post(LOGIN, {"phone": spelling, "password": "Manish.0360"}, follow=True)
    assert response.status_code == 200
    assert user.full_name.encode() in response.content


def test_bad_password_shows_an_error_and_does_not_sign_in(client, owner):
    response = client.post(LOGIN, {"phone": owner.phone, "password": "wrong"})
    assert response.status_code == 200
    assert b"Incorrect phone number or password" in response.content
    assert client.get(DASHBOARD).status_code == 302


def test_failed_web_login_is_audited(client, owner):
    client.post(LOGIN, {"phone": owner.phone, "password": "wrong"})
    assert AuditLog.objects.filter(action=AuditLog.Action.LOGIN_FAILED).exists()


def test_retailer_cannot_use_the_admin(client, retailer):
    """Retailers use the app. The admin is an internal surface (05 §8)."""
    retailer.set_password("retailer-password-123")
    retailer.save(update_fields=["password"])
    response = client.post(LOGIN, {"phone": retailer.phone, "password": "retailer-password-123"})
    assert response.status_code == 200
    assert b"cannot sign in here" in response.content


def test_signed_in_user_is_redirected_away_from_the_login_page(client, owner):
    client.post(LOGIN, {"phone": owner.phone, "password": "owner-password-123"})
    response = client.get(LOGIN)
    assert response.status_code == 302


def test_logout_ends_the_session(client, owner):
    client.post(LOGIN, {"phone": owner.phone, "password": "owner-password-123"})
    assert client.get(DASHBOARD).status_code == 200
    assert client.post(LOGOUT).status_code == 302
    assert client.get(DASHBOARD).status_code == 302
