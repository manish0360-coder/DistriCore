# Runbook — ACT-E, the go-live opening position

> **A corrupt starting position undermines every derived figure permanently** (`01` R-6).

`02` §ACT-E — *"Opening-balance load and reconciliation | M11 | Go-live (R-6)"*. `00` §19.2's
M11 → live gate opens with *"Opening balances loaded and reconciled."* This is that load, and
the report the owner signs.

**Status: ready to execute. Not executed.** The procedure was **rehearsed on 2026-09-12**
against a disposable database and passed on every property — see *Rehearsal log* below. The
**Load log** at the end is a different table: it is empty and stays empty until someone
watches a real run against real figures, the same posture the restore rehearsal took (B-3).
**A rehearsal is not a load**, and nothing in the Load log may be recorded from synthetic
data.

---

## What is loaded, and what is not

| Position | Loaded by | Status |
| --- | --- | --- |
| **Receivables** — what customers owe | `manage.py load_opening_balances` | this runbook |
| **Payables** — what we owe suppliers | the same command, `SUPPLIER` rows | this runbook |
| **Stock** | the web admin: **Stock → Entry**, one movement per product with a reason code | already reachable; no import needed |

R-6 names all three. Stock has had an operator path since M2 and needs nothing new.

**Master data is not loaded here.** Customers, suppliers and products must already exist —
the command resolves them by `code` and **refuses a row whose party it cannot find**. It
loads balances, never parties.

---

## The file

CSV, UTF-8, header row required, four columns in this order:

```
party,code,amount,entry_date
CUSTOMER,C-0142,4500.00,2026-03-31
SUPPLIER,S-0007,-1200.00,2026-03-31
```

| Column | Meaning |
| --- | --- |
| `party` | `CUSTOMER` or `SUPPLIER`, case-insensitive |
| `code` | the party's existing code — `Customer.code` / `Supplier.code` |
| `amount` | see the sign rules below; the two sides differ, and both differences are ruled |
| `entry_date` | the date the position applies to. **Required for `SUPPLIER`**, optional for `CUSTOMER` |

### The sign rules, and why they differ

| | `CUSTOMER` | `SUPPLIER` |
| --- | --- | --- |
| Amount | **greater than zero only** | non-zero; **negative is valid** |
| Why | *"a customer who owes nothing needs no entry"* | a payables position can be a credit — an advance paid, or goods returned before go-live. `ck_sle_sign` omits `OPENING` from both lists deliberately |
| `entry_date` | defaults to today | **required, no fallback** — P-4: a machine clock must not decide a business fact. The balance ages from this date, and dating it earlier than go-live is usually correct |
| Re-load | idempotent; returns the existing entry (D-10) | refused; the command skips it and reports `already carried` |

**Do not "fix" a refusal by flipping a sign.** A customer credit balance and a supplier debit
balance are real situations the corpus has not ruled on for `OPENING`; if you meet one, stop
and raise it rather than inventing a representation.

---

## Procedure

### 1. Prepare the file

One row per party with a non-zero opening position. Omit parties who start at zero — an entry
of zero is refused, correctly.

### 2. Dry run — this is the default and it writes nothing

```bash
docker compose -f docker/compose.yml -f docker/compose.prod.yml --env-file .env \
  exec -T app python manage.py load_opening_balances \
    --csv /srv/import/opening.csv --owner-phone <the owner's number>
```

Read the report. Every refusal names its **line number**. Fix the file and repeat until the
run is clean. **Nothing has been written yet, whatever the report says.**

### 3. Take a backup

```bash
./ops/backup.sh
```

B-6 and MIG-7: a verified backup before any risky write. This is the riskiest write the
system will ever perform.

### 4. Load

```bash
… python manage.py load_opening_balances \
    --csv /srv/import/opening.csv --owner-phone <number> --commit
```

Exit status `0` means every row loaded and the reconciliation held. Anything else means it
did not, and the report says which line.

### 5. Reconcile — this is what the owner signs

The report prints three figures per party class, **each derived independently**:

```
A  source total    Σ amounts in the file                  what the business asserts
B  loaded total    Σ the OPENING entries that now exist   what the ledger stores
C  derived total   Σ settled_balance / supplier_balance   what the system reports
```

- **`A = B`** proves the load wrote what the file said. The command asserts this.
- **`B = C`** proves the ledger derives what it stores. **Reported, not asserted** — C counts
  *every* ledger entry, so any trading after go-live legitimately makes it differ. At
  go-live, before any trading, they are equal. If they differ and you have not traded,
  **stop**.

The owner signs the printed report: row counts, A/B/C per class, and every refusal.

### 6. Cross-check against the system's own reports

Independent of the command:

- **Receivables ageing** (web admin → Reports) — the total must equal A for `CUSTOMER`.
- **A customer statement** for two or three known parties — the opening line must match the
  file.

Two surfaces agreeing is worth more than one surface agreeing with itself.

---

## If it goes wrong

**The file is re-runnable.** Whatever mix of loaded and not-loaded rows a failure left
behind, run the same file again: customers are idempotent by natural key (D-10), and
suppliers already carried are skipped rather than refused. Re-running is the designed
recovery, not a risk.

**A wrong amount that has already been loaded is not edited.** A ledger entry is immutable
(BR-006, R-3). The correction is a further entry through the ordinary services — an
adjustment or a payment — not a change to the opening balance. If the whole load is wrong,
restore from the step-3 backup (`docs/runbooks/restore-from-backup.md`) and start again.

**`--allow-partial`** loads the valid rows despite refusals. It is on the record in the
report and the run still exits non-zero. Use it only when you have decided that the refused
parties will be loaded separately, and say so in the log below.

---

## Common refusals

| Message | Meaning |
| --- | --- |
| `no customer with this code` | the party does not exist. **Create it first** — this command never does |
| `a customer opening balance must be > 0` | zero or negative on a `CUSTOMER` row |
| `an opening balance cannot be zero` | a party who starts at zero needs no row at all |
| `entry_date is required for a supplier` | P-4 — supply the real date |
| `duplicate of line N in this file` | two rows for one party. The file does not know its own answer |
| `is not a number` / `is not an ISO date` | malformed cell; dates are `YYYY-MM-DD` |
| `the file is missing column(s)` | header wrong; four columns, named |

---

## Rehearsal

Before go-live, run the whole procedure against the **disposable** `districore_perf`
database, never the development or production one.

> **The rehearsal needs parties, not a transaction corpus — and never `make perf`.**
>
> ACT-E writes one `OPENING` row per party through a service. Its cost does not scale with
> transaction history, so the DR-8 dataset proves nothing here that the twenty contracts in
> `test_opening_balance_load.py` do not already prove against a real database inside
> `make verify`. What the rehearsal uniquely proves is **B-4** — that the procedure below
> works when a human follows it.
>
> **`make perf` must not be used to populate it.** Its recipe ends
> `… --json - > ops/perf-latest.json`, a truncating redirect over the authoritative
> 2026-09-08 DR-8 artefact that `docs/M10.6_Performance_Report.md` §10 names as evidence of
> record. Re-running it for a data side-effect would overwrite signed evidence. `--stage`
> gates measurement only, and `--profile m7` builds the same 73,000 invoices, so neither
> avoids the cost.
>
> `make perf-db` gives a migrated, disposable database with an OWNER at `+919000000000` and
> **no master data**. Create the handful of parties the rehearsal needs through the same
> services the web admin calls:
>
> ```bash
> DC="docker compose -f docker/compose.yml -f docker/compose.dev.yml --env-file .env"
> PERF='DATABASE_URL="${DATABASE_URL%/*}/districore_perf"'
>
> make perf-db
>
> $DC exec -T app sh -c "$PERF python manage.py shell -c \"
> from identity.selectors import get_active_user_by_phone
> from customers.services import create_customer
> from purchasing.services import create_supplier
> o = get_active_user_by_phone('+919000000000')
> for n in range(8):
>     create_customer(actor=o, code=f'PERF-C-{n:05d}', shop_name=f'Rehearsal Shop {n}',
>                     phone=f'+9170000{n:05d}', billing_address='Rehearsal Bazaar')
> create_supplier(actor=o, code='S-0007', name='Acme Distributors',
>                 phone='+919876500011', billing_address='Industrial Estate')
> \""
> ```
>
> `Customer.zone` is nullable, so no zone is required. Seconds, not minutes — and
> `ops/perf-latest.json` is never touched.

**A rehearsal file must contain deliberate mistakes**, or the refusal path is assumed rather
than exercised:

```bash
cd /mnt/e/Projects/DistriCore

cat > backend/opening-rehearsal.csv <<'CSV'
party,code,amount,entry_date
CUSTOMER,PERF-C-00000,4500.00,2026-03-31
CUSTOMER,PERF-C-00001,1250.50,2026-03-31
CUSTOMER,PERF-C-00002,99999.99,2026-03-31
CUSTOMER,PERF-C-00003,0.00,2026-03-31
CUSTOMER,PERF-C-00004,-250.00,2026-03-31
CUSTOMER,NO-SUCH-CODE,100.00,2026-03-31
CUSTOMER,PERF-C-00001,777.00,2026-03-31
CUSTOMER,PERF-C-00005,abc,2026-03-31
CUSTOMER,PERF-C-00006,100.00,31-03-2026
PARTNER,PERF-C-00007,100.00,2026-03-31
CSV
```

Rows 2–4 are valid; rows 5–11 are each a different refusal — zero, negative, unknown code,
duplicate of line 3, unparseable amount, non-ISO date, unknown party.

```bash
DC="docker compose -f docker/compose.yml -f docker/compose.dev.yml --env-file .env"
PERF='DATABASE_URL="${DATABASE_URL%/*}/districore_perf"'

# 1. dry run — must refuse 7 rows and write nothing
$DC exec -T app sh -c "$PERF python manage.py load_opening_balances \
  --csv /app/backend/opening-rehearsal.csv --owner-phone 9000000000"

# 2. the valid rows only, committed
$DC exec -T app sh -c "$PERF python manage.py load_opening_balances \
  --csv /app/backend/opening-rehearsal.csv --owner-phone 9000000000 --commit --allow-partial"

# 3. run it again — must be a no-op and still reconcile
$DC exec -T app sh -c "$PERF python manage.py load_opening_balances \
  --csv /app/backend/opening-rehearsal.csv --owner-phone 9000000000 --commit --allow-partial"

rm backend/opening-rehearsal.csv
make perf-clean
```

**Expected, including the exit status — all three steps exit non-zero, and that is correct:**

| Step | Exit | What proves what |
| --- | :-: | --- |
| 1 dry run | **non-zero** | seven refusals, each named by line; **nothing written**. `A vs B not evaluated — dry run` |
| 2 `--commit --allow-partial` | **non-zero** | three customers loaded; `A = B`; the report names `--allow-partial`; still refuses to read as signed off, because refusals remain |
| 3 the same file again | **non-zero** | three `already carried`; **nothing new written**; `A = B` identical to step 2 |

Steps 2 and 3 exit non-zero because refusals are present — the file is deliberately dirty.
**That is the contract, not a failure of the rehearsal**: a run with refused rows never reads
as the report an owner signs, whatever was loaded. A clean file exits `0`, which is what
go-live itself will do.

**Step 3 is the property that matters** — a go-live import that cannot be re-run is one
nobody dares re-run.

Then confirm the development database was never touched:

```bash
$DC exec -T db psql -U districore -d districore \
  -c "SELECT count(*) FROM customer_ledger_entry WHERE entry_type = 'OPENING';"
```

Zero, unless you have genuinely loaded opening balances there.

### Rehearsal log — observed runs

> **This is the rehearsal, not the load.** It records that the *procedure* works against a
> disposable database. The go-live Load log below is a different table and stays empty until
> real figures are loaded against the real database.

| Date | Database | Result |
| --- | --- | --- |
| 2026-09-12 | `districore_perf` (disposable, dropped afterwards) | **PASS** — see below |

**2026-09-12, as observed.** Ten data rows: three valid, seven deliberate refusals.

| Step | Exit | Observed |
| --- | :-: | --- |
| 1 — dry run | non-zero | **7 rows refused**; 0 customer rows, 0 supplier rows; `DRY RUN — nothing written`; `NOT signed off` |
| 2 — `--commit --allow-partial` | non-zero | **3 customer rows loaded**; **A = B = C = 105,750.49**; `A = B`; 7 rows still refused; `NOT signed off` |
| 3 — same file again | non-zero | **0 loaded, 3 already carried**; **A = B = C = 105,750.49** unchanged; same 7 refusals; `NOT signed off` |

`105,750.49 = 4,500.00 + 1,250.50 + 99,999.99` — the three valid rows, and nothing else.

**What each property proved:**

- **Dry-run validation** — the file was judged and *nothing was written*, exactly as a
  validation pass must behave.
- **Fail-closed refusals** — all seven classes refused by line number: zero, negative,
  unknown code, in-file duplicate, unparseable amount, non-ISO date, unknown party.
  Non-zero exit in **both** modes, so a scripted operator cannot mistake a dirty file for a
  loadable one.
- **Partial load under `--allow-partial`** — the three valid rows loaded; the run still
  refused to read as signed off, because refusals remained.
- **Idempotent re-run** — the same file again wrote nothing and reported `already carried`.
  This is the property that makes the load safely re-runnable after a partial failure (D-10),
  and the one most worth having proved before go-live.
- **A/B/C reconciliation** — three independently derived figures agreed on both committed
  runs. B came from the `OPENING` entries, C from `settled_balance`; their agreement is
  evidence rather than tautology.
- **Development-database isolation** — afterwards,
  `SELECT count(*) FROM customer_ledger_entry WHERE entry_type = 'OPENING'` on `districore`
  returned **0**.
- **Cleanup** — the rehearsal CSV was removed and `make perf-clean` dropped
  `districore_perf`.

**Every step exited non-zero, and that is the contract**: the rehearsal file is deliberately
dirty, and a run carrying refusals never reads as the report an owner signs. Go-live uses a
clean file, which exits `0`.

**ACT-E is ready to execute. It has not been executed.**

---

## Load log

> **Empty, and deliberately so.** ACT-E has **not been executed**. The mechanism exists and
> is verified; the load itself is an owner action against real figures and is recorded here
> only by the person who watched it. An invented row is worse than an empty table.
>
> Record a failed or partial load just as carefully.

| Date | File | Rows (cust / supp) | A total (cust / supp) | Verdict | By |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
