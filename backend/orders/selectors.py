"""Order read queries and credit exposure."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from core.fields import MoneyField
from core.permissions import Role, has_role
from customers.models import Customer
from ledger import selectors as ledger_selectors
from orders.models import SalesOrder

ZERO_MONEY = Value(Decimal("0.00"), output_field=MoneyField())

# D-9 — orders that are still alive commercially. NOT the same thing as "unbilled".
#
# M3 had this list as (PLACED, CONFIRMED) and that was correct only while no order could
# reach DISPATCHED. M5 makes DISPATCHED reachable, and a dispatched-but-uninvoiced order
# would then belong to NEITHER exposure term — the wrong status for the open term, no
# ledger entry for the settled term. It would vanish from exposure at the exact moment
# the distributor is most exposed: goods gone, nothing billed.
LIVE_STATUSES = (
    SalesOrder.Status.PLACED,
    SalesOrder.Status.CONFIRMED,
    SalesOrder.Status.DISPATCHED,
    SalesOrder.Status.DELIVERED,
)


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
    """Value of this customer's orders that are **agreed but not yet billed** (D-9).

    The predicate is ledger presence, not order status. An order leaves this term at the
    instant its invoice writes a ledger entry, and enters ``settled_balance`` in the same
    transaction — so the two terms **partition** rather than overlap, and double counting
    is impossible by construction rather than by careful status lists.

    R-1: anchored on ``Customer`` and coalesced to a typed zero, so a customer with no
    orders returns ``0.00`` rather than ``None``.
    """
    row = (
        Customer.objects.filter(pk=customer.pk)
        .annotate(
            exposure=Coalesce(
                Sum(
                    "orders__total_amount",
                    filter=(
                        Q(orders__status__in=LIVE_STATUSES)
                        & ~Q(orders__pk__in=ledger_selectors.settled_order_ids(customer))
                    ),
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

    **The ledger is the source** (D-2, ADR-0008). ``customer.opening_balance_amount``
    is documentation; the balance that counts is ``SUM(customer_ledger_entry.amount)``,
    and an ``OPENING`` entry loaded at go-live (ACT-E) is how a pre-existing debt enters
    it.

    M3's D-1 promised the formula in ``credit_exposure`` would not change when this
    term's source became the ledger. It has not.
    """
    return ledger_selectors.settled_balance(customer)


def credit_exposure(customer: Customer) -> Decimal:
    """Total commercial exposure: settled debt plus agreed-but-unbilled orders (D-1).

    The two terms are mutually exclusive (D-9): every live order contributes to exactly
    one of them, and an order moves between them atomically at invoice issue.
    """
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


def awaiting_dispatch(actor: Any) -> QuerySet[SalesOrder]:
    """Orders agreed but not yet gone — the fourth dashboard number (M7 D-4).

    ``CONFIRMED`` and no further: ``PLACED`` is not yet agreed, and ``DISPATCHED`` has
    already left. Which status means "waiting on the warehouse" is an *orders* fact, so it
    is named here rather than as a literal in a report (M7 D-3).
    """
    return visible_orders(actor).filter(status=SalesOrder.Status.CONFIRMED)
