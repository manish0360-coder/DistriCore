"""Auth endpoints end to end (05 §9.1, §10.1)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

OTP_REQUEST = "/api/v1/auth/otp/request"
OTP_VERIFY = "/api/v1/auth/otp/verify"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def test_otp_request_returns_202_without_disclosing_registration(api, sms):
    known = api.post(OTP_REQUEST, {"phone": "+919876500001"}, format="json")
    assert known.status_code == 202
    assert "expires_in_seconds" in known.json()
    # Unknown number: identical shape, identical status (FR-IAM-004).
    unknown = api.post(OTP_REQUEST, {"phone": "+919999999999"}, format="json")
    assert unknown.status_code == 202
    assert unknown.json().keys() == known.json().keys()


def test_otp_verify_returns_tokens_and_user(api, salesman, sms):
    api.post(OTP_REQUEST, {"phone": salesman.phone}, format="json")
    code = sms.sent[-1][1]
    response = api.post(
        OTP_VERIFY, {"phone": salesman.phone, "code": code, "device_id": "dev-1"}, format="json"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] and body["refresh_token"]
    # roles is an array — one person may be SALESMAN and DELIVERY (C-12).
    assert set(body["user"]["roles"]) == {"SALESMAN", "DELIVERY"}


def test_errors_are_problem_json_with_stable_code(api, salesman, sms):
    api.post(OTP_REQUEST, {"phone": salesman.phone}, format="json")
    response = api.post(OTP_VERIFY, {"phone": salesman.phone, "code": "000000"}, format="json")
    assert response.status_code == 422
    assert response["Content-Type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "OTP_INVALID"
    for key in ("type", "title", "status", "detail", "instance", "request_id", "errors"):
        assert key in body


def test_validation_error_is_422_with_field_paths(api):
    response = api.post(OTP_VERIFY, {"phone": ""}, format="json")
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert any(e["field"] in {"phone", "code"} for e in body["errors"])


def test_password_login_and_me(api, owner):
    response = api.post(
        LOGIN, {"phone": owner.phone, "password": "owner-password-123"}, format="json"
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    me = api.get(ME)
    assert me.status_code == 200
    assert me.json()["roles"] == ["OWNER"]


def test_wrong_password_does_not_reveal_whether_the_user_exists(api, owner):
    known = api.post(LOGIN, {"phone": owner.phone, "password": "wrong"}, format="json")
    unknown = api.post(LOGIN, {"phone": "+919999999999", "password": "wrong"}, format="json")
    assert known.status_code == unknown.status_code == 401
    assert known.json()["detail"] == unknown.json()["detail"]


def test_me_requires_authentication(api):
    response = api.get(ME)
    assert response.status_code == 401
    assert response.json()["code"] in {"TOKEN_INVALID", "TOKEN_EXPIRED"}


def test_request_id_is_echoed(api):
    response = api.get(ME, HTTP_X_REQUEST_ID="abc123")
    assert response["X-Request-Id"] == "abc123"
