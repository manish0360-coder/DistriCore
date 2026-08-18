"""D-M9.3-1 — does the access token actually carry `device_id`?

`GET /sync/status` identifies the requesting device from the JWT claim, because a
client-supplied `device_id` would permit cross-device status access (FR-SYN-011). That
design rests on one unproven assumption: **the claim is written on the *refresh* token
(`auth_views._issue_tokens`) and nothing in this codebase has ever read it back.**
`request.auth` appears nowhere.

So this file exists before the endpoint does. If the claim does not survive onto the access
token — or does not survive rotation through `/auth/refresh` — the M9.3 design is wrong and
must be re-decided rather than patched.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework_simplejwt.tokens import AccessToken

from api.v1.auth_views import _issue_tokens

pytestmark = pytest.mark.django_db

DEVICE = "a3f9c1d2e4b6a8c0"


def test_the_access_token_carries_the_device_id_claim(salesman):
    """The load-bearing assertion. Everything in M9.3 depends on this being true."""
    tokens = _issue_tokens(salesman, DEVICE)

    decoded = AccessToken(tokens["access_token"])

    assert decoded["device_id"] == DEVICE
    # `roles` travels the same way; if one custom claim is copied both are, and a failure
    # here would mean the copy mechanism itself changed.
    assert "roles" in decoded


def test_an_omitted_device_id_yields_an_empty_claim_not_a_missing_one(salesman):
    """`OtpVerifySerializer` and `PasswordLoginSerializer` both default it to `""`.

    A *missing* claim would make the status endpoint raise; an empty one makes it report on
    device `""`, which is wrong but recoverable. The distinction decides whether M9.3 needs
    a guard, so it is asserted rather than assumed.
    """
    tokens = _issue_tokens(salesman)

    decoded = AccessToken(tokens["access_token"])

    assert decoded["device_id"] == ""


def test_the_claim_survives_a_refresh_rotation(api, salesman):
    """C-7's refresh path must not silently drop the device identity.

    `RefreshView` mutates the presented token in place (`set_jti`/`set_exp`/`set_iat`) and
    returns its `access_token`. If custom claims were lost there, a device would carry the
    claim until its first refresh and then lose it — a failure that would only appear after
    thirty minutes of use.
    """
    issued = _issue_tokens(salesman, DEVICE)

    response = api.post(
        reverse("v1:refresh"),
        {"refresh_token": issued["refresh_token"]},
        format="json",
    )

    assert response.status_code == 200
    assert AccessToken(response.json()["access_token"])["device_id"] == DEVICE


def test_the_claim_arrives_through_a_real_password_login(api, owner):
    """End to end, over HTTP, with the serializer in the path.

    The client sends `device_id` in the body (`DeviceInterceptor` injects it on every write,
    C-10). This proves the whole chain — serializer default, service, token mint — rather
    than just the helper.
    """
    response = api.post(
        reverse("v1:login"),
        {"phone": owner.phone, "password": "owner-password-123", "device_id": DEVICE},
        format="json",
    )

    assert response.status_code == 200
    assert AccessToken(response.json()["access_token"])["device_id"] == DEVICE


def test_request_auth_exposes_the_validated_token_to_a_view(api, salesman):
    """The access side of the mechanism, not just the token's contents.

    M9.3 reads the claim from `request.auth`, and **no view in this codebase does that
    today**. `/auth/me` is used as a live authenticated request; if `request.auth` were not
    a decoded token, this endpoint could not have authorised it in the first place — so a
    200 here plus the assertions above is what makes the design safe to build on.
    """
    tokens = _issue_tokens(salesman, DEVICE)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}")

    response = api.get(reverse("v1:me"))

    assert response.status_code == 200
