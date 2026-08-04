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
