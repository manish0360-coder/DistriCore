"""Unit tests for the M5 services: ledger, numbering, GST, fulfilment.

Scenario-level behaviour lives in the adversarial suite. These cover the rules each
service holds on its own, and the edge cases the scenarios do not reach.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from billing.models import Invoice, NumberSeries
from billing.services import _round_off, _split_tax, issue_invoice
from core.exceptions import PermissionDenied, ValidationFailed
from core.services import update_business_profile
from customers.selectors import state_code_for
from fulfilment.models import Delivery
from fulfilment.services import (
    assign_delivery,
    complete_delivery,
    dispatch_delivery,
    fail_delivery,
)
from inventory.selectors import on_hand_for
from inventory.services import receive_stock
from ledger.models import CustomerLedgerEntry
from ledger.selectors import settled_balance, statement_for
from ledger.services import record_entry
from orders.services import confirm_order, place_order


# --------------------------------------------------------------------------- pure
class TestTaxSplit:
    """M5-7. No database: these are arithmetic rules."""

    def test_intra_state_halves_into_cgst_and_sgst(self):
        split = _split_tax(tax_amount=Decimal("165.60"), intra_state=True)
        assert split["cgst_amount"] == Decimal("82.80")
        assert split["sgst_amount"] == Decimal("82.80")
        assert split["igst_amount"] == Decimal("0.00")

    def test_an_odd_paisa_still_sums_exactly(self):
        """``sgst = tax - cgst`` rather than a second halving.

        Halving 165.67 twice and rounding each would give 82.84 + 82.84 = 165.68, which
        would not reconcile against the line it came from.
        """
        split = _split_tax(tax_amount=Decimal("165.67"), intra_state=True)
        assert split["cgst_amount"] + split["sgst_amount"] == Decimal("165.67")

    def test_inter_state_is_a_single_igst(self):
        split = _split_tax(tax_amount=Decimal("165.67"), intra_state=False)
        assert split["igst_amount"] == Decimal("165.67")
        assert split["cgst_amount"] == split["sgst_amount"] == Decimal("0.00")

    @pytest.mark.parametrize("intra", [True, False])
    def test_the_split_is_never_mixed(self, intra):
        """Whatever the input, one side is always zero — matching ``ck_invoice_gst_split``."""
        split = _split_tax(tax_amount=Decimal("77.77"), intra_state=intra)
        assert split["igst_amount"] == 0 or (
            split["cgst_amount"] == 0 and split["sgst_amount"] == 0
        )


class TestRoundOff:
    """M5-11 — visible on the document and reproducible from it."""

    @pytest.mark.parametrize(
        ("raw", "expected_off", "expected_payable"),
        [
            ("1840.80", "0.20", "1841.00"),
            ("1840.20", "-0.20", "1840.00"),
            ("1840.50", "0.50", "1841.00"),
            ("1840.00", "0.00", "1840.00"),
        ],
    )
    def test_rounds_to_the_rupee(self, raw, expected_off, expected_payable):
        off, payable = _round_off(Decimal(raw))
        assert off == Decimal(expected_off)
        assert payable == Decimal(expected_payable)
        assert Decimal(raw) + off == payable, "the difference must reconcile"


# --------------------------------------------------------------------------- ledger
@pytest.mark.django_db
class TestLedgerService:
    def test_the_sign_must_agree_with_the_type(self, owner, credit_customer):
        """The service does not helpfully negate: a sign error means the caller has the
        accounting backwards, and silently correcting it hides that."""
        with pytest.raises(ValidationFailed, match="must be negative"):
            record_entry(
                actor=owner,
                customer=credit_customer,
                entry_type=CustomerLedgerEntry.Type.PAYMENT,
                amount=Decimal("500.00"),
                narration="wrong sign",
            )
        with pytest.raises(ValidationFailed, match="must be positive"):
            record_entry(
                actor=owner,
                customer=credit_customer,
                entry_type=CustomerLedgerEntry.Type.INVOICE,
                amount=Decimal("-500.00"),
                narration="wrong sign",
            )

    def test_adjustment_may_go_either_way(self, owner, credit_customer):
        record_entry(
            actor=owner,
            customer=credit_customer,
            entry_type=CustomerLedgerEntry.Type.ADJUSTMENT,
            amount=Decimal("-25.00"),
            narration="down",
        )
        record_entry(
            actor=owner,
            customer=credit_customer,
            entry_type=CustomerLedgerEntry.Type.ADJUSTMENT,
            amount=Decimal("25.00"),
            narration="up",
        )
        assert settled_balance(credit_customer) == Decimal("0.00")

    def test_a_zero_entry_is_refused(self, owner, credit_customer):
        with pytest.raises(ValidationFailed, match="cannot be zero"):
            record_entry(
                actor=owner,
                customer=credit_customer,
                entry_type=CustomerLedgerEntry.Type.ADJUSTMENT,
                amount=Decimal("0.00"),
                narration="nothing",
            )

    def test_an_unknown_type_is_refused(self, owner, credit_customer):
        with pytest.raises(ValidationFailed, match="Unknown ledger entry type"):
            record_entry(
                actor=owner,
                customer=credit_customer,
                entry_type="NOT_A_TYPE",
                amount=Decimal("1.00"),
                narration="x",
            )

    def test_an_unregistered_source_document_is_refused(self, owner, credit_customer):
        """R-2: the caller must possess a registered document, not merely name one."""
        with pytest.raises(ValidationFailed, match="not a permitted ledger source"):
            record_entry(
                actor=owner,
                customer=credit_customer,
                entry_type=CustomerLedgerEntry.Type.OPENING,
                amount=Decimal("100.00"),
                narration="x",
                source_document=credit_customer,
            )

    def test_an_unsaved_source_document_is_refused(self, owner, credit_customer):
        with pytest.raises(ValidationFailed, match="must be saved"):
            record_entry(
                actor=owner,
                customer=credit_customer,
                entry_type=CustomerLedgerEntry.Type.OPENING,
                amount=Decimal("100.00"),
                narration="x",
                source_document=Invoice(),
            )

    def test_an_opening_balance_is_the_truth_not_the_column(self, owner, credit_customer):
        """``customer.opening_balance_amount`` is documentation (04 T-22)."""
        record_entry(
            actor=owner,
            customer=credit_customer,
            entry_type=CustomerLedgerEntry.Type.OPENING,
            amount=Decimal("4500.00"),
            narration="Balance carried at go-live",
            entry_date=date(2026, 4, 1),
        )
        assert settled_balance(credit_customer) == Decimal("4500.00")

    def test_a_statement_reads_oldest_first(self, owner, credit_customer):
        for day, amount in ((1, "100.00"), (2, "-40.00"), (3, "25.00")):
            record_entry(
                actor=owner,
                customer=credit_customer,
                entry_type=CustomerLedgerEntry.Type.ADJUSTMENT,
                amount=Decimal(amount),
                narration=f"day {day}",
                entry_date=date(2026, 5, day),
            )
        entries = list(statement_for(credit_customer))
        assert [e.narration for e in entries] == ["day 1", "day 2", "day 3"]
        assert settled_balance(credit_customer) == Decimal("85.00")

    def test_a_balance_as_of_a_past_date_ignores_later_entries(self, owner, credit_customer):
        record_entry(
            actor=owner,
            customer=credit_customer,
            entry_type=CustomerLedgerEntry.Type.OPENING,
            amount=Decimal("100.00"),
            narration="opening",
            entry_date=date(2026, 5, 1),
        )
        record_entry(
            actor=owner,
            customer=credit_customer,
            entry_type=CustomerLedgerEntry.Type.PAYMENT,
            amount=Decimal("-60.00"),
            narration="paid",
            entry_date=date(2026, 6, 1),
        )
        assert settled_balance(credit_customer, as_of=date(2026, 5, 15)) == Decimal("100.00")
        assert settled_balance(credit_customer) == Decimal("40.00")


# --------------------------------------------------------------------------- state code
@pytest.mark.django_db
class TestBuyerStateResolution:
    """D-3. ``customers`` answers *which state*; ``billing`` decides the tax."""

    def test_an_explicit_code_wins(self, customer):
        customer.state_code = "27"
        customer.gstin = "10ABCDE1234F1Z5"
        assert state_code_for(customer) == "27"

    def test_otherwise_it_comes_from_the_gstin(self, customer):
        customer.gstin = "10ABCDE1234F1Z5"
        assert state_code_for(customer) == "10"

    def test_an_unregistered_buyer_has_no_knowable_state(self, customer):
        assert state_code_for(customer) == ""

    def test_a_malformed_gstin_is_not_guessed_at(self, customer):
        customer.gstin = "XXABCDE1234F1Z5"
        assert state_code_for(customer) == ""

    def test_billing_records_that_it_assumed(self, owner, customer, product, receipt_reason):
        """A wrong tax split is a legal defect, so the assumption is on the document."""
        update_business_profile(actor=owner, state_code="10", gstin="10AAAAA0000A1Z5")
        receive_stock(
            actor=owner, product=product, quantity=Decimal("100"), reason_code=receipt_reason
        )
        order = place_order(
            actor=owner, customer=customer, lines=[{"product": product, "quantity": "5"}]
        )
        confirm_order(actor=owner, order=order)
        dispatch_delivery(
            actor=owner,
            delivery=assign_delivery(actor=owner, order=order, assigned_user=owner),
        )
        invoice = issue_invoice(actor=owner, order=order)

        assert invoice.buyer_state_assumed is True
        assert invoice.buyer_state_code == "10"
        assert invoice.igst_amount == Decimal("0.00"), "assumed intra-state"
        assert invoice.cgst_amount > 0

    def test_an_out_of_state_buyer_gets_igst(self, owner, customer, product, receipt_reason):
        update_business_profile(actor=owner, state_code="10", gstin="10AAAAA0000A1Z5")
        customer.gstin = "27BBBBB1111B1Z5"
        customer.save(update_fields=["gstin"])
        receive_stock(
            actor=owner, product=product, quantity=Decimal("100"), reason_code=receipt_reason
        )
        order = place_order(
            actor=owner, customer=customer, lines=[{"product": product, "quantity": "5"}]
        )
        confirm_order(actor=owner, order=order)
        dispatch_delivery(
            actor=owner,
            delivery=assign_delivery(actor=owner, order=order, assigned_user=owner),
        )
        invoice = issue_invoice(actor=owner, order=order)

        assert invoice.buyer_state_assumed is False
        assert invoice.igst_amount > 0
        assert invoice.cgst_amount == invoice.sgst_amount == Decimal("0.00")


# --------------------------------------------------------------------------- fulfilment
@pytest.mark.django_db
class TestFulfilment:
    @pytest.fixture
    def order(self, owner, credit_customer, product, receipt_reason):
        receive_stock(
            actor=owner, product=product, quantity=Decimal("500"), reason_code=receipt_reason
        )
        placed = place_order(
            actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "10"}]
        )
        confirm_order(actor=owner, order=placed)
        return placed

    def test_only_a_confirmed_order_can_be_assigned(self, owner, credit_customer, product):
        placed = place_order(
            actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "1"}]
        )
        with pytest.raises(ValidationFailed, match="confirmed order"):
            assign_delivery(actor=owner, order=placed, assigned_user=owner)

    def test_assignment_is_idempotent_on_the_order(self, owner, order):
        first = assign_delivery(actor=owner, order=order, assigned_user=owner)
        second = assign_delivery(actor=owner, order=order, assigned_user=owner)
        assert first.pk == second.pk
        assert Delivery.objects.count() == 1

    def test_assignment_is_idempotent_on_the_client_uuid(self, owner, order):
        key = "11111111-1111-1111-1111-111111111111"
        first = assign_delivery(actor=owner, order=order, assigned_user=owner, client_uuid=key)
        second = assign_delivery(actor=owner, order=order, assigned_user=owner, client_uuid=key)
        assert first.pk == second.pk

    def test_a_retailer_cannot_be_assigned_a_delivery(self, owner, order, retailer):
        with pytest.raises(ValidationFailed, match="internal staff"):
            assign_delivery(actor=owner, order=order, assigned_user=retailer)

    def test_dispatch_is_idempotent(self, owner, order, product):
        """F-5: a retried dispatch must not issue the stock a second time."""
        delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
        dispatch_delivery(actor=owner, delivery=delivery)
        after_first = on_hand_for(product)
        dispatch_delivery(actor=owner, delivery=delivery)
        assert on_hand_for(product) == after_first

    def test_failing_twice_does_not_return_the_stock_twice(self, owner, order, product):
        """F-6 — the other half of the double-restock family."""
        delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
        dispatch_delivery(actor=owner, delivery=delivery)
        fail_delivery(actor=owner, delivery=delivery, reason="Shop shut")
        after_first = on_hand_for(product)
        fail_delivery(actor=owner, delivery=delivery, reason="Shop shut again")
        assert on_hand_for(product) == after_first

    def test_completing_twice_is_a_no_op(self, owner, order):
        delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
        dispatch_delivery(actor=owner, delivery=delivery)
        complete_delivery(actor=owner, delivery=delivery, recipient_name="First")
        again = complete_delivery(actor=owner, delivery=delivery, recipient_name="Second")
        assert again.recipient_name == "First"

    def test_an_undispatched_delivery_cannot_be_completed(self, owner, order):
        delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
        with pytest.raises(ValidationFailed, match="not been dispatched"):
            complete_delivery(actor=owner, delivery=delivery)

    def test_a_failure_needs_a_reason(self, owner, order):
        delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
        dispatch_delivery(actor=owner, delivery=delivery)
        with pytest.raises(ValidationFailed, match="needs a reason"):
            fail_delivery(actor=owner, delivery=delivery, reason="   ")

    def test_a_salesman_cannot_dispatch(self, owner, order, salesman):
        delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
        with pytest.raises(PermissionDenied):
            dispatch_delivery(actor=salesman, delivery=delivery)

    def test_a_retailer_cannot_record_an_outcome(self, owner, order, retailer):
        delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
        dispatch_delivery(actor=owner, delivery=delivery)
        with pytest.raises(PermissionDenied):
            complete_delivery(actor=retailer, delivery=delivery)
        with pytest.raises(PermissionDenied):
            fail_delivery(actor=retailer, delivery=delivery, reason="nope")


# --------------------------------------------------------------------------- billing
@pytest.mark.django_db
class TestInvoiceIssue:
    @pytest.fixture
    def dispatched_order(self, owner, credit_customer, product, receipt_reason):
        receive_stock(
            actor=owner, product=product, quantity=Decimal("500"), reason_code=receipt_reason
        )
        order = place_order(
            actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "10"}]
        )
        confirm_order(actor=owner, order=order)
        dispatch_delivery(
            actor=owner,
            delivery=assign_delivery(actor=owner, order=order, assigned_user=owner),
        )
        return order

    def test_an_undispatched_order_cannot_be_invoiced(self, owner, credit_customer, product):
        """B-2 — money is owed once the goods have gone, not before."""
        order = place_order(
            actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "1"}]
        )
        confirm_order(actor=owner, order=order)
        with pytest.raises(ValidationFailed, match="dispatched order"):
            issue_invoice(actor=owner, order=order)

    def test_a_stale_order_instance_does_not_change_the_answer(self, owner, dispatched_order):
        """**The M5 verification's root cause, pinned.**

        ``dispatch_delivery`` moves the order through its own locked instance, so every
        other Python reference to that order keeps whatever status it last loaded. An
        instance held from before dispatch still says ``CONFIRMED`` while the row says
        ``DISPATCHED``.

        ``issue_invoice`` must therefore read the row, not the argument. This test holds
        a deliberately stale instance and asserts the invoice is still issued — and the
        symmetric case matters more: a stale instance must never let a cancelled order
        be invoiced.
        """
        from orders.models import SalesOrder

        stale = SalesOrder.objects.get(pk=dispatched_order.pk)
        stale.status = SalesOrder.Status.CONFIRMED  # never saved; only this object lies

        invoice = issue_invoice(actor=owner, order=stale)
        assert invoice.pk is not None
        assert invoice.sales_order_id == dispatched_order.pk

    def test_a_stale_instance_cannot_invoice_a_cancelled_order(
        self, owner, credit_customer, product, receipt_reason
    ):
        """The dangerous direction of the same defect."""
        from orders.services import cancel_order

        receive_stock(
            actor=owner, product=product, quantity=Decimal("100"), reason_code=receipt_reason
        )
        order = place_order(
            actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "2"}]
        )
        confirm_order(actor=owner, order=order)
        cancel_order(actor=owner, order=order, reason="Retailer changed mind")

        order.status = "DISPATCHED"  # the lie a stale caller would be holding
        with pytest.raises(ValidationFailed, match="dispatched order"):
            issue_invoice(actor=owner, order=order)
        assert not Invoice.objects.exists()

    def test_one_invoice_per_order(self, owner, dispatched_order):
        first = issue_invoice(actor=owner, order=dispatched_order)
        second = issue_invoice(actor=owner, order=dispatched_order)
        assert first.pk == second.pk
        assert Invoice.objects.count() == 1

    def test_issue_is_idempotent_on_the_client_uuid(self, owner, dispatched_order):
        key = "22222222-2222-2222-2222-222222222222"
        first = issue_invoice(actor=owner, order=dispatched_order, client_uuid=key)
        second = issue_invoice(actor=owner, order=dispatched_order, client_uuid=key)
        assert first.pk == second.pk

    def test_only_the_owner_may_invoice(self, salesman, dispatched_order):
        with pytest.raises(PermissionDenied):
            issue_invoice(actor=salesman, order=dispatched_order)

    def test_the_invoice_agrees_with_the_order_to_the_paisa(self, owner, dispatched_order):
        """M3-8's line-level rounding exists so this holds."""
        invoice = issue_invoice(actor=owner, order=dispatched_order)
        assert (
            invoice.taxable_amount
            + invoice.cgst_amount
            + invoice.sgst_amount
            + (invoice.igst_amount)
            + invoice.round_off_amount
            == invoice.total_amount
        )
        raw = invoice.taxable_amount + invoice.cgst_amount + invoice.sgst_amount
        assert abs(raw - dispatched_order.total_amount) <= Decimal("0.01")

    def test_every_line_value_is_snapshotted(self, owner, dispatched_order, product):
        invoice = issue_invoice(actor=owner, order=dispatched_order)
        line = invoice.lines.first()
        order_line = dispatched_order.lines.first()
        assert line.product_code == order_line.product_code
        assert line.product_name == order_line.product_name
        assert line.unit_price == order_line.unit_price
        assert line.hsn_code == product.hsn_code
        assert line.quantity == order_line.quantity

    def test_the_seller_identity_is_snapshotted(self, owner, dispatched_order):
        update_business_profile(actor=owner, legal_name="Before Rename", state_code="10")
        invoice = issue_invoice(actor=owner, order=dispatched_order)
        update_business_profile(actor=owner, legal_name="After Rename")
        invoice.refresh_from_db()
        assert invoice.seller_legal_name == "Before Rename"

    def test_a_number_series_row_is_created_on_demand(self, owner, dispatched_order):
        """The first invoice of a new financial year must not require a deployment."""
        assert not NumberSeries.objects.exists()
        issue_invoice(actor=owner, order=dispatched_order)
        assert NumberSeries.objects.filter(series_key=NumberSeries.Key.INVOICE).exists()

    def test_an_inactive_series_refuses(self, owner, dispatched_order):
        from billing.services import allocate_number

        issue_invoice(actor=owner, order=dispatched_order)
        NumberSeries.objects.update(is_active=False)
        with pytest.raises(ValidationFailed, match="not active"):
            allocate_number(series_key=NumberSeries.Key.INVOICE, on=date(2026, 6, 1))

    def test_a_credit_note_needs_a_reason(self, owner, dispatched_order):
        from billing.services import issue_credit_note

        invoice = issue_invoice(actor=owner, order=dispatched_order)
        with pytest.raises(ValidationFailed, match="needs a reason"):
            issue_credit_note(
                actor=owner,
                invoice=invoice,
                lines=[{"invoice_line": invoice.lines.first(), "quantity": Decimal("1")}],
                reason="  ",
            )

    def test_a_credit_note_needs_lines(self, owner, dispatched_order):
        from billing.services import issue_credit_note

        invoice = issue_invoice(actor=owner, order=dispatched_order)
        with pytest.raises(ValidationFailed, match="at least one line"):
            issue_credit_note(actor=owner, invoice=invoice, lines=[], reason="Nothing")

    def test_a_credited_quantity_must_be_positive(self, owner, dispatched_order):
        from billing.services import issue_credit_note

        invoice = issue_invoice(actor=owner, order=dispatched_order)
        with pytest.raises(ValidationFailed, match="greater than zero"):
            issue_credit_note(
                actor=owner,
                invoice=invoice,
                lines=[{"invoice_line": invoice.lines.first(), "quantity": Decimal("0")}],
                reason="Zero",
            )

    def test_a_credit_note_is_idempotent_on_the_client_uuid(self, owner, dispatched_order):
        from billing.services import issue_credit_note

        invoice = issue_invoice(actor=owner, order=dispatched_order)
        key = "33333333-3333-3333-3333-333333333333"
        payload = {
            "actor": owner,
            "invoice": invoice,
            "lines": [{"invoice_line": invoice.lines.first(), "quantity": Decimal("1")}],
            "reason": "Short supply",
            "client_uuid": key,
        }
        assert issue_credit_note(**payload).pk == issue_credit_note(**payload).pk

    def test_a_cancellation_needs_a_reason(self, owner, dispatched_order):
        from billing.services import cancel_invoice

        invoice = issue_invoice(actor=owner, order=dispatched_order)
        with pytest.raises(ValidationFailed, match="needs a reason"):
            cancel_invoice(actor=owner, invoice=invoice, reason=" ")

    def test_cancelling_twice_is_a_no_op(self, owner, dispatched_order):
        from billing.services import cancel_invoice

        invoice = issue_invoice(actor=owner, order=dispatched_order)
        cancel_invoice(actor=owner, invoice=invoice, reason="Wrong customer")
        again = cancel_invoice(actor=owner, invoice=invoice, reason="Again")
        assert again.cancelled_reason == "Wrong customer"
