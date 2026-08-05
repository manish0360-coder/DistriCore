"""Product rules (04 T-10, FR-PRD-*)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from catalogue.models import Product
from catalogue.services import (
    create_product,
    deactivate_product,
    set_price,
    update_product,
)
from core.exceptions import PermissionDenied, ValidationFailed
from core.models import AuditLog

pytestmark = pytest.mark.django_db


def test_owner_creates_a_product(owner):
    product = create_product(
        actor=owner, code="p-1", name=" Soap ", selling_price=Decimal("42.50"), pack_size=12
    )
    assert product.code == "P-1"  # normalised
    assert product.name == "Soap"
    assert product.pack_size == 12


def test_creation_is_audited(owner):
    product = create_product(actor=owner, code="P-2", name="Soap", selling_price=Decimal("10"))
    assert AuditLog.objects.filter(
        entity_type="product", entity_id=product.pk, action=AuditLog.Action.CREATE
    ).exists()


@pytest.mark.parametrize("role_fixture", ["salesman", "retailer"])
def test_only_the_owner_may_create(request, role_fixture):
    actor = request.getfixturevalue(role_fixture)
    with pytest.raises(PermissionDenied):
        create_product(actor=actor, code="P-9", name="X", selling_price=Decimal("1"))


def test_duplicate_code_is_rejected(owner, product):
    with pytest.raises(ValidationFailed) as exc:
        create_product(actor=owner, code=product.code, name="Other", selling_price=Decimal("5"))
    assert exc.value.errors[0]["code"] == "DUPLICATE"


def test_negative_price_is_rejected(owner):
    with pytest.raises(ValidationFailed):
        create_product(actor=owner, code="P-N", name="X", selling_price=Decimal("-1"))


def test_price_change_gets_its_own_audit_action(owner, product):
    set_price(actor=owner, product=product, price=Decimal("150.00"))
    product.refresh_from_db()
    assert product.selling_price == Decimal("150.00")
    entry = AuditLog.objects.get(entity_type="product", action=AuditLog.Action.PRICE_CHANGE)
    assert entry.before_state["selling_price"] == "100.00"
    assert entry.after_state["selling_price"] == "150.00"


def test_unchanged_price_writes_no_audit(owner, product):
    set_price(actor=owner, product=product, price=product.selling_price)
    assert not AuditLog.objects.filter(action=AuditLog.Action.PRICE_CHANGE).exists()


def test_update_routes_price_through_set_price(owner, product):
    update_product(actor=owner, product=product, name="Renamed", selling_price=Decimal("77.00"))
    product.refresh_from_db()
    assert product.name == "Renamed"
    assert product.selling_price == Decimal("77.00")
    assert AuditLog.objects.filter(action=AuditLog.Action.PRICE_CHANGE).exists()


def test_deactivate_never_deletes(owner, product):
    deactivate_product(actor=owner, product=product)
    product.refresh_from_db()
    assert product.is_active is False
    assert Product.objects.filter(pk=product.pk).exists()


def test_pack_conversion(product):
    assert product.to_base_units(2, in_packs=True) == 24
    assert product.to_base_units(2) == 2
