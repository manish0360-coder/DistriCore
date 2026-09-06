"""**TD-36 — a Decimal must never leave a report as a JSON number** (`05` AD-02).

TD-36, opened at M8 task 0 and carried since:

> *"The seven report endpoints **emit money as JSON floats**, against AD-02 — whose rationale
> names Dart and whose client obligation is C-1."*

`05` **AD-02**: *"Every monetary and quantity value crosses the wire as a string."*
`config.settings.base` sets ``COERCE_DECIMAL_TO_STRING``, but that reaches
``serializers.DecimalField`` only — and ``report_views._as_json`` hand-builds its response
dict, so DRF's encoder rendered ``Decimal("1180.00")`` as ``1180.0``.

**Why this survived four reviews and a blocking type gate.** The one assertion that touched
the figure read ``Decimal(str(body["total"]["sales"]))``. That ``str()`` makes it pass
whichever type arrives — a test that could not fail, guarding the principle P-3 says cannot
be repaired after the fact. This suite asserts the **wire type**, which is the thing that was
never asserted.

**The client half is already correct and needs no change.** ``mobile/lib/data/api/money.dart``
refuses a number outright — ``if (raw is num) throw MoneyFormatException.notAString(raw)`` —
so every float the server sends is a hard failure on the device rather than a silent rounding.
That is why TD-36 blocks Companion Mode: the frozen codec throws on the first cell.

**How the anti-vacuity proofs work.** The rule is a pure function, ``check_wire_format``, over
a rendered payload. The live tests feed it real API responses for **every registered report**;
the mutation tests feed it deliberately broken copies. Both exercise the same code, so a
mutation that passes is proof the rule is inert — the construction ``test_report_registration``
uses for ``check_registration``, applied to types instead of sets.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from billing.services import issue_invoice
from core.fields import to_money, to_quantity
from fulfilment.services import assign_delivery, dispatch_delivery
from inventory.services import receive_stock
from orders.services import confirm_order, place_order
from reporting.tables import ColumnKind
from sync.models import SyncOperation

pytestmark = [pytest.mark.adversarial, pytest.mark.django_db]

#: The kinds AD-02 governs, and the canonical form each must arrive in.
#:
#: `04` §1.6 fixes the scales — money ``NUMERIC(14,2)``, quantity ``NUMERIC(14,3)`` — and
#: `05` AD-02 fixes the string form (``"12450.00"``, ``"24.000"``). ``RATE`` is a percentage
#: at two places, the scale ``core.fields.to_percent`` has always used.
CANONICAL = {
    ColumnKind.MONEY.value: re.compile(r"^-?\d+\.\d{2}$"),
    ColumnKind.QUANTITY.value: re.compile(r"^-?\d+\.\d{3}$"),
    ColumnKind.RATE.value: re.compile(r"^-?\d+\.\d{2}$"),
}

#: Exact in JSON already. Stringifying a count would break AD-02's intent in the other
#: direction — the reason a semantic kind replaced ``numeric: bool``.
COUNT = ColumnKind.COUNT.value


# --------------------------------------------------------------------------- the rule
def check_wire_format(
    *, columns: list[dict[str, Any]], rows: list[dict[str, Any]], total: dict[str, Any] | None
) -> list[str]:
    """The whole of TD-36, as a pure function. Returns failures; empty means conformant.

    **Pure and total on purpose.** It reaches for nothing — no client, no URL conf, no
    database — so the mutation tests can hand it any shape at all, including shapes a running
    system could not produce. A rule exercisable only against live output could only ever be
    proven to pass.
    """
    failures: list[str] = []
    kinds = {column["key"]: column.get("kind") for column in columns}

    for label, record in [*((f"row {i}", r) for i, r in enumerate(rows)), ("total", total or {})]:
        for key, value in record.items():
            kind = kinds.get(key)
            where = f"{label}.{key}"

            # The catch-all, and the one that does not depend on a column being declared.
            # `rows` carries every key the selector produced: `_sales_by_customer` emits a
            # `key` no column names, and an undeclared Decimal would reach the encoder.
            if isinstance(value, float):
                failures.append(f"{where}: {value!r} is a JSON number — AD-02 requires a string")
                continue

            if kind in CANONICAL:
                if not isinstance(value, str):
                    if value is None:
                        continue  # a blank cell is an absent measurement, not a value
                    failures.append(
                        f"{where}: {kind} arrived as {type(value).__name__} {value!r}, "
                        "not a string"
                    )
                elif not CANONICAL[kind].match(value):
                    failures.append(f"{where}: {kind} {value!r} is not canonical")
            elif kind == COUNT and not isinstance(value, (int, type(None))):
                failures.append(
                    f"{where}: COUNT arrived as {type(value).__name__} {value!r}; a count is "
                    "exact in JSON and must not be stringified"
                )

    return failures


# ------------------------------------------------------------------- the live adapters
@pytest.fixture
def stocked(owner, product, receipt_reason):
    receive_stock(
        actor=owner, product=product, quantity=Decimal("1000"), reason_code=receipt_reason
    )
    return product


@pytest.fixture
def exercised(owner, credit_customer, stocked):
    """Real data in **every** kind, because the rule is quantified over cells.

    Without rows the checks below are vacuous six times over, and without a *settled* sync
    operation ``conflict_rate`` is ``None`` and the only RATE column in the system is never
    exercised. ``test_every_kind_was_actually_seen`` is what makes that failure loud.
    """
    order = place_order(
        actor=owner, customer=credit_customer, lines=[{"product": stocked, "quantity": "10"}]
    )
    confirm_order(actor=owner, order=order)
    dispatch_delivery(
        actor=owner, delivery=assign_delivery(actor=owner, order=order, assigned_user=owner)
    )
    invoice = issue_invoice(actor=owner, order=order)

    for status in (SyncOperation.Status.ACCEPTED, SyncOperation.Status.REJECTED):
        SyncOperation.objects.create(
            client_uuid=uuid.uuid4(),
            device_id="device-wire",
            app_user=owner,
            operation_type=SyncOperation.Type.VISIT_CREATE,
            client_created_at=timezone.now(),
            status=status,
            # `ck_sync_operation_rejected`: a rejection with no reason is unactionable.
            error_code="VALIDATION_FAILED" if status == SyncOperation.Status.REJECTED else "",
        )
    return invoice


def _registered_reports() -> list[str]:
    """Every report, read from the registry rather than from a list maintained here.

    A hand-kept list would be a sixth place to forget a report — the failure TD-29 exists to
    catch — and this suite would then silently stop covering the newest endpoint.
    """
    from webadmin.report_views import REPORT_MENU

    return [f"v1:{name.split(':', 1)[-1]}" for name, _label in REPORT_MENU]


def _payload(client, name: str) -> dict[str, Any]:
    response = client.get(reverse(name))
    assert response.status_code == 200, f"{name} did not answer: {response.status_code}"
    return response.json()


# ------------------------------------------------------------------------ the contract
@pytest.mark.parametrize("name", _registered_reports())
def test_every_registered_report_conforms_to_ad_02(auth, owner, exercised, name):
    """**TD-36, closed.** Requirements 1-5 and 9, over every report at once."""
    failures = check_wire_format(**_report_parts(_payload(auth(owner), name)))
    assert not failures, f"{name} violates AD-02:\n  " + "\n  ".join(failures)


def _report_parts(body: dict[str, Any]) -> dict[str, Any]:
    return {"columns": body["columns"], "rows": body["rows"], "total": body["total"]}


def test_the_statement_conforms_too(auth, owner, exercised, credit_customer):
    """C-6's sixth report renders through the same ``_as_json`` and is easy to forget."""
    body = _payload_at(auth(owner), "v1:customer-statement", credit_customer.pk)
    assert not check_wire_format(**_report_parts(body))


def _payload_at(client, name: str, *args) -> dict[str, Any]:
    response = client.get(reverse(name, args=args))
    assert response.status_code == 200
    return response.json()


def test_every_kind_was_actually_seen(auth, owner, exercised):
    """Anti-vacuity for the fixtures. Every check above is quantified over cells.

    If the fixture stopped producing rows, or if a kind vanished from the column model, the
    parametrised test would pass while asserting nothing. This names the four kinds and
    fails if any of them never reached the wire.
    """
    seen: set[str] = set()
    for name in _registered_reports():
        body = _payload(auth(owner), name)
        kinds = {column["key"]: column["kind"] for column in body["columns"]}
        for record in [*body["rows"], body["total"] or {}]:
            for key, value in record.items():
                if key in kinds and value is not None:
                    seen.add(kinds[key])

    assert {"MONEY", "QUANTITY", "COUNT", "RATE"} <= seen, (
        f"a column kind never reached the wire, so its assertions were vacuous: saw {sorted(seen)}"
    )


def test_canonical_scales_are_the_ones_04_and_05_fix(auth, owner, exercised):
    """Requirements 6-8 — the scale is `04` §1.6's, not merely *a* scale.

    **Asserted as a fixed point rather than against a hard-coded business figure.** A cell is
    canonical exactly when re-encoding it changes nothing, so ``to_money`` and ``to_quantity``
    — where NFR-INT-006 puts the rounding rule, once — are the oracle. Pinning "990.000" here
    would make this test fail whenever a fixture changed a quantity, which is not the property
    under test.
    """
    stock = _payload(auth(owner), "v1:report-stock")
    on_hand = next(row["on_hand"] for row in stock["rows"])
    assert on_hand == str(to_quantity(Decimal(on_hand))), (
        f"quantity is 14,3 (`04` §1.6) and already canonical; got {on_hand!r}"
    )
    assert len(on_hand.split(".")[1]) == 3

    sales = _payload(auth(owner), "v1:report-sales")
    money = sales["total"]["sales"]
    assert money == str(to_money(Decimal(money))), f"money is 14,2; got {money!r}"
    assert len(money.split(".")[1]) == 2

    # The rate *is* pinned, because this fixture fully determines it: one rejection in two
    # settled operations. `05` §9.11.2's definition is unchanged by TD-36 — only its encoding.
    health = _payload(auth(owner), "v1:report-sync-health")
    rate = next(row["conflict_rate"] for row in health["rows"])
    assert rate == "50.00", f"one rejection in two settled is 50.00; got {rate!r}"

    orders = _payload(auth(owner), "v1:report-order-status")
    assert isinstance(orders["total"]["orders"], int), "a count stays a JSON integer"


def test_a_count_is_not_stringified(auth, owner, exercised):
    """Requirement 4, per column rather than per total — the direction of the *other* error."""
    health = _payload(auth(owner), "v1:report-sync-health")
    row = health["rows"][0]
    for key in ("accepted", "duplicate", "deferred", "rejected", "in_flight", "settled"):
        assert isinstance(row[key], int), f"{key} arrived as {type(row[key]).__name__}"


def test_the_response_says_what_each_column_means(auth, owner, exercised):
    """The additive half of the fix.

    A client holding ``"25.00"`` cannot tell a rate from an amount, and ``numeric`` told it
    neither. ``kind`` makes the payload self-describing — the same reason ``definition``
    travels with the figure (M7-1). ``numeric`` is kept so no existing consumer breaks.
    """
    body = _payload(auth(owner), "v1:report-sync-health")
    by_key = {column["key"]: column for column in body["columns"]}

    assert by_key["conflict_rate"]["kind"] == "RATE"
    assert by_key["accepted"]["kind"] == "COUNT"
    assert by_key["device_id"]["kind"] == "TEXT"
    assert by_key["conflict_rate"]["numeric"] is True
    assert by_key["device_id"]["numeric"] is False


# ------------------------------------------------------------ anti-vacuity: mutation
#
# Each test below breaks a payload and requires the rule to notice. Nothing here touches the
# repository or the database; the mutations are dictionaries.
#
# Without these, `check_wire_format` could be `return []` and everything above would pass.


def _conformant() -> dict[str, Any]:
    return {
        "columns": [
            {"key": "label", "kind": "TEXT"},
            {"key": "orders", "kind": "COUNT"},
            {"key": "value", "kind": "MONEY"},
            {"key": "on_hand", "kind": "QUANTITY"},
            {"key": "conflict_rate", "kind": "RATE"},
        ],
        "rows": [
            {
                "label": "CONFIRMED",
                "orders": 3,
                "value": "1180.00",
                "on_hand": "24.000",
                "conflict_rate": "12.50",
            }
        ],
        "total": {"label": "Total", "orders": 3, "value": "1180.00"},
    }


def test_the_conformant_payload_passes():
    """The control. Without it, a rule that failed everything would satisfy every mutation."""
    assert not check_wire_format(**_conformant())


@pytest.mark.parametrize(
    ("key", "broken"),
    [
        ("value", 1180.0),  # the TD-36 defect itself
        ("on_hand", 24.0),
        ("conflict_rate", 12.5),
    ],
)
def test_a_decimal_arriving_as_a_json_number_is_caught(key, broken):
    payload = _conformant()
    payload["rows"][0][key] = broken

    failures = check_wire_format(**payload)
    assert any("JSON number" in failure for failure in failures), (
        f"{key} = {broken!r} is the exact defect TD-36 records and it was not caught: {failures}"
    )


def test_the_defect_is_caught_in_the_total_row_too():
    """The total is a separate dict, and it is the figure an owner actually reads."""
    payload = _conformant()
    payload["total"]["value"] = 1180.0

    assert any("total.value" in failure for failure in check_wire_format(**payload))


def test_an_undeclared_decimal_is_caught_without_a_column():
    """The backstop. ``rows`` carries keys no column declares — ``_sales_by_customer``'s
    ``key`` among them — so the rule must not depend on a declaration existing."""
    payload = _conformant()
    payload["rows"][0]["undeclared"] = 99.5

    assert any("undeclared" in failure for failure in check_wire_format(**payload))


@pytest.mark.parametrize(
    ("key", "wrong"),
    [("value", "1180.0"), ("value", "1180"), ("on_hand", "24.00"), ("conflict_rate", "12.5")],
)
def test_a_string_at_the_wrong_scale_is_caught(key, wrong):
    """A string is necessary and not sufficient. ``"11800"`` and ``"11800.00"`` are the same
    number and a different declared scale — the drift ``Money.scale`` exists to prevent."""
    payload = _conformant()
    payload["rows"][0][key] = wrong

    assert any("not canonical" in failure for failure in check_wire_format(**payload)), (
        f"{key} = {wrong!r} passed as canonical"
    )


def test_a_stringified_count_is_caught():
    """The opposite error, and the reason ``numeric: bool`` could not have fixed TD-36."""
    payload = _conformant()
    payload["rows"][0]["orders"] = "3"

    assert any("must not be stringified" in f for f in check_wire_format(**payload))


def test_a_null_cell_is_allowed():
    """`05` §9.11.2 depends on it: a device that has settled nothing reports a blank rate,
    never ``0%``. ``null`` is the absence of a measurement, not a malformed one."""
    payload = _conformant()
    payload["rows"][0]["conflict_rate"] = None

    assert not check_wire_format(**payload)
