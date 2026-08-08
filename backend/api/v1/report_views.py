"""Report endpoints (`05` §9.11, amended by M7 §2 C-6/C-7).

Seven reads, no writes, no locks. Every view does the same three things: parse the period,
call one selector, render the ``ReportTable`` it returned as JSON or CSV.

**`?format=csv` is a rendering, not a second query** (I-5). The CSV branch renders the same
object the JSON branch serialises, so the export and the screen cannot disagree — which
matters because the export is the artefact that leaves the building.

Scope is derived from the token and enforced inside the selectors (`reporting._internal`
plus the existing `visible_*` predicates), never here. A report is exactly the place a
scoping bug becomes an information leak with a CSV attached (FR-RPT-014, AR-5).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.renderers import CsvRenderer
from reporting import csv as report_csv
from reporting import selectors as report_selectors
from reporting.tables import ReportTable

#: Both renderers must be declared on any view that honours `?format=csv`. DRF negotiates
#: that parameter against this list and raises ``Http404`` when nothing matches — see
#: ``api.v1.renderers``.
REPORT_RENDERERS = [JSONRenderer, CsvRenderer]


def _parse_date(request: Request, name: str) -> date | None:
    """A malformed date is treated as absent, matching every other read endpoint.

    Refusing the request would be defensible, but `05` §4.1 already settled that a report
    with no period is a valid request; an unparseable one is the same request typed badly.
    """
    raw = request.query_params.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_int(request: Request, name: str, default: int) -> int:
    raw = request.query_params.get(name)
    if raw is None or not raw.lstrip("-").isdigit():
        return default
    return int(raw)


def _as_json(table: ReportTable) -> dict[str, Any]:
    return {
        "key": table.key,
        "title": table.title,
        "definition": table.definition,
        "notes": list(table.notes),
        "date_from": table.date_from,
        "date_to": table.date_to,
        "as_of": table.as_of,
        "group_by": table.group_by,
        "columns": [
            {"key": column.key, "label": column.label, "numeric": column.numeric}
            for column in table.columns
        ],
        "rows": [dict(row) for row in table.rows],
        "total": dict(table.total) if table.total else None,
    }


def csv_response(table: ReportTable) -> Response:
    """One CSV response shape, used by the reports and by the M6 statement.

    A DRF ``Response`` rather than a bare ``HttpResponse``: negotiation has already chosen
    ``CsvRenderer``, so letting the framework render keeps the declared renderer on the
    live path instead of leaving it as a formality that could rot.
    """
    response = Response(report_csv.render(table))
    # A quoted filename: report keys are ASCII, but the period is caller-influenced.
    response["Content-Disposition"] = f'attachment; filename="{report_csv.filename(table)}"'
    return response


def wants_csv(request: Request) -> bool:
    return (request.query_params.get("format") or "").lower() == "csv"


def _render(request: Request, table: ReportTable) -> Response:
    return csv_response(table) if wants_csv(request) else Response(_as_json(table))


class _ReportView(APIView):
    """One parse-and-render path, seven reports.

    Subclasses supply only ``build``. Repeating the format negotiation seven times is how
    one report ends up exporting something the others do not.
    """

    permission_classes = [IsAuthenticated]
    renderer_classes = REPORT_RENDERERS
    build: Callable[..., ReportTable]

    def parameters(self, request: Request) -> dict[str, Any]:
        return {
            "date_from": _parse_date(request, "date_from"),
            "date_to": _parse_date(request, "date_to"),
        }

    def get(self, request: Request) -> Response:
        table = type(self).build(request.user, **self.parameters(request))
        return _render(request, table)


class SalesReportView(_ReportView):
    build = staticmethod(report_selectors.sales_report)

    def parameters(self, request: Request) -> dict[str, Any]:
        return {
            **super().parameters(request),
            "group_by": request.query_params.get("group_by") or "day",
        }


class StockReportView(_ReportView):
    """On hand only (C-2), quantity only (C-7)."""

    build = staticmethod(report_selectors.stock_position)

    def parameters(self, request: Request) -> dict[str, Any]:
        return {"as_of": _parse_date(request, "as_of")}


class StockVarianceReportView(_ReportView):
    build = staticmethod(report_selectors.stock_variance)

    def parameters(self, request: Request) -> dict[str, Any]:
        return {
            **super().parameters(request),
            "reason_code": request.query_params.get("reason_code") or None,
        }


class ReturnsReportView(_ReportView):
    """The financial trace (D-2). Its total is the credit-note deduction inside sales."""

    build = staticmethod(report_selectors.returns_report)

    def parameters(self, request: Request) -> dict[str, Any]:
        return {
            **super().parameters(request),
            "group_by": request.query_params.get("group_by") or "reason",
        }


class ReceivablesReportView(_ReportView):
    build = staticmethod(report_selectors.receivables_ageing)

    def parameters(self, request: Request) -> dict[str, Any]:
        return {"as_of": _parse_date(request, "as_of")}


class TopCustomersReportView(_ReportView):
    build = staticmethod(report_selectors.top_customers)

    def parameters(self, request: Request) -> dict[str, Any]:
        return {**super().parameters(request), "limit": _parse_int(request, "limit", 10)}


class OrderStatusReportView(_ReportView):
    build = staticmethod(report_selectors.order_pipeline)
