"""M9.3 — `GET /sync/status` (05 §11.5).

The endpoint exists so a device can compare its own outbox depth against the server's view.
Every assertion here is over HTTP, because the property that matters — **device A never sees
device B** — is a property of the token, not of a function argument.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from django.urls import reverse

from api.v1.auth_views import _issue_tokens
from sync.models import SyncOperation

pytestmark = pytest.mark.django_db

DEVICE_A = "a3f9c1d2e4b6a8c0"
DEVICE_B = "b7e2d4f6a8c0e2d4"
WHEN = datetime(2026, 8, 16, 6, 41, 10, tzinfo=UTC)


def as_device(api, user, device_id):
    tokens = _issue_tokens(user, device_id)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}")
    return api


def record(user, device_id, status, *, error_code="", offset=0):
    return SyncOperation.objects.create(
        client_uuid=uuid.uuid4(),
        device_id=device_id,
        app_user=user,
        operation_type=SyncOperation.Type.DELIVERY_COMPLETE,
        client_created_at=WHEN + timedelta(minutes=offset),
        status=status,
        error_code=error_code,
    )


def get_status(api):
    return api.get(reverse("v1:sync-status"))


# ------------------------------------------------------------------ empty
def test_a_device_that_has_never_synced_gets_zeroes_not_an_error(api, salesman):
    """A fresh phone asks this question legitimately. Zeroes are the honest answer."""
    response = get_status(as_device(api, salesman, DEVICE_A))

    assert response.status_code == 200
    assert response.json() == {
        "device_id": DEVICE_A,
        "last_sync_at": None,
        "pending_count": 0,
        "deferred_count": 0,
        "rejected_count": 0,
        "rejected": [],
    }


# ------------------------------------------------------------------ counts
def test_counts_come_from_the_operation_statuses(api, salesman):
    record(salesman, DEVICE_A, SyncOperation.Status.RECEIVED)
    record(salesman, DEVICE_A, SyncOperation.Status.DEFERRED)
    record(salesman, DEVICE_A, SyncOperation.Status.DEFERRED)
    record(salesman, DEVICE_A, SyncOperation.Status.REJECTED, error_code="VALIDATION_FAILED")
    # Acknowledged work is not outstanding and must not inflate any counter.
    record(salesman, DEVICE_A, SyncOperation.Status.ACCEPTED)
    record(salesman, DEVICE_A, SyncOperation.Status.DUPLICATE)

    body = get_status(as_device(api, salesman, DEVICE_A)).json()

    assert body["pending_count"] == 1
    assert body["deferred_count"] == 2
    assert body["rejected_count"] == 1


def test_last_sync_at_is_the_most_recent_received_at(api, salesman):
    first = record(salesman, DEVICE_A, SyncOperation.Status.ACCEPTED)
    latest = record(salesman, DEVICE_A, SyncOperation.Status.ACCEPTED)
    # `received_at` is `auto_now_add`, so the second row is the later one by construction.
    assert latest.received_at >= first.received_at

    body = get_status(as_device(api, salesman, DEVICE_A)).json()

    assert body["last_sync_at"] is not None
    assert body["last_sync_at"].startswith(latest.received_at.strftime("%Y-%m-%dT%H:%M"))


# ------------------------------------------------------------------ isolation
def test_device_a_never_sees_device_b(api, salesman):
    """**The reason the device id comes from the token** (D-M9.3-1, FR-SYN-011).

    Same user, two phones. A client-supplied identifier would make this test unwritable,
    because the caller would simply ask for the other device.
    """
    record(salesman, DEVICE_B, SyncOperation.Status.DEFERRED)
    record(salesman, DEVICE_B, SyncOperation.Status.REJECTED, error_code="X")

    body = get_status(as_device(api, salesman, DEVICE_A)).json()

    assert body["device_id"] == DEVICE_A
    assert body["deferred_count"] == 0
    assert body["rejected_count"] == 0
    assert body["rejected"] == []


def test_a_query_string_device_id_is_ignored(api, salesman):
    """Belt and braces: the claim wins, and a supplied value changes nothing."""
    record(salesman, DEVICE_B, SyncOperation.Status.REJECTED, error_code="X")

    response = as_device(api, salesman, DEVICE_A).get(
        reverse("v1:sync-status"), {"device_id": DEVICE_B}
    )

    assert response.json()["device_id"] == DEVICE_A
    assert response.json()["rejected"] == []


# ------------------------------------------------------------------ rejected[]
def test_rejected_carries_exactly_the_four_frozen_fields(api, salesman):
    rejected = record(
        salesman, DEVICE_A, SyncOperation.Status.REJECTED, error_code="VALIDATION_FAILED"
    )
    rejected.error_detail = "Unknown delivery."
    rejected.payload = {"delivery_id": 999_999, "recipient_name": "Nobody"}
    rejected.save(update_fields=["error_detail", "payload"])

    entry = get_status(as_device(api, salesman, DEVICE_A)).json()["rejected"][0]

    # D-M9.3-2. `payload` is business data the device already holds; `error_detail` is prose
    # `05` §5 permits rewording, so no client may branch on it.
    assert set(entry) == {
        "client_uuid",
        "operation_type",
        "error_code",
        "client_created_at",
    }
    assert entry["client_uuid"] == str(rejected.client_uuid)
    assert entry["operation_type"] == "DELIVERY_COMPLETE"
    assert entry["error_code"] == "VALIDATION_FAILED"


def test_only_rejected_operations_are_listed(api, salesman):
    record(salesman, DEVICE_A, SyncOperation.Status.ACCEPTED)
    record(salesman, DEVICE_A, SyncOperation.Status.DEFERRED)
    record(salesman, DEVICE_A, SyncOperation.Status.REJECTED, error_code="X")

    body = get_status(as_device(api, salesman, DEVICE_A)).json()

    assert len(body["rejected"]) == 1
    assert body["rejected"][0]["error_code"] == "X"


# ------------------------------------------------------------------ auth
def test_unauthenticated_access_is_refused(api):
    assert get_status(api).status_code == 401


def test_a_session_minted_without_a_device_id_reports_on_the_empty_device(api, salesman):
    """Both auth serializers default `device_id` to `""` (proven in the M9.3 claim tests).

    That produces an empty claim rather than a missing one, so this answers zeroes instead
    of raising — degraded, but not broken, and visible to whoever reads it.
    """
    record(salesman, DEVICE_A, SyncOperation.Status.DEFERRED)

    tokens = _issue_tokens(salesman)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}")
    body = get_status(api).json()

    assert body["device_id"] == ""
    assert body["deferred_count"] == 0


# ------------------------------------------------------------------ read-only
def test_reading_the_status_mutates_nothing(api, salesman):
    """§11.5 is a view onto state, not a step in a workflow."""
    rows = [
        record(salesman, DEVICE_A, SyncOperation.Status.ACCEPTED),
        record(salesman, DEVICE_A, SyncOperation.Status.DEFERRED),
        record(salesman, DEVICE_A, SyncOperation.Status.REJECTED, error_code="X"),
    ]
    before = [(r.pk, r.status, r.processed_at, r.retry_count) for r in rows]

    get_status(as_device(api, salesman, DEVICE_A))
    get_status(as_device(api, salesman, DEVICE_A))

    for row in rows:
        row.refresh_from_db()
    after = [(r.pk, r.status, r.processed_at, r.retry_count) for r in rows]
    assert after == before
    assert SyncOperation.objects.count() == 3
