"""Owner report screens (M7 task 8).

One view function per report, each doing what the API views do: parse the period, call one
selector, render the ``ReportTable``. The screen and the export come from the same object,
so I-5 holds here for the same reason it holds in the API — there is only one query.

No model is imported (N-02) and no rule is evaluated (N-01). Authorisation lives in
``reporting.selectors._internal`` and the ``visible_*`` predicates beneath it, so reaching
these reports through the browser cannot see more than reaching them through the API.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from core.exceptions import PermissionDenied
from customers import selectors as customer_selectors
from reporting import csv as report_csv
from reporting import selectors as report_selectors
from reporting.tables import ReportTable

#: Rendered as the report menu. One place, so a new report cannot be added to the router
#: and forgotten by the navigation.
REPORT_MENU = (
    ("webadmin:report-sales", "Sales"),
    ("webadmin:report-stock", "Stock position"),
    ("webadmin:report-stock-variance", "Stock variance"),
    ("webadmin:report-returns", "Returns"),
    ("webadmin:report-receivables", "Receivables ageing"),
    ("webadmin:report-top-customers", "Top customers"),
    ("webadmin:report-order-status", "Order pipeline"),
)


def _parse_date(request: HttpRequest, name: str) -> date | None:
    raw = request.GET.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _respond(request: HttpRequest, table: ReportTable) -> HttpResponse:
    if request.GET.get("format") == "csv":
        response = HttpResponse(report_csv.render(table), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="{report_csv.filename(table)}"'
        )
        return response
    # Carry the current filters into the export link, minus any `format` already there —
    # otherwise clicking Export twice produces `format=csv&format=csv`.
    export_query = request.GET.copy()
    export_query.pop("format", None)
    export_query["format"] = "csv"

    return render(
        request,
        "webadmin/report.html",
        {
            "table": table,
            "export_query": export_query.urlencode(),
            "header_lines": report_csv.header_lines(table),
            "menu": REPORT_MENU,
            "date_from": request.GET.get("date_from", ""),
            "date_to": request.GET.get("date_to", ""),
            "as_of": request.GET.get("as_of", ""),
            "group_by": table.group_by,
            "groupings": (
                report_selectors.SALES_GROUPINGS if table.key == "sales" else ()
            ),
        },
    )


def _report(build: Callable[..., ReportTable], **parameters: Any):
    """Shared shape: build, or send an unauthorised caller back to the dashboard.

    ``_internal`` raises for a retailer. In the browser that is a redirect rather than an
    error page — the same "looks like absence" posture `05` §4.1 takes in the API.
    """

    def view(request: HttpRequest) -> HttpResponse:
        try:
            table = build(request.user, **{k: v(request) for k, v in parameters.items()})
        except PermissionDenied:
            return redirect("webadmin:dashboard")
        return _respond(request, table)

    return view


_period = {
    "date_from": lambda r: _parse_date(r, "date_from"),
    "date_to": lambda r: _parse_date(r, "date_to"),
}


@login_required
def sales(request: HttpRequest) -> HttpResponse:
    return _report(
        report_selectors.sales_report,
        **_period,
        group_by=lambda r: r.GET.get("group_by") or "day",
    )(request)


@login_required
def stock(request: HttpRequest) -> HttpResponse:
    return _report(report_selectors.stock_position, as_of=lambda r: _parse_date(r, "as_of"))(
        request
    )


@login_required
def stock_variance(request: HttpRequest) -> HttpResponse:
    return _report(
        report_selectors.stock_variance,
        **_period,
        reason_code=lambda r: r.GET.get("reason_code") or None,
    )(request)


@login_required
def returns(request: HttpRequest) -> HttpResponse:
    return _report(
        report_selectors.returns_report,
        **_period,
        group_by=lambda r: r.GET.get("group_by") or "reason",
    )(request)


@login_required
def receivables(request: HttpRequest) -> HttpResponse:
    return _report(report_selectors.receivables_ageing, as_of=lambda r: _parse_date(r, "as_of"))(
        request
    )


@login_required
def top_customers(request: HttpRequest) -> HttpResponse:
    return _report(report_selectors.top_customers, **_period)(request)


@login_required
def order_status(request: HttpRequest) -> HttpResponse:
    return _report(report_selectors.order_pipeline, **_period)(request)


@login_required
def customer_statement_csv(request: HttpRequest, pk: int) -> HttpResponse:
    """The sixth report's export (C-6). Scoped through the customer selector, not by role."""
    customer = customer_selectors.visible_customers(request.user).filter(pk=pk).first()
    if customer is None:
        return redirect("webadmin:customer-list")
    table = report_selectors.statement_table(
        customer,
        date_from=_parse_date(request, "date_from"),
        date_to=_parse_date(request, "date_to"),
    )
    response = HttpResponse(report_csv.render(table), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{report_csv.filename(table)}"'
    return response
