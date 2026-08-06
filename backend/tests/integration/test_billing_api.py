"""The M5 endpoints, over HTTP (05 §9.4-9.6).

Authorisation is asserted **against the API**, bypassing every client, because the
Flutter binary is public and must be assumed decompiled (DV-4). A scope violation
returns 404 rather than 403 (05 §4.1): a 403 would confirm the resource exists.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from billing.services import issue_invoice
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.services import receive_stock
from orders.services import confirm_order, place_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def stocked(owner, product, receipt_reason):
    receive_stock(
        actor=owner, product=product, quantity=Decimal("1000"), reason_code=receipt_reason
    )
    return product


@pytest.fixture
def confirmed(owner, credit_customer, stocked):
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": stocked, "quantity": "10"}]
    )
    confirm_order(actor=owner, order=order)
    return order


@pytest.fixture
def dispatched(owner, confirmed):
    delivery = assign_delivery(actor=owner, order=confirmed, assigned_user=owner)
    return dispatch_delivery(actor=owner, delivery=delivery)


# --------------------------------------------------------------------------- delivery
def test_the_full_flow_over_http(auth, owner, confirmed, stocked):
    client = auth(owner)

    created = client.post(
        reverse("v1:delivery-list"),
        {"sales_order_id": confirmed.pk, "assigned_user_id": owner.pk},
        format="json",
    )
    assert created.status_code == 201
    delivery_id = created.json()["id"]

    dispatched = client.post(reverse("v1:delivery-dispatch", args=[delivery_id]), format="json")
    assert dispatched.status_code == 200
    assert dispatched.json()["dispatched_at"] is not None

    invoiced = client.post(
        reverse("v1:invoice-list"), {"sales_order_id": confirmed.pk}, format="json"
    )
    assert invoiced.status_code == 201
    assert invoiced.json()["invoice_number"].startswith("INV/")

    completed = client.post(
        reverse("v1:delivery-complete", args=[delivery_id]),
        {"recipient_name": "Shop owner"},
        format="json",
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "DELIVERED"


def test_delivery_list_and_detail(auth, owner, dispatched):
    client = auth(owner)
    listing = client.get(reverse("v1:delivery-list"))
    assert listing.status_code == 200
    assert listing.json()["count"] == 1

    detail = client.get(reverse("v1:delivery-detail", args=[dispatched.pk]))
    assert detail.status_code == 200
    assert detail.json()["order_number"] == dispatched.sales_order.order_number


def test_filtering_deliveries_by_status(auth, owner, dispatched):
    client = auth(owner)
    assert client.get(reverse("v1:delivery-list"), {"status": "PENDING"}).json()["count"] == 1
    assert client.get(reverse("v1:delivery-list"), {"status": "FAILED"}).json()["count"] == 0
    assert client.get(reverse("v1:delivery-list"), {"assigned_to": "me"}).json()["count"] == 1


def test_recording_a_failure_over_http(auth, owner, dispatched):
    response = auth(owner).post(
        reverse("v1:delivery-fail", args=[dispatched.pk]),
        {"reason": "Shop shut"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "FAILED"


def test_a_failure_without_a_reason_is_rejected(auth, owner, dispatched):
    """422, not 400.

    ``05`` §4.1 and the exception handler are explicit: the request was understood
    perfectly and its values are invalid, which is 422. 400 is reserved for a body that
    could not be parsed at all (``MALFORMED_REQUEST``). These three assertions had the
    wrong number; the API is right.
    """
    response = auth(owner).post(
        reverse("v1:delivery-fail", args=[dispatched.pk]), {}, format="json"
    )
    assert response.status_code == 422
    assert response["Content-Type"] == "application/problem+json"


def test_half_a_coordinate_pair_is_rejected(auth, owner, dispatched):
    response = auth(owner).post(
        reverse("v1:delivery-complete", args=[dispatched.pk]),
        {"latitude": "25.594095"},
        format="json",
    )
    assert response.status_code == 422


def test_assigning_an_unknown_user_is_a_404(auth, owner, confirmed):
    response = auth(owner).post(
        reverse("v1:delivery-list"),
        {"sales_order_id": confirmed.pk, "assigned_user_id": 999999},
        format="json",
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- invoice
def test_invoice_detail_and_listing(auth, owner, dispatched):
    invoice = issue_invoice(actor=owner, order=dispatched.sales_order)
    client = auth(owner)

    listing = client.get(reverse("v1:invoice-list"))
    assert listing.json()["count"] == 1

    detail = client.get(reverse("v1:invoice-detail", args=[invoice.pk]))
    assert detail.status_code == 200
    body = detail.json()
    assert body["invoice_number"] == invoice.invoice_number
    assert len(body["lines"]) == 1


def test_invoice_filters(auth, owner, dispatched):
    invoice = issue_invoice(actor=owner, order=dispatched.sales_order)
    client = auth(owner)
    assert client.get(reverse("v1:invoice-list"), {"status": "ISSUED"}).json()["count"] == 1
    assert client.get(reverse("v1:invoice-list"), {"status": "CANCELLED"}).json()["count"] == 0
    assert (
        client.get(reverse("v1:invoice-list"), {"financial_year": invoice.financial_year}).json()[
            "count"
        ]
        == 1
    )
    assert (
        client.get(reverse("v1:invoice-list"), {"customer_id": str(invoice.customer_id)}).json()[
            "count"
        ]
        == 1
    )


def test_cancelling_over_http(auth, owner, dispatched):
    invoice = issue_invoice(actor=owner, order=dispatched.sales_order)
    response = auth(owner).post(
        reverse("v1:invoice-cancel", args=[invoice.pk]),
        {"reason": "Wrong customer"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_a_client_cannot_supply_invoice_amounts(auth, owner, dispatched):
    """Every figure is derived server-side. Extra keys are ignored, not honoured."""
    response = auth(owner).post(
        reverse("v1:invoice-list"),
        {"sales_order_id": dispatched.sales_order_id, "total_amount": "1.00"},
        format="json",
    )
    assert response.status_code == 201
    assert Decimal(response.json()["total_amount"]) > Decimal("1.00")


# --------------------------------------------------------------------------- credit note
def test_issuing_a_credit_note_over_http(auth, owner, dispatched):
    invoice = issue_invoice(actor=owner, order=dispatched.sales_order)
    client = auth(owner)
    response = client.post(
        reverse("v1:credit-note-list"),
        {
            "invoice_id": invoice.pk,
            "reason": "Two damaged in transit",
            "lines": [{"invoice_line_id": invoice.lines.first().pk, "quantity": "2"}],
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["credit_note_number"].startswith("CN/")
    assert client.get(reverse("v1:credit-note-list")).json()["count"] == 1


def test_a_credit_note_line_from_another_invoice_is_a_404(auth, owner, dispatched):
    invoice = issue_invoice(actor=owner, order=dispatched.sales_order)
    response = auth(owner).post(
        reverse("v1:credit-note-list"),
        {
            "invoice_id": invoice.pk,
            "reason": "x",
            "lines": [{"invoice_line_id": 999999, "quantity": "1"}],
        },
        format="json",
    )
    assert response.status_code == 404


def test_an_empty_credit_note_is_rejected(auth, owner, dispatched):
    invoice = issue_invoice(actor=owner, order=dispatched.sales_order)
    response = auth(owner).post(
        reverse("v1:credit-note-list"),
        {"invoice_id": invoice.pk, "reason": "x", "lines": []},
        format="json",
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- ledger
def test_ledger_and_balance_endpoints(auth, owner, credit_customer, dispatched):
    invoice = issue_invoice(actor=owner, order=dispatched.sales_order)
    client = auth(owner)

    ledger = client.get(reverse("v1:customer-ledger", args=[credit_customer.pk]))
    assert ledger.json()["count"] == 1
    assert ledger.json()["results"][0]["entry_type"] == "INVOICE"

    balance = client.get(reverse("v1:customer-balance", args=[credit_customer.pk]))
    body = balance.json()
    assert Decimal(body["settled_balance"]) == invoice.total_amount
    assert Decimal(body["open_order_value"]) == Decimal("0.00")
    assert Decimal(body["credit_exposure"]) == invoice.total_amount


def test_a_customer_with_no_entries_returns_zero_not_an_error(auth, owner, customer):
    balance = auth(owner).get(reverse("v1:customer-balance", args=[customer.pk]))
    assert balance.status_code == 200
    assert Decimal(balance.json()["settled_balance"]) == Decimal("0.00")


# --------------------------------------------------------------------------- A-7, A-8
def test_a_salesman_cannot_issue_an_invoice(auth, salesman, dispatched):
    response = auth(salesman).post(
        reverse("v1:invoice-list"),
        {"sales_order_id": dispatched.sales_order_id},
        format="json",
    )
    assert response.status_code in (403, 404)


def test_a_retailer_cannot_issue_an_invoice(auth, retailer_login, dispatched):
    response = auth(retailer_login).post(
        reverse("v1:invoice-list"),
        {"sales_order_id": dispatched.sales_order_id},
        format="json",
    )
    assert response.status_code in (403, 404)


def test_a_retailer_cannot_dispatch(auth, retailer_login, owner, confirmed):
    delivery = assign_delivery(actor=owner, order=confirmed, assigned_user=owner)
    response = auth(retailer_login).post(
        reverse("v1:delivery-dispatch", args=[delivery.pk]), format="json"
    )
    assert response.status_code in (403, 404)


def test_a_retailer_sees_another_shops_invoice_as_absent_not_forbidden(
    auth, owner, retailer, customer, dispatched
):
    """A-8. 404, never 403 — a 403 is an existence oracle."""
    from tests.factories import CustomerFactory

    other = CustomerFactory()
    retailer.customer = other
    retailer.save(update_fields=["customer"])
    retailer.__dict__.pop("_role_codes", None)

    invoice = issue_invoice(actor=owner, order=dispatched.sales_order)
    response = auth(retailer).get(reverse("v1:invoice-detail", args=[invoice.pk]))
    assert response.status_code == 404


def test_an_anonymous_caller_is_refused(api):
    assert api.get(reverse("v1:invoice-list")).status_code == 401
    assert api.get(reverse("v1:delivery-list")).status_code == 401
