"""**TD-39 — `/deliveries/{id}/complete` and `/fail` are idempotent on `client_uuid`.**

`05` §9.4 marks both endpoints `Idem ✓` and §6's I-1…I-6 define what that means. The
implementation keyed replay on `delivery.id` + status instead, which produced the *right
behaviour* — no duplicate stock, `200` with the original row — by a different mechanism than
the contract names.

**What was already safe, and must stay safe:** `_lock_dispatched` takes `SELECT … FOR UPDATE`
and the `PENDING` guard returns the existing row. `test_completing_twice_is_a_no_op` and
`test_failing_twice_does_not_return_the_stock_twice` cover that, and TD-39 must not weaken it.

**What is new:** an outcome identity that survives across requests, so a retry after a dropped
connection is recognisable as *the same operation* rather than merely *a delivery that is no
longer pending* — a distinction the client cannot otherwise make (C-4).

Adversarial rather than unit, because the properties under test are the ones a concurrent
double-submit is supposed to break.
"""

from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal

import pytest
from django.db import IntegrityError

from fulfilment.models import Delivery
from fulfilment.services import assign_delivery, complete_delivery, dispatch_delivery, fail_delivery
from inventory.selectors import on_hand_for
from inventory.services import receive_stock
from orders.services import confirm_order, place_order

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]

KEY = "11111111-2222-3333-4444-555555555555"
OTHER_KEY = "99999999-8888-7777-6666-555555555555"


@pytest.fixture
def dispatched(owner, credit_customer, product, receipt_reason):
    """A delivery that has left the warehouse — the only state an outcome is legal from."""
    receive_stock(actor=owner, product=product, quantity=Decimal("500"), reason_code=receipt_reason)
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "10"}]
    )
    confirm_order(actor=owner, order=order)
    delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
    dispatch_delivery(actor=owner, delivery=delivery)
    return delivery


# ------------------------------------------------------------------ A. complete + replay
def test_completing_twice_with_the_same_key_returns_the_original(owner, dispatched):
    """I-4: *"`200 OK` with the original resource. Never `409`, never a duplicate."*"""
    first = complete_delivery(
        actor=owner, delivery=dispatched, recipient_name="Ravi", client_uuid=KEY
    )
    second = complete_delivery(
        actor=owner, delivery=dispatched, recipient_name="Someone else", client_uuid=KEY
    )

    assert second.pk == first.pk
    assert second.status == Delivery.Status.DELIVERED
    # The replay did not overwrite the recorded fact. The first handover is what happened.
    assert second.recipient_name == "Ravi"
    assert Delivery.objects.filter(outcome_client_uuid=KEY).count() == 1


def test_the_outcome_key_is_stored_and_is_not_the_assignment_key(owner, dispatched):
    """The two identities are separate columns because they are separate operations."""
    assignment_key = dispatched.client_uuid
    completed = complete_delivery(actor=owner, delivery=dispatched, client_uuid=KEY)

    assert str(completed.outcome_client_uuid) == KEY
    assert completed.client_uuid == assignment_key, "assignment identity must be untouched"


# ---------------------------------------------------------------------- B. fail + replay
def test_failing_twice_with_the_same_key_returns_no_stock_twice(owner, product, dispatched):
    """The defect this milestone exists to make impossible by key, not only by state."""
    before = on_hand_for(product)
    first = fail_delivery(actor=owner, delivery=dispatched, reason="Shop shut", client_uuid=KEY)
    after_first = on_hand_for(product)

    second = fail_delivery(actor=owner, delivery=dispatched, reason="Shop shut", client_uuid=KEY)

    assert after_first == before + Decimal("10"), "exactly one RETURN per line"
    assert on_hand_for(product) == after_first, "the replay returned nothing a second time"
    assert second.pk == first.pk
    assert second.failure_reason == "Shop shut"


def test_one_return_movement_per_order_line(owner, dispatched):
    from inventory.models import StockMovement

    fail_delivery(actor=owner, delivery=dispatched, reason="Nobody there", client_uuid=KEY)
    fail_delivery(actor=owner, delivery=dispatched, reason="Nobody there", client_uuid=KEY)

    returns = StockMovement.objects.filter(
        movement_type=StockMovement.Type.RETURN,
        source_document_id=dispatched.pk,
    )
    assert returns.count() == dispatched.sales_order.lines.count()


# ------------------------------------------------------- C. the same key, concurrent-ish
def test_the_unique_constraint_is_the_guarantee_not_the_service_check(
    owner, credit_customer, product, receipt_reason, dispatched
):
    """**I-6.** *"Enforced by a database unique constraint, not by an application check — a
    concurrent double-submit would defeat an application check."*

    Asserted by going **around** the service and writing the column directly, so it holds
    even if every check in `fulfilment.services` were deleted.

    The second delivery is on a **different order** on purpose: `uq_delivery_sales_order`
    would otherwise fire first and this test would pass for the wrong reason — proving one
    delivery per order, which is not what it claims to prove.
    """
    complete_delivery(actor=owner, delivery=dispatched, client_uuid=KEY)

    receive_stock(actor=owner, product=product, quantity=Decimal("50"), reason_code=receipt_reason)
    other_order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "1"}]
    )
    confirm_order(actor=owner, order=other_order)
    other = assign_delivery(actor=owner, order=other_order, assigned_user=owner)

    with pytest.raises(IntegrityError):
        Delivery.objects.filter(pk=other.pk).update(outcome_client_uuid=KEY)


def test_a_replay_resolves_to_the_same_delivery_even_from_a_stale_instance(owner, dispatched):
    """The retry a flaky connection actually produces: the caller still holds the old row."""
    stale = Delivery.objects.get(pk=dispatched.pk)
    first = complete_delivery(actor=owner, delivery=dispatched, client_uuid=KEY)
    second = complete_delivery(actor=owner, delivery=stale, client_uuid=KEY)
    assert first.pk == second.pk == dispatched.pk


# ------------------------------------------------- D. a different key on the same delivery
def test_a_different_key_does_not_reopen_a_terminal_delivery(owner, product, dispatched):
    """The state guard stays authoritative. A new identity is not a licence to act twice."""
    fail_delivery(actor=owner, delivery=dispatched, reason="Shop shut", client_uuid=KEY)
    after_first = on_hand_for(product)

    again = fail_delivery(
        actor=owner, delivery=dispatched, reason="Second attempt", client_uuid=OTHER_KEY
    )

    assert on_hand_for(product) == after_first, "no second restock"
    assert again.status == Delivery.Status.FAILED
    assert again.failure_reason == "Shop shut", "the original outcome stands"
    assert str(again.outcome_client_uuid) == KEY, "the first key keeps the outcome"


def test_completing_after_failing_with_a_new_key_is_still_refused(owner, dispatched):
    fail_delivery(actor=owner, delivery=dispatched, reason="Shop shut", client_uuid=KEY)
    result = complete_delivery(actor=owner, delivery=dispatched, client_uuid=OTHER_KEY)
    assert result.status == Delivery.Status.FAILED


# --------------------------------------------------------- E. behaviour without a key
def test_without_a_key_nothing_changes(owner, product, dispatched):
    """Every pre-TD-39 caller must be unaffected — the webadmin screens send no key."""
    before = on_hand_for(product)
    first = fail_delivery(actor=owner, delivery=dispatched, reason="Shop shut")
    second = fail_delivery(actor=owner, delivery=dispatched, reason="Shop shut")

    assert first.pk == second.pk
    assert on_hand_for(product) == before + Decimal("10")
    assert first.outcome_client_uuid is None, "no key sent, no key stored"


def test_two_deliveries_may_both_have_no_outcome_key(owner, credit_customer, product, dispatched):
    """`NULL` is not a value: uniqueness must not collapse every un-keyed delivery into one."""
    complete_delivery(actor=owner, delivery=dispatched, recipient_name="First")

    second_order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "1"}]
    )
    confirm_order(actor=owner, order=second_order)
    second = assign_delivery(actor=owner, order=second_order, assigned_user=owner)
    dispatch_delivery(actor=owner, delivery=second)
    complete_delivery(actor=owner, delivery=second, recipient_name="Second")

    assert Delivery.objects.filter(outcome_client_uuid__isnull=True).count() == 2


# --------------------------------------------------------------- F. the key is in the BODY
def test_the_api_reads_client_uuid_from_the_body_not_a_header(auth, owner, dispatched):
    """AD-09: *"a body field rather than an `Idempotency-Key` header … the value **is** part
    of the resource"* — stored, queried and reported on."""
    from django.urls import reverse

    url = reverse("v1:delivery-complete", args=[dispatched.pk])
    client = auth(owner)

    first = client.post(url, {"client_uuid": KEY, "recipient_name": "Ravi"}, format="json")
    assert first.status_code == 200

    second = client.post(url, {"client_uuid": KEY, "recipient_name": "Ravi"}, format="json")
    assert second.status_code == 200, "a replay is a success, never a 409 (I-4)"
    assert second.json()["id"] == first.json()["id"]

    dispatched.refresh_from_db()
    assert str(dispatched.outcome_client_uuid) == KEY


def test_a_header_client_uuid_is_ignored(auth, owner, dispatched):
    """A header would be accepted by the transport and dropped by the serializer. The point
    of asserting it: silence is the failure mode, and silence looks like success."""
    from django.urls import reverse

    response = auth(owner).post(
        reverse("v1:delivery-fail", args=[dispatched.pk]),
        {"reason": "Shop shut"},
        format="json",
        HTTP_CLIENT_UUID=KEY,
    )
    assert response.status_code == 200
    dispatched.refresh_from_db()
    assert dispatched.outcome_client_uuid is None


def test_a_malformed_key_is_refused_before_anything_moves(auth, owner, product, dispatched):
    from django.urls import reverse

    before = on_hand_for(product)
    response = auth(owner).post(
        reverse("v1:delivery-fail", args=[dispatched.pk]),
        {"reason": "Shop shut", "client_uuid": "not-a-uuid"},
        format="json",
    )
    assert response.status_code == 422
    assert on_hand_for(product) == before
    dispatched.refresh_from_db()
    assert dispatched.status == Delivery.Status.PENDING


# ----------------------------------------------------- G. assignment semantics unchanged
def test_assignment_idempotency_is_untouched(owner, credit_customer, product, receipt_reason):
    """`Delivery.client_uuid` still keys the *assignment*, and still only that."""
    receive_stock(actor=owner, product=product, quantity=Decimal("50"), reason_code=receipt_reason)
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "2"}]
    )
    confirm_order(actor=owner, order=order)

    first = assign_delivery(actor=owner, order=order, assigned_user=owner, client_uuid=KEY)
    second = assign_delivery(actor=owner, order=order, assigned_user=owner, client_uuid=KEY)

    assert first.pk == second.pk
    assert str(first.client_uuid) == KEY
    assert first.outcome_client_uuid is None, "assigning is not an outcome"


def test_the_same_uuid_may_key_an_assignment_and_a_different_delivery_outcome(
    owner, credit_customer, product, receipt_reason, dispatched
):
    """The two columns are independent. A key used for one assignment does not block its
    use as an outcome identity elsewhere — they are different operations on different rows,
    and `05` I-5 scopes idempotency per resource type.
    """
    receive_stock(actor=owner, product=product, quantity=Decimal("50"), reason_code=receipt_reason)
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "2"}]
    )
    confirm_order(actor=owner, order=order)
    assign_delivery(actor=owner, order=order, assigned_user=owner, client_uuid=uuid_lib.UUID(KEY))

    completed = complete_delivery(actor=owner, delivery=dispatched, client_uuid=KEY)
    assert str(completed.outcome_client_uuid) == KEY
