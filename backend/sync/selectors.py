"""Reads over `sync_operation` (05 §11.5).

**One read path, and it never writes.** `GET /sync/status` exists so a device can compare
its own outbox depth against the server's view — *"a disagreement between the two is visible
rather than assumed away"*. An endpoint that mutated anything while answering that question
would make the two views agree by changing one of them.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from typing import Any

from django.db.models import Count, Max, Q, QuerySet
from django.utils import timezone

from core.exceptions import ValidationFailed
from customers.models import Customer
from customers.selectors import visible_customers
from fulfilment.selectors import visible_deliveries
from sync.models import SyncOperation

#: **O-5: 500 records per collection.** A server may cap below it; the contract a client
#: obeys is `has_more` and `next_page_token`, never the number (D-M9.4-5, corrected).
PULL_PAGE_SIZE = 500

#: A collection that has not started paging yet, distinct from one that has finished.
#: `None` in a decoded token means **exhausted**; this sentinel means **from the beginning**.
_START = object()


def pull(
    *, actor: Any, since: datetime | None, page_token: str | None = None
) -> dict[str, Any]:
    """`GET /sync/pull` for the two collections M9.4 implements (D-M9.4-2).

    **`server_time` is sampled once, here, before any query runs** (D-M9.4-4). Reading it
    afterwards would drop every row written between the query and the sample — the same
    silent skip §11.1 describes for a client's own clock, arriving from the other direction.

    **`since` absent is a full bootstrap** (P-1). **`updated_at >= since`** otherwise: `>`
    can permanently miss a row stamped in the same microsecond as the `server_time` that
    became this `since`, and a lost row is unrecoverable where a resent one is not.

    `products`, `offers`, `zones`, `reason_codes` and `orders` are **absent, not empty** —
    M9.4 does not implement them, and an empty collection would tell a client they exist and
    have nothing in them.
    """
    server_time = timezone.now()
    positions = _decode_token(page_token)

    customers, customers_next = _collect(
        visible_customers(actor), since, positions.get("c", _START)
    )
    deliveries, deliveries_next = _collect(
        visible_deliveries(actor), since, positions.get("d", _START)
    )

    has_more = customers_next is not None or deliveries_next is not None

    return {
        "server_time": server_time,
        "since": since,
        # **P-7.** Present exactly when `has_more`, absent otherwise. It carries a position
        # per collection so each advances independently — one scalar `since` could not, which
        # is what forced a token rather than a rewording of P-5 (D-M9.4-8).
        "next_page_token": _encode_token(customers_next, deliveries_next)
        if has_more
        else None,
        # P-5: the client repeats with the **same** `since` and this token until `has_more`
        # is false, then advances its persisted cursor. True while *either* collection is
        # still behind — a client must not advance while one of them is.
        "has_more": has_more,
        "customers": {
            "updated": list(customers),
            # **The only removal mechanism** (D-M9.4-3). Absence from a delta pull is not
            # deletion, and a customer rescoped out of this user's zones is a recorded
            # contract gap rather than something inferred here.
            #
            # Read **unscoped on purpose**: P-4 exists because *"a deactivated row may no
            # longer appear in `updated` under scoping"*. Only ids leave, never a field.
            # Sent on the **first page of a pull only** — the list is identical on every
            # page and removal is idempotent, so repeating it is waste rather than safety.
            # A deactivation that lands mid-pull is caught next pull, because the cursor has
            # not advanced.
            "deactivated_ids": []
            if page_token
            else list(_deactivated_customer_ids(since)),
        },
        # §11.1 gives deliveries `{updated}` only — no `deactivated_ids`. A delivery is not
        # deactivated; it reaches a terminal status and stays visible.
        "deliveries": {"updated": list(deliveries)},
    }


def _collect(
    queryset: QuerySet[Any], since: datetime | None, position: Any
) -> tuple[list[Any], tuple[str, int] | None]:
    """One bounded page of a collection, and where the next one resumes.

    Returns `(rows, next_position)`. **`next_position` is `None` when the collection is
    finished** — that is what lets `has_more` be false while the *other* collection is still
    paging, and what stops an exhausted collection being re-queried on every later page.

    **Keyset, not offset.** AD-10 rejected offset for sync by name: *"offset pagination
    silently skips rows when the underlying set changes mid-pagination — precisely the
    failure that loses a transaction (BR-014)."* A row inserted behind the cursor shifts
    every offset; it cannot shift a `(updated_at, id)` comparison.
    """
    if position is None:
        return [], None  # already exhausted on an earlier page

    if since is not None:
        # **`>= since` is untouched** (D-M9.4-4). The keyset below is a *position within this
        # pull*; the inclusive bound is the sync cursor. They are different questions.
        queryset = queryset.filter(updated_at__gte=since)

    if position is not _START:
        last_at, last_id = position
        queryset = queryset.filter(
            Q(updated_at__gt=last_at) | Q(updated_at=last_at, id__gt=last_id)
        )

    # The secondary sort is not cosmetic: `timestamptz` is microsecond-resolution but not
    # unique — one transaction can stamp two rows identically — and a tie split across a page
    # boundary drops or repeats a row. It is also what makes the keyset above total.
    rows = list(queryset.order_by("updated_at", "id")[: PULL_PAGE_SIZE + 1])

    if len(rows) <= PULL_PAGE_SIZE:
        return rows, None

    page = rows[:PULL_PAGE_SIZE]
    last = page[-1]
    return page, (last.updated_at.isoformat(), last.pk)


def _encode_token(
    customers: tuple[str, int] | None, deliveries: tuple[str, int] | None
) -> str:
    """**Opaque by contract** (P-7). The encoding is base64 JSON and a client must not read
    it — one that parsed this would couple itself to a server internal, which is the whole
    reason the contract says opaque rather than describing a shape."""
    payload = json.dumps({"c": customers, "d": deliveries}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_token(page_token: str | None) -> dict[str, Any]:
    """`{}` for the first page; `{"c": [...] | None, "d": [...] | None}` thereafter.

    A malformed token is a `422`, not a silent restart: restarting the pull would look like
    it worked and would quietly re-send every page.
    """
    if not page_token:
        return {}
    try:
        decoded = json.loads(base64.urlsafe_b64decode(page_token.encode()))
    except (ValueError, binascii.Error) as error:
        raise ValidationFailed(
            "Malformed page token.",
            errors=[
                {
                    "field": "page_token",
                    "code": "INVALID",
                    "message": "The continuation token could not be read.",
                }
            ],
        ) from error

    # **Structure is validated, not just syntax.** `{"not": "a token"}` is valid base64 and
    # valid JSON, and a decoder that only checked those would let every key fall back to
    # "start from the beginning" — silently restarting the pull and answering `200`. That is
    # the worst available outcome: it looks like it worked and re-sends every page.
    if not isinstance(decoded, dict) or set(decoded) != {"c", "d"}:
        raise _bad_token()

    return {key: _position(decoded[key]) for key in ("c", "d")}


def _position(value: Any) -> tuple[str, int] | None:
    """`None` for an exhausted collection, otherwise a validated `(updated_at, id)` pair.

    Every field is checked because each one reaches a database filter: an unparseable
    timestamp or a string id would surface as a `500` from deep inside the ORM rather than
    as the `422` the client can act on.
    """
    if value is None:
        return None

    if not isinstance(value, list) or len(value) != 2:
        raise _bad_token()

    updated_at, row_id = value

    # `bool` is a subclass of `int` in Python, so `True` would otherwise pass as an id.
    if not isinstance(row_id, int) or isinstance(row_id, bool) or row_id < 1:
        raise _bad_token()

    if not isinstance(updated_at, str):
        raise _bad_token()
    try:
        parsed = datetime.fromisoformat(updated_at)
    except ValueError:
        raise _bad_token() from None
    # N-08: everything is UTC-aware. A naive value compared against an aware column raises
    # inside the ORM, which is a 500 for what is really a bad request.
    if parsed.tzinfo is None:
        raise _bad_token()

    return (updated_at, row_id)


def _bad_token() -> ValidationFailed:
    """One message for every structural failure.

    Deliberately uninformative about *which* field was wrong: the token is opaque by
    contract (P-7), and a client that could learn its shape from error messages would start
    depending on it.
    """
    return ValidationFailed(
        "Malformed page token.",
        errors=[
            {
                "field": "page_token",
                "code": "INVALID",
                "message": "The continuation token could not be read.",
            }
        ],
    )


def _deactivated_customer_ids(since: datetime | None) -> QuerySet[Customer, int]:
    """Customers deactivated since the cursor.

    `is_active=False` **and** `updated_at >= since` — verified sound because
    `customers.services` deactivation saves with `update_fields=["is_active", "updated_at"]`,
    so the timestamp moves with the flag. Django fires `auto_now` only for fields actually
    written, so that had to be checked rather than assumed.

    On a full bootstrap (`since` absent) this is empty: a device with no cache has nothing to
    remove, and sending every customer ever deactivated would be a list it cannot use.
    """
    if since is None:
        return Customer.objects.none().values_list("id", flat=True)
    return (
        Customer.objects.filter(is_active=False, updated_at__gte=since)
        .order_by("id")
        .values_list("id", flat=True)
    )


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


def fleet_status(
    *, date_from: datetime | None = None, date_to: datetime | None = None
) -> list[dict[str, Any]]:
    """Per-device operation counts across **every** device — `05` §9.11.2, FR-RPT-009.

    **The sibling of `device_status`, and it lives here for the same reason.** `sync` owns
    `SyncOperation`; N-02 forbids another module importing it, and `reporting` already reaches
    `billing`, `inventory`, `orders` and `receivables` through their selectors and never
    through their models. So the read belongs on this side of the boundary and the *metric*
    belongs to `reporting`, which owns FR-SYN-015's definition.

    **Counts only — no derived rate.** This function states what happened; it does not decide
    what a "conflict" is. That decision is `01` §10.3's and it is applied one layer up, where
    it can be stated in the report's own `definition` and travel into the CSV (M7-1).

    **Deliberately unscoped by device.** `device_status` is scoped by a `device_id` its caller
    takes from the JWT (D-M9.3-1); this is the fleet view, and its authorisation is the
    `_internal` rule the report applies before calling. Keeping the two functions separate is
    what stops a device-facing endpoint ever growing a fleet-wide branch by accident.

    Ordered by `device_id` so the report and its CSV are stable between runs.
    """
    operations = SyncOperation.objects.all()
    if date_from is not None:
        operations = operations.filter(received_at__gte=date_from)
    if date_to is not None:
        operations = operations.filter(received_at__lte=date_to)

    grouped = (
        operations.values("device_id")
        .annotate(
            last_sync_at=Max("received_at"),
            accepted=Count("id", filter=Q(status=SyncOperation.Status.ACCEPTED)),
            duplicate=Count("id", filter=Q(status=SyncOperation.Status.DUPLICATE)),
            deferred=Count("id", filter=Q(status=SyncOperation.Status.DEFERRED)),
            rejected=Count("id", filter=Q(status=SyncOperation.Status.REJECTED)),
            # `RECEIVED` is recorded-but-not-resolved (`05` §11.5). It is reported so a
            # persistent value is visible as an orphan, and excluded from the denominator
            # one layer up because it is not yet a synchronised transaction.
            in_flight=Count("id", filter=Q(status=SyncOperation.Status.RECEIVED)),
        )
        .order_by("device_id")
    )
    return list(grouped)
