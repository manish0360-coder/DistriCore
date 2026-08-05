"""Order endpoints and owner screens (05 §9.3, M3 tasks 8-9)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db

ORDERS = "/api/v1/orders"


@pytest.fixture
def priced(product):
    product.selling_price = Decimal("65.00")
    product.tax_rate_percent = Decimal("18.00")
    product.pack_size = 12
    product.save(update_fields=["selling_price", "tax_rate_percent", "pack_size"])
    return product


def _payload(product, **kw):
    body = {"lines": [{"product_id": product.pk, "quantity": "24"}]}
    body.update(kw)
    return body


def test_owner_places_an_order(auth, owner, credit_customer, priced, profile):
    response = auth(owner).post(
        ORDERS, _payload(priced, customer_id=credit_customer.pk), format="json"
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PLACED"
    assert body["total_amount"] == "1840.80"
    assert body["order_number"].startswith("SO-")
    assert isinstance(body["subtotal_amount"], str)  # AD-02


def test_retailer_orders_for_their_own_shop_without_naming_it(
    auth, retailer_login, customer, priced, profile
):
    """AD-11: the endpoint accepts no customer_id from a retailer."""
    response = auth(retailer_login).post(ORDERS, _payload(priced), format="json")
    assert response.status_code == 201
    assert response.json()["customer_id"] == customer.pk
    assert response.json()["source"] == "PORTAL"


def test_retailer_cannot_order_for_another_shop(auth, retailer_login, priced, profile):
    from tests.factories import CustomerFactory

    other = CustomerFactory()
    response = auth(retailer_login).post(
        ORDERS, _payload(priced, customer_id=other.pk), format="json"
    )
    # customer_id is ignored for retailers; the order lands on their own shop.
    assert response.status_code == 201
    assert response.json()["customer_id"] != other.pk


def test_salesman_cannot_place_an_order(auth, salesman, credit_customer, priced, profile):
    response = auth(salesman).post(
        ORDERS, _payload(priced, customer_id=credit_customer.pk), format="json"
    )
    assert response.status_code == 403


def test_replaying_a_client_uuid_returns_the_same_order(
    auth, owner, credit_customer, priced, profile
):
    key = str(uuid.uuid4())
    client = auth(owner)
    first = client.post(
        ORDERS, _payload(priced, customer_id=credit_customer.pk, client_uuid=key), format="json"
    )
    second = client.post(
        ORDERS, _payload(priced, customer_id=credit_customer.pk, client_uuid=key), format="json"
    )
    assert first.json()["id"] == second.json()["id"]


def test_confirm_and_cancel_are_actions_not_status_patches(
    auth, owner, credit_customer, priced, profile
):
    """AD-08 / M3-4: a client that could PATCH status would hold the state machine."""
    client = auth(owner)
    order_id = client.post(
        ORDERS, _payload(priced, customer_id=credit_customer.pk), format="json"
    ).json()["id"]

    confirmed = client.post(f"{ORDERS}/{order_id}/confirm", {}, format="json")
    assert confirmed.json()["status"] == "CONFIRMED"

    cancelled = client.post(
        f"{ORDERS}/{order_id}/cancel", {"reason": "Retailer changed mind"}, format="json"
    )
    assert cancelled.json()["status"] == "CANCELLED"


def test_cancel_without_a_reason_is_422(auth, owner, credit_customer, priced, profile):
    client = auth(owner)
    order_id = client.post(
        ORDERS, _payload(priced, customer_id=credit_customer.pk), format="json"
    ).json()["id"]
    assert client.post(f"{ORDERS}/{order_id}/cancel", {}, format="json").status_code == 422


def test_confirming_twice_is_a_conflict(auth, owner, credit_customer, priced, profile):
    client = auth(owner)
    order_id = client.post(
        ORDERS, _payload(priced, customer_id=credit_customer.pk), format="json"
    ).json()["id"]
    client.post(f"{ORDERS}/{order_id}/confirm", {}, format="json")
    again = client.post(f"{ORDERS}/{order_id}/confirm", {}, format="json")
    assert again.status_code == 422
    assert again.json()["errors"][0]["code"] == "INVALID_TRANSITION"


def test_a_retailer_cannot_see_another_shops_order(
    auth, owner, retailer_login, credit_customer, priced, profile
):
    order_id = (
        auth(owner)
        .post(ORDERS, _payload(priced, customer_id=credit_customer.pk), format="json")
        .json()["id"]
    )
    assert auth(retailer_login).get(f"{ORDERS}/{order_id}").status_code == 404


def test_credit_endpoint_reports_exposure(auth, owner, credit_customer, priced, profile):
    client = auth(owner)
    client.post(ORDERS, _payload(priced, customer_id=credit_customer.pk), format="json")
    body = client.get(f"/api/v1/customers/{credit_customer.pk}/credit").json()
    assert body["credit_limit_amount"] == "10000.00"
    assert body["exposure_amount"] == "1840.80"
    assert body["available_amount"] == "8159.20"


def test_orders_require_authentication(api):
    assert api.get(ORDERS).status_code == 401


# --------------------------------------------------------------------------- admin
@pytest.fixture
def signed_in(client, owner):
    client.post("/login/", {"phone": owner.phone, "password": "owner-password-123"})
    return client


def test_order_screens_render(signed_in, credit_customer, priced, profile):
    assert signed_in.get("/orders/").status_code == 200
    assert signed_in.get("/orders/new/").status_code == 200


def test_owner_places_an_order_through_the_form(signed_in, credit_customer, priced, profile):
    response = signed_in.post(
        "/orders/new/",
        {
            "customer_id": str(credit_customer.pk),
            "product_id": [str(priced.pk), "", "", "", ""],
            "quantity": ["24", "", "", "", ""],
            "notes": "Morning delivery",
        },
    )
    assert response.status_code == 302
    from orders.models import SalesOrder

    assert SalesOrder.objects.get().total_amount == Decimal("1840.80")


def test_order_detail_and_confirm_through_the_screen(
    signed_in, owner, credit_customer, priced, profile
):
    from orders.services import place_order

    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": priced, "quantity": Decimal("24")}],
    )
    assert signed_in.get(f"/orders/{order.pk}/").status_code == 200
    assert signed_in.post(f"/orders/{order.pk}/confirm/").status_code == 302
    order.refresh_from_db()
    assert order.status == "CONFIRMED"


def test_business_profile_screen(signed_in, profile):
    assert signed_in.get("/settings/").status_code == 200
    response = signed_in.post(
        "/settings/",
        {
            "legal_name": "Kumar Distributors",
            "gstin": "10AABCU9603R1ZM",
            "state_code": "10",
            "max_manual_discount_percent": "7.5",
            "credit_limit_mode": "BLOCK",
            "otp_expiry_minutes": "15",
        },
    )
    assert response.status_code == 302
    from core.services import get_business_profile

    saved = get_business_profile()
    assert saved.legal_name == "Kumar Distributors"
    assert saved.max_manual_discount_percent == Decimal("7.50")
    assert saved.credit_limit_mode == "BLOCK"


def test_api_refuses_a_line_with_both_units(auth, owner, credit_customer, priced, profile):
    response = auth(owner).post(
        ORDERS,
        {
            "customer_id": credit_customer.pk,
            "lines": [{"product_id": priced.pk, "quantity": "24", "pack_quantity": "2"}],
        },
        format="json",
    )
    assert response.status_code == 422


def test_api_accepts_a_pack_quantity(auth, owner, credit_customer, priced, profile):
    response = auth(owner).post(
        ORDERS,
        {
            "customer_id": credit_customer.pk,
            "lines": [{"product_id": priced.pk, "pack_quantity": "2"}],
        },
        format="json",
    )
    assert response.status_code == 201
    line = response.json()["lines"][0]
    assert line["quantity"] == "24.000"
    assert line["pack_quantity"] == "2.000"
