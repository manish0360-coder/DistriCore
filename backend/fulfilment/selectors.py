"""Delivery read queries. Scope is derived from the actor, never accepted (AD-11)."""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from core.permissions import Role, has_role
from fulfilment.models import Delivery


def visible_deliveries(actor: Any) -> QuerySet[Delivery]:
    """Deliveries the caller may see (05 §8)."""
    base = Delivery.objects.select_related("sales_order", "sales_order__customer", "assigned_user")
    if has_role(actor, Role.OWNER):
        return base
    if has_role(actor, Role.SALESMAN, Role.DELIVERY):
        return base.filter(
            Q(assigned_user=actor) | Q(sales_order__customer__zone__assigned_user=actor)
        )
    if has_role(actor, Role.RETAILER):
        return base.filter(sales_order__customer_id=getattr(actor, "customer_id", None) or 0)
    return base.none()


def search_deliveries(
    actor: Any, *, status: str | None = None, assigned_to_me: bool = False
) -> QuerySet[Delivery]:
    queryset = visible_deliveries(actor)
    if status:
        queryset = queryset.filter(status=status)
    if assigned_to_me:
        queryset = queryset.filter(assigned_user=actor)
    return queryset


def get_delivery_for(actor: Any, delivery_id: int) -> Delivery | None:
    """Scope violations look like absence, never like refusal (05 §4.1)."""
    return visible_deliveries(actor).filter(pk=delivery_id).first()


def pending_deliveries(actor: Any) -> QuerySet[Delivery]:
    """The delivery run — dispatched and awaiting an outcome."""
    return visible_deliveries(actor).filter(
        status=Delivery.Status.PENDING, dispatched_at__isnull=False
    )
