"""Customer and zone business rules.

N-01: every rule lives here. Views and serialisers call these functions; they never
reimplement any part of them.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction

from core.exceptions import PermissionDenied, ResourceNotFound, ValidationFailed
from core.fields import to_money
from core.models import AuditLog
from core.permissions import Role, has_role, require_roles
from core.services import record_audit
from customers.models import Customer, Zone


# --------------------------------------------------------------------------- zones
@transaction.atomic
def create_zone(*, actor: Any, name: str, **fields: Any) -> Zone:
    require_roles(actor, Role.OWNER)
    zone = Zone.objects.create(name=name.strip(), **_zone_fields(fields))
    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type="zone",
        entity_id=zone.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={"name": zone.name},
    )
    return zone


@transaction.atomic
def update_zone(*, actor: Any, zone: Zone, **fields: Any) -> Zone:
    require_roles(actor, Role.OWNER)
    before = {"name": zone.name, "assigned_user_id": zone.assigned_user_id}
    for key, value in _zone_fields(fields).items():
        setattr(zone, key, value)
    if "name" in fields:
        zone.name = str(fields["name"]).strip()
    zone.save()
    record_audit(
        action=AuditLog.Action.UPDATE,
        entity_type="zone",
        entity_id=zone.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state=before,
        after_state={"name": zone.name, "assigned_user_id": zone.assigned_user_id},
    )
    return zone


def _zone_fields(fields: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "road_name",
        "pin_code",
        "panchayat",
        "ward_number",
        "city",
        "assigned_user",
        "assigned_user_id",
        "is_active",
    }
    return {k: v for k, v in fields.items() if k in allowed}


# --------------------------------------------------------------------------- customers
@transaction.atomic
def create_customer(
    *,
    actor: Any,
    code: str,
    shop_name: str,
    phone: str,
    billing_address: str,
    **fields: Any,
) -> Customer:
    """Create a retailer.

    Salesmen may create customers in the field (client requirement "customer add"), so
    this is not owner-only. But only the OWNER may set a credit limit (FR-CUS-005) —
    a salesman-created customer starts at zero.
    """
    require_roles(actor, Role.OWNER, Role.SALESMAN)

    code = code.strip().upper()
    if Customer.objects.filter(code=code).exists():
        raise ValidationFailed(
            "That customer code is already in use.",
            errors=[{"field": "code", "code": "DUPLICATE", "message": code}],
        )

    payload = _customer_fields(fields)
    requested_limit = payload.pop("credit_limit_amount", None)
    if requested_limit is not None and not has_role(actor, Role.OWNER):
        raise PermissionDenied("Only the owner may set a credit limit.")

    customer = Customer.objects.create(
        code=code,
        shop_name=shop_name.strip(),
        phone=phone.strip(),
        billing_address=billing_address.strip(),
        created_by=actor if getattr(actor, "pk", None) else None,
        **({"credit_limit_amount": requested_limit} if requested_limit is not None else {}),
        **payload,
    )
    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type="customer",
        entity_id=customer.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={"code": customer.code, "shop_name": customer.shop_name},
    )
    return customer


@transaction.atomic
def update_customer(*, actor: Any, customer: Customer, **fields: Any) -> Customer:
    require_roles(actor, Role.OWNER, Role.SALESMAN)
    payload = _customer_fields(fields)

    if "credit_limit_amount" in payload:
        new_limit = payload.pop("credit_limit_amount")
        set_credit_limit(actor=actor, customer=customer, amount=new_limit)

    if payload:
        before = {k: getattr(customer, k) for k in payload}
        for key, value in payload.items():
            setattr(customer, key, value)
        customer.save()
        record_audit(
            action=AuditLog.Action.UPDATE,
            entity_type="customer",
            entity_id=customer.pk,
            actor=actor,
            surface=AuditLog.Surface.WEB,
            before_state=before,
            after_state={k: getattr(customer, k) for k in payload},
        )
    return customer


@transaction.atomic
def set_credit_limit(*, actor: Any, customer: Customer, amount: Decimal) -> Customer:
    """Only the OWNER may change a credit limit, and every change is audited.

    FR-CUS-005. This is a separate function because it is a distinct authority and a
    distinct audit action — folding it into update_customer would lose both.
    """
    require_roles(actor, Role.OWNER)
    # Quantize on entry: the stored value, the audited value and the value the database
    # returns must be the same string (NFR-INT-006).
    amount = to_money(amount)
    if amount < 0:
        raise ValidationFailed(
            "A credit limit cannot be negative.",
            errors=[{"field": "credit_limit_amount", "code": "MIN_VALUE", "message": str(amount)}],
        )
    previous = customer.credit_limit_amount
    customer.credit_limit_amount = amount
    customer.save(update_fields=["credit_limit_amount", "updated_at"])
    record_audit(
        action=AuditLog.Action.CREDIT_LIMIT_CHANGE,
        entity_type="customer",
        entity_id=customer.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"credit_limit_amount": to_money(previous)},
        after_state={"credit_limit_amount": amount},
    )
    return customer


@transaction.atomic
def deactivate_customer(*, actor: Any, customer: Customer) -> Customer:
    """Deactivate, never delete. History must survive (FR-CUS-008/009, D-03)."""
    require_roles(actor, Role.OWNER)
    customer.is_active = False
    customer.save(update_fields=["is_active", "updated_at"])
    record_audit(
        action=AuditLog.Action.DEACTIVATE,
        entity_type="customer",
        entity_id=customer.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )
    return customer


def get_customer_for(actor: Any, customer_id: int) -> Customer:
    """Fetch a customer within the caller's scope.

    A retailer requesting another retailer's record receives ResourceNotFound, never
    PermissionDenied: a 403 would confirm the record exists (05 §4.1).
    """
    customer = Customer.objects.filter(pk=customer_id).first()
    if customer is None:
        raise ResourceNotFound("Customer not found.")
    if has_role(actor, Role.RETAILER) and not has_role(actor, *Role.INTERNAL):
        if getattr(actor, "customer_id", None) != customer.pk:
            raise ResourceNotFound("Customer not found.")
    return customer


def _customer_fields(fields: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "owner_name",
        "alt_phone",
        "gstin",
        "zone",
        "zone_id",
        "delivery_address",
        "credit_limit_amount",
        "credit_days",
        # **Documentation, not a balance** (`04` §591, `ledger.models`). Setting it creates
        # no ledger entry, so a customer record can read 4,500 while `receivables_position`
        # and every report derive 0. The balance that counts is an `OPENING` entry written
        # at go-live by ACT-E — `manage.py load_opening_balances`, which calls
        # `receivables.services.load_opening_balance`. Never assign one here.
        "opening_balance_amount",
        "latitude",
        "longitude",
        "is_active",
        "shop_name",
        "phone",
        "billing_address",
    }
    return {k: v for k, v in fields.items() if k in allowed}
