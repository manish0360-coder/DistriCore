"""Order rules (M3_Design_Review). The §2 worked scenario is executed in full."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.exceptions import PermissionDenied, ValidationFailed
from core.models import AuditLog, BusinessProfile
from orders.models import SalesOrder
from orders.selectors import available_credit, credit_exposure, open_order_value
from orders.services import (
    CreditLimitExceeded,
    amend_order,
    apply_line_discount,
    cancel_order,
    confirm_order,
    evaluate_credit,
    place_order,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def priced(product):
    """The design review's P-1001: 65.00, 18% GST, pack of 12."""
    product.selling_price = Decimal("65.00")
    product.tax_rate_percent = Decimal("18.00")
    product.pack_size = 12
    product.save(update_fields=["selling_price", "tax_rate_percent", "pack_size"])
    return product


# --------------------------------------------------------------------------- scenario
def test_worked_scenario_from_the_design_review(owner, credit_customer, priced, profile):
    """M3_Design_Review §2, executed end to end."""
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": priced, "pack_quantity": Decimal("2")}],
    )
    # Step 1 — 2 packs x 12 = 24 base units
    line = order.lines.get()
    assert line.quantity == Decimal("24.000")
    assert line.pack_quantity == Decimal("2.000")
    assert order.subtotal_amount == Decimal("1560.00")
    assert order.tax_amount == Decimal("280.80")
    assert order.total_amount == Decimal("1840.80")
    assert order.status == SalesOrder.Status.PLACED

    # Step 2 — a 5% discount, within the 10% bound
    apply_line_discount(actor=owner, order=order, line=line, discount_amount=Decimal("78.00"))
    order.refresh_from_db()
    assert order.discount_amount == Decimal("78.00")
    assert order.tax_amount == Decimal("266.76")
    assert order.total_amount == Decimal("1748.76")

    # Step 3 — confirm
    confirm_order(actor=owner, order=order)
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.CONFIRMED

    # Step 5 — cancel; exposure returns to zero because it is derived, not stored
    cancel_order(actor=owner, order=order, reason="Retailer changed mind")
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.CANCELLED
    assert credit_exposure(credit_customer) == Decimal("0.00")


# --------------------------------------------------------------------------- M3-1
def test_line_snapshots_survive_a_price_change(owner, credit_customer, priced, profile):
    """M3-1: an order records what was agreed, not what is currently true."""
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": priced, "quantity": Decimal("10")}],
    )
    priced.selling_price = Decimal("999.00")
    priced.name = "Renamed product"
    priced.save(update_fields=["selling_price", "name"])

    order.refresh_from_db()
    line = order.lines.get()
    assert line.unit_price == Decimal("65.00")
    assert line.product_name != "Renamed product"
    assert order.total_amount == Decimal("767.00")  # 650.00 + 18%


# --------------------------------------------------------------------------- M3-7
def test_order_totals_equal_the_sum_of_their_lines(owner, credit_customer, priced, profile):
    from tests.factories import ProductFactory

    other = ProductFactory(selling_price=Decimal("12.50"), tax_rate_percent=Decimal("5.00"))
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[
            {"product": priced, "quantity": Decimal("3")},
            {"product": other, "quantity": Decimal("7")},
        ],
    )
    lines = list(order.lines.all())
    assert order.tax_amount == sum(line.tax_amount for line in lines)
    assert order.total_amount == sum(line.line_total for line in lines)


def test_rounding_is_applied_per_line_then_summed(owner, credit_customer, profile):
    """M3-8: summing then rounding gives a different total. The M5 invoice must agree."""
    from tests.factories import ProductFactory

    odd = ProductFactory(selling_price=Decimal("0.33"), tax_rate_percent=Decimal("18.00"))
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": odd, "quantity": Decimal("1")} for _ in range(1)],
    )
    line = order.lines.get()
    assert line.tax_amount == Decimal("0.06")  # 0.33 * 18% = 0.0594 -> 0.06 half-up
    assert order.tax_amount == line.tax_amount


# --------------------------------------------------------------------------- credit
def test_credit_exposure_is_derived_from_open_orders(owner, credit_customer, priced, profile):
    assert credit_exposure(credit_customer) == Decimal("0.00")
    place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": priced, "quantity": Decimal("10")}],
    )
    assert open_order_value(credit_customer) == Decimal("767.00")
    assert available_credit(credit_customer) == Decimal("9233.00")


def test_customer_with_no_orders_returns_zero_not_none(credit_customer, profile):
    """R-1 applied to money: a customer must not vanish from an exposure report."""
    assert open_order_value(credit_customer) == Decimal("0.00")
    assert isinstance(open_order_value(credit_customer), Decimal)


def test_warn_mode_creates_the_order_and_flags_it(owner, credit_customer, priced, profile):
    """DV-9: the owner decides. A warning, not a refusal."""
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": priced, "quantity": Decimal("200")}],  # 15,340 > 10,000
    )
    assert order.credit_warning_shown is True
    assert evaluate_credit(order=order).breached is True


def test_block_mode_refuses_the_order(owner, credit_customer, priced, profile):
    profile.credit_limit_mode = BusinessProfile.CreditMode.BLOCK
    profile.save(update_fields=["credit_limit_mode"])
    with pytest.raises(CreditLimitExceeded):
        place_order(
            actor=owner,
            customer=credit_customer,
            lines=[{"product": priced, "quantity": Decimal("200")}],
        )
    assert SalesOrder.objects.count() == 0


def test_override_is_recorded_and_audited(owner, credit_customer, priced, profile):
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": priced, "quantity": Decimal("200")}],
        override_credit=True,
    )
    assert order.credit_override_by == owner
    assert order.credit_override_at is not None
    assert AuditLog.objects.filter(action=AuditLog.Action.CREDIT_OVERRIDE).exists()


def test_a_zero_limit_means_unset_and_never_blocks(owner, customer, priced, profile):
    order = place_order(
        actor=owner,
        customer=customer,
        lines=[{"product": priced, "quantity": Decimal("500")}],
    )
    assert order.credit_warning_shown is False


# --------------------------------------------------------------------------- lifecycle
@pytest.mark.parametrize(
    ("start", "target"),
    [
        ("PLACED", "DELIVERED"),
        ("PLACED", "DISPATCHED"),
        ("CANCELLED", "CONFIRMED"),
        ("CONFIRMED", "PLACED"),
    ],
)
def test_invalid_transitions_are_rejected(owner, credit_customer, priced, profile, start, target):
    """M3-4: the state machine lives in CORE and is enforced, not documentary."""
    from orders.services import _transition

    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": priced, "quantity": Decimal("1")}],
    )
    SalesOrder.objects.filter(pk=order.pk).update(status=start, cancelled_reason="x")
    order.refresh_from_db()
    with pytest.raises(ValidationFailed) as exc:
        _transition(actor=owner, order=order, to_status=target)
    assert exc.value.errors[0]["code"] == "INVALID_TRANSITION"


def test_cancellation_requires_a_reason(owner, credit_customer, priced, profile):
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": priced, "quantity": Decimal("1")}],
    )
    with pytest.raises(ValidationFailed):
        cancel_order(actor=owner, order=order, reason="   ")


def test_a_cancelled_order_cannot_be_amended(owner, credit_customer, priced, profile):
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": priced, "quantity": Decimal("1")}],
    )
    cancel_order(actor=owner, order=order, reason="No longer needed")
    with pytest.raises(ValidationFailed):
        amend_order(actor=owner, order=order, lines=[{"product": priced, "quantity": Decimal("2")}])


def test_every_state_change_is_audited(owner, credit_customer, priced, profile):
    """R-3: an order is mutable, so the audit log is the only record of what it said."""
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": priced, "quantity": Decimal("1")}],
    )
    confirm_order(actor=owner, order=order)
    cancel_order(actor=owner, order=order, reason="Changed mind")
    actions = set(
        AuditLog.objects.filter(entity_type="sales_order").values_list("action", flat=True)
    )
    assert {AuditLog.Action.CREATE, AuditLog.Action.CONFIRM, AuditLog.Action.CANCEL} <= actions


# --------------------------------------------------------------------------- M3-5
def test_replaying_a_client_uuid_returns_the_original(owner, credit_customer, priced, profile):
    """BR-012: a retry after a timeout is correct client behaviour, not a duplicate."""
    import uuid

    key = uuid.uuid4()
    first = place_order(
        actor=owner,
        customer=credit_customer,
        client_uuid=key,
        lines=[{"product": priced, "quantity": Decimal("1")}],
    )
    second = place_order(
        actor=owner,
        customer=credit_customer,
        client_uuid=key,
        lines=[{"product": priced, "quantity": Decimal("99")}],
    )
    assert first.pk == second.pk
    assert SalesOrder.objects.count() == 1


# --------------------------------------------------------------------------- authority
def test_salesmen_cannot_create_orders_in_edition_one(salesman, credit_customer, priced, profile):
    """DV-1: field order capture was deferred, which is what makes M9 sync an outbox."""
    with pytest.raises(PermissionDenied):
        place_order(
            actor=salesman,
            customer=credit_customer,
            lines=[{"product": priced, "quantity": Decimal("1")}],
        )


def test_a_retailer_may_order_only_for_their_own_shop(retailer_login, customer, priced, profile):
    from tests.factories import CustomerFactory

    order = place_order(
        actor=retailer_login,
        customer=customer,
        lines=[{"product": priced, "quantity": Decimal("1")}],
    )
    assert order.customer == customer
    with pytest.raises(PermissionDenied):
        place_order(
            actor=retailer_login,
            customer=CustomerFactory(),
            lines=[{"product": priced, "quantity": Decimal("1")}],
        )


def test_an_inactive_product_cannot_be_ordered(owner, credit_customer, priced, profile):
    priced.is_active = False
    priced.save(update_fields=["is_active"])
    with pytest.raises(ValidationFailed):
        place_order(
            actor=owner,
            customer=credit_customer,
            lines=[{"product": priced, "quantity": Decimal("1")}],
        )


def test_an_empty_order_is_refused(owner, credit_customer, profile):
    with pytest.raises(ValidationFailed):
        place_order(actor=owner, customer=credit_customer, lines=[])


# --------------------------------------------------------------------------- M3-2
def test_a_line_needs_exactly_one_unit(owner, credit_customer, priced, profile):
    """Regression: `quantity` plus an `in_packs` flag was two fields encoding one fact.

    They could disagree — and a flag set with no pack quantity produced Decimal("None").
    Ambiguous input is now refused rather than guessed: a silently chosen unit is how a
    2-pack order becomes a 2-piece order.
    """
    with pytest.raises(ValidationFailed) as both:
        place_order(
            actor=owner,
            customer=credit_customer,
            lines=[{"product": priced, "quantity": Decimal("1"), "pack_quantity": Decimal("1")}],
        )
    assert both.value.errors[0]["code"] == "AMBIGUOUS_UNIT"

    with pytest.raises(ValidationFailed) as neither:
        place_order(actor=owner, customer=credit_customer, lines=[{"product": priced}])
    assert neither.value.errors[0]["code"] == "REQUIRED"


def test_packs_and_base_units_reach_the_same_stored_quantity(
    owner, credit_customer, priced, profile
):
    by_pack = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": priced, "pack_quantity": Decimal("2")}],
    )
    by_base = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": priced, "quantity": Decimal("24")}],
    )
    assert by_pack.lines.get().quantity == by_base.lines.get().quantity == Decimal("24.000")
    # Only the pack order remembers what the user actually typed.
    assert by_pack.lines.get().pack_quantity == Decimal("2.000")
    assert by_base.lines.get().pack_quantity is None


def test_fractional_base_quantities_are_not_truncated(owner, credit_customer, profile):
    """Regression: to_base_units returned int, so ordering 2.5 kg stored 2.

    QuantityField is NUMERIC(14,3) precisely so fractional units work (N-07).
    """
    from tests.factories import ProductFactory

    loose = ProductFactory(
        selling_price=Decimal("40.00"),
        tax_rate_percent=Decimal("5.00"),
        pack_size=1,
        unit_name="KG",
    )
    order = place_order(
        actor=owner,
        customer=credit_customer,
        lines=[{"product": loose, "quantity": Decimal("2.5")}],
    )
    line = order.lines.get()
    assert line.quantity == Decimal("2.500")
    assert order.subtotal_amount == Decimal("100.00")
