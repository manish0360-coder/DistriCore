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
from core.fields import to_money
from reporting import csv as report_csv
from reporting import selectors as report_selectors
from reporting.tables import Dashboard, ReportTable

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


def money_string(value: Any) -> str:
    """AD-02: money crosses the wire as a decimal string, never as a JSON number.

    ``COERCE_DECIMAL_TO_STRING`` is set, but it only reaches ``serializers.DecimalField``.
    A view that hand-builds its response dict bypasses serialisation entirely, and DRF's
    JSON encoder renders ``Decimal("1180.00")`` as ``1180.0`` — the exactness N-07 protects
    all the way from the column to the selector is then lost at the last hop, in the one
    place no database constraint can catch it.

    ``to_money`` before ``str`` so the scale is the canonical one: without it the same
    figure could reach a client as ``"1180"`` from an aggregate and ``"1180.00"`` from a
    column, and a client comparing two responses for equality would be wrong about both.
    """
    return str(to_money(value))


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


class SyncHealthReportView(_ReportView):
    """FR-RPT-009 / FR-SYN-015 — `05` §9.11.2.

    **Parameters are inherited and that is the whole security story.** The base returns
    `date_from` and `date_to` only, so a `?device_id=` on the query string is ignored: this
    report is fleet-wide by construction and has no per-device branch to escape into.
    `GET /sync/status` remains the device-scoped view, and its `device_id` comes from the JWT
    (D-M9.3-1), never from a request.
    """

    build = staticmethod(report_selectors.sync_health)


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


# -------------------------------------------------------------------------- dashboard
def _dashboard_json(board: Dashboard) -> dict[str, Any]:
    """Arrange the four metrics. Compute nothing.

    ``is_money`` decides the encoding, and the selector already decides ``is_money``. The
    count of orders awaiting dispatch stays a JSON number because it is a count — sending
    it as ``"3.00"`` would be over-applying AD-02 until it lies about the type.
    """
    return {
        "as_of": board.as_of,
        "metrics": [
            {
                "key": metric.key,
                "label": metric.label,
                "value": money_string(metric.value) if metric.is_money else metric.value,
                "caption": metric.caption,
                "is_live": metric.is_live,
                "is_money": metric.is_money,
            }
            for metric in board.metrics
        ],
    }


class DashboardView(APIView):
    """The four D-4 numbers over HTTP (M8 §3.4.1). Read-only, and not exportable.

    **Deliberately not a ``_ReportView``.** That base renders a ``ReportTable`` and honours
    ``?format=csv``; a dashboard has neither columns nor rows. Subclassing it would mean
    inheriting a shape in order to override both halves of it away.

    **The refusal of CSV is the renderer list, not a branch.** Declaring only
    ``JSONRenderer`` leaves DRF's format negotiation nothing to match ``?format=csv``
    against, so it raises ``Http404`` — the mechanism M7 discovered when every CSV route
    appeared to be missing. An ``if wants_csv: raise`` would be a rule someone can delete
    while adding a feature; an absent renderer cannot be deleted by accident.

    M7 §8.2 refused this endpoint on the grounds that two of the four numbers describe
    *today* and are therefore not reproducible. That objection is to a figure acquiring the
    authority of a **document**, which is an argument about export — so the export stays
    refused and the read is allowed. ``is_live`` travels with each metric to say which two.

    **No period parameter.** ``dashboard()`` accepts ``today`` so tests can pin the day;
    exposing it would make the live numbers reproducible for arbitrary past dates, which is
    precisely the authority M7 §8.2 withholds. ``/reports/sales`` already answers that
    question, over any period, with a CSV.
    """

    permission_classes = [IsAuthenticated]
    renderer_classes = [JSONRenderer]

    def get(self, request: Request) -> Response:
        return Response(_dashboard_json(report_selectors.dashboard(request.user)))
