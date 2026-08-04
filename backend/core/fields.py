"""Exact numeric field types (N-07, I-07).

Defined once so no model can accidentally use a float for money. Floating point is
forbidden in monetary and quantity paths; these are the only permitted types.
"""

from __future__ import annotations

from typing import Any

from django.db import models


class MoneyField(models.DecimalField):
    """NUMERIC(14,2). Ceiling ~ Rs 999 crore, far beyond the DR-8 envelope."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 14)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(**kwargs)


class QuantityField(models.DecimalField):
    """NUMERIC(14,3). Fractional units (kg, litre) without a later schema change."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 14)
        kwargs.setdefault("decimal_places", 3)
        super().__init__(**kwargs)


class PercentField(models.DecimalField):
    """NUMERIC(5,2). 0.00 - 999.99."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 5)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(**kwargs)


class CoordinateField(models.DecimalField):
    """NUMERIC(9,6). ~0.1 m precision, exact — unlike float (04 §1.6)."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 9)
        kwargs.setdefault("decimal_places", 6)
        super().__init__(**kwargs)
