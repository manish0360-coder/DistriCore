"""Supplier and product-supplier rules (D5 Stage 1 — FR-PUR-001, FR-PUR-002).

Stage 1 is master data only. Nothing here touches stock, money or a purchase document,
because none of those exists yet (`D5_Design_Review` v0.4.0 §8).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db.utils import IntegrityError

from catalogue.services import create_product
from core.exceptions import PermissionDenied, ValidationFailed
from core.models import AuditLog
from purchasing.models import ProductSupplier, Supplier
from purchasing.selectors import (
    active_suppliers,
    products_for_supplier,
    search_suppliers,
    suppliers_for_product,
)
from purchasing.services import (
    create_supplier,
    deactivate_supplier,
    link_product_supplier,
    set_preferred_supplier,
    unlink_product_supplier,
    update_supplier,
)

pytestmark = pytest.mark.django_db


def _supplier(actor, code="sup-1", **kw):
    fields = {
        "code": code,
        "name": " Hindustan Traders ",
        "phone": "+919876512345",
        "billing_address": "Industrial Estate",
    }
    fields.update(kw)
    return create_supplier(actor=actor, **fields)


def _product(actor, code="p-1"):
    return create_product(
        actor=actor, code=code, name=f"Product {code}", selling_price=Decimal("10.00")
    )


# --------------------------------------------------------------- FR-PUR-001 supplier


def test_owner_creates_a_supplier(owner):
    supplier = _supplier(owner)
    assert supplier.code == "SUP-1"  # canonical upper-case, as for customers and products
    assert supplier.name == "Hindustan Traders"  # stripped
    assert supplier.is_active is True
    assert supplier.payment_terms_days == 0
    assert supplier.created_by_id == owner.pk


def test_supplier_code_is_unique(owner):
    _supplier(owner, code="dup")
    with pytest.raises(ValidationFailed):
        _supplier(owner, code="dup")


def test_supplier_code_uniqueness_is_case_insensitive_in_effect(owner):
    """Codes are canonicalised, so `dup` and `DUP` are the same supplier — which is what a
    human reading two invoices would assume."""
    _supplier(owner, code="dup")
    with pytest.raises(ValidationFailed):
        _supplier(owner, code="DUP")


@pytest.mark.parametrize("missing", ["code", "name", "phone", "billing_address"])
def test_the_irreducible_fields_are_required(owner, missing):
    with pytest.raises(ValidationFailed):
        _supplier(owner, **{missing: "   "})


def test_negative_payment_terms_are_refused_before_the_database_sees_them(owner):
    """The CHECK constraint would also refuse this. Refusing in the service turns a database
    error into a message the owner can act on."""
    with pytest.raises(ValidationFailed):
        _supplier(owner, payment_terms_days=-1)


def test_non_numeric_payment_terms_are_refused(owner):
    with pytest.raises(ValidationFailed):
        _supplier(owner, payment_terms_days="soon")


def test_update_changes_terms_and_contact(owner):
    supplier = _supplier(owner)
    update_supplier(actor=owner, supplier=supplier, contact_name="R. Sharma", payment_terms_days=30)
    supplier.refresh_from_db()
    assert supplier.contact_name == "R. Sharma"
    assert supplier.payment_terms_days == 30


def test_the_code_cannot_be_changed(owner):
    """A code appears on documents. Renaming it would silently re-point history."""
    supplier = _supplier(owner, code="fixed")
    update_supplier(actor=owner, supplier=supplier, code="SOMETHING-ELSE", name="Renamed")
    supplier.refresh_from_db()
    assert supplier.code == "FIXED"
    assert supplier.name == "Renamed"


def test_deactivate_never_deletes(owner):
    supplier = _supplier(owner)
    deactivate_supplier(actor=owner, supplier=supplier)
    supplier.refresh_from_db()
    assert supplier.is_active is False
    assert Supplier.objects.filter(pk=supplier.pk).exists()
    assert supplier not in list(active_suppliers())


# ------------------------------------------------------------ FR-PUR-002 association


def test_a_product_may_have_several_suppliers(owner):
    product = _product(owner)
    first, second = _supplier(owner, code="s1"), _supplier(owner, code="s2")
    link_product_supplier(actor=owner, supplier=first, product=product, supplier_sku="A-1")
    link_product_supplier(actor=owner, supplier=second, product=product)
    assert suppliers_for_product(product).count() == 2


def test_a_supplier_may_supply_several_products(owner):
    supplier = _supplier(owner)
    for code in ("p-1", "p-2"):
        link_product_supplier(actor=owner, supplier=supplier, product=_product(owner, code))
    assert products_for_supplier(supplier).count() == 2


def test_relinking_the_same_pair_updates_rather_than_duplicating(owner):
    product, supplier = _product(owner), _supplier(owner)
    link_product_supplier(actor=owner, supplier=supplier, product=product, supplier_sku="OLD")
    link_product_supplier(actor=owner, supplier=supplier, product=product, supplier_sku="NEW")
    links = ProductSupplier.objects.filter(product=product, supplier=supplier)
    assert links.count() == 1
    assert links.first().supplier_sku == "NEW"


def test_the_pair_is_unique_at_the_database_level(owner):
    """The service is idempotent, so the constraint is asserted directly — a rule enforced
    only in a service is a rule a second code path can bypass."""
    product, supplier = _product(owner), _supplier(owner)
    ProductSupplier.objects.create(product=product, supplier=supplier)
    with pytest.raises(IntegrityError):
        ProductSupplier.objects.create(product=product, supplier=supplier)


def test_at_most_one_preferred_supplier_per_product(owner):
    product = _product(owner)
    first, second = _supplier(owner, code="s1"), _supplier(owner, code="s2")
    link_product_supplier(actor=owner, supplier=first, product=product, is_preferred=True)
    link_product_supplier(actor=owner, supplier=second, product=product, is_preferred=True)

    preferred = ProductSupplier.objects.filter(product=product, is_preferred=True)
    assert preferred.count() == 1
    assert preferred.first().supplier_id == second.pk


def test_the_preferred_constraint_is_enforced_by_the_database(owner):
    """Proved able to fail: the partial unique index, not the service, is the guarantee."""
    product = _product(owner)
    first, second = _supplier(owner, code="s1"), _supplier(owner, code="s2")
    ProductSupplier.objects.create(product=product, supplier=first, is_preferred=True)
    with pytest.raises(IntegrityError):
        ProductSupplier.objects.create(product=product, supplier=second, is_preferred=True)


def test_two_products_may_each_have_their_own_preferred_supplier(owner):
    """The index is partial on `product`, not global — this is the case that would fail if
    someone rewrote it as a plain unique index on `is_preferred`."""
    supplier = _supplier(owner)
    for code in ("p-1", "p-2"):
        product = _product(owner, code)
        link_product_supplier(actor=owner, supplier=supplier, product=product, is_preferred=True)
    assert ProductSupplier.objects.filter(is_preferred=True).count() == 2


def test_preferred_first_in_the_read_order(owner):
    product = _product(owner)
    first, second = _supplier(owner, code="aaa"), _supplier(owner, code="zzz")
    link_product_supplier(actor=owner, supplier=first, product=product)
    link_product_supplier(actor=owner, supplier=second, product=product, is_preferred=True)
    assert suppliers_for_product(product).first().supplier_id == second.pk


def test_preferring_an_unlinked_supplier_is_refused(owner):
    with pytest.raises(ValidationFailed):
        set_preferred_supplier(actor=owner, product=_product(owner), supplier=_supplier(owner))


def test_unlink_removes_the_association(owner):
    product, supplier = _product(owner), _supplier(owner)
    link_product_supplier(actor=owner, supplier=supplier, product=product)
    unlink_product_supplier(actor=owner, supplier=supplier, product=product)
    assert not ProductSupplier.objects.filter(product=product, supplier=supplier).exists()


def test_unlinking_something_not_linked_is_refused(owner):
    with pytest.raises(ValidationFailed):
        unlink_product_supplier(actor=owner, supplier=_supplier(owner), product=_product(owner))


# ------------------------------------------------------------------- authorization


@pytest.mark.parametrize(
    "call",
    [
        lambda actor, s, p: create_supplier(
            actor=actor, code="x", name="X", phone="1", billing_address="a"
        ),
        lambda actor, s, p: update_supplier(actor=actor, supplier=s, name="X"),
        lambda actor, s, p: deactivate_supplier(actor=actor, supplier=s),
        lambda actor, s, p: link_product_supplier(actor=actor, supplier=s, product=p),
        lambda actor, s, p: set_preferred_supplier(actor=actor, product=p, supplier=s),
        lambda actor, s, p: unlink_product_supplier(actor=actor, supplier=s, product=p),
    ],
)
def test_only_the_owner_may_touch_purchasing(owner, salesman, call):
    """`05` §8 has four roles and none of the other three buys anything — the same reasoning
    `inventory.services.receive_stock` records for goods in."""
    supplier, product = _supplier(owner), _product(owner)
    with pytest.raises(PermissionDenied):
        call(salesman, supplier, product)


# -------------------------------------------------------------------------- audit


def test_creating_a_supplier_is_audited(owner):
    supplier = _supplier(owner)
    entry = AuditLog.objects.filter(entity_type="supplier", entity_id=supplier.pk).get()
    assert entry.action == AuditLog.Action.CREATE
    assert entry.actor_user_id == owner.pk
    # `supplier_code`, not `code`: `core.services._SENSITIVE` redacts the latter for OTP
    # reasons and the match is exact. Asserting the plaintext value here is what proves the
    # key was chosen to survive the scrubber — `tests/unit/test_audit.py` holds the other
    # half, that `code` itself is still redacted.
    assert entry.after_state["supplier_code"] == supplier.code


def test_updating_a_supplier_records_both_sides(owner):
    supplier = _supplier(owner)
    update_supplier(actor=owner, supplier=supplier, payment_terms_days=45)
    entry = AuditLog.objects.filter(entity_type="supplier", action=AuditLog.Action.UPDATE).get()
    assert entry.before_state["payment_terms_days"] == 0
    assert entry.after_state["payment_terms_days"] == 45


def test_deactivation_is_audited_distinctly(owner):
    supplier = _supplier(owner)
    deactivate_supplier(actor=owner, supplier=supplier)
    assert AuditLog.objects.filter(
        entity_type="supplier", action=AuditLog.Action.DEACTIVATE
    ).exists()


def test_the_association_is_audited_under_its_own_entity_type(owner):
    """D5 adds no `AuditLog.Action` values. Entities are distinguished by `entity_type`,
    which is the convention `create_zone` and `create_customer` already follow."""
    product, supplier = _product(owner), _supplier(owner)
    link_product_supplier(actor=owner, supplier=supplier, product=product)
    assert AuditLog.objects.filter(
        entity_type="product_supplier", action=AuditLog.Action.CREATE
    ).exists()


def test_unlinking_is_audited_with_the_state_that_was_removed(owner):
    product, supplier = _product(owner), _supplier(owner)
    link_product_supplier(actor=owner, supplier=supplier, product=product)
    unlink_product_supplier(actor=owner, supplier=supplier, product=product)
    entry = AuditLog.objects.filter(
        entity_type="product_supplier", action=AuditLog.Action.DEACTIVATE
    ).get()
    assert entry.before_state["supplier_id"] == supplier.pk


# ----------------------------------------------------------------------- selectors


def test_search_matches_code_and_name(owner):
    _supplier(owner, code="acme", name="Acme Distributors")
    assert search_suppliers(term="acme").count() == 1
    assert search_suppliers(term="Distrib").count() == 1
    assert search_suppliers(term="nothing").count() == 0
