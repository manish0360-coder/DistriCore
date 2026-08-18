"""Reads over `sync_operation` (05 §11.5).

**One read path, and it never writes.** `GET /sync/status` exists so a device can compare
its own outbox depth against the server's view — *"a disagreement between the two is visible
rather than assumed away"*. An endpoint that mutated anything while answering that question
would make the two views agree by changing one of them.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Max, Q

from sync.models import SyncOperation


def device_status(*, device_id: str) -> dict[str, Any]:
    """`05` §11.5, for one device.

    **Scoped by `device_id` and nothing else.** The caller takes that value from the
    authenticated JWT claim (D-M9.3-1), never from the request, so device isolation is a
    property of the token rather than of a filter someone can forget to apply.

    An unknown device is not an error: a phone that has never synced asks this question
    legitimately, and the honest answer is zeroes and a null `last_sync_at`.
    """
    operations = SyncOperation.objects.filter(device_id=device_id)

    # One query for all four aggregates. `pending` here is the **server's** notion —
    # recorded but not yet resolved — which is deliberately not the device's notion of
    # pending (unsent). The two differing is the information this endpoint exists to expose.
    totals = operations.aggregate(
        last_sync_at=Max("received_at"),
        pending_count=Count("id", filter=Q(status=SyncOperation.Status.RECEIVED)),
        deferred_count=Count("id", filter=Q(status=SyncOperation.Status.DEFERRED)),
        rejected_count=Count("id", filter=Q(status=SyncOperation.Status.REJECTED)),
    )

    rejected = (
        operations.filter(status=SyncOperation.Status.REJECTED)
        # The owner's exception list, newest last so the device shows them in the order they
        # were captured. `ix_sync_op_exceptions` is the partial index this walks.
        .order_by("client_created_at")
        # **Exactly the four frozen fields (D-M9.3-2).** `payload` is business data the
        # device already holds — echoing it back doubles the exposure for no gain — and
        # `error_detail` is prose `05` §5 permits rewording, so no client may branch on it.
        .values_list("client_uuid", "operation_type", "error_code", "client_created_at")
    )

    return {
        "device_id": device_id,
        "last_sync_at": totals["last_sync_at"],
        "pending_count": totals["pending_count"],
        "deferred_count": totals["deferred_count"],
        "rejected_count": totals["rejected_count"],
        "rejected": [
            {
                "client_uuid": str(client_uuid),
                "operation_type": operation_type,
                "error_code": error_code,
                "client_created_at": client_created_at,
            }
            for client_uuid, operation_type, error_code, client_created_at in rejected
        ],
    }
