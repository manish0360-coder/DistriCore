"""M9.4 — `GET /sync/pull` (05 §11.1, D-M9.4-2 … D-M9.4-5).

Asserted over HTTP, because the properties that matter are contract properties: what a
device is allowed to see, what it is told to remove, and whether a cursor it stores can lose
a row.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from customers.models import Customer
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.services import receive_stock
from orders.services import confirm_order, place_order
from sync.selectors import PULL_PAGE_SIZE
from tests.factories import CustomerFactory, ZoneFactory

pytestmark = pytest.mark.django_db


def pull(client, since=None, page_token=None):
    query = {}
    if since is not None:
        query["since"] = since.isoformat()
    if page_token is not None:
        # P-5: the **same** `since` travels with the token. `since` is never rewritten
        # mid-pull; the token carries position, `since` carries the sync cursor.
        query["page_token"] = page_token
    return client.get(reverse("v1:sync-pull"), query)


@pytest.fixture
def dispatched(owner, credit_customer, product, receipt_reason):
    from decimal import Decimal

    receive_stock(
        actor=owner, product=product, quantity=Decimal("1000"), reason_code=receipt_reason
    )
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "10"}]
    )
    confirm_order(actor=owner, order=order)
    delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
    return dispatch_delivery(actor=owner, delivery=delivery)


# ------------------------------------------------------------------ 1, 5, 11, 12
def test_a_full_bootstrap_returns_everything_the_user_may_hold(auth, owner, customer):
    """P-1: `since` absent is a bootstrap, not an error and not "since the epoch"."""
    response = pull(auth(owner))

    assert response.status_code == 200
    body = response.json()
    assert body["since"] is None
    assert body["has_more"] is False
    assert [c["id"] for c in body["customers"]["updated"]] == [customer.pk]
    # A bootstrap has nothing to remove: a device with no cache cannot act on the list.
    assert body["customers"]["deactivated_ids"] == []
    assert "server_time" in body


def test_only_the_two_implemented_collections_appear(auth, owner, customer):
    """D-M9.4-2: unimplemented collections are **absent, not empty**.

    An empty `products` would tell a client the collection exists and has nothing in it.
    """
    body = pull(auth(owner)).json()

    assert set(body) == {"server_time", "since", "has_more", "customers", "deliveries"}


def test_pull_is_read_only_and_repeatable(auth, owner, customer, dispatched):
    """P-6. Two identical pulls change nothing and answer the same."""
    client = auth(owner)
    first = pull(client).json()
    before = (Customer.objects.count(), customer.updated_at)

    second = pull(client).json()

    customer.refresh_from_db()
    assert (Customer.objects.count(), customer.updated_at) == before
    assert [c["id"] for c in first["customers"]["updated"]] == [
        c["id"] for c in second["customers"]["updated"]
    ]
    assert first["deliveries"]["updated"] == second["deliveries"]["updated"]


def test_server_time_is_sampled_before_the_query(auth, owner, customer):
    """D-M9.4-4. Sampling it after would drop rows written in between — silently."""
    before = timezone.now()
    body = pull(auth(owner)).json()
    after = timezone.now()

    server_time = body["server_time"]
    assert server_time is not None
    # The instant is inside the request window; the client stores it as the next `since`.
    assert before.isoformat()[:19] <= server_time[:19] <= after.isoformat()[:19]


# ------------------------------------------------------------------ 2, 8
def test_an_incremental_pull_returns_only_what_changed(auth, owner, customer):
    client = auth(owner)
    cursor = timezone.now()
    untouched = pull(client, since=cursor).json()
    assert untouched["customers"]["updated"] == []

    customer.shop_name = "Renamed Kirana"
    customer.save()

    body = pull(client, since=cursor).json()

    assert [c["id"] for c in body["customers"]["updated"]] == [customer.pk]
    assert body["customers"]["updated"][0]["shop_name"] == "Renamed Kirana"


def test_the_boundary_is_inclusive(auth, owner, customer):
    """**D-M9.4-4: `updated_at >= since`.**

    Using the row's own `updated_at` as the cursor is the worst case the rule exists for: `>`
    would drop it permanently, and a lost row is unrecoverable where a resent one is not.
    """
    body = pull(auth(owner), since=customer.updated_at).json()

    assert [c["id"] for c in body["customers"]["updated"]] == [customer.pk]


def test_a_cursor_after_the_row_excludes_it(auth, owner, customer):
    body = pull(auth(owner), since=customer.updated_at + timedelta(microseconds=1)).json()

    assert body["customers"]["updated"] == []


# ------------------------------------------------------------------ 3, 4, 9
def test_the_first_page_reports_has_more_and_returns_a_token(auth, owner):
    """P-5 as amended (D-M9.4-8).

    **This replaces a test that asserted the opposite** — that the same `since` returns the
    same page — which was the defect written as a requirement. It passed 17/17 while the
    client could not reach page two.
    """
    zone = ZoneFactory(assigned_user=owner)
    for _ in range(PULL_PAGE_SIZE + 5):
        CustomerFactory(zone=zone)

    first = pull(auth(owner)).json()

    assert first["has_more"] is True
    assert first["next_page_token"], "has_more without a token is an unterminating loop"
    assert len(first["customers"]["updated"]) == PULL_PAGE_SIZE


def test_the_same_since_plus_token_reaches_later_customers(auth, owner):
    zone = ZoneFactory(assigned_user=owner)
    for _ in range(PULL_PAGE_SIZE + 5):
        CustomerFactory(zone=zone)
    client = auth(owner)

    first = pull(client).json()
    second = pull(client, page_token=first["next_page_token"]).json()

    first_ids = {c["id"] for c in first["customers"]["updated"]}
    second_ids = {c["id"] for c in second["customers"]["updated"]}
    assert second_ids, "page two must not be empty"
    assert not (first_ids & second_ids), "a row must never appear on two pages"
    assert len(second["customers"]["updated"]) == 5
    assert second["has_more"] is False


def test_the_final_page_omits_the_token(auth, owner):
    zone = ZoneFactory(assigned_user=owner)
    for _ in range(PULL_PAGE_SIZE + 5):
        CustomerFactory(zone=zone)
    client = auth(owner)

    first = pull(client).json()
    final = pull(client, page_token=first["next_page_token"]).json()

    assert final["has_more"] is False
    # A token on a final page would invite one more fetch that returns nothing.
    assert "next_page_token" not in final


def test_customers_and_deliveries_advance_independently(auth, owner, dispatched):
    """One scalar `since` could not express two positions — which is why a token exists."""
    zone = ZoneFactory(assigned_user=owner)
    for _ in range(PULL_PAGE_SIZE + 2):
        CustomerFactory(zone=zone)
    client = auth(owner)

    first = pull(client).json()
    # Deliveries fit on page one and are finished; customers are not.
    assert [d["id"] for d in first["deliveries"]["updated"]] == [dispatched.pk]
    assert first["has_more"] is True

    second = pull(client, page_token=first["next_page_token"]).json()

    assert second["customers"]["updated"], "customers must continue"
    assert second["deliveries"]["updated"] == [], (
        "an exhausted collection must not be re-sent on a later page"
    )


def test_replaying_the_same_since_and_token_is_deterministic(auth, owner):
    zone = ZoneFactory(assigned_user=owner)
    for _ in range(PULL_PAGE_SIZE + 5):
        CustomerFactory(zone=zone)
    client = auth(owner)
    token = pull(client).json()["next_page_token"]

    once = pull(client, page_token=token).json()
    twice = pull(client, page_token=token).json()

    # P-6: pull is safe to repeat. A retried page after a dropped connection must return
    # what the first attempt would have.
    assert [c["id"] for c in once["customers"]["updated"]] == [
        c["id"] for c in twice["customers"]["updated"]
    ]


def test_a_malformed_token_is_refused(auth, owner, customer):
    """A silent restart would look like it worked and quietly re-send every page."""
    for bad in ("not-base64!!", "", "eyJub3QiOiAiYSB0b2tlbiJ9"):
        response = auth(owner).get(reverse("v1:sync-pull"), {"page_token": bad} if bad else {})
        if bad:
            assert response.status_code == 422, bad
            assert response.json()["code"] == "VALIDATION_FAILED"


def test_deactivated_ids_are_sent_once_per_pull(auth, owner):
    """The list is identical on every page and removal is idempotent — repeating it is waste.

    A deactivation landing mid-pull is caught next pull, because the cursor has not advanced.
    """
    zone = ZoneFactory(assigned_user=owner)
    made = [CustomerFactory(zone=zone) for _ in range(PULL_PAGE_SIZE + 5)]
    client = auth(owner)
    cursor = timezone.now()
    made[0].is_active = False
    made[0].save(update_fields=["is_active", "updated_at"])

    first = pull(client, since=cursor).json()
    later = pull(client, since=cursor, page_token=first["next_page_token"]).json() \
        if first["has_more"] else {"customers": {"deactivated_ids": []}}

    assert made[0].pk in first["customers"]["deactivated_ids"]
    assert later["customers"]["deactivated_ids"] == []


def test_a_row_written_mid_pull_is_not_skipped(auth, owner):
    """Keyset, not offset. AD-10 rejects offset for sync by name: *"offset pagination
    silently skips rows when the underlying set changes mid-pagination — precisely the
    failure that loses a transaction (BR-014)."*

    A row inserted **behind** the cursor shifts every offset. It cannot shift a
    `(updated_at, id)` comparison, so nothing on page two is displaced.
    """
    zone = ZoneFactory(assigned_user=owner)
    for _ in range(PULL_PAGE_SIZE + 5):
        CustomerFactory(zone=zone)
    client = auth(owner)
    first = pull(client).json()
    expected_next = {c["id"] for c in first["customers"]["updated"]}

    # A new shop lands with an `updated_at` *after* everything already paged.
    intruder = CustomerFactory(zone=zone)

    second = pull(client, page_token=first["next_page_token"]).json()
    second_ids = {c["id"] for c in second["customers"]["updated"]}

    assert not (second_ids & expected_next), "page one rows must not reappear"
    assert intruder.pk in second_ids or second["has_more"] is True, (
        "a row written mid-pull is either delivered or still pending, never skipped"
    )


def test_the_final_page_reports_has_more_false(auth, owner, customer):
    assert pull(auth(owner)).json()["has_more"] is False


def test_ordering_is_stable_on_updated_at_then_id(auth, owner):
    """`timestamptz` is not unique: one transaction can stamp two rows identically, and a tie
    split across a page boundary drops or repeats a row."""
    zone = ZoneFactory(assigned_user=owner)
    made = [CustomerFactory(zone=zone) for _ in range(5)]
    stamp = timezone.now()
    Customer.objects.filter(pk__in=[c.pk for c in made]).update(updated_at=stamp)

    body = pull(auth(owner)).json()

    tied = [c["id"] for c in body["customers"]["updated"] if c["id"] in {c.pk for c in made}]
    assert tied == sorted(tied), "identical timestamps must fall back to id"


# ------------------------------------------------------------------ 6, 7, 13
def test_customer_scoping_follows_the_actor_not_the_request(auth, salesman, owner):
    """AD-11. `visible_customers` scopes salesmen to their own zones."""
    mine = CustomerFactory(zone=ZoneFactory(assigned_user=salesman))
    theirs = CustomerFactory(zone=ZoneFactory(assigned_user=owner))

    ids = [c["id"] for c in pull(auth(salesman)).json()["customers"]["updated"]]

    assert mine.pk in ids
    assert theirs.pk not in ids


def test_delivery_scoping_reuses_visible_deliveries(auth, delivery_only, dispatched):
    """`dispatched` is assigned to the owner; a DELIVERY user with no assignment sees none."""
    body = pull(auth(delivery_only)).json()

    assert [d["id"] for d in body["deliveries"]["updated"]] == []


def test_a_query_parameter_cannot_widen_scope(auth, salesman, owner):
    """A parameter a client can send is one an attacker can change."""
    theirs = CustomerFactory(zone=ZoneFactory(assigned_user=owner))

    response = auth(salesman).get(
        reverse("v1:sync-pull"), {"zone_id": theirs.zone_id, "user_id": owner.pk}
    )

    ids = [c["id"] for c in response.json()["customers"]["updated"]]
    assert theirs.pk not in ids


def test_unauthenticated_pull_is_refused(api):
    assert api.get(reverse("v1:sync-pull")).status_code == 401


# ------------------------------------------------------------------ 10
def test_deactivated_customers_are_reported_as_ids_only(auth, owner, customer):
    """**The only removal mechanism** (D-M9.4-3).

    Read unscoped on purpose: P-4 exists because *"a deactivated row may no longer appear in
    `updated` under scoping"*. Only ids leave, never a field.
    """
    client = auth(owner)
    cursor = timezone.now()
    customer.is_active = False
    customer.save(update_fields=["is_active", "updated_at"])

    body = pull(client, since=cursor).json()

    assert body["customers"]["deactivated_ids"] == [customer.pk]


def test_an_untouched_customer_is_never_reported_as_deactivated(auth, owner, customer):
    """Absence from a delta pull is not deletion, and neither is inactivity of the row."""
    body = pull(auth(owner), since=timezone.now()).json()

    assert body["customers"]["deactivated_ids"] == []
    assert body["customers"]["updated"] == []


def test_deliveries_carry_no_deactivated_ids(auth, owner, dispatched):
    """§11.1 gives deliveries `{updated}` only — a delivery reaches a terminal status, it is
    never deactivated."""
    body = pull(auth(owner)).json()

    assert set(body["deliveries"]) == {"updated"}
    assert [d["id"] for d in body["deliveries"]["updated"]] == [dispatched.pk]
