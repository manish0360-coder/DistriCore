"""Refresh rotation, reuse detection and logout (05 §7.1)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

OTP_REQUEST = "/api/v1/auth/otp/request"
OTP_VERIFY = "/api/v1/auth/otp/verify"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


@pytest.fixture
def tokens(api, salesman, sms):
    api.post(OTP_REQUEST, {"phone": salesman.phone}, format="json")
    code = sms.sent[-1][1]
    response = api.post(OTP_VERIFY, {"phone": salesman.phone, "code": code}, format="json")
    return response.json()


def test_refresh_issues_a_new_pair(api, tokens):
    response = api.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json")
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["refresh_token"] != tokens["refresh_token"]


def test_reusing_a_rotated_refresh_token_is_rejected(api, tokens):
    """A replayed refresh token means it was captured (05 §7.1)."""
    first = api.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json")
    assert first.status_code == 200
    second = api.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json")
    assert second.status_code == 401
    assert second.json()["code"] == "REFRESH_EXPIRED"


def test_garbage_refresh_token_is_rejected(api):
    response = api.post(REFRESH, {"refresh_token": "not-a-token"}, format="json")
    assert response.status_code == 401
    assert response["Content-Type"].startswith("application/problem+json")


def test_refresh_requires_the_field(api):
    assert api.post(REFRESH, {}, format="json").status_code == 422


def test_logout_blacklists_the_refresh_token(api, tokens):
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}")
    logout = api.post(LOGOUT, {"refresh_token": tokens["refresh_token"]}, format="json")
    assert logout.status_code == 204
    api.credentials()
    replay = api.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json")
    assert replay.status_code == 401


def test_logout_is_idempotent_and_tolerates_an_invalid_token(api, tokens):
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}")
    assert api.post(LOGOUT, {"refresh_token": "rubbish"}, format="json").status_code == 204
    assert api.post(LOGOUT, {}, format="json").status_code == 204


def test_logout_requires_authentication(api):
    assert api.post(LOGOUT, {}, format="json").status_code == 401


def test_access_token_reaches_a_protected_endpoint(api, tokens):
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}")
    assert api.get(ME).status_code == 200


def test_rotated_token_is_itself_usable(api, tokens):
    """Rotation must mint a working token, not merely a different string."""
    first = api.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json")
    assert first.status_code == 200
    rotated = first.json()["refresh_token"]

    second = api.post(REFRESH, {"refresh_token": rotated}, format="json")
    assert second.status_code == 200
    assert second.json()["refresh_token"] != rotated


def test_rotated_access_token_authenticates(api, tokens):
    response = api.post(REFRESH, {"refresh_token": tokens["refresh_token"]}, format="json")
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access_token']}")
    assert api.get(ME).status_code == 200
