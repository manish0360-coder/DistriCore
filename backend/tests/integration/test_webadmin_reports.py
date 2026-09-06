"""The owner report screens and the four-number dashboard (M7 task 7-8, D-4).

The browser path and the API path must not differ in what they show or in what they let a
caller see. Both call the same selectors; these tests prove the wiring rather than the
arithmetic, which ``tests/unit/test_report_selectors.py`` already owns.
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

SCREENS = [
    "webadmin:report-sales",
    "webadmin:report-stock",
    "webadmin:report-stock-variance",
    "webadmin:report-returns",
    "webadmin:report-receivables",
    "webadmin:report-top-customers",
    "webadmin:report-order-status",
    "webadmin:report-sync-health",
]


@pytest.fixture
def traded(owner, credit_customer, product, receipt_reason):
    receive_stock(
        actor=owner, product=product, quantity=Decimal("1000"), reason_code=receipt_reason
    )
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "10"}]
    )
    confirm_order(actor=owner, order=order)
    dispatch_delivery(
        actor=owner, delivery=assign_delivery(actor=owner, order=order, assigned_user=owner)
    )
    return issue_invoice(actor=owner, order=order)


@pytest.fixture
def signed_in(client, owner):
    client.force_login(owner)
    return client


@pytest.mark.parametrize("name", SCREENS)
def test_every_report_screen_renders(signed_in, traded, name):
    response = signed_in.get(reverse(name))
    assert response.status_code == 200
    assert b"Export CSV" in response.content


@pytest.mark.parametrize("name", SCREENS)
def test_every_report_screen_exports(signed_in, traded, name):
    response = signed_in.get(reverse(name), {"format": "csv"})
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")


@pytest.mark.parametrize("name", SCREENS)
def test_a_report_screen_requires_a_session(client, name):
    response = client.get(reverse(name))
    assert response.status_code == 302
    assert "/login" in response["Location"]


def test_the_screen_shows_the_definition_the_file_carries(signed_in, traded):
    """I-5 at the header level — the sentence on screen is the sentence in the export."""
    response = signed_in.get(reverse("webadmin:report-sales"))
    assert b"GST and round-off are excluded" in response.content


def test_the_returns_screen_names_its_trace(signed_in, traded):
    """AR-7 layer 3. The footer is the weakest mitigation, so it is at least asserted."""
    response = signed_in.get(reverse("webadmin:report-returns"))
    assert b"FINANCIAL trace" in response.content


def test_the_variance_screen_names_the_other_one(signed_in, traded):
    response = signed_in.get(reverse("webadmin:report-stock-variance"))
    assert b"PHYSICAL trace" in response.content


def test_the_stock_screen_says_why_there_is_no_money_column(signed_in, traded):
    """C-7. An absent figure with no explanation reads as an oversight."""
    response = signed_in.get(reverse("webadmin:report-stock"))
    assert b"cost basis" in response.content


def test_the_sales_screen_offers_every_grouping(signed_in, traded):
    response = signed_in.get(reverse("webadmin:report-sales")).content.decode()
    for grouping in ("day", "customer", "product", "salesman"):
        assert f'value="{grouping}"' in response


# ------------------------------------------------------------------------------ dashboard
def test_the_dashboard_shows_four_numbers(signed_in, traded):
    response = signed_in.get(reverse("webadmin:dashboard"))
    assert response.status_code == 200
    body = response.content.decode()
    for label in (
        "Sales today",
        "Collected today",
        "Total outstanding",
        "Orders awaiting dispatch",
    ):
        assert label in body


def test_the_dashboard_says_the_live_figures_are_not_a_record(signed_in, traded):
    """D-4: two of the four describe today, so I-6 does not apply and the page says so."""
    body = signed_in.get(reverse("webadmin:dashboard")).content.decode()
    assert "they are not a record" in body


def test_the_dashboard_offers_no_export(signed_in, traded):
    """A non-reproducible figure must not acquire the authority of a document."""
    body = signed_in.get(reverse("webadmin:dashboard")).content.decode()
    assert "format=csv" not in body


def test_a_retailer_sees_the_shell_without_the_numbers(client, retailer_login, traded):
    """Absence rather than an error page, matching `05` §4.1's posture."""
    client.force_login(retailer_login)
    body = client.get(reverse("webadmin:dashboard")).content.decode()
    assert "Sales today" not in body


def test_a_retailer_is_redirected_away_from_a_report(client, retailer_login, traded):
    client.force_login(retailer_login)
    response = client.get(reverse("webadmin:report-sales"))
    assert response.status_code == 302


def test_the_statement_export_is_reachable_from_the_browser(signed_in, traded, credit_customer):
    response = signed_in.get(
        reverse("webadmin:customer-statement-csv", args=[credit_customer.pk])
    )
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
