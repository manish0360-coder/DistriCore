"""Product read queries."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from catalogue.models import Product


def active_products() -> QuerySet[Product]:
    return Product.objects.filter(is_active=True).select_related("image_media")


def search_products(*, term: str = "", is_active: bool | None = None) -> QuerySet[Product]:
    qs = Product.objects.select_related("image_media")
    if term:
        qs = qs.filter(Q(name__icontains=term) | Q(code__icontains=term))
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs
