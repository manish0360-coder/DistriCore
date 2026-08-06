"""Fulfilment, billing and ledger endpoints (05 §9.4-9.6).

Views parse and delegate. Every rule — the credit re-check at dispatch, the GST split,
gapless numbering, the credit cap — lives in a service (N-01). Scope is derived from the
token, never accepted from a parameter (AD-11), and a scope violation returns 404 rather
than 403 so it cannot be used to probe for existence (05 §4.1).

State changes are **actions, not PATCHes of a status field** (AD-08). A client that could
PATCH `status` would hold the state machine.
"""

from __future__ import annotations

from typing import Any

from django.http import FileResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.billing_serializers import (
    CreditNoteCreateSerializer,
    CreditNoteSerializer,
    CustomerBalanceSerializer,
    DeliveryCompleteSerializer,
    DeliveryCreateSerializer,
    DeliveryFailSerializer,
    DeliverySerializer,
    DispatchSerializer,
    InvoiceCancelSerializer,
    InvoiceCreateSerializer,
    InvoiceSerializer,
    LedgerEntrySerializer,
)
from api.v1.pagination import StandardPagination
from billing import pdf as billing_pdf
from billing import selectors as billing_selectors
from billing import services as billing_services
from core import selectors as core_selectors
from core.exceptions import ResourceNotFound
from core.media import open_media
from customers import services as customer_services
from fulfilment import selectors as delivery_selectors
from fulfilment import services as delivery_services
from identity import selectors as identity_selectors
from inventory import selectors as inventory_selectors
from ledger import selectors as ledger_selectors
from orders import selectors as order_selectors


def _delivery(request: Request, pk: int) -> Any:
    found = delivery_selectors.get_delivery_for(request.user, pk)
    if found is None:
        raise ResourceNotFound("Delivery not found.")
    return found


def _invoice(request: Request, pk: int) -> Any:
    found = billing_selectors.get_invoice_for(request.user, pk)
    if found is None:
        raise ResourceNotFound("Invoice not found.")
    return found


def _order(request: Request, pk: int) -> Any:
    found = order_selectors.get_order_for(request.user, pk)
    if found is None:
        raise ResourceNotFound("Order not found.")
    return found


# --------------------------------------------------------------------------- delivery
class DeliveryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = delivery_selectors.search_deliveries(
            request.user,
            status=request.query_params.get("status") or None,
            assigned_to_me=request.query_params.get("assigned_to") == "me",
        )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(DeliverySerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        payload = DeliveryCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        assignee = identity_selectors.get_active_user(data["assigned_user_id"])
        if assignee is None:
            raise ResourceNotFound("That user does not exist.")
        delivery = delivery_services.assign_delivery(
            actor=request.user,
            order=_order(request, data["sales_order_id"]),
            assigned_user=assignee,
            client_uuid=data.get("client_uuid"),
        )
        return Response(DeliverySerializer(delivery).data, status=status.HTTP_201_CREATED)


class DeliveryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        return Response(DeliverySerializer(_delivery(request, pk)).data)


class DeliveryDispatchView(APIView):
    """Send the goods. **This is where stock leaves** (M5-1)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        payload = DispatchSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        delivery = delivery_services.dispatch_delivery(
            actor=request.user,
            delivery=_delivery(request, pk),
            override_reason=payload.validated_data.get("override_reason", ""),
        )
        return Response(DeliverySerializer(delivery).data)


class DeliveryCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        payload = DeliveryCompleteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        photo = None
        if data.get("photo_media_id"):
            photo = core_selectors.get_media(data["photo_media_id"])
            if photo is None:
                raise ResourceNotFound("That photo does not exist.")

        delivery = delivery_services.complete_delivery(
            actor=request.user,
            delivery=_delivery(request, pk),
            recipient_name=data.get("recipient_name", ""),
            delivered_at=data.get("delivered_at"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            photo_media=photo,
            device_id=data.get("device_id", ""),
        )
        return Response(DeliverySerializer(delivery).data)


class DeliveryFailView(APIView):
    """Record a failure. **Returns the stock** — it does not undo the issue (M5-9)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        payload = DeliveryFailSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        delivery = delivery_services.fail_delivery(
            actor=request.user,
            delivery=_delivery(request, pk),
            reason=payload.validated_data["reason"],
            device_id=payload.validated_data.get("device_id", ""),
        )
        return Response(DeliverySerializer(delivery).data)


# --------------------------------------------------------------------------- invoice
class InvoiceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        raw_customer = request.query_params.get("customer_id")
        queryset = billing_selectors.search_invoices(
            request.user,
            customer_id=int(raw_customer) if raw_customer and raw_customer.isdigit() else None,
            status=request.query_params.get("status") or None,
            financial_year=request.query_params.get("financial_year") or None,
        ).prefetch_related("lines")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(InvoiceSerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        payload = InvoiceCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        invoice = billing_services.issue_invoice(
            actor=request.user,
            order=_order(request, data["sales_order_id"]),
            invoice_date=data.get("invoice_date"),
            client_uuid=data.get("client_uuid"),
        )
        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


class InvoiceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        return Response(InvoiceSerializer(_invoice(request, pk)).data)


class InvoiceCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        payload = InvoiceCancelSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        invoice = billing_services.cancel_invoice(
            actor=request.user,
            invoice=_invoice(request, pk),
            reason=payload.validated_data["reason"],
        )
        return Response(InvoiceSerializer(invoice).data)


class InvoicePdfView(APIView):
    """Stream the PDF, rendering it on the first request and caching it (D-5)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Any:
        invoice = _invoice(request, pk)
        media = billing_pdf.invoice_pdf(actor=request.user, invoice=invoice)
        handle, content_type = open_media(media)
        response = FileResponse(
            handle,
            content_type=content_type,
            filename=f"{invoice.invoice_number.replace('/', '-')}.pdf",
        )
        # An invoice is commercial evidence, not a public asset (NFR-SEC-006).
        response["Cache-Control"] = "private, max-age=3600"
        return response


# --------------------------------------------------------------------------- credit note
class CreditNoteListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = billing_selectors.visible_credit_notes(request.user).prefetch_related("lines")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(CreditNoteSerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        payload = CreditNoteCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        invoice = _invoice(request, data["invoice_id"])

        lines = []
        for raw in data["lines"]:
            line = billing_selectors.get_invoice_line(invoice, raw["invoice_line_id"])
            if line is None:
                raise ResourceNotFound("That invoice line does not exist.")
            lines.append({"invoice_line": line, "quantity": raw.get("quantity") or line.quantity})

        reason_code = None
        if data.get("reason_code_id"):
            reason_code = inventory_selectors.get_active_reason_code(data["reason_code_id"])
            if reason_code is None:
                raise ResourceNotFound("That reason code does not exist.")

        note = billing_services.issue_credit_note(
            actor=request.user,
            invoice=invoice,
            lines=lines,
            reason=data["reason"],
            reason_code=reason_code,
            credit_note_date=data.get("credit_note_date"),
            client_uuid=data.get("client_uuid"),
        )
        return Response(CreditNoteSerializer(note).data, status=status.HTTP_201_CREATED)


# --------------------------------------------------------------------------- ledger
class CustomerLedgerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        customer = customer_services.get_customer_for(request.user, pk)
        queryset = ledger_selectors.statement_for(customer)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(LedgerEntrySerializer(page, many=True).data)


class CustomerBalanceView(APIView):
    """The two exposure terms, shown separately because they answer different questions."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        customer = customer_services.get_customer_for(request.user, pk)
        settled = order_selectors.settled_balance(customer)
        open_value = order_selectors.open_order_value(customer)
        return Response(
            CustomerBalanceSerializer(
                {
                    "customer_id": customer.pk,
                    "settled_balance": settled,
                    "open_order_value": open_value,
                    "credit_exposure": settled + open_value,
                    "credit_limit_amount": customer.credit_limit_amount,
                    "available_amount": order_selectors.available_credit(customer),
                }
            ).data
        )
