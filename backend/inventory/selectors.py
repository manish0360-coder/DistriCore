"""Stock read queries.

**R-1 — aggregate selectors anchor on the DIMENSION, never on the fact table.**

Anchoring a stock query on ``StockMovement`` with a ``GROUP BY`` makes products with zero
movements disappear from the result set. A ``None`` is visibly wrong; a silently shorter
stock report is not — the owner reads it, believes it, and orders against it. So every
aggregate below starts from ``Product`` and left-joins the ledger.

``Coalesce`` targets a **typed** zero. A bare ``0`` returns an ``int`` and reintroduces
the canonical-representation defect fixed in M1 (`M1_Verification_Report` §4.3).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, TypedDict

from django.db.models import Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from catalogue.models import Product
from core.fields import QuantityField
from inventory.models import ReasonCode, StockMovement

if TYPE_CHECKING:
    # `stock_on_hand` returns products carrying an `on_hand` the database computed, which
    # exists on no model field. django-stubs ships `WithAnnotations` for exactly this: it
    # describes *this queryset's* rows without asserting anything about `Product`
    # elsewhere.
    #
    # A hand-rolled stub class declaring `Product.on_hand` was considered and rejected —
    # it would make the type system believe every Product has the attribute, including on
    # the many paths where it does not. A mechanism that appears to guarantee something it
    # does not is worse than none.
    from django_stubs_ext import WithAnnotations

    class _OnHand(TypedDict):
        on_hand: Decimal

    AnnotatedProduct = WithAnnotations[Product, _OnHand]
else:
    # Never evaluated under `from __future__ import annotations`, and `django_stubs_ext`
    # is a dev dependency that production does not install. The alias is bound anyway so
    # the module stays importable if anything ever resolves these hints at runtime.
    AnnotatedProduct = Product

ZERO = Value(Decimal("0.000"), output_field=QuantityField())


def _on_hand_expression(*, as_of: datetime | None = None) -> Coalesce:
    """Sum of movements, left-joined from Product, coalesced to a typed zero.

    ``filter=None`` is `Sum`'s own default, so passing it explicitly is the same
    aggregate — verified attribute by attribute against the previous form. The kwargs
    dict it replaces was inferred as ``dict[str, QuantityField]`` from its first
    assignment, which made the later ``kwargs["filter"] = Q(...)`` a type error. Naming
    both arguments states the shape instead of assembling it.
    """
    movement_filter = Q(movements__occurred_at__lte=as_of) if as_of is not None else None
    return Coalesce(
        Sum("movements__quantity", filter=movement_filter, output_field=QuantityField()),
        ZERO,
    )


def stock_on_hand(
    *, as_of: datetime | None = None, include_inactive: bool = False
) -> QuerySet[AnnotatedProduct]:
    """Every product with its derived on-hand quantity (FR-STK-002, R-1).

    ``as_of`` gives the balance at any past instant — something a stored quantity could
    never answer, because it only ever knows *now*.
    """
    queryset = Product.objects.all() if include_inactive else Product.objects.filter(is_active=True)
    return queryset.annotate(on_hand=_on_hand_expression(as_of=as_of)).order_by("name")


def on_hand_for(product: Product, *, as_of: datetime | None = None) -> Decimal:
    """On-hand quantity for one product. Zero, never None, when nothing has moved."""
    row = (
        Product.objects.filter(pk=product.pk)
        .annotate(on_hand=_on_hand_expression(as_of=as_of))
        .values_list("on_hand", flat=True)
        .first()
    )
    return row if row is not None else Decimal("0.000")


def movements_for(
    product: Product | None = None,
    *,
    reason_code_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> QuerySet[StockMovement]:
    """The ledger itself, newest first. This is what explains a balance."""
    queryset = StockMovement.objects.select_related(
        "product", "reason_code", "location", "lot", "created_by"
    )
    if product is not None:
        queryset = queryset.filter(product=product)
    if reason_code_id is not None:
        queryset = queryset.filter(reason_code_id=reason_code_id)
    if date_from is not None:
        queryset = queryset.filter(occurred_at__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(occurred_at__lte=date_to)
    return queryset.order_by("-occurred_at", "-id")


def variance_by_reason(
    *, date_from: datetime | None = None, date_to: datetime | None = None
) -> QuerySet[StockMovement, dict[str, Any]]:
    """Adjustments grouped by reason (FR-STK-025).

    Anchored on the movement deliberately: this reports on movements that *happened*, so
    a reason code with no movements correctly contributes nothing. R-1 governs balances,
    not event counts.

    **The two type parameters are the model and the row.** `values().annotate()` still
    queries `StockMovement`, but each row is a **dict**, not a movement. The previous
    annotation said `QuerySet[StockMovement]` — which claimed the rows were model
    instances — and that single false statement produced five type errors: one here and
    four in `reporting.selectors`, where the caller iterates the dicts this actually
    returns. Nothing about the query changed; only the description of it was wrong.
    """
    queryset = StockMovement.objects.filter(reason_code__isnull=False)
    if date_from is not None:
        queryset = queryset.filter(occurred_at__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(occurred_at__lte=date_to)
    return (
        queryset.values("reason_code__code", "reason_code__name")
        .annotate(total_quantity=Coalesce(Sum("quantity"), ZERO))
        .order_by("reason_code__code")
    )


def negative_stock() -> QuerySet[Product]:
    """Products whose derived balance is below zero.

    Not an error state (D-2, ADR-0006): it means paperwork lags physical reality. This
    selector is how the owner finds and reconciles it — which is why permitting negatives
    is safe, and blocking them would not be.
    """
    return stock_on_hand(include_inactive=True).filter(on_hand__lt=Decimal("0.000"))


def active_reason_codes(*, direction: str | None = None) -> QuerySet[ReasonCode]:
    queryset = ReasonCode.objects.filter(is_active=True)
    if direction:
        queryset = queryset.filter(direction__in=[direction, ReasonCode.Direction.BOTH])
    return queryset.order_by("code")


def get_active_reason_code(reason_code_id: int) -> ReasonCode | None:
    """Fetch a usable reason code. Exists so no delivery layer imports the model (N-02)."""
    return ReasonCode.objects.filter(pk=reason_code_id, is_active=True).first()
