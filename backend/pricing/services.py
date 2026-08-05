"""Price resolution, discount bounds and line arithmetic.

**Every surface resolves a price through this module or PO-6 is unverifiable** (BR-001).
Edition 1 has one price list, so the computation is trivial; the value is that there is
exactly one function.

Rounding is half-up at two decimal places **applied at line level** (M3-8, OI-7). Summing
then rounding gives different totals from rounding then summing, and the M5 invoice must
agree with the M3 order to the paisa.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from core.exceptions import ValidationFailed
from core.fields import to_money, to_percent
from core.services import get_business_profile


@dataclass(frozen=True)
class LineAmounts:
    """The computed money for one order line. All values already at money scale."""

    unit_price: Decimal
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    tax_rate_percent: Decimal
    tax_amount: Decimal
    line_total: Decimal


def resolve_price(*, product: Any, customer: Any = None) -> Decimal:
    """The selling price for a product, for a customer, right now.

    ``customer`` is accepted and **ignored in Edition 1**: there is one price list
    (02A §13.2). It is in the signature because customer-specific pricing is the
    dimension Edition 2 adds (02A §7.5), and because a resolver that cannot see the
    customer invites callers to apply customer logic themselves — which is exactly the
    BR-001 failure this module exists to prevent (D-2).
    """
    return to_money(product.selling_price)


def max_discount_amount(*, gross_amount: Decimal) -> Decimal:
    """The largest manual discount permitted on a line of this value (FR-PRC-017)."""
    percent = to_percent(get_business_profile().max_manual_discount_percent)
    return to_money(to_money(gross_amount) * percent / Decimal("100"))


def compute_line(
    *,
    product: Any,
    quantity: Decimal,
    customer: Any = None,
    discount_amount: Decimal | int | str = 0,
) -> LineAmounts:
    """Resolve price and compute one line's money, rounding at line level (M3-8).

    Raises if the discount exceeds the bound in ``business_profile``.
    """
    unit_price = resolve_price(product=product, customer=customer)
    gross = to_money(unit_price * Decimal(quantity))

    discount = to_money(discount_amount)
    if discount < 0:
        raise ValidationFailed(
            "A discount cannot be negative.",
            errors=[{"field": "discount_amount", "code": "MIN_VALUE", "message": str(discount)}],
        )
    ceiling = max_discount_amount(gross_amount=gross)
    if discount > ceiling:
        raise ValidationFailed(
            f"Discount exceeds the maximum of {ceiling} for this line.",
            errors=[{"field": "discount_amount", "code": "ABOVE_LIMIT", "message": str(ceiling)}],
        )

    taxable = to_money(gross - discount)
    tax_rate = to_percent(product.tax_rate_percent)
    tax = to_money(taxable * tax_rate / Decimal("100"))

    return LineAmounts(
        unit_price=unit_price,
        gross_amount=gross,
        discount_amount=discount,
        taxable_amount=taxable,
        tax_rate_percent=tax_rate,
        tax_amount=tax,
        line_total=to_money(taxable + tax),
    )
