"""M6 endpoints and owner screens (05 §9.6)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from receivables.services import load_opening_balance, record_payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def owing(owner, credit_customer):
    load_opening_balance(actor=owner, customer=credit_customer, amount="1000.00")
    return credit_customer


@pytest.fixture
def signed_in(client, owner):
    client.force_login(owner)
    return client


# --------------------------------------------------------------------------- API
def test_recording_a_collection_returns_the_new_balance(auth, owner, owing):
    """`05` §10.4 — the salesman is standing in front of the retailer."""
    response = auth(owner).post(
        reverse("v1:payment-list"),
        {"customer_id": owing.pk, "amount": "400.00", "method": "UPI"},
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["payment_number"].startswith("PAY-")
    assert Decimal(body["balance_after_amount"]) == Decimal("600.00")


def test_a_replayed_collection_returns_200_not_409(auth, owner, owing):
    """05 §5 — answering 409 trains clients to treat a success as a failure."""
    client = auth(owner)
    payload = {
        "customer_id": owing.pk,
        "amount": "400.00",
        "method": "UPI",
        "client_uuid": "55555555-5555-5555-5555-555555555555",
    }
    first = client.post(reverse("v1:payment-list"), payload, format="json")
    second = client.post(reverse("v1:payment-list"), payload, format="json")
    assert first.json()["id"] == second.json()["id"]
    assert client.get(reverse("v1:payment-list")).json()["count"] == 1


def test_listing_and_filtering_payments(auth, owner, owing):
    record_payment(actor=owner, customer=owing, amount="100.00", method="CASH")
    record_payment(actor=owner, customer=owing, amount="200.00", method="UPI")
    client = auth(owner)
    assert client.get(reverse("v1:payment-list")).json()["count"] == 2
    assert client.get(reverse("v1:payment-list"), {"method": "UPI"}).json()["count"] == 1
    assert (
        client.get(reverse("v1:payment-list"), {"customer_id": str(owing.pk)}).json()["count"]
        == 2
    )


def test_reversing_over_http(auth, owner, owing):
    payment = record_payment(actor=owner, customer=owing, amount="400.00", method="CASH")
    response = auth(owner).post(
        reverse("v1:payment-reverse", args=[payment.pk]),
        {"reason": "Wrong customer"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["is_reversed"] is True


def test_a_salesman_cannot_reverse(auth, salesman, owner, owing):
    payment = record_payment(actor=owner, customer=owing, amount="400.00", method="CASH")
    response = auth(salesman).post(
        reverse("v1:payment-reverse", args=[payment.pk]), {"reason": "x"}, format="json"
    )
    assert response.status_code in (403, 404)


def test_a_salesman_sees_only_what_they_collected(auth, salesman, owner, owing):
    """05 §8 — payments read is `◐ collected`, a narrower predicate than the ledger's."""
    record_payment(actor=owner, customer=owing, amount="100.00", method="CASH")
    record_payment(actor=salesman, customer=owing, amount="200.00", method="CASH")
    assert auth(salesman).get(reverse("v1:payment-list")).json()["count"] == 1
    assert auth(owner).get(reverse("v1:payment-list")).json()["count"] == 2


def test_the_statement_returns_opening_entries_and_closing(auth, owner, owing):
    record_payment(actor=owner, customer=owing, amount="300.00", method="CASH")
    response = auth(owner).get(reverse("v1:customer-statement", args=[owing.pk]))
    body = response.json()
    assert Decimal(body["closing_balance"]) == Decimal("700.00")
    assert len(body["entries"]) == 2


def test_the_outstanding_view_is_derived(auth, owner, owing):
    record_payment(actor=owner, customer=owing, amount="400.00", method="CASH")
    body = auth(owner).get(reverse("v1:customer-outstanding", args=[owing.pk])).json()
    assert Decimal(body["total_outstanding"]) == Decimal("600.00")
    assert Decimal(body["credit_on_account"]) == Decimal("0.00")
    assert len(body["outstanding"]) == 1
    assert body["outstanding"][0]["bucket"] == "0-30"


def test_a_write_off_over_http_is_owner_only(auth, salesman, owner, owing):
    refused = auth(salesman).post(
        reverse("v1:write-off"),
        {"customer_id": owing.pk, "amount": "100.00", "reason": "x"},
        format="json",
    )
    assert refused.status_code in (403, 404)

    allowed = auth(owner).post(
        reverse("v1:write-off"),
        {"customer_id": owing.pk, "amount": "100.00", "reason": "Shop closed"},
        format="json",
    )
    assert allowed.status_code == 201
    assert Decimal(allowed.json()["balance_after_amount"]) == Decimal("900.00")


def test_an_invalid_amount_is_422(auth, owner, owing):
    """05 §4.1 — understood perfectly, values invalid."""
    response = auth(owner).post(
        reverse("v1:payment-list"),
        {"customer_id": owing.pk, "amount": "0.00", "method": "CASH"},
        format="json",
    )
    assert response.status_code == 422


def test_an_anonymous_caller_is_refused(api):
    assert api.get(reverse("v1:payment-list")).status_code == 401


# --------------------------------------------------------------------------- screens
def test_the_owner_screens_render(signed_in, owner, owing):
    record_payment(actor=owner, customer=owing, amount="400.00", method="CASH")

    payments = signed_in.get(reverse("webadmin:payment-list"))
    assert payments.status_code == 200
    assert "PAY-" in payments.content.decode()

    outstanding = signed_in.get(reverse("webadmin:customer-outstanding", args=[owing.pk]))
    assert outstanding.status_code == 200
    assert "600.00" in outstanding.content.decode()

    position = signed_in.get(reverse("webadmin:receivables-position"))
    assert position.status_code == 200
    assert owing.shop_name in position.content.decode()


def test_the_owner_can_collect_and_reverse_from_the_screens(signed_in, owner, owing):
    signed_in.post(
        reverse("webadmin:payment-record", args=[owing.pk]),
        {"amount": "250.00", "method": "CASH"},
    )
    from receivables.models import Payment

    payment = Payment.objects.get()
    assert payment.amount == Decimal("250.00")

    signed_in.post(reverse("webadmin:payment-reverse", args=[payment.pk]), {"reason": "Error"})
    payment.refresh_from_db()
    assert payment.is_reversed is True


def test_a_bad_amount_flashes_rather_than_crashing(signed_in, owing):
    response = signed_in.post(
        reverse("webadmin:payment-record", args=[owing.pk]),
        {"amount": "-5.00", "method": "CASH"},
    )
    assert response.status_code == 302


def test_writing_off_from_the_screen(signed_in, owing):
    response = signed_in.post(
        reverse("webadmin:write-off", args=[owing.pk]),
        {"amount": "100.00", "reason": "Shop closed"},
    )
    assert response.status_code == 302
    from ledger.selectors import settled_balance

    assert settled_balance(owing) == Decimal("900.00")


def test_unknown_records_redirect(signed_in):
    assert (
        signed_in.get(reverse("webadmin:customer-outstanding", args=[999999])).status_code == 302
    )


def test_the_screens_require_a_login(client, owing):
    for url in (
        reverse("webadmin:payment-list"),
        reverse("webadmin:receivables-position"),
        reverse("webadmin:customer-outstanding", args=[owing.pk]),
    ):
        assert client.get(url).status_code == 302
