"""**ACT-E — the most financially sensitive write the system performs** (`02` §ACT-E, R-6).

> *"A corrupt starting position undermines every derived figure permanently."* — `01` R-6

`00` §19.2's M11 → live gate opens with *"Opening balances loaded and reconciled."* The two
services that do the loading were built at M6 and BD-5 and left with **no caller outside the
test suite** — `load_opening_balance`'s own docstring speaks of *"re-running the whole
import"* for an import that did not exist. `load_opening_balances` is that import.

**What these contracts hold, and why each one is here.**

1. **Authorisation.** The load runs as a named OWNER or not at all.
2. **The single writer.** D-8: *"No bulk-insert path, no management command writing rows
   directly."* The command must reach the ledger only through the services.
3. **Idempotency, and it differs by party.** Customers are idempotent by natural key (D-10);
   suppliers *refuse* a second load, so the command must skip them rather than fail. A file
   must be re-runnable whichever way a previous run died.
4. **Refusals.** Zero, wrong sign, unknown party, malformed row, duplicate inside the file.
5. **Fail-closed on mixed input.** One bad row stops the whole load unless the operator says
   otherwise in writing.
6. **The reconciliation arithmetic.** A, B and C derived independently, because the owner
   signs the report and a report that computes one number three ways proves nothing.
"""

from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from ledger.models import CustomerLedgerEntry, SupplierLedgerEntry
from ledger.selectors import settled_balance, supplier_balance
from purchasing.services import create_supplier

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]

COMMAND = Path(__file__).resolve().parents[2] / (
    "receivables/management/commands/load_opening_balances.py"
)


# ------------------------------------------------------------------------------ fixtures
@pytest.fixture
def owner_phone(owner):
    """The OWNER the command resolves. `owner` already carries the role."""
    return owner.phone


@pytest.fixture
def supplier(owner):
    """Through the service, like every other supplier in the suite — not `objects.create`."""
    return create_supplier(
        actor=owner,
        code="S-0007",
        name="Acme Distributors",
        phone="+919876500011",
        billing_address="Industrial Estate",
    )


def _write(tmp_path: Path, rows: str, *, header: str = "party,code,amount,entry_date") -> Path:
    path = tmp_path / "opening.csv"
    path.write_text(f"{header}\n{rows}", encoding="utf-8")
    return path


def _run(path: Path, phone: str, *extra: str) -> str:
    out = StringIO()
    call_command(
        "load_opening_balances", "--csv", str(path), "--owner-phone", phone, *extra, stdout=out
    )
    return out.getvalue()


# --------------------------------------------------------------- 2. the single writer, D-8
def test_the_command_never_writes_a_ledger_row_directly():
    """**D-8, mechanically.** *"No bulk-insert path, no management command writing rows
    directly. The go-live load (ACT-E) is a privileged owner action that calls the same
    single writer everything else calls."*

    Asserted on the imports rather than on behaviour: a command that reached a model could
    pass every functional test above while bypassing the sign rules, the source-document
    registry and the audit — which is precisely the failure D-8 was written against.
    """
    tree = ast.parse(COMMAND.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    models = sorted(name for name in imported if name.endswith(".models"))
    assert not models, (
        f"the ACT-E command imports {models}. Every write must go through a service so "
        "`record_entry` stays the single ledger writer (D-8)."
    )
    assert "receivables.services" in imported and "purchasing.services" in imported, (
        "the command no longer calls both opening-balance services"
    )

    source = COMMAND.read_text(encoding="utf-8")
    for forbidden in (".objects.create(", ".objects.bulk_create(", ".save()"):
        assert forbidden not in source, f"the command writes directly: `{forbidden}`"


# ------------------------------------------------------------------- 1. authorisation
def test_a_non_owner_cannot_load_an_opening_balance(tmp_path, salesman, credit_customer):
    """The services enforce OWNER; the command must not become a way around them.

    Checked through the command rather than the service, because the service's own guard is
    already tested — what is unproven is that this new surface reaches it.
    """
    path = _write(tmp_path, f"CUSTOMER,{credit_customer.code},1000.00,2026-03-31\n")
    with pytest.raises(CommandError):
        _run(path, salesman.phone, "--commit")
    assert not CustomerLedgerEntry.objects.filter(
        customer=credit_customer, entry_type=CustomerLedgerEntry.Type.OPENING
    ).exists()


def test_the_operator_may_type_the_number_the_way_a_person_says_it(
    tmp_path, owner, credit_customer
):
    """**The defect `identity/phone.py` was written to end, reproduced on a new surface.**

    `04` T-01 makes the phone number the login identity, so `bootstrap_owner --phone
    9000000000` stores `+919000000000`. An operator running ACT-E types the ten digits they
    know. Looking the raw string up gives *"no active user"* — which is true of the query and
    misleading about the cause, the exact sentence that module's docstring uses about the
    superuser who *"could therefore never log in"*.

    The rest of this suite passed `owner.phone`, which is **already canonical**, so every
    contract here agreed with the command and none of them exercised what an operator types.

    Parameterising over the spellings is the point: the reader must use the writer's
    canonical form, not a second one of its own.
    """
    path = _write(tmp_path, f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\n")
    ten_digits = owner.phone.removeprefix("+91")

    report = _run(path, ten_digits, "--commit")

    assert "RECONCILED" in report
    assert settled_balance(credit_customer) == Decimal("4500.00")


def test_an_unknown_operator_is_refused(tmp_path, credit_customer):
    path = _write(tmp_path, f"CUSTOMER,{credit_customer.code},1000.00,2026-03-31\n")
    with pytest.raises(CommandError, match="no active user"):
        _run(path, "9999999999", "--commit")


# ------------------------------------------------------------------- dry run is the default
def test_a_dry_run_writes_nothing(tmp_path, owner_phone, credit_customer):
    """**Fail-closed.** R-6 makes the wrong starting position permanent, so writing is opt-in.

    The same posture `make restore-rehearsal` takes toward the live database: the dangerous
    thing requires a word, and the default is the safe one.
    """
    path = _write(tmp_path, f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\n")
    report = _run(path, owner_phone)

    assert "DRY RUN" in report
    assert not CustomerLedgerEntry.objects.filter(
        entry_type=CustomerLedgerEntry.Type.OPENING
    ).exists(), "a dry run wrote to the ledger"


# ----------------------------------------------------------------------- the happy path
def test_a_committed_load_writes_through_the_service_and_reconciles(
    tmp_path, owner, owner_phone, credit_customer, supplier
):
    """Both ledgers, both sign conventions, one report.

    The supplier amount is **negative** on purpose: `ck_sle_sign` omits `OPENING` from both
    lists so a payables opening position may be a credit — an advance paid, or goods returned
    before go-live. A command that rejected it would contradict a ruled requirement.
    """
    path = _write(
        tmp_path,
        f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\n"
        f"SUPPLIER,{supplier.code},-1200.00,2026-03-31\n",
    )
    report = _run(path, owner_phone, "--commit")

    entry = CustomerLedgerEntry.objects.get(
        customer=credit_customer, entry_type=CustomerLedgerEntry.Type.OPENING
    )
    assert entry.amount == Decimal("4500.00")
    assert entry.entry_date == date(2026, 3, 31), "the file's date must win over the clock"

    payable = SupplierLedgerEntry.objects.get(
        supplier=supplier, entry_type=SupplierLedgerEntry.Type.OPENING
    )
    assert payable.amount == Decimal("-1200.00")

    assert "COMMITTED" in report and "RECONCILED" in report


def test_the_customer_side_records_an_audit_row_and_the_supplier_side_does_not(
    tmp_path, owner_phone, credit_customer, supplier
):
    """The divergence is ruled (R-3), so the command must not accidentally level it.

    The supplier entry carries actor, timestamp, amount and narration already; an audit row
    would duplicate a record that cannot change. The customer side's extra row is a recorded
    legacy anomaly, not the convention — and this asserts the command changed neither.
    """
    from core.models import AuditLog

    path = _write(
        tmp_path,
        f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\n"
        f"SUPPLIER,{supplier.code},900.00,2026-03-31\n",
    )
    _run(path, owner_phone, "--commit")

    audited = AuditLog.objects.filter(entity_type="customer_ledger_entry").count()
    assert audited == 1, "the customer opening balance is no longer audited"
    assert not AuditLog.objects.filter(entity_type="supplier_ledger_entry").exists(), (
        "the supplier side gained an audit row; R-3 says the entry is already the record"
    )


# ------------------------------------------------------ 3. idempotency and re-run safety
def test_running_the_whole_file_twice_changes_nothing(
    tmp_path, owner_phone, credit_customer, supplier
):
    """**The property D-10 exists for**, across both ledgers at once.

    A customer re-load returns the existing entry; a supplier re-load would be *refused*, so
    the command detects the existing entry and reports it. Either way the second run must
    write nothing new and must not fail — a go-live import that cannot be re-run after a
    partial failure is a go-live import nobody dares re-run.
    """
    path = _write(
        tmp_path,
        f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\n"
        f"SUPPLIER,{supplier.code},900.00,2026-03-31\n",
    )
    _run(path, owner_phone, "--commit")
    first = (
        CustomerLedgerEntry.objects.count(),
        SupplierLedgerEntry.objects.count(),
        settled_balance(credit_customer),
        supplier_balance(supplier),
    )

    report = _run(path, owner_phone, "--commit")

    second = (
        CustomerLedgerEntry.objects.count(),
        SupplierLedgerEntry.objects.count(),
        settled_balance(credit_customer),
        supplier_balance(supplier),
    )
    assert first == second, "the second run changed the ledger"
    assert "already carried" in report


def test_a_partial_failure_leaves_the_file_rerunnable(
    tmp_path, owner_phone, credit_customer, supplier
):
    """Load one party, then re-run a file naming both. The loaded one is skipped, not fatal.

    This is the shape a real partial failure leaves behind — some rows in, some not — and the
    supplier service refuses rather than shrugging, so it is the case most likely to strand
    an operator halfway through go-live.
    """
    _run(_write(tmp_path, f"SUPPLIER,{supplier.code},900.00,2026-03-31\n"), owner_phone, "--commit")

    both = _write(
        tmp_path,
        f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\n"
        f"SUPPLIER,{supplier.code},900.00,2026-03-31\n",
    )
    report = _run(both, owner_phone, "--commit")

    assert (
        SupplierLedgerEntry.objects.filter(entry_type=SupplierLedgerEntry.Type.OPENING).count() == 1
    )
    assert settled_balance(credit_customer) == Decimal("4500.00"), "the new row did not load"
    assert "RECONCILED" in report


# ---------------------------------------------------------------------- 4. refusals
@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("CUSTOMER,{code},0.00,2026-03-31", "must be > 0"),
        ("CUSTOMER,{code},-100.00,2026-03-31", "must be > 0"),
        ("CUSTOMER,NOPE-1,100.00,2026-03-31", "no customer with this code"),
        ("SUPPLIER,NOPE-2,100.00,2026-03-31", "no supplier with this code"),
        ("PARTNER,{code},100.00,2026-03-31", "party must be one of"),
        ("CUSTOMER,{code},abc,2026-03-31", "is not a number"),
        ("CUSTOMER,{code},100.00,31-03-2026", "is not an ISO date"),
        ("CUSTOMER,,100.00,2026-03-31", "code is empty"),
    ],
)
def test_a_bad_row_is_refused_by_line_and_nothing_is_written(
    tmp_path, owner_phone, credit_customer, row, reason
):
    """Every refusal names its line, because a 400-row file is fixed by line number.

    Zero and negative are refused for customers on the service's own reasoning — *"a customer
    who owes nothing needs no entry"* — and the command states it before the first write so
    the whole file can be judged at once.
    """
    path = _write(tmp_path, row.format(code=credit_customer.code) + "\n")
    with pytest.raises(CommandError, match="refused"):
        _run(path, owner_phone, "--commit")
    assert not CustomerLedgerEntry.objects.filter(
        entry_type=CustomerLedgerEntry.Type.OPENING
    ).exists()


def test_a_supplier_row_without_a_date_is_refused(tmp_path, owner_phone, supplier):
    """**P-4.** *"A machine clock must not decide a business fact."*

    The customer service defaults the date; the supplier service refuses to. An opening
    position is a fact about a period that ended before this system existed, and dating it
    "today" would age it from the wrong day for ever.
    """
    path = _write(tmp_path, f"SUPPLIER,{supplier.code},900.00,\n")
    with pytest.raises(CommandError, match="refused"):
        _run(path, owner_phone, "--commit")
    assert not SupplierLedgerEntry.objects.filter(
        entry_type=SupplierLedgerEntry.Type.OPENING
    ).exists()


def test_a_duplicate_party_inside_one_file_is_refused(tmp_path, owner_phone, credit_customer):
    """Two rows, one party, two different balances — the file does not know what it means.

    For a customer the second row would silently no-op behind D-10's idempotency; for a
    supplier it would raise. Neither is a truthful answer, so the file is refused instead.
    """
    path = _write(
        tmp_path,
        f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\n"
        f"CUSTOMER,{credit_customer.code},9999.00,2026-03-31\n",
    )
    with pytest.raises(CommandError, match="refused"):
        _run(path, owner_phone, "--commit")
    assert not CustomerLedgerEntry.objects.filter(
        entry_type=CustomerLedgerEntry.Type.OPENING
    ).exists()


def test_a_missing_column_is_refused_before_any_row_is_read(tmp_path, owner_phone):
    path = _write(tmp_path, "CUSTOMER,C-1,100.00\n", header="party,code,amount")
    with pytest.raises(CommandError, match="missing column"):
        _run(path, owner_phone, "--commit")


# ------------------------------------------------------ 5. mixed input fails closed
def test_one_bad_row_stops_the_whole_load(tmp_path, owner_phone, credit_customer):
    """**The R-6 posture.** D-10 makes a partial *failure* recoverable; it does not make
    partial *input* normal. A file that is 99% right is a file with a mistake in it.
    """
    path = _write(
        tmp_path,
        f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\nCUSTOMER,NOPE-9,100.00,2026-03-31\n",
    )
    with pytest.raises(CommandError, match="nothing was loaded"):
        _run(path, owner_phone, "--commit")

    assert settled_balance(credit_customer) == Decimal("0.00"), (
        "the good row was loaded despite a bad row in the same file"
    )


def test_allow_partial_loads_the_good_rows_and_says_so(tmp_path, owner_phone, credit_customer):
    """The escape hatch exists, and it is on the record.

    An operator who deliberately loads 1 of 2 rows must be able to prove later that they
    chose it — so the flag appears in the report and the run still exits non-zero.
    """
    path = _write(
        tmp_path,
        f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\nCUSTOMER,NOPE-9,100.00,2026-03-31\n",
    )
    with pytest.raises(CommandError, match="not reconciled"):
        _run(path, owner_phone, "--commit", "--allow-partial")

    assert settled_balance(credit_customer) == Decimal("4500.00")


# ------------------------------------------------- 6. the reconciliation the owner signs
def test_the_three_totals_are_derived_independently_and_agree(
    tmp_path, owner_phone, credit_customer, supplier
):
    """A from the file, B from the OPENING entries, C from the balance selectors.

    B and C are computed from different queries — B reads the entry, C sums the ledger — so
    agreement is evidence rather than tautology. At go-live, before any trading, they must be
    equal; that equality is what makes the signature mean something (R-6).
    """
    path = _write(
        tmp_path,
        f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\n"
        f"SUPPLIER,{supplier.code},-1200.00,2026-03-31\n",
    )
    report = _run(path, owner_phone, "--commit")

    assert "A source" in report and "B loaded" in report and "C derived" in report
    assert "4,500.00" in report and "-1,200.00" in report
    assert "A = B" in report
    assert "MISMATCH" not in report
    assert settled_balance(credit_customer) == Decimal("4500.00")
    assert supplier_balance(supplier) == Decimal("-1200.00")


def test_the_report_refuses_to_call_a_dry_run_signed_off(tmp_path, owner_phone, credit_customer):
    """**The B-3 lesson, in the one place it would cost the most.**

    A gate that manufactures its own evidence is worse than no gate. A dry run has loaded
    nothing, so its report must never read as the thing the owner signs.
    """
    path = _write(tmp_path, f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\n")
    report = _run(path, owner_phone)

    assert "NOT signed off" in report
    assert "RECONCILED" not in report.replace("NOT signed off", "")


def test_a_dry_run_over_a_bad_file_still_fails(tmp_path, owner_phone, credit_customer):
    """**Validating is the dry run's whole purpose**, so an invalid file must fail it.

    The correction that made a *clean* dry run succeed must not make a *dirty* one succeed
    too. Step 2 of `go-live-data.md` says *"fix the file and repeat until the run is clean"*,
    and an operator scripting that needs a non-zero status to know it is not yet clean.
    """
    path = _write(
        tmp_path,
        f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\nCUSTOMER,NOPE-9,100.00,2026-03-31\n",
    )
    with pytest.raises(CommandError, match="refused"):
        _run(path, owner_phone)

    assert not CustomerLedgerEntry.objects.filter(
        entry_type=CustomerLedgerEntry.Type.OPENING
    ).exists()


def test_editing_an_amount_after_a_load_and_re_running_is_caught_not_silently_ignored(
    tmp_path, owner_phone, credit_customer
):
    """**The R-6 trap that idempotency creates.**

    D-10 makes a customer re-load return the *existing* entry — which is what makes a partial
    failure safely re-runnable. The cost is that correcting a number by editing the file and
    re-running would write nothing and, without this, report success.

    The A ≡ B comparison is what catches it: the file now asserts 9,999 and the ledger holds
    4,500, so the run fails and says so. **A ledger entry is immutable** (BR-006, R-3) — the
    correction is a further entry through the ordinary services, which is what the runbook
    tells the operator to do.
    """
    _write(tmp_path, f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\n")
    _run(tmp_path / "opening.csv", owner_phone, "--commit")

    edited = _write(tmp_path, f"CUSTOMER,{credit_customer.code},9999.00,2026-03-31\n")
    with pytest.raises(CommandError, match="not reconciled"):
        _run(edited, owner_phone, "--commit")

    assert settled_balance(credit_customer) == Decimal("4500.00"), (
        "the edited file changed the ledger; an opening entry must be immutable"
    )


def test_trading_after_go_live_shows_up_as_c_differing_rather_than_being_hidden(
    tmp_path, owner, owner_phone, credit_customer
):
    """B ≡ C holds only when the file is the whole opening position, and the report says so.

    Rather than asserting an equality that stops being true the moment the business trades,
    C is reported separately. This proves the difference is *visible* — the alternative is a
    reconciliation that quietly absorbs a figure nobody chose to accept.
    """
    from receivables.services import record_payment

    path = _write(tmp_path, f"CUSTOMER,{credit_customer.code},4500.00,2026-03-31\n")
    _run(path, owner_phone, "--commit")
    record_payment(actor=owner, customer=credit_customer, amount="500.00", method="CASH")

    report = _run(path, owner_phone, "--commit")

    assert "A = B" in report, "the load itself still reconciles"
    assert "C differs" in report, "post-go-live activity is invisible in the report"
    assert settled_balance(credit_customer) == Decimal("4000.00")
