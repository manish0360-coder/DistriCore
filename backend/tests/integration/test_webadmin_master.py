"""Owner screens for master data (ADR-003, client direction 3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(client, owner):
    client.post("/login/", {"phone": owner.phone, "password": "owner-password-123"})
    return client


def test_product_list_renders(signed_in, product):
    response = signed_in.get("/products/")
    assert response.status_code == 200
    assert product.code.encode() in response.content


def test_product_list_search(signed_in, product):
    assert product.code.encode() in signed_in.get(f"/products/?q={product.code}").content
    assert product.code.encode() not in signed_in.get("/products/?q=zzzz").content


def test_owner_creates_a_product_through_the_form(signed_in):
    response = signed_in.post(
        "/products/new/",
        {
            "code": "P-FORM",
            "name": "Form product",
            "selling_price": "65.00",
            "tax_rate_percent": "18",
            "pack_size": "6",
            "unit_name": "PCS",
            "pack_name": "CASE",
        },
    )
    assert response.status_code == 302
    from catalogue.models import Product

    assert Product.objects.get(code="P-FORM").selling_price == Decimal("65.00")


def test_form_shows_a_domain_error_rather_than_crashing(signed_in, product):
    response = signed_in.post(
        "/products/new/", {"code": product.code, "name": "Dup", "selling_price": "1"}
    )
    assert response.status_code == 200
    assert b"already in use" in response.content


def test_customer_list_and_form(signed_in, zone):
    assert signed_in.get("/customers/").status_code == 200
    response = signed_in.post(
        "/customers/new/",
        {
            "code": "C-FORM",
            "shop_name": "Form Shop",
            "phone": "+919876500123",
            "billing_address": "Bazaar",
            "zone_id": str(zone.pk),
            "credit_limit_amount": "5000",
            "credit_days": "15",
        },
    )
    assert response.status_code == 302
    from customers.models import Customer

    created = Customer.objects.get(code="C-FORM")
    assert created.zone == zone
    assert created.credit_limit_amount == Decimal("5000.00")


def test_customer_edit_page_loads(signed_in, customer):
    assert signed_in.get(f"/customers/{customer.pk}/").status_code == 200


def test_zone_and_reason_code_lists_render(signed_in, zone):
    assert zone.name.encode() in signed_in.get("/zones/").content
    assert b"DAMAGE" in signed_in.get("/reason-codes/").content


def test_master_screens_require_authentication(client):
    for url in ("/products/", "/customers/", "/zones/", "/reason-codes/"):
        assert client.get(url).status_code == 302
