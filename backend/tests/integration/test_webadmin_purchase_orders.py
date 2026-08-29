"""Owner purchase-order screens (D5 Stage 2 — FR-PUR-003, FR-PUR-005, surface `S1`).

The rules are asserted in `tests/unit/test_purchase_order_services.py`; these assert the
delivery layer is wired to them. Fixtures are **model-level** so that
`test_the_screens_require_a_login` receives an unauthenticated client — the trap Stage 1's
first version fell into, since pytest-django hands every test the same `client` instance.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db

ORDER_DATE = date(2026, 8, 26)


@pytest.fixture
def signed_in(client, owner):
    client.post("/login/", {"phone": owner.phone, "password": "owner-password-123"})
    return client


@pytest.fixture
def supplier(owner):
    from purchasing.services import create_supplier

    return create_supplier(
        actor=owner,
        code="acme",
        name="Acme Distributors",
        phone="+919876500011",
        billing_address="Industrial Estate",
    )


@pytest.fixture
def widget(owner):
    from catalogue.services import create_product

    return create_product(
        actor=owner,
        code="w-1",
        name="Widget",
        selling_price=Decimal("100.00"),
        tax_rate_percent=Decimal("18.00"),
    )


@pytest.fixture
def draft(owner, supplier, widget):
    from purchasing.services import create_purchase_order

    return create_purchase_order(
        actor=owner,
        supplier=supplier,
        order_date=ORDER_DATE,
        lines=[
            {"product": widget, "quantity_ordered": Decimal("10"), "unit_cost": Decimal("50.00")}
        ],
    )


def test_the_list_renders(signed_in, draft):
    response = signed_in.get("/purchase-orders/")
    assert response.status_code == 200
    assert draft.po_number.encode() in response.content


def test_the_list_filters_by_status(signed_in, draft):
    assert draft.po_number.encode() in signed_in.get("/purchase-orders/?status=DRAFT").content
    assert draft.po_number.encode() not in signed_in.get("/purchase-orders/?status=ISSUED").content


def test_owner_creates_an_order_through_the_form(signed_in, supplier, widget):
    response = signed_in.post(
        "/purchase-orders/new/",
        {
            "supplier": supplier.pk,
            "order_date": ORDER_DATE.isoformat(),
            "product": [str(widget.pk)],
            "quantity_ordered": ["4"],
            "unit_cost": ["25.00"],
        },
    )
    assert response.status_code == 302

    from purchasing.selectors import search_purchase_orders

    created = search_purchase_orders().get()
    assert created.po_number.startswith("PO-")
    assert created.total_amount == Decimal("118.00")  # 100.00 + 18%


def test_a_form_error_is_shown_rather_than_raised(signed_in, supplier):
    """No lines posted — the service refuses, the form reports it."""
    response = signed_in.post(
        "/purchase-orders/new/",
        {"supplier": supplier.pk, "order_date": ORDER_DATE.isoformat()},
    )
    assert response.status_code == 200
    assert b"at least one line" in response.content


def test_the_detail_page_shows_lines_and_totals(signed_in, draft):
    response = signed_in.get(f"/purchase-orders/{draft.pk}/")
    assert response.status_code == 200
    assert b"590.00" in response.content
    assert b"Widget" in response.content


def test_owner_amends_a_draft(signed_in, draft, widget):
    response = signed_in.post(
        f"/purchase-orders/{draft.pk}/edit/",
        {"product": [str(widget.pk)], "quantity_ordered": ["1"], "unit_cost": ["50.00"]},
    )
    assert response.status_code == 302
    draft.refresh_from_db()
    assert draft.total_amount == Decimal("59.00")


def test_owner_issues_an_order(signed_in, draft):
    response = signed_in.post(f"/purchase-orders/{draft.pk}/issue/")
    assert response.status_code == 302
    draft.refresh_from_db()
    assert draft.status == "ISSUED"


def test_an_issued_order_redirects_away_from_the_edit_form(signed_in, draft):
    signed_in.post(f"/purchase-orders/{draft.pk}/issue/")
    response = signed_in.get(f"/purchase-orders/{draft.pk}/edit/")
    assert response.status_code == 302


def test_re_issuing_reports_the_refusal_on_the_page(signed_in, draft):
    signed_in.post(f"/purchase-orders/{draft.pk}/issue/")
    response = signed_in.post(f"/purchase-orders/{draft.pk}/issue/")
    assert response.status_code == 200
    assert b"cannot go from" in response.content


def test_owner_cancels_with_a_reason(signed_in, draft):
    response = signed_in.post(
        f"/purchase-orders/{draft.pk}/cancel/", {"reason": "Supplier out of stock"}
    )
    assert response.status_code == 302
    draft.refresh_from_db()
    assert draft.status == "CANCELLED"
    assert draft.cancelled_reason == "Supplier out of stock"


def test_cancelling_without_a_reason_is_reported(signed_in, draft):
    response = signed_in.post(f"/purchase-orders/{draft.pk}/cancel/", {"reason": ""})
    assert response.status_code == 200
    assert b"reason is required" in response.content


def test_an_unknown_order_redirects_rather_than_erroring(signed_in):
    assert signed_in.get("/purchase-orders/999999/").status_code == 302


def test_the_screens_require_a_login(client, draft):
    for url in ("/purchase-orders/", f"/purchase-orders/{draft.pk}/"):
        assert client.get(url).status_code == 302
