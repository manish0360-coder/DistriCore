"""Exact numeric field types (N-07, I-07).

Defined once so no model can accidentally use a float for money. Floating point is
forbidden in monetary and quantity paths; these are the only permitted types.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import models

# --------------------------------------------------------------------------------
# Rounding is defined ONCE, here, and applied consistently (NFR-INT-006, OI-7).
#
# The scales below are the database column scales from 04 §1.6, and they are also the
# canonical STRING form of these values everywhere they are written down: on the wire
# (05 AD-02: "12450.00", "24.000"), and in the audit trail.
#
# "0" and "0.00" are the same number and different strings. An audit that records them
# inconsistently cannot be diffed, and cannot be reconciled against the document it
# describes (FR-AUD-005). So the canonical form is fixed at the point a value enters
# the domain, not patched where it is displayed.
# --------------------------------------------------------------------------------

MONEY_SCALE = Decimal("0.01")  # NUMERIC(14,2)
QUANTITY_SCALE = Decimal("0.001")  # NUMERIC(14,3)
PERCENT_SCALE = Decimal("0.01")  # NUMERIC(5,2)


def _quantize(value: Any, scale: Decimal) -> Decimal:
    """Coerce to Decimal at a fixed scale, half-up.

    ``Decimal(str(value))`` rather than ``Decimal(value)``: constructing a Decimal from
    a float would import the float's error, which N-07 forbids.
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(scale, rounding=ROUND_HALF_UP)


def to_money(value: Any) -> Decimal:
    """Canonical money value: NUMERIC(14,2), half-up."""
    return _quantize(value, MONEY_SCALE)


def to_quantity(value: Any) -> Decimal:
    """Canonical quantity value: NUMERIC(14,3), half-up."""
    return _quantize(value, QUANTITY_SCALE)


def to_percent(value: Any) -> Decimal:
    """Canonical percentage value: NUMERIC(5,2), half-up."""
    return _quantize(value, PERCENT_SCALE)


class MoneyField(models.DecimalField):
    """NUMERIC(14,2). Ceiling ~ Rs 999 crore, far beyond the DR-8 envelope."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 14)
        kwargs.setdefault("decimal_places", 2)
        if "default" in kwargs and kwargs["default"] is not None:
            # MoneyField(default=0) put an int on a freshly created instance, so
            # str() produced "0" until the row was reloaded and became "0.00".
            kwargs["default"] = to_money(kwargs["default"])
        super().__init__(**kwargs)


class QuantityField(models.DecimalField):
    """NUMERIC(14,3). Fractional units (kg, litre) without a later schema change."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 14)
        kwargs.setdefault("decimal_places", 3)
        if "default" in kwargs and kwargs["default"] is not None:
            kwargs["default"] = to_quantity(kwargs["default"])
        super().__init__(**kwargs)


class PercentField(models.DecimalField):
    """NUMERIC(5,2). 0.00 - 999.99."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 5)
        kwargs.setdefault("decimal_places", 2)
        if "default" in kwargs and kwargs["default"] is not None:
            kwargs["default"] = to_percent(kwargs["default"])
        super().__init__(**kwargs)


class CoordinateField(models.DecimalField):
    """NUMERIC(9,6). ~0.1 m precision, exact — unlike float (04 §1.6)."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 9)
        kwargs.setdefault("decimal_places", 6)
        super().__init__(**kwargs)
