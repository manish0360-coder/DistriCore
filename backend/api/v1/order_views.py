"""Order endpoints (05 §9.3).

Views parse and delegate. Every rule — pricing, discount bounds, credit, transitions —
lives in `orders.services` (N-01). Retailer scope is derived from the token (AD-11).
"""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.order_serializers import (
    CreditStatusSerializer,
    OrderCancelSerializer,
    OrderSerializer,
    OrderWriteSerializer,
)
from api.v1.pagination import StandardPagination
from catalogue import selectors as product_selectors
from core.exceptions import ResourceNotFound
from core.permissions import Role, has_role
from customers import services as customer_services
from orders import selectors as order_selectors
from orders import services as order_services


def _resolve_customer(request: Request, customer_id: Any) -> Any:
    """AD-11: a retailer's customer comes from the token, never from the payload."""
    if has_role(request.user, Role.RETAILER) and not has_role(request.user, *Role.INTERNAL):
        own = getattr(request.user, "customer_id", None)
        if own is None:
            raise ResourceNotFound("This login is not linked to a shop.")
        return customer_services.get_customer_for(request.user, own)
    if not customer_id:
        raise ResourceNotFound("Customer not found.")
    return customer_services.get_customer_for(request.user, int(customer_id))


def _build_lines(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines = []
    for raw in payload:
        product = product_selectors.search_products().filter(pk=raw["product_id"]).first()
        if product is None:
            raise ResourceNotFound(f"Product {raw['product_id']} not found.")
        lines.append(
            {
                "product": product,
                "quantity": raw.get("quantity"),
                "pack_quantity": raw.get("pack_quantity"),
                "discount_amount": raw.get("discount_amount", 0),
            }
        )
    return lines


class OrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        raw_customer = request.query_params.get("customer_id")
        queryset = order_selectors.search_orders(
            request.user,
            status=request.query_params.get("status") or None,
            customer_id=int(raw_customer) if raw_customer and raw_customer.isdigit() else None,
            assigned_to_me=request.query_params.get("assigned_to") == "me",
        ).prefetch_related("lines")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(OrderSerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        payload = OrderWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        order = order_services.place_order(
            actor=request.user,
            customer=_resolve_customer(request, data.get("customer_id")),
            lines=_build_lines(data["lines"]),
            source=("PORTAL" if has_role(request.user, Role.RETAILER) else "WEB"),
            client_uuid=data.get("client_uuid"),
            expected_delivery_date=data.get("expected_delivery_date"),
            notes=data.get("notes", ""),
            override_credit=data.get("override_credit", False),
        )
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        return Response(OrderSerializer(_get(request, pk)).data)

    def patch(self, request: Request, pk: int) -> Response:
        payload = OrderWriteSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        order = order_services.amend_order(
            actor=request.user,
            order=_get(request, pk),
            lines=_build_lines(payload.validated_data["lines"]),
        )
        return Response(OrderSerializer(order).data)


class OrderConfirmView(APIView):
    """AD-08: a state change is an action, not a PATCH of `status` (M3-4)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        order = order_services.confirm_order(actor=request.user, order=_get(request, pk))
        return Response(OrderSerializer(order).data)


class OrderCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        payload = OrderCancelSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        order = order_services.cancel_order(
            actor=request.user, order=_get(request, pk), reason=payload.validated_data["reason"]
        )
        return Response(OrderSerializer(order).data)


class CustomerCreditView(APIView):
    """Exposure against the limit (D-1). Read-only."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        customer = customer_services.get_customer_for(request.user, pk)
        return Response(
            CreditStatusSerializer(
                {
                    "credit_limit_amount": customer.credit_limit_amount,
                    "exposure_amount": order_selectors.credit_exposure(customer),
                    "available_amount": order_selectors.available_credit(customer),
                    "breached": order_selectors.available_credit(customer) < 0,
                    "mode": "WARN",
                }
            ).data
        )


def _get(request: Request, pk: int) -> Any:
    order = order_selectors.get_order_for(request.user, pk)
    if order is None:
        raise ResourceNotFound("Order not found.")
    return order
