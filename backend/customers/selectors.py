"""Customer and zone read queries."""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from core.permissions import Role, has_role
from customers.models import Customer, Zone


def visible_customers(actor: Any) -> QuerySet[Customer]:
    """Customers the caller may see (05 §8).

    Scoping is derived from the actor, never from a request parameter (AD-11): the
    Flutter binary is public, so a parameter a client can send is one an attacker can
    change.
    """
    base = Customer.objects.select_related("zone")
    if has_role(actor, Role.OWNER):
        return base
    if has_role(actor, Role.SALESMAN, Role.DELIVERY):
        return base.filter(Q(zone__assigned_user=actor) | Q(zone__isnull=True))
    if has_role(actor, Role.RETAILER):
        return base.filter(pk=getattr(actor, "customer_id", None) or 0)
    return base.none()


def search_customers(
    actor: Any, *, term: str = "", zone_id: int | None = None, is_active: bool | None = None
) -> QuerySet[Customer]:
    qs = visible_customers(actor)
    if term:
        qs = qs.filter(
            Q(shop_name__icontains=term) | Q(code__icontains=term) | Q(phone__icontains=term)
        )
    if zone_id is not None:
        qs = qs.filter(zone_id=zone_id)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs


def active_zones() -> QuerySet[Zone]:
    return Zone.objects.filter(is_active=True).select_related("assigned_user")


def state_code_for(customer: Customer) -> str:
    """This customer's GST state code, or ``""`` when it is not knowable (D-3).

    Order of authority:

    1. ``state_code``, set explicitly by the owner;
    2. the first two characters of the GSTIN — an Indian GSTIN **encodes** the state
       there, so for a registered buyer the answer is already on file;
    3. unknown.

    This function answers *"which state is this customer in"* and nothing else. What to
    do when the answer is unknown is a tax decision, and tax decisions belong to
    ``billing`` — keeping the fallback out of here is what stops a master-data module
    quietly deciding a statutory question.
    """
    if customer.state_code:
        return customer.state_code
    gstin = (customer.gstin or "").strip()
    if len(gstin) >= 2 and gstin[:2].isdigit():
        return gstin[:2]
    return ""
