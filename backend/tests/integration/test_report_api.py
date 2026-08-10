"""The report endpoints over HTTP, and the scoping grid (05 §9.11, FR-RPT-014, AR-5).

**A report is where a scoping bug becomes an information leak with a CSV attached.** So the
role grid is asserted per endpoint rather than once: a single shared assertion would still
pass while one report quietly used an unscoped selector.

M6 established that "the caller's scope" is not one predicate — a salesman sees payments
*they collected* but ledgers for *their own zones*. These tests exercise that surface, which
is also what TD-23 was asking for.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from api.v1.report_views import money_string
from billing.services import issue_invoice
from core.fields import to_money
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.services import receive_stock
from orders.services import confirm_order, place_order
from receivables.services import record_payment
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


# ------------------------------------------------------------------------------ dashboard
#: D-4, in the order the selector returns them. Asserted as a set *and* a length so that
#: adding a fifth number is a failing test rather than a silent change to a screen the
#: owner reads daily.
DASHBOARD_KEYS = {"sales_today", "collected_today", "total_outstanding", "awaiting_dispatch"}


@pytest.fixture
def collected(owner, credit_customer, traded):
    """A payment recorded today, so `collected_today` is not trivially zero.

    Without it the money-encoding tests would pass against `"0.00"`, which is a string
    whatever the encoder does — the assertion would hold and prove nothing.
    """
    return record_payment(
        actor=owner, customer=credit_customer, amount=Decimal("500.00"), method="CASH"
    )


def test_the_dashboard_answers_with_exactly_four_numbers(auth, owner, traded):
    response = auth(owner).get(reverse("v1:dashboard"))
    assert response.status_code == 200
    body = response.json()
    assert body["as_of"], "a dashboard without an as_of is a figure with no date"
    assert {metric["key"] for metric in body["metrics"]} == DASHBOARD_KEYS
    assert len(body["metrics"]) == 4, "D-4 is four numbers, not four-or-more"


def test_the_dashboard_sends_money_as_a_decimal_string(auth, owner, traded, collected):
    """AD-02 / C-1, and M8 P-3. **The reason this endpoint exists is a Dart client.**

    DRF's JSON encoder renders `Decimal("1180.00")` as the JSON number `1180.0`, and
    `jsonDecode` in Dart yields a `double` for it. A rupee figure that has been exact
    through the column, the service and the selector would become inexact in the last
    hop — and the client cannot detect that it happened.
    """
    body = auth(owner).get(reverse("v1:dashboard")).json()
    money = [metric for metric in body["metrics"] if metric["is_money"]]
    assert len(money) == 3, "three of the four D-4 numbers are money"

    for metric in money:
        assert isinstance(metric["value"], str), (
            f"{metric['key']} crossed the wire as {type(metric['value']).__name__}, "
            "not a decimal string (AD-02)"
        )
        Decimal(metric["value"])  # raises InvalidOperation if it is not an exact decimal
        assert metric["value"].count(".") == 1 and len(metric["value"].split(".")[1]) == 2, (
            f"{metric['key']} = {metric['value']!r} is not at the canonical money scale"
        )

    assert any(Decimal(metric["value"]) > 0 for metric in money), (
        "every money figure is zero — this test would pass without an encoder"
    )


def test_the_dashboard_does_not_stringify_a_count(auth, owner, traded):
    """The other half of AD-02: it applies to money and quantity, not to everything.

    Over-applying it is as wrong as under-applying it — `"3.00"` orders awaiting dispatch
    would be a type the client has to un-learn.
    """
    body = auth(owner).get(reverse("v1:dashboard")).json()
    count = next(m for m in body["metrics"] if m["key"] == "awaiting_dispatch")
    assert count["is_money"] is False
    assert isinstance(count["value"], int)


def test_the_dashboard_marks_which_numbers_are_live(auth, owner, traded):
    """M7 §8.2. The client must be able to tell a reproducible figure from a live one."""
    body = auth(owner).get(reverse("v1:dashboard")).json()
    live = {metric["key"] for metric in body["metrics"] if metric["is_live"]}
    assert live == {"sales_today", "collected_today"}


def test_the_dashboard_refuses_csv(auth, owner, traded):
    """M7 §8.2 — the half of the ruling M8 did **not** overturn.

    404 rather than 400 because the refusal is structural: `DashboardView` declares only
    `JSONRenderer`, so DRF's own negotiation has nothing to match and raises `Http404`
    before the view runs. If someone adds `CsvRenderer` to that list, this test fails.
    """
    assert auth(owner).get(reverse("v1:dashboard"), {"format": "csv"}).status_code == 404


def test_the_dashboard_is_absent_from_the_report_csv_suite():
    """TD-29's shape, inverted: the dashboard must *not* be wired into the CSV path.

    `REPORTS` is parametrised over the FR-RPT-012 export assertion. A dashboard added to
    that list would be given an export by a test rather than by a decision.
    """
    assert "v1:dashboard" not in REPORTS
    assert len(REPORTS) == 7, "the seven reports export CSV; the dashboard is not one of them"


def test_the_dashboard_requires_authentication(api):
    assert api.get(reverse("v1:dashboard")).status_code == 401


def test_a_retailer_cannot_read_the_dashboard(auth, retailer_login, traded):
    """Same refusal as the seven reports, from the same `_internal` predicate."""
    assert auth(retailer_login).get(reverse("v1:dashboard")).status_code == 403


def test_the_dashboard_is_scoped_to_the_caller(
    auth, owner, salesman_with_zone, foreign_trade, other_zone_customer
):
    """AR-5 again. A scoped selector reached through a new view is not scoped by assumption.

    `foreign_trade` puts a real invoice outside the salesman's zone, so the owner's
    outstanding is strictly larger. Without the fixture both figures would be zero and
    this would pass whatever the view did.
    """

    def outstanding(user):
        body = auth(user).get(reverse("v1:dashboard")).json()
        metric = next(m for m in body["metrics"] if m["key"] == "total_outstanding")
        return Decimal(metric["value"])

    owner_total, salesman_total = outstanding(owner), outstanding(salesman_with_zone)
    assert owner_total > 0, "the fixture is not exercising the scoping"
    assert salesman_total < owner_total


def test_the_dashboard_endpoint_derives_nothing_of_its_own(auth, owner, traded, collected):
    """The view arranges; the selector derives (D-3).

    Asserted by equality against the selector rather than against literals: a hard-coded
    expectation would still pass if the view quietly recomputed a number its own way.

    The selector is pinned to the day the *response* reports, not to `date.today()` read a
    second time. Two live figures compared across an unpinned midnight is TD-31's defect
    class, and this test would be the fifth instance of it.
    """
    from reporting import selectors as reports

    body = auth(owner).get(reverse("v1:dashboard")).json()
    served = {metric["key"]: metric["value"] for metric in body["metrics"]}
    as_of = date.fromisoformat(body["as_of"])
    for metric in reports.dashboard(owner, today=as_of).metrics:
        expected = str(to_money(metric.value)) if metric.is_money else metric.value
        assert served[metric.key] == expected, f"{metric.key} disagrees with the selector"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1180", "1180.00"), ("1180.005", "1180.01"), ("0", "0.00"), ("-12.5", "-12.50")],
)
def test_money_string_is_canonical_and_half_up(raw, expected):
    """One scale, one rounding rule (N-07). `1180` and `1180.00` are the same rupees."""
    assert money_string(Decimal(raw)) == expected
