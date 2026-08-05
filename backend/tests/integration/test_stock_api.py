"""Stock endpoints and admin screens (05 §9.7, M2 tasks 8-9)."""

from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db

STOCK = "/api/v1/stock"
MOVEMENTS = "/api/v1/stock/movements"


def test_on_hand_includes_products_with_no_movements(auth, owner, product):
    """R-1 over HTTP: a product with zero movements must not vanish from the report."""
    body = auth(owner).get(STOCK).json()
    assert body["count"] == 1
    row = body["results"][0]
    assert row["on_hand"] == "0.000"
    assert isinstance(row["on_hand"], str)  # AD-02


def test_receipt_then_on_hand(auth, owner, product, receipt_reason):
    created = auth(owner).post(
        MOVEMENTS,
        {
            "product_id": product.pk,
            "quantity": "100",
            "movement_type": "RECEIPT",
            "reason_code_id": receipt_reason.pk,
            "in_packs": True,
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.json()["quantity"] == "1200.000"  # 100 packs x 12
    row = auth(owner).get(STOCK).json()["results"][0]
    assert row["on_hand"] == "1200.000"
    assert row["on_hand_packs"] == "100"


def test_issue_is_stored_negative(auth, owner, product, receipt_reason):
    client = auth(owner)
    client.post(
        MOVEMENTS,
        {
            "product_id": product.pk,
            "quantity": "50",
            "movement_type": "RECEIPT",
            "reason_code_id": receipt_reason.pk,
        },
        format="json",
    )
    from inventory.models import ReasonCode

    both = ReasonCode.objects.get(code="COUNT_ADJ")
    issued = client.post(
        MOVEMENTS,
        {
            "product_id": product.pk,
            "quantity": "20",
            "movement_type": "ISSUE",
            "reason_code_id": both.pk,
        },
        format="json",
    )
    assert issued.json()["quantity"] == "-20.000"
    assert client.get(STOCK).json()["results"][0]["on_hand"] == "30.000"


def test_non_writable_movement_type_is_rejected(auth, owner, product, receipt_reason):
    response = auth(owner).post(
        MOVEMENTS,
        {
            "product_id": product.pk,
            "quantity": "1",
            "movement_type": "OPENING",
            "reason_code_id": receipt_reason.pk,
        },
        format="json",
    )
    assert response.status_code == 422


def test_unknown_product_is_not_found(auth, owner, receipt_reason):
    response = auth(owner).post(
        MOVEMENTS,
        {
            "product_id": 999999,
            "quantity": "1",
            "movement_type": "RECEIPT",
            "reason_code_id": receipt_reason.pk,
        },
        format="json",
    )
    assert response.status_code == 404


def test_movements_list_and_filter(auth, owner, product, damage_reason):
    from inventory.services import adjust_stock

    adjust_stock(actor=owner, product=product, quantity=Decimal("-2"), reason_code=damage_reason)
    body = auth(owner).get(f"{MOVEMENTS}?product_id={product.pk}").json()
    assert body["count"] == 1
    assert body["results"][0]["reason_code"] == "DAMAGE"


@pytest.mark.parametrize("role_fixture", ["salesman", "retailer", "delivery_only"])
def test_stock_writes_are_owner_only_over_http(
    request, auth, product, receipt_reason, role_fixture
):
    actor = request.getfixturevalue(role_fixture)
    response = auth(actor).post(
        MOVEMENTS,
        {
            "product_id": product.pk,
            "quantity": "1",
            "movement_type": "RECEIPT",
            "reason_code_id": receipt_reason.pk,
        },
        format="json",
    )
    assert response.status_code == 403


def test_stock_endpoints_require_authentication(api):
    assert api.get(STOCK).status_code == 401
    assert api.get(MOVEMENTS).status_code == 401


# --------------------------------------------------------------------------- admin
@pytest.fixture
def signed_in(client, owner):
    client.post("/login/", {"phone": owner.phone, "password": "owner-password-123"})
    return client


def test_stock_screens_render(signed_in, product):
    assert signed_in.get("/stock/").status_code == 200
    assert signed_in.get("/stock/movements/").status_code == 200
    assert signed_in.get("/stock/entry/").status_code == 200


def test_stock_entry_form_records_a_movement(signed_in, product, receipt_reason):
    response = signed_in.post(
        "/stock/entry/",
        {
            "product_id": str(product.pk),
            "movement_type": "RECEIPT",
            "quantity": "10",
            "in_packs": "on",
            "reason_code_id": str(receipt_reason.pk),
            "notes": "First delivery",
        },
    )
    assert response.status_code == 302
    from inventory.selectors import on_hand_for

    assert on_hand_for(product) == Decimal("120.000")  # 10 packs x 12


def test_stock_entry_shows_a_domain_error(signed_in, product, damage_reason):
    """DAMAGE is OUT-only; a positive adjustment must be refused, not crash."""
    response = signed_in.post(
        "/stock/entry/",
        {
            "product_id": str(product.pk),
            "movement_type": "ADJUSTMENT",
            "quantity": "5",
            "reason_code_id": str(damage_reason.pk),
        },
    )
    assert response.status_code == 200
    assert b"only decrease stock" in response.content


# --------------------------------------------------------------------------- TD-12
def test_owner_can_create_a_zone_through_the_screen(signed_in):
    """TD-12: M1 shipped zone services with no screen — the dropdown was unfillable."""
    response = signed_in.post(
        "/zones/new/",
        {"name": "Station Road", "pin_code": "800001", "city": "Patna", "ward_number": "12A"},
    )
    assert response.status_code == 302
    from customers.models import Zone

    zone = Zone.objects.get(name="Station Road")
    assert zone.ward_number == "12A"  # VARCHAR, not INT


def test_zone_edit_screen_loads(signed_in, zone):
    assert signed_in.get(f"/zones/{zone.pk}/").status_code == 200


# --------------------------------------------------------------------------- TD-13
def test_product_form_accepts_an_image(signed_in, settings, tmp_path):
    """TD-13: media upload worked over the API but the admin form had no field."""
    settings.MEDIA_ROOT = tmp_path
    from django.core.files.uploadedfile import SimpleUploadedFile

    image = SimpleUploadedFile(
        "p.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 64, content_type="image/jpeg"
    )
    response = signed_in.post(
        "/products/new/",
        {
            "code": "P-IMG",
            "name": "With image",
            "selling_price": "10.00",
            "tax_rate_percent": "18",
            "pack_size": "1",
            "unit_name": "PCS",
            "pack_name": "CASE",
            "image": image,
        },
    )
    assert response.status_code == 302
    from catalogue.models import Product

    assert Product.objects.get(code="P-IMG").image_media_id is not None
