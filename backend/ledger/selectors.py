"""Ledger read queries.

**R-1 — aggregate selectors anchor on the DIMENSION, never on the fact table.**

R-1 was written during M2 with this module named as its next trap: *"a customer with no
ledger entries must show a zero balance, not vanish from the receivables report."* A
customer who owes nothing is the most common customer there is, and a receivables report
that silently omits them is read, believed, and acted on.

So every aggregate below starts from ``Customer`` and left-joins the ledger, coalescing
to a **typed** zero. A bare ``0`` returns an ``int`` and reintroduces the
canonical-representation defect fixed in M1 (`M1_Verification_Report` §4.3).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from core.fields import MoneyField
from customers.models import Customer
from ledger.models import CustomerLedgerEntry, SupplierLedgerEntry

ZERO_MONEY = Value(Decimal("0.00"), output_field=MoneyField())


def _balance_expression(*, as_of: date | None = None) -> Coalesce:
    """Sum of entries, left-joined from Customer, coalesced to a typed zero.

    ``filter=None`` is `Sum`'s own default, so passing it explicitly is the same
    aggregate. The kwargs dict it replaces was inferred as ``dict[str, MoneyField]`` from
    its first assignment, which made the later ``kwargs["filter"] = Q(...)`` a type error.
    Naming both arguments states the shape instead of assembling it.
    """
    entry_filter = Q(ledger_entries__entry_date__lte=as_of) if as_of is not None else None
    return Coalesce(
        Sum("ledger_entries__amount", filter=entry_filter, output_field=MoneyField()),
        ZERO_MONEY,
    )


def settled_balance(customer: Customer, *, as_of: date | None = None) -> Decimal:
    """What this customer owes from billed activity. Zero, never None."""
    row = (
        Customer.objects.filter(pk=customer.pk)
        .annotate(balance=_balance_expression(as_of=as_of))
        .values_list("balance", flat=True)
        .first()
    )
    return row if row is not None else Decimal("0.00")


def outstanding_balances(*, include_inactive: bool = False) -> QuerySet[Customer]:
    """Every customer with their derived balance (R-1).

    Customers with no entries appear with ``0.00`` rather than disappearing.
    """
    queryset = (
        Customer.objects.all() if include_inactive else Customer.objects.filter(is_active=True)
    )
    return queryset.annotate(balance=_balance_expression()).order_by("shop_name")


def statement_for(
    customer: Customer,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> QuerySet[CustomerLedgerEntry]:
    """The ledger itself, oldest first. This is what explains a balance."""
    queryset = CustomerLedgerEntry.objects.filter(customer=customer).select_related("created_by")
    if date_from is not None:
        queryset = queryset.filter(entry_date__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(entry_date__lte=date_to)
    return queryset.order_by("entry_date", "id")


def settled_order_ids(customer: Customer) -> QuerySet[CustomerLedgerEntry, int]:
    """Primary keys of this customer's orders that have reached the ledger (D-9).

    The exposure query uses this to subtract orders whose value has become settled debt,
    so the open and settled terms partition rather than overlap. Returning ids rather
    than a boolean per order keeps it one subquery instead of N.

    **The two type parameters are the model and the row.** A `values_list(flat=True)`
    still *queries* `CustomerLedgerEntry` — it only changes what each row is. The previous
    annotation said `QuerySet[int]`, which claimed the queryset was over a model called
    `int`; it stays a queryset so that `orders.selectors` can use it as one subquery
    rather than N.
    """
    return (
        CustomerLedgerEntry.objects.filter(
            customer=customer,
            sales_order__isnull=False,
            entry_type=CustomerLedgerEntry.Type.INVOICE,
        )
        .values_list("sales_order_id", flat=True)
        .distinct()
    )


# --------------------------------------------------------------------------------
# Payables (D5 Stage 3).
#
# **Why the supplier equivalents are split across two modules and the customer ones are
# not.** `customers` sits BELOW `ledger` in the layer contract, so this module may import
# `Customer` and anchor R-1 aggregates on it. `purchasing` sits ABOVE `ledger`, so
# importing `Supplier` here would invert the graph and import-linter would reject it.
#
# The scalar below therefore anchors on the fact table, which is safe for exactly the
# reason R-1's trap does not apply: `aggregate()` has no row dimension to lose, so a
# supplier with no entries yields a coalesced `0.00` rather than vanishing. The *list*
# form does have that dimension, so it lives in `purchasing.selectors`, anchored on
# `Supplier`, where the import runs downhill.
# --------------------------------------------------------------------------------


def supplier_balance(supplier: Any, *, as_of: date | None = None) -> Decimal:
    """What we owe this supplier. Zero, never None.

    Positive means a liability outstanding (D-PUR-3). Derived on every read — there is no
    stored balance to fall out of step (N-03, E-01).
    """
    queryset = SupplierLedgerEntry.objects.filter(supplier=supplier)
    if as_of is not None:
        queryset = queryset.filter(entry_date__lte=as_of)
    return queryset.aggregate(
        balance=Coalesce(Sum("amount", output_field=MoneyField()), ZERO_MONEY)
    )["balance"]


def supplier_statement_for(
    supplier: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> QuerySet[SupplierLedgerEntry]:
    """The payables ledger itself, oldest first. This is what explains a balance."""
    queryset = SupplierLedgerEntry.objects.filter(supplier=supplier).select_related("created_by")
    if date_from is not None:
        queryset = queryset.filter(entry_date__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(entry_date__lte=date_to)
    return queryset.order_by("entry_date", "id")
