"""The report endpoints over HTTP, and the scoping grid (05 §9.11, FR-RPT-014, AR-5).

**A report is where a scoping bug becomes an information leak with a CSV attached.** So the
role grid is asserted per endpoint rather than once: a single shared assertion would still
pass while one report quietly used an unscoped selector.

M6 established that "the caller's scope" is not one predicate — a salesman sees payments
*they collected* but ledgers for *their own zones*. These tests exercise that surface, which
is also what TD-23 was asking for.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from billing.services import issue_invoice
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.services import receive_stock
from orders.services import confirm_order, place_order
from tests.factories import CustomerFactory, ZoneFactory

pytestmark = pytest.mark.django_db

REPORTS = [
    "v1:report-sales",
    "v1:report-stock",
    "v1:report-stock-variance",
    "v1:report-returns",
    "v1:report-receivables",
    "v1:report-top-customers",
    "v1:report-order-status",
]


@pytest.fixture
def stocked(owner, product, receipt_reason):
    receive_stock(
        actor=owner, product=product, quantity=Decimal("1000"), reason_code=receipt_reason
    )
    return product


@pytest.fixture
def traded(owner, credit_customer, stocked):
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": stocked, "quantity": "10"}]
    )
    confirm_order(actor=owner, order=order)
    dispatch_delivery(
        actor=owner, delivery=assign_delivery(actor=owner, order=order, assigned_user=owner)
    )
    return issue_invoice(actor=owner, order=order)


# ------------------------------------------------------------------------------ contract
@pytest.mark.parametrize("name", REPORTS)
def test_every_report_answers_and_names_its_columns(auth, owner, traded, name):
    response = auth(owner).get(reverse(name))
    assert response.status_code == 200
    body = response.json()
    assert body["columns"], f"{name} returned no columns"
    assert "rows" in body


@pytest.mark.parametrize("name", REPORTS)
def test_every_report_exports_csv(auth, owner, traded, name):
    """FR-RPT-012 — *every* report, which is why this is parametrised over all seven."""
    response = auth(owner).get(reverse(name), {"format": "csv"})
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert "attachment; filename=" in response["Content-Disposition"]
    assert response.content.decode().startswith("#"), "the CSV lost its self-describing header"


@pytest.mark.parametrize("name", REPORTS)
def test_a_report_requires_authentication(api, name):
    assert api.get(reverse(name)).status_code == 401


@pytest.mark.parametrize("name", REPORTS)
def test_a_retailer_cannot_read_a_cross_cutting_report(auth, retailer_login, traded, name):
    """A report that ranks customers or totals a zone is not a retailer's to read.

    Scoping it to one shop would produce a meaningless page rather than a refusal, so the
    refusal is explicit — enforced in the selector, not the view, so both delivery layers
    inherit it.
    """
    assert auth(retailer_login).get(reverse(name)).status_code == 403


# ------------------------------------------------------------------------------- scoping
@pytest.fixture
def other_zone_customer(seeded_roles):
    """A customer in a zone no test salesman is assigned to."""
    return CustomerFactory(code="C-9999", zone=ZoneFactory(name="Far Zone"))


@pytest.fixture
def salesman_with_zone(salesman, credit_customer):
    zone = ZoneFactory(name="Home Zone", assigned_user=salesman)
    credit_customer.zone = zone
    credit_customer.save(update_fields=["zone"])
    return salesman


@pytest.fixture
def foreign_trade(owner, other_zone_customer, stocked, traded):
    """A real invoice for a customer outside the salesman's zone.

    Without this the scoping tests would pass vacuously — a customer with no transactions
    is absent from every report whether the scoping works or not.
    """
    order = place_order(
        actor=owner, customer=other_zone_customer, lines=[{"product": stocked, "quantity": "5"}]
    )
    confirm_order(actor=owner, order=order)
    dispatch_delivery(
        actor=owner, delivery=assign_delivery(actor=owner, order=order, assigned_user=owner)
    )
    return issue_invoice(actor=owner, order=order)


def test_a_salesman_sees_only_their_own_zone_in_the_sales_report(
    auth, owner, salesman_with_zone, foreign_trade, other_zone_customer
):
    """AR-5. The leak this prevents arrives as a spreadsheet, not as an error."""
    owner_body = auth(owner).get(
        reverse("v1:report-sales"), {"group_by": "customer"}
    ).json()
    salesman_body = auth(salesman_with_zone).get(
        reverse("v1:report-sales"), {"group_by": "customer"}
    ).json()

    assert other_zone_customer.code in str(owner_body["rows"]), "the fixture is not exercising"
    assert other_zone_customer.code not in str(salesman_body["rows"])
    assert Decimal(str(salesman_body["total"]["sales"])) < Decimal(
        str(owner_body["total"]["sales"])
    )


@pytest.mark.parametrize(
    "name", ["v1:report-sales", "v1:report-receivables", "v1:report-top-customers"]
)
def test_a_salesman_csv_carries_the_same_scope_as_the_screen(
    auth, salesman_with_zone, foreign_trade, other_zone_customer, name
):
    """The export must not be the wider path. It is the one that leaves the building."""
    exported = auth(salesman_with_zone).get(reverse(name), {"format": "csv"})
    assert exported.status_code == 200
    assert other_zone_customer.code not in exported.content.decode()


def test_top_customers_is_scoped_too(auth, salesman_with_zone, foreign_trade, other_zone_customer):
    body = auth(salesman_with_zone).get(reverse("v1:report-top-customers")).json()
    assert other_zone_customer.code not in str(body["rows"])


# ---------------------------------------------------------------------------- parameters
def test_the_sales_report_accepts_every_documented_grouping(auth, owner, traded):
    client = auth(owner)
    for grouping in ("day", "customer", "product", "salesman"):
        response = client.get(reverse("v1:report-sales"), {"group_by": grouping})
        assert response.status_code == 200
        assert response.json()["group_by"] == grouping


def test_a_malformed_date_is_treated_as_absent(auth, owner, traded):
    """The same request, typed badly. `05` §4.1 already allows a report with no period."""
    response = auth(owner).get(reverse("v1:report-sales"), {"date_from": "not-a-date"})
    assert response.status_code == 200
    assert response.json()["date_from"] is None


def test_the_limit_is_clamped_not_trusted(auth, owner, traded):
    response = auth(owner).get(reverse("v1:report-top-customers"), {"limit": "99999"})
    assert response.status_code == 200
    assert len(response.json()["rows"]) <= 100


def test_a_negative_limit_falls_back_to_the_default(auth, owner, traded):
    assert auth(owner).get(reverse("v1:report-top-customers"), {"limit": "-5"}).status_code == 200


# ------------------------------------------------------------------------------ statement
def test_the_customer_statement_exports_csv(auth, owner, traded, credit_customer):
    """C-6: the sixth report. Built at M6; M7 adds only the export."""
    response = auth(owner).get(
        reverse("v1:customer-statement", args=[credit_customer.pk]), {"format": "csv"}
    )
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert "Closing balance" in response.content.decode()


def test_the_statement_still_returns_json_by_default(auth, owner, traded, credit_customer):
    response = auth(owner).get(reverse("v1:customer-statement", args=[credit_customer.pk]))
    assert response.status_code == 200
    assert "closing_balance" in response.json()
