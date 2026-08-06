"""The M5 owner screens, and the PDF path.

The PDF tests exercise D-5 end to end: rendered on first request, cached, and never
replaced. The database refuses replacement, so "never regenerated" is a fact rather than
a comment.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from billing.pdf import invoice_pdf, render_invoice_html
from billing.services import issue_credit_note, issue_invoice
from core.models import MediaFile
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.services import receive_stock
from orders.services import confirm_order, place_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def dispatched(owner, credit_customer, product, receipt_reason):
    receive_stock(
        actor=owner, product=product, quantity=Decimal("1000"), reason_code=receipt_reason
    )
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "10"}]
    )
    confirm_order(actor=owner, order=order)
    return dispatch_delivery(
        actor=owner, delivery=assign_delivery(actor=owner, order=order, assigned_user=owner)
    )


@pytest.fixture
def invoice(owner, dispatched):
    return issue_invoice(actor=owner, order=dispatched.sales_order)


@pytest.fixture
def signed_in(client, owner):
    client.force_login(owner)
    return client


@pytest.fixture(autouse=True)
def _media_root(settings, tmp_path):
    """Rendered PDFs land in a temporary directory, never the real media root."""
    settings.MEDIA_ROOT = tmp_path


# --------------------------------------------------------------------------- screens
def test_the_delivery_screen_lists_and_filters(signed_in, dispatched):
    response = signed_in.get(reverse("webadmin:delivery-list"))
    assert response.status_code == 200
    assert dispatched.sales_order.order_number in response.content.decode()

    filtered = signed_in.get(reverse("webadmin:delivery-list"), {"status": "FAILED"})
    assert filtered.status_code == 200


def test_the_invoice_screens_render(signed_in, invoice):
    listing = signed_in.get(reverse("webadmin:invoice-list"))
    assert invoice.invoice_number in listing.content.decode()

    detail = signed_in.get(reverse("webadmin:invoice-detail", args=[invoice.pk]))
    assert detail.status_code == 200
    assert "TAX INVOICE" in detail.content.decode()


def test_the_ledger_and_receivables_screens_render(signed_in, invoice, credit_customer):
    ledger = signed_in.get(reverse("webadmin:customer-ledger", args=[credit_customer.pk]))
    assert ledger.status_code == 200
    assert invoice.invoice_number in ledger.content.decode()

    receivables = signed_in.get(reverse("webadmin:receivables"))
    assert receivables.status_code == 200
    assert credit_customer.shop_name in receivables.content.decode()


def test_a_customer_who_owes_nothing_still_appears(signed_in, customer):
    """R-1 again: the receivables report must not silently shorten."""
    response = signed_in.get(reverse("webadmin:receivables"))
    assert customer.shop_name in response.content.decode()


def test_unknown_records_redirect_rather_than_error(signed_in):
    assert signed_in.get(reverse("webadmin:invoice-detail", args=[999999])).status_code == 302
    assert signed_in.get(reverse("webadmin:customer-ledger", args=[999999])).status_code == 302
    assert signed_in.get(reverse("webadmin:invoice-pdf", args=[999999])).status_code == 302


def test_the_screens_require_a_login(client, invoice, credit_customer):
    for url in (
        reverse("webadmin:delivery-list"),
        reverse("webadmin:invoice-list"),
        reverse("webadmin:receivables"),
        reverse("webadmin:customer-ledger", args=[credit_customer.pk]),
    ):
        assert client.get(url).status_code == 302


def test_the_owner_can_drive_the_whole_flow_from_the_screens(
    signed_in, owner, credit_customer, product, receipt_reason
):
    receive_stock(actor=owner, product=product, quantity=Decimal("100"), reason_code=receipt_reason)
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "4"}]
    )
    confirm_order(actor=owner, order=order)

    signed_in.post(
        reverse("webadmin:delivery-assign", args=[order.pk]), {"assigned_user_id": owner.pk}
    )
    order.refresh_from_db()
    delivery = order.delivery

    signed_in.post(reverse("webadmin:delivery-dispatch", args=[delivery.pk]))
    order.refresh_from_db()
    assert order.status == "DISPATCHED"

    signed_in.post(reverse("webadmin:invoice-issue", args=[order.pk]))
    from billing.models import Invoice

    assert Invoice.objects.filter(sales_order=order).exists()

    signed_in.post(
        reverse("webadmin:delivery-complete", args=[delivery.pk]), {"recipient_name": "Shop owner"}
    )
    order.refresh_from_db()
    assert order.status == "DELIVERED"


def test_a_failed_dispatch_flashes_rather_than_crashing(signed_in, owner, credit_customer, product):
    """An unconfirmed order cannot be assigned; the screen must survive the refusal."""
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "1"}]
    )
    response = signed_in.post(
        reverse("webadmin:delivery-assign", args=[order.pk]), {"assigned_user_id": owner.pk}
    )
    assert response.status_code == 302


def test_recording_a_failure_from_the_screen(signed_in, dispatched):
    response = signed_in.post(
        reverse("webadmin:delivery-fail", args=[dispatched.pk]), {"reason": "Shop closed"}
    )
    assert response.status_code == 302
    dispatched.refresh_from_db()
    assert dispatched.status == "FAILED"


# --------------------------------------------------------------------------- D-5
def test_the_html_renders_from_the_document_alone(invoice, product, owner):
    """One template, two outputs — and neither joins to current master data."""
    from catalogue.services import update_product

    before = render_invoice_html(invoice)
    update_product(actor=owner, product=product, name="Renamed After Issue")
    after = render_invoice_html(invoice)
    assert before == after
    assert "Renamed After Issue" not in after


def test_the_pdf_is_rendered_once_and_cached(owner, invoice):
    assert invoice.pdf_media_id is None
    first = invoice_pdf(actor=owner, invoice=invoice)
    assert MediaFile.objects.filter(purpose=MediaFile.Purpose.INVOICE_PDF).count() == 1

    invoice.refresh_from_db()
    second = invoice_pdf(actor=owner, invoice=invoice)
    assert first.pk == second.pk
    assert MediaFile.objects.filter(purpose=MediaFile.Purpose.INVOICE_PDF).count() == 1, (
        "a second request must serve the stored rendering, not make another"
    )


def test_the_stored_pdf_can_never_be_replaced(owner, invoice):
    """D-5, enforced by the database: a PDF handed to a retailer must not change.

    ``pytest.raises`` is the outer context so the savepoint rolls back before the
    exception is swallowed; the other order leaves an aborted transaction behind.
    """
    from django.db import connection, transaction

    invoice_pdf(actor=owner, invoice=invoice)
    invoice.refresh_from_db()
    assert invoice.pdf_media_id is not None

    with (
        pytest.raises(Exception, match="never regenerated"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("UPDATE invoice SET pdf_media_id = NULL WHERE id = %s", [invoice.pk])


def test_the_pdf_streams_over_http(signed_in, invoice):
    response = signed_in.get(reverse("webadmin:invoice-pdf", args=[invoice.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


def test_the_pdf_streams_over_the_api(auth, owner, invoice):
    response = auth(owner).get(reverse("v1:invoice-pdf", args=[invoice.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


def test_a_cancelled_invoice_renders_with_its_reason(owner, invoice):
    from billing.services import cancel_invoice

    cancel_invoice(actor=owner, invoice=invoice, reason="Wrong customer")
    invoice.refresh_from_db()
    html = render_invoice_html(invoice)
    assert "CANCELLED" in html
    assert "Wrong customer" in html


def test_an_inter_state_invoice_shows_igst(owner, customer, product, receipt_reason):
    from core.services import update_business_profile

    update_business_profile(actor=owner, state_code="10", gstin="10AAAAA0000A1Z5")
    customer.gstin = "27BBBBB1111B1Z5"
    customer.save(update_fields=["gstin"])
    receive_stock(actor=owner, product=product, quantity=Decimal("50"), reason_code=receipt_reason)
    order = place_order(
        actor=owner, customer=customer, lines=[{"product": product, "quantity": "3"}]
    )
    confirm_order(actor=owner, order=order)
    dispatch_delivery(
        actor=owner, delivery=assign_delivery(actor=owner, order=order, assigned_user=owner)
    )
    inter_state = issue_invoice(actor=owner, order=order)

    html = render_invoice_html(inter_state)
    assert "IGST" in html
    assert "Inter-state" in html


def test_the_credit_note_reduces_what_the_ledger_shows(signed_in, owner, invoice, credit_customer):
    issue_credit_note(
        actor=owner,
        invoice=invoice,
        lines=[{"invoice_line": invoice.lines.first(), "quantity": Decimal("2")}],
        reason="Two damaged",
    )
    response = signed_in.get(reverse("webadmin:customer-ledger", args=[credit_customer.pk]))
    body = response.content.decode()
    assert "Credit note" in body
