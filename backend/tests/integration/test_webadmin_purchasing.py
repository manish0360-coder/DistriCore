"""Owner supplier screens (D5 Stage 1 — FR-PUR-001, FR-PUR-002, surface `S1`).

The round trip that proves the form reaches the service: the rules are asserted in
`tests/unit/test_purchasing_services.py`, and these assert the delivery layer is wired to
them. `webadmin` may not import `purchasing.models` — the import-linter contract enforces it —
so a screen that worked while bypassing the service would fail the gate, not these tests.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(client, owner):
    client.post("/login/", {"phone": owner.phone, "password": "owner-password-123"})
    return client


@pytest.fixture
def supplier(owner):
    """Built through the service, not the form — deliberately.

    A fixture that posts to `/suppliers/new/` has to sign the client in first, and
    pytest-django hands every test the **same** client instance: `signed_in` mutates it and
    returns it rather than wrapping it. `test_the_screens_require_a_login` would then be
    handed an already-authenticated client and assert nothing at all.

    The form path loses no coverage — `test_owner_creates_a_supplier_through_the_form` is
    exactly that round trip. This fixture only needs a row to exist. Same shape as
    `test_webadmin_billing.py`, whose fixtures are all model-level for the same reason.
    """
    from purchasing.services import create_supplier

    return create_supplier(
        actor=owner,
        code="acme",
        name="Acme Distributors",
        phone="+919876500011",
        billing_address="Industrial Estate",
        payment_terms_days=30,
    )


def test_supplier_list_renders(signed_in, supplier):
    response = signed_in.get("/suppliers/")
    assert response.status_code == 200
    assert supplier.code.encode() in response.content


def test_supplier_list_search(signed_in, supplier):
    assert supplier.code.encode() in signed_in.get("/suppliers/?q=ACME").content
    assert supplier.code.encode() not in signed_in.get("/suppliers/?q=zzzz").content


def test_owner_creates_a_supplier_through_the_form(signed_in):
    response = signed_in.post(
        "/suppliers/new/",
        {
            "code": "new-1",
            "name": "New Supplier",
            "phone": "+919876500022",
            "billing_address": "Market Road",
            "email": "sales@example.com",
            "payment_terms_days": "15",
        },
    )
    assert response.status_code == 302

    from purchasing.selectors import search_suppliers

    created = search_suppliers(term="NEW-1").get()
    assert created.name == "New Supplier"
    assert created.payment_terms_days == 15
    assert created.email == "sales@example.com"


def test_a_duplicate_code_is_reported_on_the_form_not_raised(signed_in, supplier):
    response = signed_in.post(
        "/suppliers/new/",
        {
            "code": "acme",
            "name": "Impostor",
            "phone": "+919876500033",
            "billing_address": "Elsewhere",
        },
    )
    assert response.status_code == 200
    assert b"already in use" in response.content


def test_owner_edits_a_supplier_through_the_form(signed_in, supplier):
    response = signed_in.post(
        f"/suppliers/{supplier.pk}/",
        {
            "name": "Acme Distributors Pvt Ltd",
            "phone": supplier.phone,
            "billing_address": supplier.billing_address,
            "payment_terms_days": "45",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    supplier.refresh_from_db()
    assert supplier.name == "Acme Distributors Pvt Ltd"
    assert supplier.payment_terms_days == 45


def test_clearing_active_deactivates_without_deleting(signed_in, supplier):
    signed_in.post(
        f"/suppliers/{supplier.pk}/",
        {
            "name": supplier.name,
            "phone": supplier.phone,
            "billing_address": supplier.billing_address,
            "payment_terms_days": "30",
        },
    )
    supplier.refresh_from_db()
    assert supplier.is_active is False


def test_owner_links_a_product_from_the_supplier_form(signed_in, supplier, product):
    response = signed_in.post(
        f"/suppliers/{supplier.pk}/products/",
        {"action": "link", "product": product.pk, "supplier_sku": "THEIR-1"},
    )
    assert response.status_code == 302

    from purchasing.selectors import products_for_supplier

    link = products_for_supplier(supplier).get()
    assert link.product_id == product.pk
    assert link.supplier_sku == "THEIR-1"


def test_the_linked_product_appears_on_the_form(signed_in, supplier, product):
    signed_in.post(f"/suppliers/{supplier.pk}/products/", {"action": "link", "product": product.pk})
    assert product.name.encode() in signed_in.get(f"/suppliers/{supplier.pk}/").content


def test_owner_marks_a_preferred_supplier(signed_in, supplier, product):
    signed_in.post(f"/suppliers/{supplier.pk}/products/", {"action": "link", "product": product.pk})
    response = signed_in.post(
        f"/suppliers/{supplier.pk}/products/", {"action": "prefer", "product": product.pk}
    )
    assert response.status_code == 302

    from purchasing.selectors import products_for_supplier

    assert products_for_supplier(supplier).get().is_preferred is True


def test_owner_unlinks_a_product(signed_in, supplier, product):
    signed_in.post(f"/suppliers/{supplier.pk}/products/", {"action": "link", "product": product.pk})
    response = signed_in.post(
        f"/suppliers/{supplier.pk}/products/", {"action": "unlink", "product": product.pk}
    )
    assert response.status_code == 302

    from purchasing.selectors import products_for_supplier

    assert products_for_supplier(supplier).count() == 0


def test_the_screens_require_a_login(client, supplier):
    """`302`, not `in (302, 403)`. `@login_required` redirects to the login page; a `403`
    would be a different mechanism, and the loose form would have passed on it silently.
    Matches `test_webadmin_billing.py::test_the_screens_require_a_login`."""
    for url in ("/suppliers/", f"/suppliers/{supplier.pk}/"):
        assert client.get(url).status_code == 302
