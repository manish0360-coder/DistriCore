"""Master-data endpoints (05 §9.2).

Views parse, delegate to a service, and shape the response. Authorisation is the
service's job (N-01, N-06): a view that checks a role is a rule in the wrong place.

Retailer scoping is derived from the token, never accepted as a parameter (AD-11).
"""

from __future__ import annotations

from typing import Any

from django.http import FileResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.master_serializers import (
    CustomerPatchSerializer,
    CustomerSerializer,
    CustomerWriteSerializer,
    MediaSerializer,
    MediaUploadSerializer,
    ProductPatchSerializer,
    ProductSerializer,
    ProductWriteSerializer,
    ReasonCodeSerializer,
    ZoneSerializer,
)
from api.v1.pagination import StandardPagination
from catalogue import selectors as product_selectors
from catalogue import services as product_services
from core import media as media_services
from core import selectors as core_selectors
from core.exceptions import ResourceNotFound
from core.permissions import Role, has_role
from customers import selectors as customer_selectors
from customers import services as customer_services
from inventory import selectors as reason_selectors


def _paginate(request: Request, queryset: Any, serializer_class: Any, view: Any) -> Response:
    paginator = StandardPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    return paginator.get_paginated_response(serializer_class(page, many=True).data)


# --------------------------------------------------------------------------- products
class ProductListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        is_active = _bool_param(request, "is_active")
        # Retailers see only sellable products (FR-PRD-014).
        if has_role(request.user, Role.RETAILER) and not has_role(request.user, *Role.INTERNAL):
            is_active = True
        queryset = product_selectors.search_products(
            term=request.query_params.get("search", ""), is_active=is_active
        )
        return _paginate(request, queryset.order_by("name"), ProductSerializer, self)

    def post(self, request: Request) -> Response:
        payload = ProductWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        product = product_services.create_product(
            actor=request.user,
            code=data.pop("code"),
            name=data.pop("name"),
            selling_price=data.pop("selling_price"),
            **data,
        )
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


class ProductDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        return Response(ProductSerializer(_get_product(request, pk)).data)

    def patch(self, request: Request, pk: int) -> Response:
        payload = ProductPatchSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        product = product_services.update_product(
            actor=request.user, product=_get_product(request, pk), **payload.validated_data
        )
        return Response(ProductSerializer(product).data)


def _get_product(request: Request, pk: int) -> Any:
    queryset = product_selectors.search_products()
    if has_role(request.user, Role.RETAILER) and not has_role(request.user, *Role.INTERNAL):
        queryset = queryset.filter(is_active=True)
    product = queryset.filter(pk=pk).first()
    if product is None:
        raise ResourceNotFound("Product not found.")
    return product


# --------------------------------------------------------------------------- customers
class CustomerListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        zone_id = request.query_params.get("zone_id")
        queryset = customer_selectors.search_customers(
            request.user,
            term=request.query_params.get("search", ""),
            zone_id=int(zone_id) if zone_id and zone_id.isdigit() else None,
            is_active=_bool_param(request, "is_active"),
        )
        return _paginate(request, queryset.order_by("shop_name"), CustomerSerializer, self)

    def post(self, request: Request) -> Response:
        payload = CustomerWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        data.pop("client_uuid", None)
        customer = customer_services.create_customer(
            actor=request.user,
            code=data.pop("code"),
            shop_name=data.pop("shop_name"),
            phone=data.pop("phone"),
            billing_address=data.pop("billing_address"),
            **data,
        )
        return Response(CustomerSerializer(customer).data, status=status.HTTP_201_CREATED)


class CustomerDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        customer = customer_services.get_customer_for(request.user, pk)
        return Response(CustomerSerializer(customer).data)

    def patch(self, request: Request, pk: int) -> Response:
        payload = CustomerPatchSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        data.pop("client_uuid", None)
        customer = customer_services.update_customer(
            actor=request.user,
            customer=customer_services.get_customer_for(request.user, pk),
            **data,
        )
        return Response(CustomerSerializer(customer).data)


# --------------------------------------------------------------------------- lookups
class ZoneListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = customer_selectors.active_zones().order_by("name")
        return _paginate(request, queryset, ZoneSerializer, self)


class ReasonCodeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        queryset = reason_selectors.active_reason_codes(
            direction=request.query_params.get("direction")
        ).order_by("code")
        return _paginate(request, queryset, ReasonCodeSerializer, self)


# --------------------------------------------------------------------------- media
class MediaUploadView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "media_upload"

    def post(self, request: Request) -> Response:
        payload = MediaUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        media = media_services.store_upload(
            actor=request.user,
            upload=payload.validated_data["file"],
            purpose=payload.validated_data["purpose"],
        )
        return Response(MediaSerializer(media).data, status=status.HTTP_201_CREATED)


class MediaDetailView(APIView):
    """Media is served ONLY through here.

    Never from the filesystem and never by a guessable public path: delivery and visit
    photographs are commercial evidence (NFR-SEC-006, 04 T-25).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Any:
        media = core_selectors.get_media(pk)
        if media is None:
            raise ResourceNotFound("File not found.")
        handle, content_type = media_services.open_media(media)
        response = FileResponse(handle, content_type=content_type)
        response["Cache-Control"] = "private, max-age=3600"
        return response


def _bool_param(request: Request, name: str) -> bool | None:
    raw = request.query_params.get(name)
    if raw is None:
        return None
    return raw.lower() in {"1", "true", "yes"}
