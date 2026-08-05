"""Price resolution, discount bounds and line arithmetic (M3-8, D-2, FR-PRC-017)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.exceptions import ValidationFailed
from pricing.services import compute_line, max_discount_amount, resolve_price

pytestmark = pytest.mark.django_db


def test_price_resolves_to_the_product_price(product, profile):
    assert resolve_price(product=product) == Decimal("100.00")


def test_price_ignores_the_customer_in_edition_one(product, customer, profile):
    """D-2: customer is in the signature so callers cannot be tempted to apply their own
    customer logic. Edition 1 has one price list."""
    assert resolve_price(product=product, customer=customer) == resolve_price(product=product)


def test_line_arithmetic_matches_the_design_review(product, profile):
    """Design review §2 step 1: 24 x 65.00, 18% GST."""
    product.selling_price = Decimal("65.00")
    product.tax_rate_percent = Decimal("18.00")
    product.save(update_fields=["selling_price", "tax_rate_percent"])

    amounts = compute_line(product=product, quantity=Decimal("24"))
    assert amounts.gross_amount == Decimal("1560.00")
    assert amounts.taxable_amount == Decimal("1560.00")
    assert amounts.tax_amount == Decimal("280.80")
    assert amounts.line_total == Decimal("1840.80")


def test_discount_reduces_the_taxable_base(product, profile):
    """Design review §2 step 2: 5% discount of 78.00 on a 1560.00 line."""
    product.selling_price = Decimal("65.00")
    product.tax_rate_percent = Decimal("18.00")
    product.save(update_fields=["selling_price", "tax_rate_percent"])

    amounts = compute_line(
        product=product, quantity=Decimal("24"), discount_amount=Decimal("78.00")
    )
    assert amounts.taxable_amount == Decimal("1482.00")
    assert amounts.tax_amount == Decimal("266.76")
    assert amounts.line_total == Decimal("1748.76")


def test_discount_bound_comes_from_the_business_profile(product, profile):
    assert max_discount_amount(gross_amount=Decimal("1000.00")) == Decimal("100.00")
    profile.max_manual_discount_percent = Decimal("5.00")
    profile.save(update_fields=["max_manual_discount_percent"])
    assert max_discount_amount(gross_amount=Decimal("1000.00")) == Decimal("50.00")


def test_discount_above_the_bound_is_refused(product, profile):
    """FR-PRC-017: manual discounting is where margin leaks."""
    with pytest.raises(ValidationFailed) as exc:
        compute_line(
            product=product, quantity=Decimal("1"), discount_amount=Decimal("50.00")
        )  # 50% of a 100.00 line, bound is 10%
    assert exc.value.errors[0]["code"] == "ABOVE_LIMIT"


def test_negative_discount_is_refused(product, profile):
    with pytest.raises(ValidationFailed):
        compute_line(product=product, quantity=Decimal("1"), discount_amount=Decimal("-1"))


def test_every_amount_is_at_money_scale(product, profile):
    """M3-9: two decimal places, always — the M1 canonical-representation rule."""
    amounts = compute_line(product=product, quantity=Decimal("3"))
    for value in (
        amounts.unit_price,
        amounts.gross_amount,
        amounts.taxable_amount,
        amounts.tax_amount,
        amounts.line_total,
    ):
        assert str(value) == str(value.quantize(Decimal("0.01")))
