"""The sync receiver (05 §11.2, 04 T-26).

**This layer coordinates; it owns no business rule.** Every operation is dispatched into
the module that already knows how to perform it — `fulfilment` for a delivery, `field` for
a visit — so there is exactly one implementation of each rule and the sync path cannot
drift from the direct API path.

**Serial, in array order, never sorted** (PU-1…PU-3). The array position *is* creation
order (FR-SYN-002); `client_created_at` is metadata, and putting a device clock on the
ordering path is what P-4 forbids.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import DomainError, ValidationFailed
from field import services as field_services
from fulfilment import selectors as fulfilment_selectors
from fulfilment import services as fulfilment_services
from sync.models import SyncOperation

#: `05` §13. A batch beyond this is refused whole — the client's outbox is the queue, so
#: nothing is lost by asking it to send less.
MAX_BATCH = 200


def process_push(
    *, actor: Any, device_id: str, operations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Apply a batch and return one result per operation, in the same order.

    **Each operation gets its own transaction.** `05` §11.2's `202` means *"received and
    processed per operation"*; rolling the batch back because operation nine failed would
    discard eight successful ones and hand the device back work it had already delivered.
    FR-SYN-004 and FR-SYN-017 both require the opposite: partial progress is retained.
    """
    if len(operations) > MAX_BATCH:
        raise ValidationFailed(
            f"A batch may carry at most {MAX_BATCH} operations.",
            errors=[
                {
                    "field": "operations",
                    "code": "BATCH_TOO_LARGE",
                    "message": f"{len(operations)} operations; the limit is {MAX_BATCH}.",
                }
            ],
        )

    return [
        _process_one(actor=actor, device_id=device_id, operation=operation)
        for operation in operations
    ]


def _process_one(
    *, actor: Any, device_id: str, operation: dict[str, Any]
) -> dict[str, Any]:
    client_uuid = operation["client_uuid"]

    # **The replay check comes first**, with a database constraint underneath it. 04 T-26:
    # every device write is recorded here *before* the business operation is attempted.
    existing = SyncOperation.objects.filter(client_uuid=client_uuid).first()
    if existing is not None:
        # BR-012 / I-4: a replay is success, and it reports what the original produced.
        return _result(existing, status=SyncOperation.Status.DUPLICATE)

    handler = _HANDLERS.get(operation["operation_type"])

    try:
        with transaction.atomic():
            record = SyncOperation.objects.create(
                client_uuid=client_uuid,
                device_id=device_id,
                app_user=actor,
                operation_type=operation["operation_type"],
                client_created_at=operation["client_created_at"],
            )
    except IntegrityError:
        # Two requests racing on one key. The constraint decided; read the winner rather
        # than guess which one it was.
        winner = SyncOperation.objects.filter(client_uuid=client_uuid).first()
        if winner is None:
            raise
        return _result(winner, status=SyncOperation.Status.DUPLICATE)

    if handler is None:
        return _reject(
            record,
            operation,
            code="SYNC_UNSUPPORTED_OPERATION",
            detail=f"{operation['operation_type']} is not supported by this server.",
        )

    try:
        with transaction.atomic():
            entity_type, entity_id = handler(
                actor=actor, device_id=device_id, operation=operation
            )
    except DomainError as error:
        # **A refused operation is kept, never discarded** (FR-SYN-006, C-3, P-5). The
        # payload is stored only here, because this row is now the owner's evidence.
        return _reject(record, operation, code=error.code, detail=error.detail)

    record.status = SyncOperation.Status.ACCEPTED
    record.result_entity_type = entity_type
    record.result_entity_id = entity_id
    record.processed_at = timezone.now()
    record.save(
        update_fields=["status", "result_entity_type", "result_entity_id", "processed_at"]
    )
    return _result(record)


def _reject(
    record: SyncOperation, operation: dict[str, Any], *, code: str, detail: str
) -> dict[str, Any]:
    record.status = SyncOperation.Status.REJECTED
    record.error_code = code[:50]
    record.error_detail = detail
    record.payload = operation.get("payload")
    record.processed_at = timezone.now()
    record.save(
        update_fields=["status", "error_code", "error_detail", "payload", "processed_at"]
    )
    return _result(record)


def _result(record: SyncOperation, *, status: str | None = None) -> dict[str, Any]:
    return {
        "client_uuid": str(record.client_uuid),
        "status": status or record.status,
        "entity_type": record.result_entity_type,
        "entity_id": record.result_entity_id,
        "error_code": record.error_code,
    }


# ------------------------------------------------------------------ dispatchers
def _handle_delivery_complete(
    *, actor: Any, device_id: str, operation: dict[str, Any]
) -> tuple[str, int]:
    """Dispatch into the fulfilment service TD-39 already made idempotent.

    **No completion logic is repeated here.** `complete_delivery` owns the state machine
    and its own `outcome_client_uuid` guard — 04 T-26's defence in depth, for any path
    that bypasses this table.
    """
    payload = operation["payload"]
    # **The scoped selector, not the manager.** `get_delivery_for` applies the same
    # per-user visibility `POST /deliveries/{id}/complete` applies — without it, sync would
    # be a second path to the same mutation with weaker authorisation than the first, which
    # is precisely the divergence N-06 and FR-SYN-012 exist to prevent. Its docstring is
    # the other half: *"scope violations look like absence, never like refusal"* (05 §4.1),
    # so an out-of-scope delivery is REJECTED as unknown and discloses nothing.
    delivery = fulfilment_selectors.get_delivery_for(actor, payload.get("delivery_id"))
    if delivery is None:
        raise ValidationFailed(
            "Unknown delivery.",
            errors=[
                {
                    "field": "delivery_id",
                    "code": "NOT_FOUND",
                    "message": "No delivery with that id.",
                }
            ],
        )

    completed = fulfilment_services.complete_delivery(
        actor=actor,
        delivery=delivery,
        recipient_name=str(payload.get("recipient_name") or ""),
        delivered_at=payload.get("delivered_at"),
        latitude=_decimal(payload.get("latitude")),
        longitude=_decimal(payload.get("longitude")),
        # PU-4: the batch supplies it. A `device_id` inside the payload is ignored.
        device_id=device_id,
        client_uuid=operation["client_uuid"],
    )
    return "delivery", completed.pk


def _handle_visit_create(
    *, actor: Any, device_id: str, operation: dict[str, Any]
) -> tuple[str, int]:
    payload = operation["payload"]
    visit = field_services.record_visit(
        actor=actor,
        customer_id=payload.get("customer_id"),
        visited_at=payload.get("visited_at"),
        outcome=str(payload.get("outcome") or ""),
        notes=str(payload.get("notes") or ""),
        latitude=_decimal(payload.get("latitude")),
        longitude=_decimal(payload.get("longitude")),
        accuracy_metres=_decimal(payload.get("accuracy_metres")),
        device_id=device_id,
        client_uuid=operation["client_uuid"],
    )
    return "visit", visit.pk


_HANDLERS: dict[str, Callable[..., tuple[str, int]]] = {
    SyncOperation.Type.DELIVERY_COMPLETE: _handle_delivery_complete,
    SyncOperation.Type.VISIT_CREATE: _handle_visit_create,
}


def _decimal(value: Any) -> Decimal | None:
    """AD-02: coordinates arrive as strings and stay exact. Never `float`."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValidationFailed("Malformed decimal in payload.") from error
