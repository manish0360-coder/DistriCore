"""Payment and statement endpoints (05 §9.6).

Views parse and delegate. Every rule — the sign, the idempotency, the reversal lock, the
FIFO walk — lives in a service (N-01). Scope is derived from the token (AD-11), and a
scope violation returns 404 rather than 403 (05 §4.1).

**`GET /customers/{id}/balance` gains `as_of` and `oldest_unpaid`.** No endpoint outside
`05` §9.6 is added: the full outstanding list is exposed through the owner screens and
through M7's `/reports/receivables`, which reads the same selector.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1 import report_views
from api.v1.pagination import StandardPagination
from api.v1.receivables_serializers import (
    OutstandingItemSerializer,
    PaymentCreatedSerializer,
    PaymentCreateSerializer,
    PaymentReverseSerializer,
    PaymentSerializer,
    StatementSerializer,
    WriteOffSerializer,
)
from core.exceptions import ResourceNotFound
from customers import services as customer_services
from orders import selectors as order_selectors
from receivables import selectors as receivable_selectors
from receivables import services as receivable_services
from reporting import selectors as report_selectors


def _parse_date(request: Request, name: str) -> date | None:
    raw = request.query_params.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _payment(request: Request, pk: int) -> Any:
    found = receivable_selectors.get_payment_for(request.user, pk)
    if found is None:
        raise ResourceNotFound("Payment not found.")
    return found


class PaymentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        raw_customer = request.query_params.get("customer_id")
        queryset = receivable_selectors.search_payments(
            request.user,
            customer_id=int(raw_customer) if raw_customer and raw_customer.isdigit() else None,
            method=request.query_params.get("method") or None,
            date_from=_parse_date(request, "date_from"),
            date_to=_parse_date(request, "date_to"),
        )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(PaymentSerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        payload = PaymentCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        customer = customer_services.get_customer_for(request.user, data["customer_id"])
        payment = receivable_services.record_payment(
            actor=request.user,
            customer=customer,
            amount=data["amount"],
            method=data["method"],
            payment_date=data.get("payment_date"),
            reference_number=data.get("reference_number", ""),
            notes=data.get("notes", ""),
            device_id=data.get("device_id", ""),
            client_uuid=data.get("client_uuid"),
        )
        body = PaymentSerializer(payment).data
        body["balance_after_amount"] = receivable_services.balance_after(customer)
        return Response(
            PaymentCreatedSerializer(body).data, status=status.HTTP_201_CREATED
        )


class PaymentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        return Response(PaymentSerializer(_payment(request, pk)).data)


class PaymentReverseView(APIView):
    """Owner only. A reversal is a compensating entry, never an edit (M6-3)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        payload = PaymentReverseSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        payment = receivable_services.reverse_payment(
            actor=request.user,
            payment=_payment(request, pk),
            reason=payload.validated_data["reason"],
        )
        return Response(PaymentSerializer(payment).data)


class WriteOffView(APIView):
    """Owner only, explicit amount, reason mandatory, audited (FR-REC-015)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        payload = WriteOffSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        customer = customer_services.get_customer_for(request.user, data["customer_id"])
        receivable_services.write_off(
            actor=request.user,
            customer=customer,
            amount=data["amount"],
            reason=data["reason"],
            entry_date=data.get("entry_date"),
        )
        return Response(
            {
                "customer_id": customer.pk,
                "balance_after_amount": receivable_services.balance_after(customer),
            },
            status=status.HTTP_201_CREATED,
        )


class CustomerStatementView(APIView):
    """Opening, entries, closing (05 §9.6), and CSV since M7 (C-6, FR-RPT-012).

    The statement is the sixth report. It was built at M6 because it is per-customer rather
    than cross-cutting; M7 adds the export through the same single CSV mechanism every
    other report uses, so its file looks like theirs.
    """

    permission_classes = [IsAuthenticated]
    # Without CsvRenderer here, DRF filters the renderer list to nothing on `?format=csv`
    # and raises Http404 before this view runs. See ``api.v1.renderers``.
    renderer_classes = report_views.REPORT_RENDERERS

    def get(self, request: Request, pk: int) -> Response:
        customer = customer_services.get_customer_for(request.user, pk)
        if report_views.wants_csv(request):
            return report_views.csv_response(
                report_selectors.statement_table(
                    customer,
                    date_from=_parse_date(request, "date_from"),
                    date_to=_parse_date(request, "date_to"),
                )
            )
        statement = receivable_selectors.customer_statement(
            customer,
            date_from=_parse_date(request, "date_from"),
            date_to=_parse_date(request, "date_to"),
        )
        return Response(
            StatementSerializer(
                {
                    "customer_id": statement.customer_id,
                    "date_from": statement.date_from,
                    "date_to": statement.date_to,
                    "opening_balance": statement.opening_balance,
                    "entries": [
                        {
                            "id": e.pk,
                            "entry_date": e.entry_date,
                            "entry_type": e.entry_type,
                            "amount": e.amount,
                            "narration": e.narration,
                        }
                        for e in statement.entries
                    ],
                    "closing_balance": statement.closing_balance,
                }
            ).data
        )


class CustomerOutstandingView(APIView):
    """The derived FIFO view for one customer (M6 §5A).

    Not a new endpoint: it is the `oldest unpaid` half of `05` §9.7's
    `/reports/receivables`, exposed per customer so the retailer portal (M12) and the
    owner screen read the same selector rather than each deriving their own.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        customer = customer_services.get_customer_for(request.user, pk)
        position = receivable_selectors.outstanding_for(
            customer, as_of=_parse_date(request, "as_of")
        )
        return Response(
            {
                "customer_id": position.customer_id,
                "as_of": position.as_of,
                "total_outstanding": position.total_outstanding,
                "credit_on_account": position.credit_on_account,
                "balance": position.balance,
                "credit_limit_amount": customer.credit_limit_amount,
                "available_amount": order_selectors.available_credit(customer),
                "outstanding": OutstandingItemSerializer(
                    position.outstanding, many=True
                ).data,
            }
        )
