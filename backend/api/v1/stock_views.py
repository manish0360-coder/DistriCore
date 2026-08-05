"""Stock endpoints (05 §9.7).

Views parse, delegate to a service, and shape the response. Authorisation is the
service's job (N-01, N-06). No view writes a StockMovement — only inventory.services can.
"""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.pagination import StandardPagination
from api.v1.stock_serializers import (
    StockMovementSerializer,
    StockMovementWriteSerializer,
    StockOnHandSerializer,
)
from catalogue import selectors as product_selectors
from core.exceptions import ResourceNotFound
from inventory import selectors as stock_selectors
from inventory import services as stock_services


def _paginate(request: Request, queryset: Any, serializer: Any, view: Any) -> Response:
    paginator = StandardPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    return paginator.get_paginated_response(serializer(page, many=True).data)


class StockOnHandView(APIView):
    """Derived on-hand per product.

    Anchored on Product (R-1): a product with no movements returns 0.000, it does not
    disappear from the report.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = stock_selectors.stock_on_hand(
            include_inactive=request.query_params.get("include_inactive") == "true"
        )
        return _paginate(request, queryset, StockOnHandSerializer, self)


class StockMovementListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        product = None
        raw = request.query_params.get("product_id")
        if raw and raw.isdigit():
            product = product_selectors.search_products().filter(pk=int(raw)).first()
            if product is None:
                raise ResourceNotFound("Product not found.")
        reason_raw = request.query_params.get("reason_code_id")
        queryset = stock_selectors.movements_for(
            product,
            reason_code_id=int(reason_raw) if reason_raw and reason_raw.isdigit() else None,
            date_from=request.query_params.get("date_from") or None,
            date_to=request.query_params.get("date_to") or None,
        )
        return _paginate(request, queryset, StockMovementSerializer, self)

    def post(self, request: Request) -> Response:
        payload = StockMovementWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        product = product_selectors.search_products().filter(pk=data["product_id"]).first()
        if product is None:
            raise ResourceNotFound("Product not found.")
        reason = stock_selectors.get_active_reason_code(data["reason_code_id"])
        if reason is None:
            raise ResourceNotFound("Reason code not found.")

        quantity = data["quantity"]
        if data.get("in_packs"):
            quantity = product.to_base_units(quantity, in_packs=True)

        movement = stock_services.record_manual_movement(
            actor=request.user,
            product=product,
            quantity=quantity,
            movement_type=data["movement_type"],
            reason_code=reason,
            notes=data.get("notes", ""),
        )
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)
