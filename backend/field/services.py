"""Visit capture (04 T-23, FR-SYN-002 field evidence).

**One writer, and it is append-only.** A visit is an observation; nothing here updates or
deletes one. The sync layer coordinates dispatch — the rule that a repeat is the original
row rather than a second visit lives here, with the constraint that enforces it.
"""

from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction

from core.exceptions import ValidationFailed
from core.models import AuditLog
from core.permissions import Role, require_roles
from core.services import record_audit
from customers.models import Customer
from field.models import Visit


def record_visit(
    *,
    actor: Any,
    customer_id: int,
    visited_at: Any,
    outcome: str = "",
    notes: str = "",
    latitude: Decimal | None = None,
    longitude: Decimal | None = None,
    accuracy_metres: Decimal | None = None,
    device_id: str = "",
    client_uuid: uuid_lib.UUID | str | None = None,
) -> Visit:
    """Record one call on one shop.

    **Idempotent on ``client_uuid``** (AD-09, BR-012, I-4/I-6). A replay returns the
    original visit rather than a second one — and the guarantee is
    ``uq_visit_client_uuid``, not the lookup below, because a concurrent double-submit
    defeats a check but not a constraint.

    Coordinates are accepted together or not at all: ``ck_visit_coords`` refuses a
    half-fix, and a latitude with no longitude is not a place.
    """
    require_roles(actor, *Role.INTERNAL)

    key = _as_uuid(client_uuid)
    if key is not None:
        replay = Visit.objects.filter(client_uuid=key).first()
        if replay is not None:
            return replay  # I-4: the original resource, not a duplicate and not an error

    if (latitude is None) != (longitude is None):
        raise ValidationFailed(
            "Latitude and longitude must be given together.",
            errors=[
                {
                    "field": "latitude",
                    "code": "COORDS_INCOMPLETE",
                    "message": "Latitude and longitude must be given together.",
                }
            ],
        )

    if outcome and outcome not in Visit.Outcome.values:
        raise ValidationFailed(
            "Unknown visit outcome.",
            errors=[
                {
                    "field": "outcome",
                    "code": "INVALID_CHOICE",
                    "message": f"'{outcome}' is not a visit outcome.",
                }
            ],
        )

    customer = Customer.objects.filter(pk=customer_id).first()
    if customer is None:
        raise ValidationFailed(
            "Unknown customer.",
            errors=[
                {
                    "field": "customer_id",
                    "code": "NOT_FOUND",
                    "message": "No customer with that id.",
                }
            ],
        )

    try:
        # A savepoint for the same reason `complete_delivery` uses one: the check above
        # races, and an IntegrityError without it would abort the caller's whole
        # transaction — turning a legitimate retry into a 500 rather than the original row.
        with transaction.atomic():
            visit = Visit.objects.create(
                client_uuid=key,
                customer=customer,
                app_user=actor,
                visited_at=visited_at,
                outcome=outcome,
                notes=notes,
                latitude=latitude,
                longitude=longitude,
                accuracy_metres=accuracy_metres,
                device_id=device_id[:64],
            )
    except IntegrityError:
        replay = Visit.objects.filter(client_uuid=key).first()
        if replay is None:
            raise
        return replay

    record_audit(
        action=AuditLog.Action.CREATE,
        entity_type="visit",
        entity_id=visit.pk,
        actor=actor,
        surface=AuditLog.Surface.API,
        device_id=device_id,
        after_state={"customer_id": customer.pk, "outcome": outcome},
    )
    return visit


def _as_uuid(client_uuid: uuid_lib.UUID | str | None) -> uuid_lib.UUID | None:
    if client_uuid is None or client_uuid == "":
        return None
    if isinstance(client_uuid, uuid_lib.UUID):
        return client_uuid
    return uuid_lib.UUID(str(client_uuid))
