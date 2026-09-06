"""FR-RPT-009 / FR-SYN-015 — the sync health report and its Edition-1 metric.

**The metric is the whole risk here, not the SQL.** `01` §10.3 measures *"sync conflicts
requiring manual intervention <= 1% of synchronised transactions"*, and `02` §5.3 marks both
Edition-1 conflict classes — `SC-DUPLICATE` and `SC-SEQUENCE` — **automatic**. A report that
counted either would publish a number that does not mean what its own requirement says, which
is precisely the defect amendment S-5 existed to fix for FR-SYN-008's *"count of unresolved
conflicts"*. So the exclusions below are asserted individually rather than inferred from one
happy-path total.

The report reads `sync_operation` (`04` T-26) and nothing else: **no model, no migration**.
`sync.selectors.fleet_status` owns the counts because N-02 forbids `reporting` importing
another module's models; `reporting` owns the *definition*, because FR-SYN-015 is a reporting
requirement rather than a sync one.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from core.exceptions import PermissionDenied
from reporting import selectors as report_selectors
from sync import selectors as sync_selectors
from sync.models import SyncOperation

pytestmark = pytest.mark.django_db

DEVICE_A = "device-aaaa"
DEVICE_B = "device-bbbb"


def _operation(device: str, status: str, *, user) -> SyncOperation:
    """One recorded operation, built the way `test_sync_status_api.record` builds one.

    `error_code` is supplied for `REJECTED` because `ck_sync_operation_rejected` forbids the
    alternative: *"a rejection with no reason is a rejection nobody can act on"* (BR-014).
    """
    return SyncOperation.objects.create(
        client_uuid=uuid.uuid4(),
        device_id=device,
        app_user=user,
        operation_type=SyncOperation.Type.VISIT_CREATE,
        client_created_at=timezone.now(),
        status=status,
        error_code="VALIDATION_FAILED" if status == SyncOperation.Status.REJECTED else "",
    )


def _row(table, device: str) -> dict:
    return next(row for row in table.rows if row["device_id"] == device)


# ------------------------------------------------------------------ aggregation
def test_counts_every_status_for_one_device(owner):
    """1 — the counts are what the fleet selector reports, per status."""
    for status in (
        SyncOperation.Status.ACCEPTED,
        SyncOperation.Status.DUPLICATE,
        SyncOperation.Status.DEFERRED,
        SyncOperation.Status.REJECTED,
        SyncOperation.Status.RECEIVED,
    ):
        _operation(DEVICE_A, status, user=owner)

    table = report_selectors.sync_health(owner)
    row = _row(table, DEVICE_A)

    assert (row["accepted"], row["duplicate"], row["deferred"]) == (1, 1, 1)
    assert (row["rejected"], row["in_flight"]) == (1, 1)


def test_multiple_devices_aggregate_separately_and_total(owner):
    """8 — one row per device, plus a fleet total. Devices must not bleed into each other."""
    for _ in range(3):
        _operation(DEVICE_A, SyncOperation.Status.ACCEPTED, user=owner)
    _operation(DEVICE_B, SyncOperation.Status.REJECTED, user=owner)

    table = report_selectors.sync_health(owner)

    assert [row["device_id"] for row in table.rows] == [DEVICE_A, DEVICE_B]
    assert _row(table, DEVICE_A)["settled"] == 3
    assert _row(table, DEVICE_B)["settled"] == 1
    assert table.total is not None
    assert table.total["settled"] == 4
    assert table.total["rejected"] == 1


# ------------------------------------------------------- the FR-SYN-015 numerator
def test_rejected_is_the_numerator(owner):
    """5 — one rejection in four settled operations is 25%."""
    for _ in range(3):
        _operation(DEVICE_A, SyncOperation.Status.ACCEPTED, user=owner)
    _operation(DEVICE_A, SyncOperation.Status.REJECTED, user=owner)

    row = _row(report_selectors.sync_health(owner), DEVICE_A)

    assert row["settled"] == 4
    assert row["conflict_rate"] == Decimal("25.00")


def test_duplicate_is_not_a_conflict(owner):
    """3 — `02` §5.3 marks `SC-DUPLICATE` **automatic**; BR-012 calls a replay success.

    A duplicate must raise the denominator and leave the numerator alone. Counting it would
    make a healthy retrying fleet look like a failing one.
    """
    _operation(DEVICE_A, SyncOperation.Status.ACCEPTED, user=owner)
    _operation(DEVICE_A, SyncOperation.Status.DUPLICATE, user=owner)

    row = _row(report_selectors.sync_health(owner), DEVICE_A)

    assert row["duplicate"] == 1
    assert row["settled"] == 2
    assert row["conflict_rate"] == Decimal("0.00")


def test_deferred_the_sc_sequence_outcome_is_not_a_conflict(owner):
    """4 — `SC-SEQUENCE` is *"held; retried automatically"*, i.e. `DEFERRED`. Also automatic.

    It is a synchronised transaction, so it counts in the denominator; it needs no human, so
    it is not in the numerator.
    """
    _operation(DEVICE_A, SyncOperation.Status.DEFERRED, user=owner)
    _operation(DEVICE_A, SyncOperation.Status.REJECTED, user=owner)

    row = _row(report_selectors.sync_health(owner), DEVICE_A)

    assert row["deferred"] == 1
    assert row["settled"] == 2
    assert row["conflict_rate"] == Decimal("50.00")


def test_received_is_excluded_from_the_denominator(owner):
    """6 — `05` §11.5: `RECEIVED` is *"business processing not completed"*.

    It is not yet a synchronised transaction, so it cannot dilute the proportion — but it is
    reported as `in_flight`, because a persistent value there is an orphan.
    """
    _operation(DEVICE_A, SyncOperation.Status.REJECTED, user=owner)
    for _ in range(9):
        _operation(DEVICE_A, SyncOperation.Status.RECEIVED, user=owner)

    row = _row(report_selectors.sync_health(owner), DEVICE_A)

    assert row["in_flight"] == 9
    assert row["settled"] == 1
    assert row["conflict_rate"] == Decimal("100.00"), "RECEIVED must not dilute the rate"


def test_a_zero_denominator_is_undefined_never_zero(owner):
    """7 — a device with only in-flight work has demonstrated nothing.

    `0%` would assert integrity that was never measured. `None` renders as an empty cell —
    `csv._format`: *"None is empty, never 'None'"* — so the honest answer survives the export.
    """
    _operation(DEVICE_A, SyncOperation.Status.RECEIVED, user=owner)

    row = _row(report_selectors.sync_health(owner), DEVICE_A)

    assert row["settled"] == 0
    assert row["conflict_rate"] is None


def test_an_empty_fleet_reports_no_rows_and_no_total(owner):
    """A valid empty report, not an error — and no `Total 0` line to misread as measured."""
    table = report_selectors.sync_health(owner)

    assert table.rows == ()
    assert table.total is None


# ------------------------------------------------------------------ the contract
def test_the_report_carries_its_own_definition(owner):
    """12 — M7-1. A figure whose meaning lives elsewhere becomes folklore once it is emailed."""
    table = report_selectors.sync_health(owner)

    assert table.definition == report_selectors.SYNC_HEALTH_DEFINITION
    assert "REJECTED" in table.definition
    assert "SC-DUPLICATE" in table.definition


def test_rows_are_not_empty_when_operations_exist(owner):
    """13 — anti-vacuity. Every assertion above is quantified over rows; if the selector ever
    returned nothing, they would all pass while the report was blank."""
    _operation(DEVICE_A, SyncOperation.Status.ACCEPTED, user=owner)

    table = report_selectors.sync_health(owner)

    assert table.rows, "operations exist but the report is empty"
    assert table.columns


# --------------------------------------------------------------- authorisation
def test_a_retailer_is_refused(retailer):
    """10 — the boundary `_internal` already draws for all seven existing reports."""
    with pytest.raises(PermissionDenied):
        report_selectors.sync_health(retailer)


def test_an_internal_role_may_read_the_fleet(owner):
    """9 — and the scope really is the fleet, not the caller's own device."""
    _operation(DEVICE_A, SyncOperation.Status.ACCEPTED, user=owner)
    _operation(DEVICE_B, SyncOperation.Status.ACCEPTED, user=owner)

    table = report_selectors.sync_health(owner)

    assert {row["device_id"] for row in table.rows} == {DEVICE_A, DEVICE_B}


def test_the_fleet_selector_takes_no_device_argument(owner):
    """14 — scope cannot be escaped because there is nothing to escape *into*.

    `fleet_status` has no `device_id` parameter, so no request value can reach one. The
    device-scoped view is `sync.selectors.device_status`, whose caller takes `device_id` from
    the JWT (D-M9.3-1) — the two are separate functions on purpose.
    """
    import inspect

    parameters = inspect.signature(sync_selectors.fleet_status).parameters

    assert "device_id" not in parameters
    assert set(parameters) == {"date_from", "date_to"}
