"""Canonical representation of money, quantity and percentage.

04 §1.6 fixes the column scales; 05 AD-02 fixes the string form on the wire
("12450.00", "24.000"); NFR-INT-006 requires the rounding rule to be defined once and
applied consistently. The audit trail is bound by the same rule: FR-AUD-005 requires a
transaction to be reconstructible from audit records, and a record that says "0" cannot
be diffed against a document that says "0.00".

Regression suite for the M1 defect: MoneyField(default=0) put an *int* on a freshly
created instance, so an audit written before the row was reloaded recorded "0".
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from catalogue.models import Product
from catalogue.services import set_price
from core.fields import to_money, to_percent, to_quantity
from core.models import AuditLog
from core.services import record_audit
from customers.models import Customer
from customers.services import set_credit_limit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, "0.00"),
        ("0", "0.00"),
        (Decimal("0"), "0.00"),
        (Decimal("2500"), "2500.00"),
        (100, "100.00"),
        ("12450", "12450.00"),
    ],
)
def test_money_is_always_scale_two(raw, expected):
    assert str(to_money(raw)) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2500.005", "2500.01"), ("2500.004", "2500.00"), ("0.005", "0.01"), ("-0.005", "-0.01")],
)
def test_rounding_is_half_up(raw, expected):
    """OI-7: half-up at two decimal places. Defined once, in core.fields."""
    assert str(to_money(raw)) == expected


def test_quantity_and_percent_have_their_own_scales():
    assert str(to_quantity(24)) == "24.000"
    assert str(to_percent(18)) == "18.00"


def test_money_never_constructed_from_a_float_binary_value():
    """N-07: Decimal(0.1) would import the float's error. Decimal(str(0.1)) does not."""
    assert str(to_money(0.1)) == "0.10"
    assert str(to_money(2.675)) == "2.68"


@pytest.mark.django_db
def test_unsaved_instance_already_holds_canonical_money():
    """The defect: an int default meant str() gave "0" until the row was reloaded."""
    assert str(Customer().credit_limit_amount) == "0.00"
    assert str(Customer().opening_balance_amount) == "0.00"
    assert str(Product().tax_rate_percent) == "0.00"


@pytest.mark.django_db
def test_audit_records_money_at_canonical_scale(owner, customer):
    set_credit_limit(actor=owner, customer=customer, amount=Decimal("2500"))
    entry = AuditLog.objects.get(action=AuditLog.Action.CREDIT_LIMIT_CHANGE)
    assert entry.before_state["credit_limit_amount"] == "0.00"
    assert entry.after_state["credit_limit_amount"] == "2500.00"


@pytest.mark.django_db
def test_audit_price_change_is_canonical(owner, product):
    set_price(actor=owner, product=product, price=Decimal("150"))
    entry = AuditLog.objects.get(action=AuditLog.Action.PRICE_CHANGE)
    assert entry.before_state["selling_price"] == "100.00"
    assert entry.after_state["selling_price"] == "150.00"


@pytest.mark.django_db
def test_audit_serialiser_never_emits_a_float(owner):
    """JSON has no decimal type; an unconverted Decimal would become a float."""
    entry = record_audit(
        action=AuditLog.Action.UPDATE,
        entity_type="customer",
        actor=owner,
        after_state={
            "amount": Decimal("1234.50"),
            "nested": {"qty": Decimal("24.000")},
            "listed": [Decimal("1.00")],
        },
    )
    entry.refresh_from_db()
    assert entry.after_state["amount"] == "1234.50"
    assert entry.after_state["nested"]["qty"] == "24.000"
    assert entry.after_state["listed"] == ["1.00"]
    assert not isinstance(entry.after_state["amount"], float)


@pytest.mark.django_db
def test_stored_and_audited_values_are_the_same_string(owner, customer):
    """FR-AUD-005: the audit must be reconcilable against the record it describes."""
    set_credit_limit(actor=owner, customer=customer, amount="7500.5")
    customer.refresh_from_db()
    entry = AuditLog.objects.get(action=AuditLog.Action.CREDIT_LIMIT_CHANGE)
    assert str(customer.credit_limit_amount) == entry.after_state["credit_limit_amount"]
    assert str(customer.credit_limit_amount) == "7500.50"
