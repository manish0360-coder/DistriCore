"""M9.1 — the sync receiver, over HTTP (`05` §11.2, `04` T-26).

Asserted **against the API**, not against the service, because the contract this milestone
implements is a wire contract: array order, `202`, one result per operation, and a
`client_uuid` that means the same thing to the device and to the database.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.urls import reverse

from field.models import Visit
from fulfilment.models import Delivery
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.services import receive_stock
from orders.services import confirm_order, place_order
from sync.models import SyncOperation

pytestmark = pytest.mark.django_db

DEVICE = "a3f9c1d2e4b6a8c0"
WHEN = "2026-08-16T06:41:10Z"


@pytest.fixture
def stocked(owner, product, receipt_reason):
    receive_stock(
        actor=owner, product=product, quantity=Decimal("1000"), reason_code=receipt_reason
    )
    return product


@pytest.fixture
def dispatched(owner, credit_customer, stocked):
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": stocked, "quantity": "10"}]
    )
    confirm_order(actor=owner, order=order)
    delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
    return dispatch_delivery(actor=owner, delivery=delivery)


def push(client, operations, device_id=DEVICE):
    return client.post(
        reverse("v1:sync-push"),
        {"device_id": device_id, "operations": operations},
        format="json",
    )


def delivery_op(delivery, *, client_uuid=None, recipient="Sharma ji"):
    return {
        "client_uuid": str(client_uuid or uuid.uuid4()),
        "operation_type": "DELIVERY_COMPLETE",
        "client_created_at": WHEN,
        "payload": {"delivery_id": delivery.pk, "recipient_name": recipient},
    }


def visit_op(customer, *, client_uuid=None, outcome="NO_ORDER"):
    return {
        "client_uuid": str(client_uuid or uuid.uuid4()),
        "operation_type": "VISIT_CREATE",
        "client_created_at": WHEN,
        "payload": {
            "customer_id": customer.pk,
            "visited_at": WHEN,
            "outcome": outcome,
        },
    }


# ------------------------------------------------------------------ 1, 6, 14
def test_delivery_complete_is_accepted_through_the_fulfilment_service(
    auth, owner, dispatched
):
    key = uuid.uuid4()
    response = push(auth(owner), [delivery_op(dispatched, client_uuid=key)])

    # 202, never 200: the batch is processed per operation (§11.2).
    assert response.status_code == 202
    result = response.json()["results"][0]
    assert result == {
        "client_uuid": str(key),
        "status": "ACCEPTED",
        "entity_type": "delivery",
        "entity_id": dispatched.pk,
        "error_code": "",
    }
    assert "server_time" in response.json()

    dispatched.refresh_from_db()
    assert dispatched.status == Delivery.Status.DELIVERED
    assert dispatched.recipient_name == "Sharma ji"
    # **The proof that dispatch went through `complete_delivery` and not around it.**
    # `outcome_client_uuid` is TD-39's key and nothing in `sync` sets it.
    assert str(dispatched.outcome_client_uuid) == str(key)
    # PU-4: the batch supplied the device, and the service recorded it.
    assert dispatched.device_id == DEVICE


# ------------------------------------------------------------------ 2, 15
def test_visit_create_is_accepted_and_writes_the_frozen_record(auth, owner, customer):
    key = uuid.uuid4()
    response = push(auth(owner), [visit_op(customer, client_uuid=key)])

    assert response.status_code == 202
    result = response.json()["results"][0]
    assert result["status"] == "ACCEPTED"
    assert result["entity_type"] == "visit"

    visit = Visit.objects.get(pk=result["entity_id"])
    assert visit.customer_id == customer.pk
    assert visit.app_user_id == owner.pk
    assert visit.outcome == Visit.Outcome.NO_ORDER
    assert visit.device_id == DEVICE
    assert str(visit.client_uuid) == str(key)
    # GPS is task 6 on the client and nullable here (04 T-23 `ck_visit_coords`).
    assert visit.latitude is None and visit.longitude is None


# ------------------------------------------------------------------ 3
def test_operations_are_applied_in_array_order_not_by_timestamp(auth, owner, customer):
    """PU-1…PU-3. The array is the order; `client_created_at` is metadata.

    The timestamps below run **backwards**, so a server that sorted by them would apply
    these in the opposite order — which is exactly the device-clock dependency P-4 forbids.
    """
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    operations = [
        {**visit_op(customer, client_uuid=first), "client_created_at": "2026-08-16T09:00:00Z"},
        {**visit_op(customer, client_uuid=second), "client_created_at": "2026-08-16T08:00:00Z"},
        {**visit_op(customer, client_uuid=third), "client_created_at": "2026-08-16T07:00:00Z"},
    ]

    response = push(auth(owner), operations)

    assert [r["client_uuid"] for r in response.json()["results"]] == [
        str(first),
        str(second),
        str(third),
    ]
    # The visits were created in array order, so their ids ascend with array position.
    ids = [r["entity_id"] for r in response.json()["results"]]
    assert ids == sorted(ids)


# ------------------------------------------------------------------ 4, 5
def test_a_repeated_client_uuid_is_duplicate_and_mutates_nothing_twice(
    auth, owner, dispatched
):
    client = auth(owner)
    key = uuid.uuid4()

    first = push(client, [delivery_op(dispatched, client_uuid=key)])
    dispatched.refresh_from_db()
    delivered_at = dispatched.delivered_at

    second = push(client, [delivery_op(dispatched, client_uuid=key, recipient="Someone else")])

    assert first.json()["results"][0]["status"] == "ACCEPTED"
    replay = second.json()["results"][0]
    # BR-012 / I-4: a replay is success and reports the original resource.
    assert second.status_code == 202
    assert replay["status"] == "DUPLICATE"
    assert replay["entity_id"] == dispatched.pk

    dispatched.refresh_from_db()
    assert dispatched.recipient_name == "Sharma ji", "the retry must not overwrite"
    assert dispatched.delivered_at == delivered_at
    assert SyncOperation.objects.filter(client_uuid=key).count() == 1


# ------------------------------------------------------------------ 16
def test_a_repeated_visit_is_idempotent(auth, owner, customer):
    client = auth(owner)
    key = uuid.uuid4()

    first = push(client, [visit_op(customer, client_uuid=key)])
    second = push(client, [visit_op(customer, client_uuid=key, outcome="ORDER_TAKEN")])

    assert second.json()["results"][0]["status"] == "DUPLICATE"
    assert Visit.objects.count() == 1
    assert Visit.objects.get().outcome == Visit.Outcome.NO_ORDER
    assert second.json()["results"][0]["entity_id"] == first.json()["results"][0]["entity_id"]


# ------------------------------------------------------------------ 7
def test_deferred_is_representable_without_a_v1_scenario():
    """`DEFERRED` is part of the frozen contract (`05` §11.2, `04` T-26).

    **No V1 operation can produce one.** Its only trigger is L-3 — a `*_client_uuid`
    reference not yet accepted — and local reference resolution is Edition 2. What this
    asserts is that the vocabulary is present and storable, not that a dispatcher emits it;
    fabricating a dependency scenario to make it emit one would be testing an invented
    feature.
    """
    assert SyncOperation.Status.DEFERRED == "DEFERRED"
    assert "DEFERRED" in SyncOperation.Status.values


# ------------------------------------------------------------------ 8
def test_a_rejected_operation_is_retained_with_its_reason_and_payload(auth, owner):
    key = uuid.uuid4()
    operation = {
        "client_uuid": str(key),
        "operation_type": "DELIVERY_COMPLETE",
        "client_created_at": WHEN,
        "payload": {"delivery_id": 999_999, "recipient_name": "Nobody"},
    }

    response = push(auth(owner), [operation])

    result = response.json()["results"][0]
    assert response.status_code == 202, "a refused operation is still a processed batch"
    assert result["status"] == "REJECTED"
    assert result["error_code"] != ""

    # FR-SYN-006 / C-3 / P-5: never discarded. The row is the owner's evidence (BR-014).
    record = SyncOperation.objects.get(client_uuid=key)
    assert record.status == SyncOperation.Status.REJECTED
    assert record.error_detail != ""
    assert record.payload == operation["payload"]
    assert record.processed_at is not None


def test_an_unsupported_operation_type_is_rejected_not_accepted(auth, owner):
    response = push(
        auth(owner),
        [
            {
                "client_uuid": str(uuid.uuid4()),
                "operation_type": "PAYMENT_CREATE",  # frozen vocabulary, unimplemented
                "client_created_at": WHEN,
                "payload": {"amount": "5000.00"},
            }
        ],
    )

    result = response.json()["results"][0]
    assert result["status"] == "REJECTED"
    assert result["error_code"] == "SYNC_UNSUPPORTED_OPERATION"


# ------------------------------------------------------------------ 9
def test_a_mixed_batch_returns_independent_results_in_order(
    auth, owner, dispatched, customer
):
    """A failure in the middle must not discard the work either side of it.

    FR-SYN-004 and FR-SYN-017: partial progress is retained. Rolling the batch back here
    would hand the device back deliveries it had already delivered.
    """
    good_delivery = delivery_op(dispatched)
    bad = {
        "client_uuid": str(uuid.uuid4()),
        "operation_type": "DELIVERY_COMPLETE",
        "client_created_at": WHEN,
        "payload": {"delivery_id": 999_999},
    }
    good_visit = visit_op(customer)

    response = push(auth(owner), [good_delivery, bad, good_visit])

    statuses = [r["status"] for r in response.json()["results"]]
    assert statuses == ["ACCEPTED", "REJECTED", "ACCEPTED"]
    assert [r["client_uuid"] for r in response.json()["results"]] == [
        good_delivery["client_uuid"],
        bad["client_uuid"],
        good_visit["client_uuid"],
    ]
    dispatched.refresh_from_db()
    assert dispatched.status == Delivery.Status.DELIVERED
    assert Visit.objects.count() == 1


# ------------------------------------------------------------------ 10
def test_a_batch_over_two_hundred_operations_is_refused(auth, owner, customer):
    operations = [visit_op(customer) for _ in range(201)]

    response = push(auth(owner), operations)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"
    assert Visit.objects.count() == 0, "the whole batch is refused, not partly applied"


def test_exactly_two_hundred_operations_is_accepted(auth, owner, customer):
    response = push(auth(owner), [visit_op(customer) for _ in range(200)])

    assert response.status_code == 202
    assert len(response.json()["results"]) == 200


# ------------------------------------------------------------------ 11, 12
def test_device_id_is_batch_level_and_reaches_the_domain(auth, owner, customer):
    push(auth(owner), [visit_op(customer)], device_id="batch-device-01")

    assert Visit.objects.get().device_id == "batch-device-01"


def test_device_id_inside_a_payload_is_refused_not_ignored(auth, owner, customer):
    """PU-4. A client that puts it there believes it is being attributed.

    Silently dropping it would lose exactly the attribution C-10 exists to protect, while
    looking like it worked — so the batch is refused and the client learns.
    """
    operation = visit_op(customer)
    operation["payload"]["device_id"] = "smuggled-device"

    response = push(auth(owner), [operation])

    assert response.status_code == 422
    assert Visit.objects.count() == 0


# ------------------------------------------------------------------ 13
def test_an_unauthenticated_push_is_refused(api, customer):
    response = api.post(
        reverse("v1:sync-push"),
        {"device_id": DEVICE, "operations": []},
        format="json",
    )

    assert response.status_code == 401
    assert SyncOperation.objects.count() == 0


def test_a_retailer_cannot_push_field_operations(auth, retailer_login, customer):
    """`record_visit` and `complete_delivery` both `require_roles(*Role.INTERNAL)`.

    The sync path must surface the *existing* authorisation failure rather than a
    sync-specific one — one rule, one implementation (N-06).
    """
    response = push(auth(retailer_login), [visit_op(customer)])

    assert response.status_code == 202
    assert response.json()["results"][0]["status"] == "REJECTED"
    assert Visit.objects.count() == 0


# ------------------------------------------------------------------ 17
def test_an_out_of_scope_delivery_cannot_be_completed_through_sync(
    auth, delivery_only, dispatched
):
    """The authorisation fix: sync uses `get_delivery_for`, the same scoped selector the
    direct endpoint uses.

    `dispatched` is assigned to the owner. A DELIVERY user with no assignment must not be
    able to complete it here when they could not there — and `05` §4.1 makes a scope
    violation look like absence, so nothing is disclosed about whether it exists.
    """
    response = push(auth(delivery_only), [delivery_op(dispatched)])

    assert response.json()["results"][0]["status"] == "REJECTED"
    dispatched.refresh_from_db()
    assert dispatched.status == Delivery.Status.PENDING


# ------------------------------------------------------------------ 18
def test_the_direct_delivery_endpoint_is_unchanged(auth, owner, dispatched):
    """M8's path still works exactly as it did — M9.1 added a second door, not a new lock."""
    client = auth(owner)

    response = client.post(
        reverse("v1:delivery-complete", args=[dispatched.pk]),
        {"client_uuid": str(uuid.uuid4()), "recipient_name": "Direct path"},
        format="json",
    )

    assert response.status_code == 200
    dispatched.refresh_from_db()
    assert dispatched.status == Delivery.Status.DELIVERED
    assert dispatched.recipient_name == "Direct path"
    assert SyncOperation.objects.count() == 0, "the direct path writes no sync row"
