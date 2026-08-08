"""The seven reports and the four dashboard numbers (M7 §8.2, D-4).

Every figure below traces to a selector another module owns. Where a figure needed a
business rule that no module had yet named — what a cancelled invoice means to a sale, what
"awaiting dispatch" means — **the rule went into the owning module**, not here (D-3).

**Anchoring.** R-1 makes *balance* selectors anchor on the dimension so a customer who owes
nothing still appears. These are **event** reports, and they anchor on the event: a product
nobody bought in August contributes nothing to August's sales, which is correct and is the
same distinction ``inventory.variance_by_reason`` and ``receivables.collections_by_user``
already draw. The one exception is the stock position report, which is a balance and
therefore anchors on ``Product`` — through ``inventory.stock_on_hand``, which already does.

**Periods are explicit.** Nothing here resolves "now" inside a query (M7 §1.2). A report
over a closed period returns the same answer on any later day (I-6), and that only holds if
the caller states the period.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from django.db.models import Count, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from billing import selectors as billing_selectors
from core.fields import MoneyField
from core.permissions import Role, require_roles
from inventory import selectors as inventory_selectors
from orders import selectors as order_selectors
from receivables import selectors as receivable_selectors
from reporting.tables import Column, Dashboard, Metric, ReportTable

ZERO_MONEY = Decimal("0.00")
ZERO_QUANTITY = Decimal("0.000")

#: Rendered on screen and written into every sales CSV (M7-1, §4.1.1). The definition of a
#: sale is irreversible because the figure is *remembered*; a report that does not state its
#: own definition turns that memory into folklore.
SALES_DEFINITION = (
    "Sales = invoice taxable value, excluding cancelled invoices, less credit note "
    "taxable value. GST and round-off are excluded, so this figure does not tie to the "
    "sum of invoice totals. A credit note reduces the period in which it was ISSUED, not "
    "the period of the invoice it credits."
)

#: D-2. Both stock reports and the returns report carry the matching half of this, because
#: the first question either one provokes is "why don't these agree?".
RETURNS_NOTE = (
    "This report is the FINANCIAL trace of a return: what was credited back. Goods that "
    "came back without a credit note appear in Stock Variance, not here."
)
VARIANCE_NOTE = (
    "This report is the PHYSICAL trace: what moved, in units. Money credited back appears "
    "in the Returns report, not here. The two are not expected to agree."
)
NO_VALUATION_NOTE = (
    "Quantities only. Stock cannot be valued until a cost basis exists (Edition 2); "
    "valuing at selling price would overstate working capital by the whole margin."
)
UNCATEGORISED = "Not categorised"

#: Accepted groupings for the sales report. `05` §9.11 named three; M7 §2 C-3 resolved that
#: salesman is buildable and FR-RPT-001 requires it, so it is offered as a fourth. Adding a
#: parameter value is additive to the frozen contract; removing one would not have been.
SALES_GROUPINGS = ("day", "customer", "product", "salesman")


# --------------------------------------------------------------------------- helpers
def _internal(actor: Any) -> None:
    """Cross-cutting reports are for the business, not for its customers.

    A retailer's own statement is theirs (M6, and M12's portal). A report that ranks
    customers or totals a zone is not, and scoping it to a single shop would produce a
    meaningless page rather than a refusal. Enforced here rather than in a view so it
    cannot be bypassed by reaching the selector through the other delivery layer (N-01).
    """
    require_roles(actor, *Role.INTERNAL)


def _start_of(day: date | None) -> datetime | None:
    if day is None:
        return None
    return timezone.make_aware(datetime.combine(day, time.min))


def _end_of(day: date | None) -> datetime | None:
    """The inclusive end of a business date, as an instant (M7-3).

    ``occurred_at`` is a timestamp and the report bound is a date. Filtering
    ``<= date_to`` against a timestamp would silently drop everything that happened after
    midnight on the last day of the period — an entire day, every time.
    """
    if day is None:
        return None
    return timezone.make_aware(datetime.combine(day, time.max))


def _money_sum(field: str) -> Any:
    return Coalesce(Sum(field), ZERO_MONEY, output_field=MoneyField())


def _within(queryset: QuerySet[Any], field: str, date_from: date | None, date_to: date | None):
    if date_from is not None:
        queryset = queryset.filter(**{f"{field}__gte": date_from})
    if date_to is not None:
        queryset = queryset.filter(**{f"{field}__lte": date_to})
    return queryset


def _sales_sources(
    actor: Any, *, date_from: date | None, date_to: date | None
) -> tuple[QuerySet[Any], QuerySet[Any]]:
    """The two halves of D-1, scoped and bounded once.

    Every sales-derived figure in M7 — the report, the top-customers ranking, the dashboard
    and I-7 — starts here. One place to be wrong is a defect; four would be a discrepancy.
    """
    invoices = _within(
        billing_selectors.issued_invoices(actor), "invoice_date", date_from, date_to
    )
    credit_notes = _within(
        billing_selectors.visible_credit_notes(actor), "credit_note_date", date_from, date_to
    )
    return invoices, credit_notes


def _merge(
    invoiced: dict[Any, dict[str, Any]], credited: dict[Any, Decimal]
) -> list[dict[str, Any]]:
    """Combine gross and credit halves, keeping keys that appear in only one.

    A period whose only activity was a credit note against an earlier invoice is a real
    period with negative sales. Dropping it because it has no invoice would hide exactly
    the month the owner most needs to see.
    """
    rows: list[dict[str, Any]] = []
    for key, row in invoiced.items():
        credited_amount = credited.pop(key, ZERO_MONEY)
        rows.append(
            {
                **row,
                "credited": credited_amount,
                "sales": row["invoiced"] - credited_amount,
            }
        )
    for key, credited_amount in credited.items():
        rows.append(
            {
                "key": key,
                "label": "",
                "invoiced": ZERO_MONEY,
                "credited": credited_amount,
                "sales": -credited_amount,
            }
        )
    return rows


# --------------------------------------------------------------------------- 1. sales
def sales_report(
    actor: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    group_by: str = "day",
) -> ReportTable:
    """FR-RPT-001. The D-1 figure, grouped four ways, totalling the same either way (I-1)."""
    _internal(actor)
    if group_by not in SALES_GROUPINGS:
        group_by = "day"
    invoices, credit_notes = _sales_sources(actor, date_from=date_from, date_to=date_to)

    if group_by == "product":
        rows = _sales_by_product(invoices, credit_notes)
        dimension = Column("label", "Product")
    elif group_by == "customer":
        rows = _sales_by_customer(invoices, credit_notes)
        dimension = Column("label", "Customer")
    elif group_by == "salesman":
        rows = _sales_by_salesman(invoices, credit_notes)
        dimension = Column("label", "Salesman")
    else:
        rows = _sales_by_day(invoices, credit_notes)
        dimension = Column("label", "Date")

    return ReportTable(
        key="sales",
        title="Sales",
        columns=(
            dimension,
            Column("invoiced", "Invoiced", numeric=True),
            Column("credited", "Credited", numeric=True),
            Column("sales", "Sales", numeric=True),
        ),
        rows=tuple(rows),
        definition=SALES_DEFINITION,
        total={
            "label": "Total",
            "invoiced": sum((r["invoiced"] for r in rows), ZERO_MONEY),
            "credited": sum((r["credited"] for r in rows), ZERO_MONEY),
            "sales": sum((r["sales"] for r in rows), ZERO_MONEY),
        },
        date_from=date_from,
        date_to=date_to,
        group_by=group_by,
    )


def _sales_by_day(invoices: QuerySet[Any], credit_notes: QuerySet[Any]) -> list[dict[str, Any]]:
    invoiced = {
        row["invoice_date"]: {
            "key": row["invoice_date"],
            "label": row["invoice_date"],
            "invoiced": row["invoiced"],
        }
        for row in invoices.values("invoice_date").annotate(invoiced=_money_sum("taxable_amount"))
    }
    credited = {
        row["credit_note_date"]: row["credited"]
        for row in credit_notes.values("credit_note_date").annotate(
            credited=_money_sum("taxable_amount")
        )
    }
    rows = _merge(invoiced, credited)
    for row in rows:
        row["label"] = row["key"]
    return sorted(rows, key=lambda r: r["key"])


def _sales_by_customer(
    invoices: QuerySet[Any], credit_notes: QuerySet[Any]
) -> list[dict[str, Any]]:
    invoiced = {
        row["customer_id"]: {
            "key": row["customer_id"],
            "label": f"{row['customer__code']} — {row['customer__shop_name']}",
            "invoiced": row["invoiced"],
        }
        for row in invoices.values(
            "customer_id", "customer__code", "customer__shop_name"
        ).annotate(invoiced=_money_sum("taxable_amount"))
    }
    labels = {
        row["customer_id"]: f"{row['customer__code']} — {row['customer__shop_name']}"
        for row in credit_notes.values("customer_id", "customer__code", "customer__shop_name")
    }
    credited = {
        row["customer_id"]: row["credited"]
        for row in credit_notes.values("customer_id").annotate(
            credited=_money_sum("taxable_amount")
        )
    }
    rows = _merge(invoiced, credited)
    for row in rows:
        if not row["label"]:
            row["label"] = labels.get(row["key"], "")
    return sorted(rows, key=lambda r: r["label"])


def _sales_by_salesman(
    invoices: QuerySet[Any], credit_notes: QuerySet[Any]
) -> list[dict[str, Any]]:
    """C-3: ``sales_order.assigned_user`` has existed since M3.

    An invoice with no order behind it — a direct counter sale — groups under "Unassigned"
    rather than vanishing, so the salesman column always totals to the same figure the
    other three groupings produce (I-1).
    """
    invoiced = {
        row["sales_order__assigned_user_id"]: {
            "key": row["sales_order__assigned_user_id"],
            "label": row["sales_order__assigned_user__full_name"] or "Unassigned",
            "invoiced": row["invoiced"],
        }
        for row in invoices.values(
            "sales_order__assigned_user_id", "sales_order__assigned_user__full_name"
        ).annotate(invoiced=_money_sum("taxable_amount"))
    }
    labels = {
        row["invoice__sales_order__assigned_user_id"]: (
            row["invoice__sales_order__assigned_user__full_name"] or "Unassigned"
        )
        for row in credit_notes.values(
            "invoice__sales_order__assigned_user_id",
            "invoice__sales_order__assigned_user__full_name",
        )
    }
    credited = {
        row["invoice__sales_order__assigned_user_id"]: row["credited"]
        for row in credit_notes.values("invoice__sales_order__assigned_user_id").annotate(
            credited=_money_sum("taxable_amount")
        )
    }
    rows = _merge(invoiced, credited)
    for row in rows:
        if not row["label"]:
            row["label"] = labels.get(row["key"], "Unassigned")
    return sorted(rows, key=lambda r: r["label"])


def _sales_by_product(
    invoices: QuerySet[Any], credit_notes: QuerySet[Any]
) -> list[dict[str, Any]]:
    """Line level, because a product dimension only exists on the lines.

    ``product_name`` is the snapshot the document carries, not the current master record
    (M5-2). Renaming a product must not rewrite last year's sales report.
    """
    invoiced = {
        row["lines__product_id"]: {
            "key": row["lines__product_id"],
            "label": row["lines__product_name"] or "",
            "invoiced": row["invoiced"],
        }
        for row in invoices.filter(lines__isnull=False)
        .values("lines__product_id", "lines__product_name")
        .annotate(invoiced=_money_sum("lines__taxable_amount"))
    }
    labels = {
        row["lines__product_id"]: row["lines__product_name"] or ""
        for row in credit_notes.filter(lines__isnull=False).values(
            "lines__product_id", "lines__product_name"
        )
    }
    credited = {
        row["lines__product_id"]: row["credited"]
        for row in credit_notes.filter(lines__isnull=False)
        .values("lines__product_id")
        .annotate(credited=_money_sum("lines__taxable_amount"))
    }
    rows = _merge(invoiced, credited)
    for row in rows:
        if not row["label"]:
            row["label"] = labels.get(row["key"], "")
    return sorted(rows, key=lambda r: r["label"])


# ------------------------------------------------------------------- 2. stock position
def stock_position(actor: Any, *, as_of: date | None = None) -> ReportTable:
    """FR-RPT-002, reduced by C-2 and C-7.

    On hand only — allocation is Edition 2, and a column that always reads zero teaches the
    owner to ignore it. **Quantity only** — no cost basis exists (C-7).
    """
    _internal(actor)
    products = inventory_selectors.stock_on_hand(as_of=_end_of(as_of))
    rows = tuple(
        {
            "code": product.code,
            "label": product.name,
            "unit": getattr(product, "unit_name", "") or "",
            "on_hand": product.on_hand,
        }
        for product in products
    )
    return ReportTable(
        key="stock-position",
        title="Stock position",
        columns=(
            Column("code", "Code"),
            Column("label", "Product"),
            Column("unit", "Unit"),
            Column("on_hand", "On hand", numeric=True),
        ),
        rows=rows,
        notes=(NO_VALUATION_NOTE,),
        total={
            "code": "",
            "label": "Total",
            "unit": "",
            "on_hand": sum((r["on_hand"] for r in rows), ZERO_QUANTITY),
        },
        as_of=as_of or date.today(),
    )


# ------------------------------------------------------------------- 3. stock variance
def stock_variance(
    actor: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    reason_code: str | None = None,
) -> ReportTable:
    """FR-RPT-003 — the physical trace (D-2), in units (C-7)."""
    _internal(actor)
    queryset = inventory_selectors.variance_by_reason(
        date_from=_start_of(date_from), date_to=_end_of(date_to)
    )
    rows = tuple(
        {
            "code": row["reason_code__code"],
            "label": row["reason_code__name"],
            "quantity": row["total_quantity"],
        }
        for row in queryset
        if reason_code is None or row["reason_code__code"] == reason_code
    )
    return ReportTable(
        key="stock-variance",
        title="Stock variance by reason",
        columns=(
            Column("code", "Reason"),
            Column("label", "Description"),
            Column("quantity", "Net quantity", numeric=True),
        ),
        rows=rows,
        notes=(VARIANCE_NOTE, NO_VALUATION_NOTE),
        total={
            "code": "",
            "label": "Total",
            "quantity": sum((r["quantity"] for r in rows), ZERO_QUANTITY),
        },
        date_from=date_from,
        date_to=date_to,
    )


# ------------------------------------------------------------------------- 4. returns
def returns_report(
    actor: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    group_by: str = "reason",
) -> ReportTable:
    """FR-RPT-010 — the financial trace (D-2).

    ``reason_code`` is **nullable**: it was optional at M5 because it drives no behaviour.
    Credits carrying none group under an explicit "Not categorised" row that is always
    rendered and never filtered out. A returns total that silently excluded them would be
    wrong in a direction the reader cannot see.
    """
    _internal(actor)
    _, credit_notes = _sales_sources(actor, date_from=date_from, date_to=date_to)

    if group_by == "customer":
        grouped = credit_notes.values("customer__code", "customer__shop_name").annotate(
            credited=_money_sum("taxable_amount"), documents=Count("id")
        )
        rows = tuple(
            {
                "label": f"{row['customer__code']} — {row['customer__shop_name']}",
                "documents": row["documents"],
                "credited": row["credited"],
            }
            for row in grouped.order_by("customer__shop_name")
        )
        dimension = Column("label", "Customer")
    else:
        group_by = "reason"
        grouped = credit_notes.values("reason_code__code", "reason_code__name").annotate(
            credited=_money_sum("taxable_amount"), documents=Count("id")
        )
        rows = tuple(
            {
                "label": (
                    f"{row['reason_code__code']} — {row['reason_code__name']}"
                    if row["reason_code__code"]
                    else UNCATEGORISED
                ),
                "documents": row["documents"],
                "credited": row["credited"],
            }
            for row in grouped.order_by("reason_code__code")
        )
        dimension = Column("label", "Reason")

    credited_total = sum((r["credited"] for r in rows), ZERO_MONEY)
    return ReportTable(
        key="returns",
        title="Returns — credit notes issued",
        columns=(
            dimension,
            Column("documents", "Credit notes", numeric=True),
            Column("credited", "Credited", numeric=True),
        ),
        rows=rows,
        definition=(
            "Credited = credit note taxable value, by the date the credit note was issued. "
            f"These credits reduced Sales for this period by {credited_total}."
        ),
        notes=(RETURNS_NOTE,),
        total={
            "label": "Total",
            "documents": sum((r["documents"] for r in rows), 0),
            "credited": credited_total,
        },
        date_from=date_from,
        date_to=date_to,
        group_by=group_by,
    )


# --------------------------------------------------------------------- 5. receivables
def receivables_ageing(actor: Any, *, as_of: date | None = None) -> ReportTable:
    """FR-RPT-004 / FR-REC-008. M6's walk and M6's buckets, arranged (M7-5).

    Nothing is recomputed. ``receivables_position`` performs the FIFO walk and
    ``OutstandingItem.bucket`` decides the bucket; this function sorts and totals.
    """
    _internal(actor)
    as_of = as_of or date.today()
    positions = receivable_selectors.receivables_position(actor, as_of=as_of)
    names = {
        customer.pk: customer
        for customer in receivable_selectors.visible_customers_for_receivables(actor)
    }
    positions.sort(key=lambda p: (p.oldest.age_days if p.oldest else -1), reverse=True)

    rows = []
    for position in positions:
        customer = names.get(position.customer_id)
        oldest = position.oldest
        rows.append(
            {
                "code": getattr(customer, "code", ""),
                "label": getattr(customer, "shop_name", ""),
                "outstanding": position.total_outstanding,
                "on_account": position.credit_on_account,
                "balance": position.balance,
                "oldest_days": oldest.age_days if oldest else 0,
                "bucket": oldest.bucket if oldest else "",
                "oldest_document": oldest.document if oldest else "",
            }
        )

    return ReportTable(
        key="receivables",
        title="Receivables ageing",
        columns=(
            Column("code", "Code"),
            Column("label", "Customer"),
            Column("outstanding", "Outstanding", numeric=True),
            Column("on_account", "On account", numeric=True),
            Column("balance", "Balance", numeric=True),
            Column("oldest_days", "Oldest (days)", numeric=True),
            Column("bucket", "Bucket"),
            Column("oldest_document", "Oldest document"),
        ),
        rows=tuple(rows),
        definition=(
            "Outstanding is derived by settling payments against the oldest unsettled "
            "debits first. Nothing here is stored; the same walk over the same immutable "
            "entries produces the same answer on any later day."
        ),
        total={
            "code": "",
            "label": "Total",
            "outstanding": sum((r["outstanding"] for r in rows), ZERO_MONEY),
            "on_account": sum((r["on_account"] for r in rows), ZERO_MONEY),
            "balance": sum((r["balance"] for r in rows), ZERO_MONEY),
            "oldest_days": "",
            "bucket": "",
            "oldest_document": "",
        },
        as_of=as_of,
    )


# ------------------------------------------------------------------- 6. top customers
def top_customers(
    actor: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 10,
) -> ReportTable:
    """`05` §9.11. Ranked on the D-1 figure, not on invoiced value.

    Ranking on gross would put a customer who returned half of what they bought above one
    who kept everything — the same reason D-1 nets credit notes in the first place.
    """
    _internal(actor)
    limit = max(1, min(limit, 100))
    rows = _sales_by_customer(*_sales_sources(actor, date_from=date_from, date_to=date_to))
    rows.sort(key=lambda r: r["sales"], reverse=True)
    ranked = tuple(
        {"rank": index, **row} for index, row in enumerate(rows[:limit], start=1)
    )
    return ReportTable(
        key="top-customers",
        title=f"Top {limit} customers",
        columns=(
            Column("rank", "#", numeric=True),
            Column("label", "Customer"),
            Column("invoiced", "Invoiced", numeric=True),
            Column("credited", "Credited", numeric=True),
            Column("sales", "Sales", numeric=True),
        ),
        rows=ranked,
        definition=SALES_DEFINITION,
        total={
            "rank": "",
            "label": f"Total (top {len(ranked)})",
            "invoiced": sum((r["invoiced"] for r in ranked), ZERO_MONEY),
            "credited": sum((r["credited"] for r in ranked), ZERO_MONEY),
            "sales": sum((r["sales"] for r in ranked), ZERO_MONEY),
        },
        date_from=date_from,
        date_to=date_to,
    )


# ------------------------------------------------------------------- 7. order pipeline
def order_pipeline(
    actor: Any, *, date_from: date | None = None, date_to: date | None = None
) -> ReportTable:
    """FR-RPT-008. Counts by state, including the exception states.

    Every visible order in the period appears in exactly one row (I-4), so the total is the
    number of orders — not a figure assembled from overlapping filters.
    """
    _internal(actor)
    queryset = _within(order_selectors.visible_orders(actor), "order_date", date_from, date_to)
    grouped = queryset.values("status").annotate(
        orders=Count("id"), value=_money_sum("total_amount")
    )
    rows = tuple(
        {"label": row["status"], "orders": row["orders"], "value": row["value"]}
        for row in grouped.order_by("status")
    )
    return ReportTable(
        key="order-status",
        title="Order pipeline",
        columns=(
            Column("label", "Status"),
            Column("orders", "Orders", numeric=True),
            Column("value", "Value", numeric=True),
        ),
        rows=rows,
        total={
            "label": "Total",
            "orders": sum((r["orders"] for r in rows), 0),
            "value": sum((r["value"] for r in rows), ZERO_MONEY),
        },
        date_from=date_from,
        date_to=date_to,
    )


# ---------------------------------------------------------------- 8. customer statement
def statement_table(customer: Any, *, date_from: date | None = None, date_to: date | None = None):
    """The sixth report, delivered at M6 — M7 adds CSV only (C-6, FR-RPT-012).

    Takes a ``Customer`` rather than an actor because the caller has already resolved and
    scoped it: this is reached per customer, through the same
    ``customers.services.get_customer_for`` gate the JSON statement uses. Re-deriving scope
    here would be a second authorisation path, and two authorisation paths is one too many.
    """
    statement = receivable_selectors.customer_statement(
        customer, date_from=date_from, date_to=date_to
    )
    rows = tuple(
        {
            "entry_date": entry.entry_date,
            "entry_type": entry.entry_type,
            "narration": entry.narration,
            "amount": entry.amount,
        }
        for entry in statement.entries
    )
    return ReportTable(
        key=f"statement-{getattr(customer, 'code', customer.pk)}",
        title=f"Statement of account — {getattr(customer, 'shop_name', '')}",
        columns=(
            Column("entry_date", "Date"),
            Column("entry_type", "Type"),
            Column("narration", "Narration"),
            Column("amount", "Amount", numeric=True),
        ),
        rows=rows,
        definition=(
            f"Opening balance {statement.opening_balance}. A positive amount increases "
            "what the customer owes; a negative amount reduces it."
        ),
        total={
            "entry_date": "",
            "entry_type": "",
            "narration": "Closing balance",
            "amount": statement.closing_balance,
        },
        date_from=statement.date_from,
        date_to=statement.date_to,
    )


# --------------------------------------------------------------------------- dashboard
def dashboard(actor: Any, *, today: date | None = None) -> Dashboard:
    """Four numbers, four different questions, no number a slice of another (D-4, M7-8).

    Sales and collections are separate because they are separate events — M5 split dispatch
    from invoicing and M6 split payment from invoice, and one merged "revenue" figure would
    undo both on the one screen the owner reads daily.

    Numbers 1 and 2 describe *today* and are therefore not reproducible. That is why this
    returns a ``Dashboard`` and not a ``ReportTable``: there is deliberately nothing here to
    export (M7 §8.2).
    """
    _internal(actor)
    today = today or date.today()

    invoices, credit_notes = _sales_sources(actor, date_from=today, date_to=today)
    invoiced = invoices.aggregate(total=_money_sum("taxable_amount"))["total"]
    credited = credit_notes.aggregate(total=_money_sum("taxable_amount"))["total"]

    collected = receivable_selectors.search_payments(
        actor, date_from=today, date_to=today, include_reversed=False
    ).aggregate(total=_money_sum("amount"))["total"]

    outstanding = sum(
        (p.total_outstanding for p in receivable_selectors.receivables_position(actor)),
        ZERO_MONEY,
    )

    return Dashboard(
        as_of=today,
        metrics=(
            Metric(
                key="sales_today",
                label="Sales today",
                value=invoiced - credited,
                caption="Taxable value, net of credit notes",
                is_live=True,
            ),
            Metric(
                key="collected_today",
                label="Collected today",
                value=collected,
                caption="Payments recorded today, excluding reversals",
                is_live=True,
            ),
            Metric(
                key="total_outstanding",
                label="Total outstanding",
                value=outstanding,
                caption="Derived from the ledger, oldest first",
            ),
            Metric(
                key="awaiting_dispatch",
                label="Orders awaiting dispatch",
                value=order_selectors.awaiting_dispatch(actor).count(),
                caption="Confirmed, not yet gone",
                is_money=False,
            ),
        ),
    )


__all__ = [
    "SALES_DEFINITION",
    "SALES_GROUPINGS",
    "UNCATEGORISED",
    "Column",
    "Dashboard",
    "Metric",
    "ReportTable",
    "dashboard",
    "order_pipeline",
    "receivables_ageing",
    "returns_report",
    "sales_report",
    "statement_table",
    "stock_position",
    "stock_variance",
    "top_customers",
]
