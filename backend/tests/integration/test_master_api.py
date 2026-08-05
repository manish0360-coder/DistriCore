"""Master-data endpoints (05 §9.2)."""

from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db

PRODUCTS = "/api/v1/products"
CUSTOMERS = "/api/v1/customers"
ZONES = "/api/v1/zones"
REASONS = "/api/v1/reason-codes"


def test_products_list_is_paginated(auth, owner, product):
    response = auth(owner).get(PRODUCTS)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 1


def test_money_crosses_the_wire_as_a_string(auth, owner, product):
    """AD-02: a JSON number would be a float on the client and lose paise."""
    row = auth(owner).get(PRODUCTS).json()["results"][0]
    assert row["selling_price"] == "100.00"
    assert isinstance(row["selling_price"], str)
    assert isinstance(row["tax_rate_percent"], str)


def test_owner_creates_a_product_over_the_api(auth, owner):
    response = auth(owner).post(
        PRODUCTS,
        {"code": "P-API", "name": "Detergent", "selling_price": "55.50", "pack_size": 24},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["code"] == "P-API"


def test_salesman_cannot_create_a_product(auth, salesman):
    response = auth(salesman).post(
        PRODUCTS, {"code": "P-X", "name": "X", "selling_price": "1.00"}, format="json"
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_invalid_product_payload_is_422_with_field_paths(auth, owner):
    response = auth(owner).post(PRODUCTS, {"code": "P-B"}, format="json")
    assert response.status_code == 422
    fields = {e["field"] for e in response.json()["errors"]}
    assert {"name", "selling_price"} <= fields


def test_retailer_sees_only_active_products(auth, retailer_login, product):
    from tests.factories import ProductFactory

    ProductFactory(is_active=False)
    body = auth(retailer_login).get(PRODUCTS).json()
    assert body["count"] == 1
    assert body["results"][0]["id"] == product.pk


def test_retailer_cannot_read_an_inactive_product(auth, retailer_login):
    from tests.factories import ProductFactory

    hidden = ProductFactory(is_active=False)
    assert auth(retailer_login).get(f"{PRODUCTS}/{hidden.pk}").status_code == 404


def test_product_patch_updates_price(auth, owner, product):
    response = auth(owner).patch(
        f"{PRODUCTS}/{product.pk}", {"selling_price": "123.00"}, format="json"
    )
    assert response.status_code == 200
    product.refresh_from_db()
    assert product.selling_price == Decimal("123.00")


def test_customers_are_scoped_to_the_retailers_own_shop(auth, retailer_login, customer):
    from tests.factories import CustomerFactory

    other = CustomerFactory()
    body = auth(retailer_login).get(CUSTOMERS).json()
    assert body["count"] == 1
    assert body["results"][0]["id"] == customer.pk
    # AD-11: scoping is derived from the token, so there is no parameter to tamper with.
    assert auth(retailer_login).get(f"{CUSTOMERS}/{other.pk}").status_code == 404


def test_salesman_creates_a_customer_over_the_api(auth, salesman):
    response = auth(salesman).post(
        CUSTOMERS,
        {
            "code": "C-API",
            "shop_name": "Nayi Dukan",
            "phone": "+919876512345",
            "billing_address": "Bazaar Road",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["credit_limit_amount"] == "0.00"


def test_salesman_creating_with_a_credit_limit_is_refused(auth, salesman):
    response = auth(salesman).post(
        CUSTOMERS,
        {
            "code": "C-CL",
            "shop_name": "X",
            "phone": "+919876512399",
            "billing_address": "A",
            "credit_limit_amount": "9999.00",
        },
        format="json",
    )
    assert response.status_code == 403


def test_zones_and_reason_codes_are_readable(auth, salesman, zone):
    assert auth(salesman).get(ZONES).json()["count"] == 1
    # Eight reason codes are seeded by migration inventory/0002.
    assert auth(salesman).get(REASONS).json()["count"] == 8


def test_reason_codes_filter_by_direction(auth, salesman):
    body = auth(salesman).get(f"{REASONS}?direction=OUT").json()
    codes = {r["code"] for r in body["results"]}
    assert "DAMAGE" in codes
    assert "PURCHASE_IN" not in codes


def test_master_endpoints_require_authentication(api):
    for url in (PRODUCTS, CUSTOMERS, ZONES, REASONS):
        assert api.get(url).status_code == 401
