"""Customer and zone rules (04 T-07, T-09, FR-CUS-*)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.exceptions import PermissionDenied, ResourceNotFound, ValidationFailed
from core.models import AuditLog
from customers.models import Customer
from customers.selectors import search_customers, visible_customers
from customers.services import (
    create_customer,
    create_zone,
    deactivate_customer,
    get_customer_for,
    set_credit_limit,
    update_customer,
    update_zone,
)

pytestmark = pytest.mark.django_db


def test_salesman_may_add_a_customer_in_the_field(salesman):
    """Client requirement: 'customer add' from the salesman app."""
    customer = create_customer(
        actor=salesman,
        code="c-1",
        shop_name=" Sharma Kirana ",
        phone="+919876500001",
        billing_address="Bazaar",
    )
    assert customer.code == "C-1"
    assert customer.shop_name == "Sharma Kirana"
    assert customer.created_by == salesman
    assert customer.credit_limit_amount == Decimal("0.00")


def test_salesman_may_not_set_a_credit_limit_on_creation(salesman):
    """FR-CUS-005: only the owner decides credit."""
    with pytest.raises(PermissionDenied):
        create_customer(
            actor=salesman,
            code="C-2",
            shop_name="X",
            phone="+91987650002",
            billing_address="A",
            credit_limit_amount=Decimal("5000"),
        )


def test_owner_may_set_a_credit_limit(owner, customer):
    set_credit_limit(actor=owner, customer=customer, amount=Decimal("10000"))
    customer.refresh_from_db()
    assert customer.credit_limit_amount == Decimal("10000.00")


def test_credit_limit_change_is_audited_with_before_and_after(owner, customer):
    set_credit_limit(actor=owner, customer=customer, amount=Decimal("2500"))
    entry = AuditLog.objects.get(action=AuditLog.Action.CREDIT_LIMIT_CHANGE)
    # Canonical money is NUMERIC(14,2) rendered at scale 2 — 04 §1.6, 05 AD-02.
    # This assertion was previously "2500", which was the non-canonical form the
    # implementation happened to produce. Both sides now assert the specification.
    assert entry.before_state["credit_limit_amount"] == "0.00"
    assert entry.after_state["credit_limit_amount"] == "2500.00"


def test_salesman_cannot_change_a_credit_limit(salesman, customer):
    with pytest.raises(PermissionDenied):
        set_credit_limit(actor=salesman, customer=customer, amount=Decimal("1"))


def test_negative_credit_limit_is_rejected(owner, customer):
    with pytest.raises(ValidationFailed):
        set_credit_limit(actor=owner, customer=customer, amount=Decimal("-1"))


def test_update_routes_credit_limit_through_the_owner_only_path(owner, customer):
    update_customer(
        actor=owner, customer=customer, shop_name="New", credit_limit_amount=Decimal("999")
    )
    customer.refresh_from_db()
    assert customer.shop_name == "New"
    assert customer.credit_limit_amount == Decimal("999.00")
    assert AuditLog.objects.filter(action=AuditLog.Action.CREDIT_LIMIT_CHANGE).exists()


def test_duplicate_code_is_rejected(owner, customer):
    with pytest.raises(ValidationFailed):
        create_customer(
            actor=owner,
            code=customer.code,
            shop_name="Other",
            phone="+919000000000",
            billing_address="B",
        )


def test_deactivate_never_deletes(owner, customer):
    deactivate_customer(actor=owner, customer=customer)
    customer.refresh_from_db()
    assert customer.is_active is False
    assert Customer.objects.filter(pk=customer.pk).exists()


def test_zone_create_and_update_are_audited(owner):
    zone = create_zone(actor=owner, name="Station Road", pin_code="800001")
    update_zone(actor=owner, zone=zone, name="Station Rd", city="Patna")
    zone.refresh_from_db()
    assert zone.name == "Station Rd"
    assert zone.city == "Patna"
    actions = set(AuditLog.objects.filter(entity_type="zone").values_list("action", flat=True))
    assert actions == {AuditLog.Action.CREATE, AuditLog.Action.UPDATE}


def test_salesman_cannot_create_a_zone(salesman):
    with pytest.raises(PermissionDenied):
        create_zone(actor=salesman, name="X")


def test_owner_sees_every_customer(owner, customer):
    assert customer in visible_customers(owner)


def test_salesman_sees_only_their_zones(salesman, zone, customer):
    from tests.factories import CustomerFactory

    zone.assigned_user = salesman
    zone.save(update_fields=["assigned_user"])
    mine = CustomerFactory(zone=zone)
    other = CustomerFactory(zone=None)
    visible = visible_customers(salesman)
    assert mine in visible
    assert other in visible  # unzoned customers are visible to every salesman
    from tests.factories import ZoneFactory

    foreign = CustomerFactory(zone=ZoneFactory())
    assert foreign not in visible_customers(salesman)


def test_retailer_sees_only_themselves(retailer_login, customer):
    from tests.factories import CustomerFactory

    CustomerFactory()
    visible = list(visible_customers(retailer_login))
    assert visible == [customer]


def test_scope_violation_looks_like_absence(retailer_login):
    """A 403 would confirm the record exists (05 §4.1)."""
    from tests.factories import CustomerFactory

    someone_else = CustomerFactory()
    with pytest.raises(ResourceNotFound):
        get_customer_for(retailer_login, someone_else.pk)


def test_search_matches_code_shop_and_phone(owner, customer):
    assert customer in search_customers(owner, term=customer.code)
    assert customer in search_customers(owner, term=customer.shop_name[:4])
    assert customer in search_customers(owner, term=customer.phone[-5:])
    assert customer not in search_customers(owner, term="zzzz-no-match")
