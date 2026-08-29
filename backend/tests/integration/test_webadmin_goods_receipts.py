"""Owner goods-receipt screens (D5 Stage 3 — FR-PUR-006…011, FR-PUR-013, surface `S1`).

The rules are asserted in `tests/unit/test_goods_receipt_services.py`; these assert the
delivery layer is wired to them. Fixtures are **model-level** so that
`test_the_screens_require_a_login` receives an unauthenticated client — pytest-django hands
every test the same `client` instance, and a fixture that logs in would mutate it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db

ORDER_DATE = date(2026, 8, 26)
RECEIPT_DATE = ORDER_DATE.isoformat()


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
def issued(owner, supplier, widget):
    from purchasing.services import create_purchase_order, issue_purchase_order

    purchase_order = create_purchase_order(
        actor=owner,
        supplier=supplier,
        order_date=ORDER_DATE,
        lines=[
            {"product": widget, "quantity_ordered": Decimal("10"), "unit_cost": Decimal("50.00")}
        ],
    )
    return issue_purchase_order(actor=owner, purchase_order=purchase_order)


def test_the_receive_form_renders_the_outstanding_lines(signed_in, issued, profile):
    response = signed_in.get(f"/purchase-orders/{issued.pk}/receive/")
    assert response.status_code == 200
    assert b"Widget" in response.content
    assert str(issued.lines.get().pk).encode() in response.content


def test_owner_posts_a_receipt_and_lands_on_it(signed_in, issued, widget, supplier, profile):
    from inventory.selectors import on_hand_for
    from ledger.selectors import supplier_balance
    from purchasing.models import GoodsReceipt, PurchaseOrder

    response = signed_in.post(
        f"/purchase-orders/{issued.pk}/receive/",
        {
            "receipt_date": RECEIPT_DATE,
            "supplier_reference": "DN-4471",
            "purchase_order_line": [str(issued.lines.get().pk)],
            "quantity_received": ["10"],
            "notes": "",
        },
    )
    receipt = GoodsReceipt.objects.get()
    assert response.status_code == 302
    assert response.url == f"/goods-receipts/{receipt.pk}/"

    assert on_hand_for(widget) == Decimal("10.000")
    assert supplier_balance(supplier) == Decimal("590.00")
    issued.refresh_from_db()
    assert issued.status == PurchaseOrder.Status.RECEIVED


def test_a_blank_quantity_row_is_skipped_not_rejected(signed_in, issued, profile):
    """The form shows every ordered line; only the ones with a figure are received."""
    from purchasing.models import PurchaseOrder

    response = signed_in.post(
        f"/purchase-orders/{issued.pk}/receive/",
        {
            "receipt_date": RECEIPT_DATE,
            "purchase_order_line": [str(issued.lines.get().pk)],
            "quantity_received": [""],
        },
    )
    # Nothing to receive -> the service's "at least one line" rule, shown on the form.
    assert response.status_code == 200
    assert b"at least one line" in response.content
    issued.refresh_from_db()
    assert issued.status == PurchaseOrder.Status.ISSUED


def test_an_over_receipt_is_refused_on_the_form(signed_in, issued, widget, profile):
    from inventory.selectors import on_hand_for
    from purchasing.models import GoodsReceipt

    response = signed_in.post(
        f"/purchase-orders/{issued.pk}/receive/",
        {
            "receipt_date": RECEIPT_DATE,
            "purchase_order_line": [str(issued.lines.get().pk)],
            "quantity_received": ["11"],
        },
    )
    assert response.status_code == 200
    assert not GoodsReceipt.objects.exists()
    assert on_hand_for(widget) == Decimal("0.000")


def test_a_forged_line_id_cannot_reach_the_service(signed_in, issued, owner, supplier, profile):
    """The candidate lines come from the server's own read of *this* order."""
    from purchasing.models import GoodsReceipt
    from purchasing.services import create_purchase_order, issue_purchase_order

    other = issue_purchase_order(
        actor=owner,
        purchase_order=create_purchase_order(
            actor=owner,
            supplier=supplier,
            order_date=ORDER_DATE,
            lines=[
                {
                    "product": issued.lines.get().product,
                    "quantity_ordered": Decimal("5"),
                    "unit_cost": Decimal("50.00"),
                }
            ],
        ),
    )
    response = signed_in.post(
        f"/purchase-orders/{issued.pk}/receive/",
        {
            "receipt_date": RECEIPT_DATE,
            "purchase_order_line": [str(other.lines.get().pk)],
            "quantity_received": ["1"],
        },
    )
    assert response.status_code == 200
    assert not GoodsReceipt.objects.exists()


def test_the_detail_shows_the_movement_each_line_produced(signed_in, issued, owner, profile):
    """FR-PUR-007 is only proven if the link is visible where an operator would check it."""
    from purchasing.services import create_goods_receipt

    receipt = create_goods_receipt(
        actor=owner,
        purchase_order=issued,
        receipt_date=ORDER_DATE,
        lines=[{"purchase_order_line": issued.lines.get(), "quantity_received": Decimal("10")}],
    )
    response = signed_in.get(f"/goods-receipts/{receipt.pk}/")
    assert response.status_code == 200
    assert receipt.grn_number.encode() in response.content
    assert f"#{receipt.lines.get().stock_movement_id}".encode() in response.content


def test_the_list_renders_and_filters(signed_in, issued, owner, profile):
    from purchasing.services import create_goods_receipt

    receipt = create_goods_receipt(
        actor=owner,
        purchase_order=issued,
        receipt_date=ORDER_DATE,
        lines=[{"purchase_order_line": issued.lines.get(), "quantity_received": Decimal("4")}],
    )
    assert receipt.grn_number.encode() in signed_in.get("/goods-receipts/").content
    assert (
        receipt.grn_number.encode()
        in signed_in.get(f"/goods-receipts/?q={issued.po_number}").content
    )
    assert receipt.grn_number.encode() not in signed_in.get("/goods-receipts/?q=ZZZZ").content


def test_the_purchase_order_offers_receiving_only_while_it_is_open(
    signed_in, issued, owner, profile
):
    from purchasing.services import create_goods_receipt

    open_page = signed_in.get(f"/purchase-orders/{issued.pk}/")
    assert b"Receive goods" in open_page.content

    create_goods_receipt(
        actor=owner,
        purchase_order=issued,
        receipt_date=ORDER_DATE,
        lines=[{"purchase_order_line": issued.lines.get(), "quantity_received": Decimal("10")}],
    )
    done_page = signed_in.get(f"/purchase-orders/{issued.pk}/")
    assert b"Receive goods" not in done_page.content


def test_the_screens_require_a_login(client, issued):
    for url in (
        "/goods-receipts/",
        f"/purchase-orders/{issued.pk}/receive/",
    ):
        assert client.get(url).status_code == 302
