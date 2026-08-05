"""Role x capability matrix for M1 master data, issued DIRECTLY at the API.

Every client is bypassed (00 §6.4, 02 §25.2). This file grows with every milestone;
M1 adds products, customers, zones, reason codes and media.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]

PRODUCTS = "/api/v1/products"
CUSTOMERS = "/api/v1/customers"
MEDIA = "/api/v1/media"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.mark.parametrize(
    ("role_fixture", "expected"),
    [("owner", 201), ("salesman", 403), ("delivery_only", 403), ("retailer", 403)],
)
def test_product_creation_is_owner_only(request, auth, role_fixture, expected):
    actor = request.getfixturevalue(role_fixture)
    response = auth(actor).post(
        PRODUCTS,
        {"code": f"P-{role_fixture}", "name": "X", "selling_price": "1.00"},
        format="json",
    )
    assert response.status_code == expected


@pytest.mark.parametrize(
    ("role_fixture", "expected"), [("owner", 201), ("salesman", 201), ("retailer", 403)]
)
def test_customer_creation_excludes_retailers(request, auth, role_fixture, expected):
    actor = request.getfixturevalue(role_fixture)
    response = auth(actor).post(
        CUSTOMERS,
        {
            "code": f"C-{role_fixture}",
            "shop_name": "X",
            "phone": "+919000000001",
            "billing_address": "A",
        },
        format="json",
    )
    assert response.status_code == expected


def test_a_retailer_cannot_enumerate_other_shops(auth, retailer_login):
    """Sequential ids are guessable; scoping is what makes that harmless (04 DBD-01)."""
    from tests.factories import CustomerFactory

    others = [CustomerFactory() for _ in range(3)]
    client = auth(retailer_login)
    for other in others:
        assert client.get(f"{CUSTOMERS}/{other.pk}").status_code == 404
    assert client.get(CUSTOMERS).json()["count"] == 1


def test_a_retailer_cannot_widen_scope_with_a_parameter(auth, retailer_login):
    """AD-11: the endpoint accepts no customer_id, so there is nothing to tamper with."""
    from tests.factories import CustomerFactory

    other = CustomerFactory()
    body = auth(retailer_login).get(f"{CUSTOMERS}?customer_id={other.pk}").json()
    assert body["count"] == 1
    assert body["results"][0]["id"] != other.pk


def test_a_retailer_cannot_raise_their_own_credit_limit(auth, retailer_login, customer):
    response = auth(retailer_login).patch(
        f"{CUSTOMERS}/{customer.pk}", {"credit_limit_amount": "999999.00"}, format="json"
    )
    assert response.status_code == 403
    customer.refresh_from_db()
    assert str(customer.credit_limit_amount) == "0.00"


def test_a_salesman_cannot_raise_a_credit_limit_by_patch(auth, salesman, customer):
    response = auth(salesman).patch(
        f"{CUSTOMERS}/{customer.pk}", {"credit_limit_amount": "50000.00"}, format="json"
    )
    assert response.status_code == 403
    customer.refresh_from_db()
    assert str(customer.credit_limit_amount) == "0.00"


def test_media_requires_authentication(api):
    upload = SimpleUploadedFile("x.jpg", JPEG, content_type="image/jpeg")
    assert api.post(MEDIA, {"file": upload, "purpose": "PRODUCT_IMAGE"}).status_code == 401


def test_media_is_never_served_from_a_guessable_public_path(auth, owner, settings, tmp_path):
    """NFR-SEC-006: retrieval is mediated by an authorised view, always."""
    settings.MEDIA_ROOT = tmp_path
    upload = SimpleUploadedFile("x.jpg", JPEG, content_type="image/jpeg")
    created = auth(owner).post(MEDIA, {"file": upload, "purpose": "PRODUCT_IMAGE"})
    assert created.status_code == 201
    media_id = created.json()["id"]

    assert auth(owner).get(f"{MEDIA}/{media_id}").status_code == 200
    from rest_framework.test import APIClient

    assert APIClient().get(f"{MEDIA}/{media_id}").status_code == 401


def test_unknown_media_is_not_found(auth, owner):
    assert auth(owner).get(f"{MEDIA}/999999").status_code == 404
