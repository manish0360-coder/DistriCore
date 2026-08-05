"""Product business rules (N-01)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction

from catalogue.models import Product
from core.exceptions import ValidationFailed
from core.fields import to_money
from core.models import AuditLog
from core.permissions import Role, require_roles
from core.services import record_audit

_EDITABLE = {
    "name",
    "description",
    "hsn_code",
    "tax_rate_percent",
    "unit_name",
    "pack_size",
    "pack_name",
    "image_media",
    "image_media_id",
    "is_active",
}


@transaction.atomic
def create_product(
    *, actor: Any, code: str, name: str, selling_price: Decimal, **fields: Any
) -> Product:
    require_roles(actor, Role.OWNER)
    code = code.strip().upper()
    if Product.objects.filter(code=code).exists():
        raise ValidationFailed(
            "That product code is already in use.",
            errors=[{"field": "code", "code": "DUPLICATE", "message": code}],
        )
    _validate_price(selling_price)
    product = Product.objects.create(
        code=code,
        name=name.strip(),
        selling_price=to_money(selling_price),
        **{k: v for k, v in fields.items() if k in _EDITABLE},
    )
    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type="product",
        entity_id=product.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        after_state={"code": product.code, "selling_price": product.selling_price},
    )
    return product


@transaction.atomic
def update_product(*, actor: Any, product: Product, **fields: Any) -> Product:
    require_roles(actor, Role.OWNER)

    if "selling_price" in fields:
        set_price(actor=actor, product=product, price=fields.pop("selling_price"))

    if "pack_size" in fields and int(fields["pack_size"]) != product.pack_size:
        # Changing pack_size retrospectively would silently rewrite historical
        # quantities (FR-PRD-003). Enforced here because the database cannot see the
        # transactional history the rule depends on.
        if _has_history(product):
            raise ValidationFailed(
                "Pack size cannot change once the product has been transacted.",
                errors=[{"field": "pack_size", "code": "IMMUTABLE", "message": product.code}],
            )

    payload = {k: v for k, v in fields.items() if k in _EDITABLE}
    if payload:
        before = {k: getattr(product, k) for k in payload}
        for key, value in payload.items():
            setattr(product, key, value)
        product.save()
        record_audit(
            action=AuditLog.Action.UPDATE,
            entity_type="product",
            entity_id=product.pk,
            actor=actor,
            surface=AuditLog.Surface.WEB,
            before_state=before,
            after_state={k: getattr(product, k) for k in payload},
        )
    return product


@transaction.atomic
def set_price(*, actor: Any, product: Product, price: Decimal) -> Product:
    """Price changes get their own audit action — margin depends on them (PO-6)."""
    require_roles(actor, Role.OWNER)
    price = to_money(price)
    _validate_price(price)
    previous = product.selling_price
    if previous == price:
        return product
    product.selling_price = price
    product.save(update_fields=["selling_price", "updated_at"])
    record_audit(
        action=AuditLog.Action.PRICE_CHANGE,
        entity_type="product",
        entity_id=product.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"selling_price": to_money(previous)},
        after_state={"selling_price": price},
    )
    return product


@transaction.atomic
def deactivate_product(*, actor: Any, product: Product) -> Product:
    """Deactivate, never delete: history and reports must survive (FR-PRD-008/009)."""
    require_roles(actor, Role.OWNER)
    product.is_active = False
    product.save(update_fields=["is_active", "updated_at"])
    record_audit(
        action=AuditLog.Action.DEACTIVATE,
        entity_type="product",
        entity_id=product.pk,
        actor=actor,
        surface=AuditLog.Surface.WEB,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )
    return product


def _validate_price(price: Decimal) -> None:
    if Decimal(price) < 0:
        raise ValidationFailed(
            "A selling price cannot be negative.",
            errors=[{"field": "selling_price", "code": "MIN_VALUE", "message": str(price)}],
        )


def _has_history(product: Product) -> bool:
    """True once anything transactional references the product.

    M1 has no transactional tables, so this is False. M2 extends it to stock movements
    and M4 to order lines. The hook exists now so the rule has one home rather than
    being rediscovered in each milestone.
    """
    return False
