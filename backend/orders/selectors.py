"""Order read queries and credit exposure."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from core.fields import MoneyField
from core.permissions import Role, has_role
from customers.models import Customer
from orders.models import SalesOrder

ZERO_MONEY = Value(Decimal("0.00"), output_field=MoneyField())

# Orders that represent live commercial exposure: agreed but not yet billed.
OPEN_STATUSES = (SalesOrder.Status.PLACED, SalesOrder.Status.CONFIRMED)


def visible_orders(actor: Any) -> QuerySet[SalesOrder]:
    """Orders the caller may see (05 §8). Scope is derived, never accepted (AD-11)."""
    base = SalesOrder.objects.select_related("customer", "assigned_user")
    if has_role(actor, Role.OWNER):
        return base
    if has_role(actor, Role.SALESMAN, Role.DELIVERY):
        return base.filter(Q(assigned_user=actor) | Q(customer__zone__assigned_user=actor))
    if has_role(actor, Role.RETAILER):
        return base.filter(customer_id=getattr(actor, "customer_id", None) or 0)
    return base.none()


def open_order_value(customer: Customer) -> Decimal:
    """Value of this customer's orders that are agreed but not yet billed.

    R-1: anchored on ``Customer`` and coalesced to a typed zero, so a customer with no
    orders returns ``0.00`` rather than ``None``.
    """
    row = (
        Customer.objects.filter(pk=customer.pk)
        .annotate(
            exposure=Coalesce(
                Sum(
                    "orders__total_amount",
                    filter=Q(orders__status__in=OPEN_STATUSES),
                    output_field=MoneyField(),
                ),
                ZERO_MONEY,
            )
        )
        .values_list("exposure", flat=True)
        .first()
    )
    return row if row is not None else Decimal("0.00")


def settled_balance(customer: Customer) -> Decimal:
    """What the customer already owes from billed activity.

    **D-1, and the honest limitation of milestone order.** The receivables ledger arrives
    in M6; until then the only settled figure available is the opening balance loaded at
    go-live. Exposure therefore understates reality for any customer who has been billed
    — inherent to the sequence, not to this design.

    At M6 this function's *source* changes to ``SUM(customer_ledger_entry.amount)``. The
    formula in ``credit_exposure`` does not change, and double counting is impossible by
    construction: an invoiced order leaves ``open_order_value`` as it enters the ledger.
    """
    return Decimal(customer.opening_balance_amount)


def credit_exposure(customer: Customer) -> Decimal:
    """Total commercial exposure: settled debt plus agreed-but-unbilled orders (D-1)."""
    return settled_balance(customer) + open_order_value(customer)


def available_credit(customer: Customer) -> Decimal:
    """Headroom against the limit. May be negative — that is a signal, not an error."""
    return Decimal(customer.credit_limit_amount) - credit_exposure(customer)


def search_orders(
    actor: Any,
    *,
    status: str | None = None,
    customer_id: int | None = None,
    assigned_to_me: bool = False,
) -> QuerySet[SalesOrder]:
    queryset = visible_orders(actor)
    if status:
        queryset = queryset.filter(status=status)
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)
    if assigned_to_me:
        queryset = queryset.filter(assigned_user=actor)
    return queryset


def get_order_for(actor: Any, order_id: int) -> SalesOrder | None:
    """Scope violations look like absence, never like refusal (05 §4.1)."""
    return visible_orders(actor).filter(pk=order_id).first()
