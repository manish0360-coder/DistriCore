"""``manage.py load_opening_balances`` — **ACT-E**, the go-live opening position.

`02` §ACT-E: *"Opening-balance load and reconciliation | M11 | Go-live (R-6)"*, and `00`
§19.2's M11 → live gate opens with *"Opening balances loaded and reconciled."*

**Why this exists.** ``receivables.services.load_opening_balance`` and
``purchasing.services.load_supplier_opening_balance`` were built, tested and left with no
caller outside the test suite. The first docstring says *"re-running the whole **import** is
therefore a no-op"* — it was written for an import that did not exist. This is that import.

**R-6 is what makes it worth doing carefully**: *"A corrupt starting position undermines
every derived figure permanently."* Everything below fails closed.

--------------------------------------------------------------------------------------
The file
--------------------------------------------------------------------------------------

CSV with a header row, four columns::

    party,code,amount,entry_date
    CUSTOMER,C-0142,4500.00,2026-03-31
    SUPPLIER,S-0007,-1200.00,2026-03-31

``party``       ``CUSTOMER`` or ``SUPPLIER``, case-insensitive.
``code``        ``Customer.code`` / ``Supplier.code`` — both ``unique``, and already the
                identifier the business uses. **No party is ever created here**: this
                command loads balances, not master data.
``amount``      See the sign rules below. They differ by party and both are ruled.
``entry_date``  **Required for SUPPLIER**, optional for CUSTOMER.

--------------------------------------------------------------------------------------
The contract, and where each clause comes from
--------------------------------------------------------------------------------------

**The two services differ in four ruled ways, and this command does not harmonise them.**
Each divergence is recorded in the services themselves; repeating the behaviour here rather
than smoothing it over is the whole point.

============== ===================================== ================================
Aspect         CUSTOMER                              SUPPLIER
============== ===================================== ================================
Sign           ``> 0`` only — *"a customer who owes  Non-zero; **negative is valid**
               nothing needs no entry"*              (an advance paid, goods returned
                                                     before go-live). ``ck_sle_sign``
                                                     omits ``OPENING`` deliberately
Re-load        **Idempotent** — returns the existing **Refused** — silently returning
               entry (D-10, M6-11)                   would report success for a change
                                                     that did not happen
``entry_date`` Defaults to today                     **Required, no fallback** (P-4: a
                                                     machine clock must not decide a
                                                     business fact)
Audit row      Written                               None — R-3: the entry already
                                                     carries actor, time and narration
============== ===================================== ================================

**Re-run safety follows from that table, not from a flag.** A customer row re-run is a pure
no-op. A supplier row re-run would be *refused* by the service, so this command detects an
existing ``OPENING`` first and reports ``ALREADY LOADED`` — which is exactly what
``load_supplier_opening_balance``'s docstring instructs a repeating caller to do:
*"a caller repeating one must skip suppliers already loaded, or handle the refusal."*
**The whole file is therefore re-runnable after a partial failure, from either side.**

**Everything is validated before anything is written.** D-10 exists so a *partial failure*
is recoverable, not so partial input is normal — and R-6 says a wrong starting position is
permanent. One bad row stops the load. ``--allow-partial`` overrides that, and the report
names it, because an operator who chooses to load 400 of 402 rows must be able to prove
later that they chose it.

**A duplicate party inside one file is refused, both rows.** For a customer the second row
would silently no-op; for a supplier it would raise. Neither is a truthful answer to a file
that states two different opening balances for one party.

--------------------------------------------------------------------------------------
Reconciliation — three figures, derived independently
--------------------------------------------------------------------------------------

The owner signs the report, so the report must not compute one number three ways::

    A  source total    Σ amounts in the file                    what the business asserts
    B  loaded total    Σ the OPENING entries that now exist     what the ledger stores
    C  derived total   Σ settled_balance / supplier_balance     what the system reports

    A ≡ B   the load wrote what the file said
    B ≡ C   the ledger derives what it stores

**A and B are compared for every run. B ≡ C holds only when the file is the whole opening
position** — at go-live, before any trading, which is when ACT-E runs. Any later activity
makes C legitimately larger, so C is reported **separately and always**, never folded into
the verdict silently: a difference has to be visible to be judged.

C comes from ``ledger.selectors``, which is the same derivation ``receivables_ageing`` and
the customer statement use (BR-005). Nothing is stored, cached or aggregated.

--------------------------------------------------------------------------------------
Running it
--------------------------------------------------------------------------------------

**``--dry-run`` is the default.** Writing requires ``--commit``, spelled out::

    manage.py load_opening_balances --csv opening.csv --owner-phone 9000000000
    manage.py load_opening_balances --csv opening.csv --owner-phone 9000000000 --commit

**Exit status, and the two modes gate differently:**

============== =========================== ==============================================
Mode           Refused rows                Exit
============== =========================== ==============================================
dry run        none                        ``0`` — the file is loadable
dry run        any                         non-zero — validating is what a dry run is for
``--commit``   none, and ``A ≡ B``         ``0`` — this is the report the owner signs
``--commit``   none, but ``A ≠ B``         non-zero
``--commit``   any (with ``--allow-partial``) non-zero, and the flag is named in the report
============== =========================== ==============================================

**Reconciliation gates a committed run only.** A dry run writes nothing, so ``B`` is
whatever the ledger already held — zero, before go-live — and ``A ≠ B`` is the expected
state of *"nothing has been loaded yet"*, not a failure. Scoring it as one would confuse an
absent result with a failed one, which is the distinction ``ops/perf_verdicts.py`` was
written to keep.

--------------------------------------------------------------------------------------
Where this lives, and why
--------------------------------------------------------------------------------------

ACT-E is **one activity producing one signature**, so it is one command; two commands would
mean two reconciliation reports for a single starting position, which is worse for R-6.

It needs both ledgers, so it must live in a module permitted to reach both. `03` §2.1's
frozen layer list places ``receivables`` above ``orders | purchasing``::

    receivables  ->  billing  ->  fulfilment | field  ->  orders | purchasing

so ``receivables`` importing ``purchasing.services`` is layering-legal, and this is the
lowest module from which ACT-E can be expressed at all. It follows ``bootstrap_owner``'s
precedent — a privileged operator action lives in the app it serves, calling services.

**No model is imported.** Every read is a selector and every write is a service, so
``record_entry`` remains the single ledger writer (D-8) and no bulk path exists.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.exceptions import DomainError
from customers.selectors import search_customers
from identity.phone import normalise_phone
from identity.selectors import get_active_user_by_phone
from ledger.selectors import (
    settled_balance,
    statement_for,
    supplier_balance,
    supplier_statement_for,
)
from purchasing.selectors import search_suppliers
from purchasing.services import load_supplier_opening_balance
from receivables.services import load_opening_balance

CUSTOMER = "CUSTOMER"
SUPPLIER = "SUPPLIER"
PARTIES = (CUSTOMER, SUPPLIER)

#: The header this command requires, in this order. A file that does not declare its own
#: columns is a file whose meaning depends on the reader's memory.
COLUMNS = ("party", "code", "amount", "entry_date")

#: The ledger entry type both services write. Compared as a string so no model is imported.
OPENING = "OPENING"

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class Row:
    """One validated line, with the party resolved."""

    line: int
    party: str
    code: str
    amount: Decimal
    entry_date: date | None
    subject: Any


@dataclass(frozen=True)
class Refusal:
    """One line that will not be loaded, and why. Carries the line number for the operator."""

    line: int
    party: str
    code: str
    reason: str


@dataclass
class Tally:
    """The three reconciliation figures for one party class, plus what happened."""

    rows: list[Row] = field(default_factory=list)
    loaded: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    source_total: Decimal = ZERO
    loaded_total: Decimal = ZERO
    derived_total: Decimal = ZERO


def _parse_amount(raw: str) -> Decimal:
    try:
        return Decimal(raw.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"`{raw}` is not a number") from exc


def _parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"`{raw}` is not an ISO date (YYYY-MM-DD)") from exc


def _opening_entry(party: str, subject: Any) -> Any:
    """The existing ``OPENING`` entry for a party, or ``None``.

    Read through the ledger selectors rather than a model query: this command must not
    reach a model directly, and the same selector explains a balance on screen.
    """
    statement = statement_for(subject) if party == CUSTOMER else supplier_statement_for(subject)
    for entry in statement:
        if entry.entry_type == OPENING:
            return entry
    return None


class Command(BaseCommand):
    help = (
        "ACT-E: load customer and supplier opening balances from a CSV and reconcile them. "
        "Dry-run by default; --commit writes. Re-runnable after a partial failure."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--csv", required=True, help="Path to the opening-balance file.")
        parser.add_argument(
            "--owner-phone",
            required=True,
            help="The OWNER performing the load. Both services require the role, and the "
            "customer side records this actor on an audit row.",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Write. Without it nothing is loaded — a dry run is the default because "
            "R-6 makes a wrong starting position permanent.",
        )
        parser.add_argument(
            "--allow-partial",
            action="store_true",
            help="Load the valid rows even though some were refused. Named in the report.",
        )

    # ---------------------------------------------------------------- the operator entry
    def handle(self, *args: Any, **options: Any) -> None:
        path = Path(options["csv"])
        if not path.is_file():
            raise CommandError(f"not found: {path}")

        actor = self._owner(options["owner_phone"])
        rows, refusals = self._read(path, actor=actor)

        if refusals and not options["allow_partial"]:
            self._report(
                path=path,
                tallies={},
                refusals=refusals,
                committed=False,
                partial=False,
                blocked=True,
            )
            raise CommandError(
                f"{len(refusals)} row(s) refused; nothing was loaded. Fix the file and re-run, "
                "or pass --allow-partial to load the rest deliberately."
            )

        tallies = self._load(rows, actor=actor, commit=options["commit"])
        self._reconcile(tallies)
        self._report(
            path=path,
            tallies=tallies,
            refusals=refusals,
            committed=options["commit"],
            partial=options["allow_partial"],
            blocked=False,
        )

        # **Refusals fail either mode; reconciliation gates only a committed run.**
        #
        # A dry run deliberately writes nothing, so B is whatever the ledger already held —
        # zero, before go-live. `A != B` is then the *expected* state of "nothing has been
        # loaded yet", not a failed reconciliation, and reporting it as one would be the
        # same confusion `ops/perf_verdicts.py` exists to prevent: **an absent result is not
        # a failed result.** A dry run over a clean file is a successful validation.
        #
        # A file with refusals still fails in both modes. Validating is the dry run's whole
        # purpose, and an operator scripting step 2 of the runbook needs a non-zero status
        # to know the file is not yet loadable.
        if refusals or (options["commit"] and not self._reconciled(tallies)):
            raise CommandError(
                "ACT-E is not reconciled. The owner must not sign this report — see the "
                "refusals and the A/B/C comparison above."
            )

    # --------------------------------------------------------------------------- reading
    def _owner(self, phone: str) -> Any:
        """The actor, by phone, **normalised through the shared canonical form**.

        `04` T-01 makes the phone number the login identity, and `identity.phone` exists
        because that discipline was once applied on read and not on write: *"a superuser
        created as `7903324153` could therefore never log in — the lookup asked for
        `+917903324153` and found nothing."* An operator types ten digits;
        `bootstrap_owner` stored `+91…`. Looking up the raw string reproduces exactly the
        defect that module was written to end, so the reader uses the writer's function.

        **This does not check the role**, deliberately: both services call
        ``require_roles(actor, Role.OWNER)`` themselves, and a second check here would be a
        rule in two places — the failure mode `02` NFR-MNT-001 names. Resolving the user is
        all that is owed.
        """
        try:
            canonical = normalise_phone(phone)
        except DomainError as exc:
            raise CommandError(f"--owner-phone is not a usable number: {exc.detail}") from exc

        user = get_active_user_by_phone(canonical)
        if user is None:
            raise CommandError(
                f"no active user with phone `{canonical}` (you gave `{phone}`). The load runs "
                "as a named OWNER; the services refuse any other role."
            )
        return user

    def _read(self, path: Path, *, actor: Any) -> tuple[list[Row], list[Refusal]]:
        """Validate every line before anything is written. Nothing here touches the database
        except to resolve a party by its code, which is a read.
        """
        rows: list[Row] = []
        refusals: list[Refusal] = []
        seen: dict[tuple[str, str], int] = {}

        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = [column for column in COLUMNS if column not in (reader.fieldnames or ())]
            if missing:
                raise CommandError(
                    f"the file is missing column(s) {missing}; expected header {list(COLUMNS)}"
                )

            for line, raw in enumerate(reader, start=2):  # line 1 is the header
                party = (raw.get("party") or "").strip().upper()
                code = (raw.get("code") or "").strip()

                if party not in PARTIES:
                    refusals.append(
                        Refusal(line, party or "?", code, f"party must be one of {list(PARTIES)}")
                    )
                    continue
                if not code:
                    refusals.append(Refusal(line, party, "", "code is empty"))
                    continue

                key = (party, code)
                if key in seen:
                    refusals.append(
                        Refusal(line, party, code, f"duplicate of line {seen[key]} in this file")
                    )
                    continue
                seen[key] = line

                try:
                    amount = _parse_amount(raw.get("amount", ""))
                    entry_date = _parse_date(raw.get("entry_date", ""))
                except ValueError as exc:
                    refusals.append(Refusal(line, party, code, str(exc)))
                    continue

                # The sign rules are the services'. Checked here too so the whole file can be
                # judged before the first write, which is what makes fail-closed possible.
                if party == CUSTOMER and amount <= 0:
                    refusals.append(
                        Refusal(line, party, code, "a customer opening balance must be > 0")
                    )
                    continue
                if party == SUPPLIER and amount == 0:
                    refusals.append(Refusal(line, party, code, "an opening balance cannot be zero"))
                    continue
                if party == SUPPLIER and entry_date is None:
                    refusals.append(
                        Refusal(line, party, code, "entry_date is required for a supplier (P-4)")
                    )
                    continue

                subject = self._resolve(party, code, actor=actor)
                if subject is None:
                    refusals.append(
                        Refusal(line, party, code, f"no {party.lower()} with this code")
                    )
                    continue

                rows.append(Row(line, party, code, amount, entry_date, subject))

        return rows, refusals

    def _resolve(self, party: str, code: str, *, actor: Any) -> Any:
        """By natural key, through a selector. **Never creates a party.**

        ``search_customers`` scopes to what the actor may see, which is the same predicate
        every other customer surface uses (BR-003). An OWNER sees all, and a load run as
        anyone else would be refused by the services anyway.
        """
        queryset = (
            search_customers(actor) if party == CUSTOMER else search_suppliers(is_active=None)
        )
        return queryset.filter(code=code).first()

    # --------------------------------------------------------------------------- loading
    def _load(self, rows: list[Row], *, actor: Any, commit: bool) -> dict[str, Tally]:
        tallies = {CUSTOMER: Tally(), SUPPLIER: Tally()}

        for row in rows:
            tally = tallies[row.party]
            tally.rows.append(row)
            tally.source_total += row.amount

            existing = _opening_entry(row.party, row.subject)
            if existing is not None:
                # Customer: the service would return this. Supplier: it would refuse.
                # Either way the truthful report is that the row is already carried.
                tally.already.append(row.code)
                continue

            if not commit:
                continue

            try:
                if row.party == CUSTOMER:
                    load_opening_balance(
                        actor=actor,
                        customer=row.subject,
                        amount=row.amount,
                        entry_date=row.entry_date,
                    )
                elif row.entry_date is None:
                    # Unreachable: `_read` refuses a dated-less supplier row before anything
                    # is written. Stated here anyway, because the invariant lives two
                    # hundred lines away and `load_supplier_opening_balance` requires a real
                    # date — P-4, no fallback. A reader of this branch should not have to
                    # find the validator to know the date cannot be absent.
                    raise CommandError(
                        f"line {row.line} ({SUPPLIER} {row.code}) reached the loader without "
                        "an entry_date. This is a defect in this command, not in the file."
                    )
                else:
                    load_supplier_opening_balance(
                        actor=actor,
                        supplier=row.subject,
                        amount=row.amount,
                        entry_date=row.entry_date,
                    )
            except DomainError as exc:
                raise CommandError(
                    f"line {row.line} ({row.party} {row.code}) was refused by the service: "
                    f"{exc.detail}. Rows before it are loaded and the file is re-runnable."
                ) from exc
            tally.loaded.append(row.code)

        return tallies

    # -------------------------------------------------------------------- reconciliation
    def _reconcile(self, tallies: dict[str, Tally]) -> None:
        """B and C, each derived independently of A and of each other."""
        for party, tally in tallies.items():
            for row in tally.rows:
                entry = _opening_entry(party, row.subject)
                if entry is not None:
                    tally.loaded_total += entry.amount
                tally.derived_total += (
                    settled_balance(row.subject)
                    if party == CUSTOMER
                    else supplier_balance(row.subject)
                )

    def _reconciled(self, tallies: dict[str, Tally]) -> bool:
        """**A ≡ B only.** B ≡ C is reported but not asserted — see the module docstring."""
        return all(tally.source_total == tally.loaded_total for tally in tallies.values())

    # -------------------------------------------------------------------------- the report
    def _report(
        self,
        *,
        path: Path,
        tallies: dict[str, Tally],
        refusals: list[Refusal],
        committed: bool,
        partial: bool,
        blocked: bool,
    ) -> None:
        out = self.stdout
        out.write("")
        out.write("=== ACT-E — opening-balance load and reconciliation ===")
        out.write(f"    file      : {path}")
        out.write(f"    mode      : {'COMMITTED' if committed else 'DRY RUN — nothing written'}")
        if partial:
            out.write("    partial   : --allow-partial was given; refused rows were skipped")
        if blocked:
            out.write("    BLOCKED   : rows were refused and --allow-partial was not given")
        out.write("")

        for party in PARTIES:
            tally = tallies.get(party)
            if tally is None or not tally.rows:
                out.write(f"    {party:<9} no rows")
                continue
            out.write(
                f"    {party:<9} {len(tally.rows)} row(s) · "
                f"{len(tally.loaded)} loaded · {len(tally.already)} already carried"
            )
            # **B and C mean something different before a load and after one.** In a dry run
            # they are the ledger's *current* state, which before go-live is zero — so
            # labelling them "loaded" and scoring `A != B` as a mismatch would report a
            # defect where there is only an unstarted job.
            already = "already in the ledger" if not committed else "OPENING entries"
            out.write(f"        A source  {tally.source_total:>16,.2f}   (what the file asserts)")
            out.write(f"        B loaded  {tally.loaded_total:>16,.2f}   ({already})")
            out.write(f"        C derived {tally.derived_total:>16,.2f}   (ledger balances)")
            if not committed:
                out.write("        A vs B not evaluated — dry run, nothing was written")
            else:
                verdict = (
                    "A = B" if tally.source_total == tally.loaded_total else "A != B  MISMATCH"
                )
                note = (
                    ""
                    if tally.loaded_total == tally.derived_total
                    else "   (C differs — see below)"
                )
                out.write(f"        {verdict}{note}")
            out.write("")

        if refusals:
            out.write(f"    {len(refusals)} refused row(s):")
            for refusal in refusals:
                out.write(
                    f"        line {refusal.line:>4}  {refusal.party:<9} "
                    f"{refusal.code:<12} {refusal.reason}"
                )
            out.write("")

        out.write(
            "    B != C is not by itself an error: C is every ledger entry, so any trading\n"
            "    after go-live makes it larger. At go-live, before any trading, they agree."
        )
        out.write("")
        if committed and not refusals and self._reconciled(tallies or {}):
            out.write("    ACT-E RECONCILED. This report is what the owner signs (R-6).")
        else:
            out.write("    NOT signed off. Nothing here may be recorded as a completed load.")
        out.write("")
