"""**M9 → M10 gate — adversarial sync integrity.** First case: the killed process.

`00` §19.2 gates M9 on *"adversarial sync suite passes: zero loss, zero duplicates"*, and
`02` §25.2 names the method: *"Fault injection: severed connections, replayed batches,
**killed processes**, clock skew, exhausted storage."* `02` §18 adds the reason this file is
adversarial rather than integration: *"A green happy-path suite is not evidence for these
requirements."*

**The window under test, and why it is suspected to exist.** `04` T-26 requires that *"every
device write is recorded here **before** the business operation is attempted"*, and
`sync.services._process_one` implements exactly that — in **two sibling transactions**:

    with transaction.atomic():                 # A — the SyncOperation row
        record = SyncOperation.objects.create(...)
    ...
    try:
        with transaction.atomic():             # B — the business effect
            entity_type, entity_id = handler(...)
    except DomainError as error:
        return _reject(...)

A is released before B is entered, so a failure inside B cannot undo A. If the process dies
in that window the row is left `RECEIVED` and the business effect never happened — and on
replay, `_process_one` returns `DUPLICATE` **without inspecting `existing.status`**, which
`05` §11.2 tells the client means *"Delete from the outbox. This is success."*

**The defect was suspected from reading the code, then reproduced here, then repaired.** Test
B failed on first run — one `SyncOperation` at `RECEIVED`, **zero** `Visit` rows, and a
`DUPLICATE` verdict telling the device to delete the only copy it had. `_process_one` now
routes an existing row through `_settle_existing`: `RECEIVED` is recovered under a row lock,
every other status keeps the verdict it had. These tests are the regression evidence, and
**the file is deliberately symmetric** — C and D prove the repair does not solve loss by
creating duplicates, which `01` §10.3 forbids just as absolutely.

**Test A is the anti-vacuity guard.** If it fails, the instrumentation is not reproducing the
intended intermediate state and **test B's result means nothing** — do not read B without A.

**No process is killed and nothing sleeps.** The interruption is injected at the seam
`_handle_visit_create` actually calls — `field.services.record_visit` — by a wrapper that
performs the real write and *then* raises. The write is therefore genuinely attempted and
genuinely rolled back with transaction B, which is a stricter reproduction than never
entering the business code at all. The exception is deliberately **not** a `DomainError`, so
`_process_one`'s `except DomainError` cannot convert it into an orderly `REJECTED`: a killed
process does not raise a domain error.

**On isolation.** These run under the suite's default `django_db` (savepoint) semantics, not
`transaction=True`. That is a deliberate trade and it is stated so nobody over-reads a pass:

* **What it proves.** A and B are *siblings*. A is released before B is entered, so B's
  rollback cannot reach A. That relationship is identical at both isolation levels, and it is
  the whole of the structural property under test.
* **What it does not prove.** That A survives a real process death as a committed row. In
  production it does — `config/settings/base.py` sets ``ATOMIC_REQUESTS = False`` with the
  comment *"transactions are explicit, in services"*, so A is a genuine top-level commit and
  there is no enclosing request transaction to roll it back.
* **Why not `transaction=True`.** pytest-django's transactional mode flushes the database on
  teardown, and without ``serialized_rollback`` that discards migration-seeded rows —
  `ReasonCode`, the default `StockLocation` — which the rest of the suite reads. Turning the
  whole suite red to harden one assertion is the wrong trade; if durability itself is ever
  doubted, that is its own change with its own verify run.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from field import services as field_services
from field.models import Visit
from fulfilment.models import Delivery
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.selectors import on_hand_for
from inventory.services import receive_stock
from orders.services import confirm_order, place_order
from sync.models import SyncOperation
from sync.services import process_push

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]

DEVICE = "a3f9c1d2e4b6a8c0"
WHEN = "2026-08-16T06:41:10Z"
KEY = "7c9e6679-7425-40de-944b-e07fc1f90ae7"


class ProcessKilled(RuntimeError):
    """The instrumented interruption.

    **Deliberately not a `DomainError`.** `_process_one` catches `DomainError` and converts
    it into a `REJECTED` row with a reason — an orderly refusal, which is the opposite of the
    event being simulated. A killed worker, an OOM, a dropped database connection and a
    container stop all leave the handler mid-flight with no verdict at all, and that is what
    must escape here.
    """


def visit_op(customer: Any, *, client_uuid: str = KEY) -> dict[str, Any]:
    """One `VISIT_CREATE`, in `05` §11.2's shape.

    `VISIT_CREATE` rather than `DELIVERY_COMPLETE` on purpose: a visit is append-only with a
    single writer (`04` T-23), so the count of visits for one `client_uuid` is an unambiguous
    oracle. A delivery carries its own TD-39 idempotency guard, which would mask the very
    thing under test.
    """
    return {
        "client_uuid": client_uuid,
        "operation_type": "VISIT_CREATE",
        "client_created_at": WHEN,
        "payload": {"customer_id": customer.pk, "visited_at": WHEN, "outcome": "NO_ORDER"},
    }


def delivery_op(delivery: Any, *, client_uuid: str = KEY) -> dict[str, Any]:
    return {
        "client_uuid": client_uuid,
        "operation_type": "DELIVERY_COMPLETE",
        "client_created_at": WHEN,
        "payload": {"delivery_id": delivery.pk, "recipient_name": "Sharma ji"},
    }


@pytest.fixture
def dispatched(owner, credit_customer, product, receipt_reason):
    """A delivery that has left the warehouse — the only state an outcome is legal from."""
    receive_stock(
        actor=owner, product=product, quantity=Decimal("500"), reason_code=receipt_reason
    )
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": product, "quantity": "10"}]
    )
    confirm_order(actor=owner, order=order)
    delivery = assign_delivery(actor=owner, order=order, assigned_user=owner)
    return dispatch_delivery(actor=owner, delivery=delivery)


@pytest.fixture
def kill_before_the_outcome_is_recorded(monkeypatch):
    """Interrupt **after** transaction B released and **before** the status write.

    This is the harder half of the window and the one the repair must not double-apply: the
    business effect is durable, and the `SyncOperation` still says `RECEIVED`. `_apply` sets
    `status`, `result_entity_*` and `processed_at` in memory and then saves them in one
    `update_fields` call — so raising on the first status-bearing save of a `SyncOperation`
    lands exactly on that boundary, with the handler's transaction already released.
    """
    real = SyncOperation.save
    calls: list[str] = []

    def wrapper(self: SyncOperation, *args: Any, **kwargs: Any) -> None:
        fields = kwargs.get("update_fields") or ()
        if "status" in fields:
            calls.append(str(self.pk))
            raise ProcessKilled("interrupted after the business effect became durable")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(SyncOperation, "save", wrapper)
    return calls


@pytest.fixture
def kill_after_the_visit_is_written(monkeypatch):
    """Interrupt inside transaction B, after the real write and before it can commit.

    Patches the module attribute `sync.services` resolves at call time
    (`field_services.record_visit`), so the production dispatch path is unchanged and the
    real service does the real work before the interruption lands.
    """
    real = field_services.record_visit
    calls: list[str] = []

    def wrapper(**kwargs: Any) -> Visit:
        visit = real(**kwargs)
        calls.append(str(visit.pk))
        raise ProcessKilled("interrupted after the business write, before it was durable")

    monkeypatch.setattr(field_services, "record_visit", wrapper)
    return calls


# ------------------------------------------------------------------ A. the window exists
def test_an_interrupted_operation_leaves_a_received_row_and_no_visit(
    owner, customer, kill_after_the_visit_is_written
):
    """**Anti-vacuity guard.** Proves the instrumentation reaches the intended state.

    If this fails, the harness is not reproducing the window and test B below is meaningless
    whichever way it goes.
    """
    with pytest.raises(ProcessKilled):
        process_push(actor=owner, device_id=DEVICE, operations=[visit_op(customer)])

    # The business write really was attempted — not skipped — and then really was undone.
    assert kill_after_the_visit_is_written, "record_visit was never reached"
    assert Visit.objects.filter(client_uuid=KEY).count() == 0, (
        "transaction B did not roll back; the interruption is landing in the wrong place"
    )

    # And transaction A survived it, because A was released before B was entered.
    record = SyncOperation.objects.get(client_uuid=KEY)
    assert record.status == SyncOperation.Status.RECEIVED
    assert record.processed_at is None
    assert record.result_entity_id is None


# ------------------------------------------------------------------ B. the oracle
def test_replaying_an_interrupted_operation_must_not_lose_the_visit(
    owner, customer, kill_after_the_visit_is_written, monkeypatch
):
    """**`01` §10.3, non-negotiable: zero lost, zero duplicated.**

    A device that receives no response keeps the row `PENDING` and resends it — that is
    FR-SYN-004's *"sync MUST be resumable"* and `05` §11.2's `REJECTED`/no-verdict handling.
    After that resend the ledger must contain the work exactly once.

    The oracle is the count of `Visit` rows for the `client_uuid` (BR-014, FR-SYN-004,
    FR-SYN-006). **1 is the only passing value.** `0` is a lost transaction; `2` or more is a
    duplicate; both are the failures `00` §19.2 gates M9 on.
    """
    # Steps 1-3: the interrupted first attempt.
    with pytest.raises(ProcessKilled):
        process_push(actor=owner, device_id=DEVICE, operations=[visit_op(customer)])

    # **The process restarted: the interruption is gone, the queue is not.** `monkeypatch` is
    # one function-scoped object shared with the fixture, so this restores the real
    # `record_visit` — the resend below runs entirely unpatched production code.
    monkeypatch.undo()
    assert field_services.record_visit.__module__ == "field.services"

    # 4. The device resends the same operation under the same key (P-6, BR-012).
    results = process_push(actor=owner, device_id=DEVICE, operations=[visit_op(customer)])

    # 5. The invariant.
    assert SyncOperation.objects.filter(client_uuid=KEY).count() == 1, (
        "one operation, one row — the `uq_sync_operation_client_uuid` guarantee"
    )
    assert Visit.objects.filter(client_uuid=KEY).count() == 1, (
        "ZERO LOSS / ZERO DUPLICATES (`01` §10.3). The visit the salesman recorded must "
        "exist exactly once after an interrupted attempt and a resend. A count of 0 means "
        "the transaction was lost and the replay reported success for work that never "
        "happened; a count above 1 means sync created a duplicate."
    )

    # The row must not still claim the work is unfinished once the device has been answered.
    record = SyncOperation.objects.get(client_uuid=KEY)
    assert record.status == SyncOperation.Status.ACCEPTED, (
        "recovery finished the operation, so the row records the outcome it produced"
    )
    assert record.result_entity_type == "visit"
    assert record.result_entity_id == Visit.objects.get(client_uuid=KEY).pk
    assert record.processed_at is not None

    # And the verdict the device was given is the one that matches what happened.
    assert results[0]["status"] == SyncOperation.Status.ACCEPTED


# ---------------------------------------------- C. the repair must not double-apply
def test_recovering_work_that_already_committed_does_not_duplicate_it(
    owner, customer, kill_before_the_outcome_is_recorded, monkeypatch
):
    """**The other half of the window, and the one the repair itself could break.**

    Here transaction B *committed* — the visit is durable — and only the status write was
    lost. A recovery that re-enters the handler blindly would create a second visit; the
    reason it does not is `record_visit`'s `client_uuid` lookup backed by the unique index
    on `visit.client_uuid` (04 T-26, *"defence in depth"*).

    Without this test the loss fix would be untested against duplication, and `01` §10.3
    forbids both equally.
    """
    with pytest.raises(ProcessKilled):
        process_push(actor=owner, device_id=DEVICE, operations=[visit_op(customer)])

    assert kill_before_the_outcome_is_recorded, "the status write was never reached"

    # The intermediate state this case is about: effect durable, receipt unfinished.
    assert Visit.objects.filter(client_uuid=KEY).count() == 1
    assert SyncOperation.objects.get(client_uuid=KEY).status == SyncOperation.Status.RECEIVED

    monkeypatch.undo()
    results = process_push(actor=owner, device_id=DEVICE, operations=[visit_op(customer)])

    assert Visit.objects.filter(client_uuid=KEY).count() == 1, (
        "ZERO DUPLICATES (`01` §10.3): recovery re-entered a handler whose work already "
        "existed and must have resolved to the original row, not created a second one"
    )
    record = SyncOperation.objects.get(client_uuid=KEY)
    assert record.status == SyncOperation.Status.ACCEPTED
    assert record.result_entity_id == Visit.objects.get(client_uuid=KEY).pk
    assert results[0]["status"] == SyncOperation.Status.ACCEPTED


# ---------------------------------------------- D. the same window on a delivery
def test_recovering_an_interrupted_delivery_completes_it_exactly_once(
    owner, dispatched, product, kill_before_the_outcome_is_recorded, monkeypatch
):
    """`DELIVERY_COMPLETE` carries stock and an order transition; both must move once.

    `complete_delivery` resolves a replay through `outcome_client_uuid`
    (`delivery_outcome_client_uuid_key`, I-6/TD-39) and returns the original row, so the
    recovery does not re-run `mark_delivered` over an order already delivered.
    """
    before = on_hand_for(product)

    with pytest.raises(ProcessKilled):
        process_push(actor=owner, device_id=DEVICE, operations=[delivery_op(dispatched)])

    dispatched.refresh_from_db()
    assert dispatched.status == Delivery.Status.DELIVERED, "transaction B committed"
    assert SyncOperation.objects.get(client_uuid=KEY).status == SyncOperation.Status.RECEIVED

    monkeypatch.undo()
    results = process_push(actor=owner, device_id=DEVICE, operations=[delivery_op(dispatched)])

    assert Delivery.objects.filter(outcome_client_uuid=KEY).count() == 1
    dispatched.refresh_from_db()
    assert dispatched.status == Delivery.Status.DELIVERED
    assert on_hand_for(product) == before, "a recovery must not move stock a second time"

    record = SyncOperation.objects.get(client_uuid=KEY)
    assert record.status == SyncOperation.Status.ACCEPTED
    assert record.result_entity_type == "delivery"
    assert results[0]["status"] == SyncOperation.Status.ACCEPTED


# ---------------------------------------------- E. terminal statuses are never re-run
def test_an_accepted_operation_still_answers_duplicate(owner, customer):
    """`05` §11.2 and BR-012 / I-4, unchanged by the repair.

    A finished operation must keep answering `DUPLICATE` — that is what tells the device it
    may delete the row, and it is correct there because the work really did happen.
    """
    first = process_push(actor=owner, device_id=DEVICE, operations=[visit_op(customer)])
    assert first[0]["status"] == SyncOperation.Status.ACCEPTED

    second = process_push(actor=owner, device_id=DEVICE, operations=[visit_op(customer)])

    assert second[0]["status"] == SyncOperation.Status.DUPLICATE
    assert second[0]["entity_id"] == first[0]["entity_id"], "the original resource (I-4)"
    assert Visit.objects.filter(client_uuid=KEY).count() == 1


def test_a_rejected_operation_is_terminal_and_is_not_re_run(owner, customer, monkeypatch):
    """**BR-014: the row is the owner's evidence, and a replay must not resurrect it.**

    A recovery that swept `REJECTED` into its retry would re-attempt work the server has
    already refused — and if the world had changed in between, would apply it.
    """
    # An unknown customer is refused by `record_visit` as a `ValidationFailed`.
    doomed = {**visit_op(customer), "payload": {"customer_id": 10**9, "visited_at": WHEN}}
    first = process_push(actor=owner, device_id=DEVICE, operations=[doomed])
    assert first[0]["status"] == SyncOperation.Status.REJECTED

    # The obstacle is gone — a retry that re-ran the handler would now succeed, which is
    # exactly what must not happen.
    second = process_push(actor=owner, device_id=DEVICE, operations=[visit_op(customer)])

    assert second[0]["status"] == SyncOperation.Status.DUPLICATE
    assert Visit.objects.filter(client_uuid=KEY).count() == 0, (
        "a REJECTED operation was re-run; BR-014 keeps it as evidence, it does not retry it"
    )
    record = SyncOperation.objects.get(client_uuid=KEY)
    assert record.status == SyncOperation.Status.REJECTED
    assert record.error_code, "ck_sync_operation_rejected: a rejection carries its reason"
    assert record.payload is not None, "the payload is retained as the owner's evidence"


# ---------------------------------------------- F. the recovery claims its row
def test_recovery_locks_the_operation_row_before_re_entering_the_handler(
    owner, customer, kill_after_the_visit_is_written, monkeypatch
):
    """**The serialisation mechanism, asserted deterministically.**

    Two workers recovering one key would otherwise both re-enter the handler and then race
    to write the outcome. `_recover` claims the row with `SELECT … FOR UPDATE` first.

    **What this proves:** the lock is actually taken, on the recovery path only. **What it
    does not prove:** the behaviour of two concurrent transactions — that needs real
    concurrency, and a threaded test here would be the timing-dependent kind this suite
    forbids. The second assertion covers the branch that concurrency would reach: a row
    already finished by the other worker answers `DUPLICATE` rather than running again.
    """
    with pytest.raises(ProcessKilled):
        process_push(actor=owner, device_id=DEVICE, operations=[visit_op(customer)])
    monkeypatch.undo()

    with CaptureQueriesContext(connection) as captured:
        process_push(actor=owner, device_id=DEVICE, operations=[visit_op(customer)])

    locking = [
        query["sql"]
        for query in captured.captured_queries
        if "FOR UPDATE" in query["sql"] and "sync_operation" in query["sql"]
    ]
    assert locking, "recovery did not claim the sync_operation row with SELECT … FOR UPDATE"

    # And the branch a loser of that race lands on: already finished, so answer DUPLICATE.
    again = process_push(actor=owner, device_id=DEVICE, operations=[visit_op(customer)])
    assert again[0]["status"] == SyncOperation.Status.DUPLICATE
    assert Visit.objects.filter(client_uuid=KEY).count() == 1
