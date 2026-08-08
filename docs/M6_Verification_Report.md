# M6 — Receivables: Verification Report

| Field | Value |
| --- | --- |
| Document ID | `M6_Verification_Report` |
| Version | 1.0.0 |
| Status | **VERIFIED** — `make verify` 8/8 |
| Date | 2026-08-07 |
| Milestone | M6 — Receivables |
| Design authority | `docs/M6_Design_Review.md` v1.2.0 |
| Verify cycles to green | **5** |

> Every figure here comes from the single passing `make verify` run. Nothing from a
> failing run is reported as if it had passed.

---

## 1. Executive summary

M6 delivers the collection side of the ledger: payments, reversal, write-off, opening
balances, the customer statement, and **the derived FIFO outstanding view** that answers
*"who owes what, and which document is oldest."*

The governing principle held throughout implementation and needed no revision:

> **A payment reduces what a customer owes. It does not pay an invoice.**

There is no allocation table and no allocation column. Which invoices are consequently
settled is recomputed from immutable inputs whenever anyone asks — the third derived
quantity in the system after stock on hand (M2) and the settled balance (M5).

Five verify cycles. **Two of them found real algorithmic defects in the FIFO walk**, both
of the same underlying kind, and both found by the randomised property test rather than by
any example-based test (§4.4, §4.5).

**No frozen design decision was revised.** Three documentation conflicts were resolved
before code (C-1, C-2, C-3), and the one unresolved design hole — AR-2 — was specified in
full before implementation began, at the Product Architect's insistence. That instruction
was correct twice over: writing the specification found a defect, and implementing it
found two more.

---

## 2. Verification results

Docker is the only authority (N-12). Run of 2026-08-07:

| # | Stage | Result |
| --: | --- | --- |
| 1 | Clean build, `--no-cache` | **PASS** — 255.1s, 27/27 |
| 2 | Start, wait for healthchecks | **PASS** — db 30.0s, app 55.5s |
| 3 | No missing migration | **PASS** — "No changes detected" |
| 4 | Lint (`ruff check`) | **PASS** — all checks passed |
| 5 | Import contracts | **PASS** — 130 files, 242 dependencies, **3 kept / 0 broken** |
| 6 | Type check (`mypy`) | Advisory (`\|\| true`) — 17 errors in 6 files, 104 checked |
| 7 | Tests + coverage gate | **PASS** — **525 passed, 0 failed**, 115.88s, **93.92%** |
| 8 | Health endpoint | **PASS** — `database.ok` true, `disk.ok` true (2.3% used, 932.0 GB free) |

`backup.ok` is `false` with reason `"no backup stamp yet"` — expected on a volume created
seconds earlier by stage 2, and asserted as such by a test.

### 2.1 Environment

The pins introduced at M5 held: this run resolved the same toolchain as the last verified
one, which is what the pins exist to guarantee.

| Component | Version |
| --- | --- |
| Python · Django | 3.12.13 · 5.1.15 |
| pytest · pytest-django · pytest-cov | 9.1.1 · **4.12.0** · 7.1.0 |
| pluggy · anyio · Faker | 1.6.0 · 4.14.2 · 40.36.0 |

### 2.2 Delta across milestones

| | M0 | M1 | M2 | M3 | M5 | **M6** |
| --- | --: | --: | --: | --: | --: | --: |
| Tests | 100 | 192 | 245 | 312 | 449 | **525** |
| Coverage | 87.30% | 93.01% | 93.56% | 93.38% | 94.33% | **93.92%** |
| Statements | — | — | — | 2,372 | 3,542 | **4,081** |
| Contracts kept | 3 | 3 | 3 | 3 | 3 | **3** |
| Verify cycles | 4 | 4 | 1 | 2 | 4 | **5** |

76 tests added against a 539-statement increase. **Coverage fell 0.41 points** and is
recorded rather than rounded away; the gate is 80% and has never moved.

> **The per-module coverage table was truncated in the captured output of the passing
> run.** Only the total is reported here, because a per-module figure taken from an
> earlier failing run would not be a verified figure.

---

## 3. Architectural decisions confirmed by the run

| Decision | Evidence |
| --- | --- |
| **M6-1** — a payment is recorded against the customer, never an invoice | No allocation table exists; a payment writes one row and one ledger entry |
| **M6-2** — `payment_number` from `nextval`, allocated before the insert | Payments are written in one statement; the trigger is never engaged |
| **M6-3** — reversal is a compensating entry; the original is never edited | The ledger gains a second row; the balance returns to its prior figure |
| **M6-4** — `payment` mutable in exactly four fields | Raw SQL against every other column is refused |
| **M6-5** — `client_uuid UNIQUE` from the first migration | A replayed collection returns the original and credits once |
| **M6-6** — a credit note reduces its own invoice; payments settle FIFO | §5A.2's two-invoice case gives 1,000 / 800, not 800 / 1,000 |
| **M6-7** — a reversal or cancellation annuls its target | A reversed payment restores its invoice **at 82 days old**, not as fresh debt |
| **M6-8** — debits order by `(entry_date, id)` | Same-date invoices settle deterministically |
| **M6-9** — `device_id` from the first migration | Present, unused until M8 (structural enabler, E-06) |
| **M6-10** — write-off is a ledger entry, explicit amount, **no lock** | Owner-only, reason mandatory, audited |
| **M6-11** — one `OPENING` entry per customer | Re-running the import is a no-op; raw SQL refused by the partial unique index |
| **D-9 / §5A.7** — the invariant | Holds across five randomised seeds spanning all six entry roles |
| **R-2** — validated source instances | `Payment` registered; the third and final Edition 1 member |
| **M2/M3/M5 boundaries** | A payment moves no stock and modifies no invoice; every prior suite passes unmodified |

---

## 4. Defects found during M6

Nine. Three before implementation (independent review), two lint, and four during
verification.

### 4.1 Three found before code — the independent review

All three upheld; all three recorded in `M6_Design_Review.md` v1.2.0.

* **`payment_number` derived from the primary key could never have worked.** M3's pattern
  is insert-then-update, and `payment` carries an immutability trigger that forbids the
  update. A false analogy from a table without a trigger to one with it. Mechanism became
  a pre-insert `nextval`.
* **The write-off lock was a false guarantee.** It would have locked a row it does not
  mutate, against writers that never take it — every other ledger writer appends lock-free
  by design since M2. **A false concurrency guarantee is worse than none**, because the
  next maintainer trusts it. Removed; write-off takes an explicit amount instead.
* **`load_opening_balance` was not idempotent.** Now guarded by a partial unique index on
  the natural key: a customer has exactly one opening balance.

### 4.2 Two lint defects (cycle 1)

A Unicode minus sign in a docstring, and an unused loop variable.

### 4.3 The two RunSQL migrations (cycle 2 — 32 of 37 failures)

`payment_number_seq` and the payment immutability trigger. Django's autodetector generates
neither, so both are hand-written — the same category as `ledger/0002` and `billing/0002`.
Expected, and sequenced deliberately so the RunSQL migrations could depend on the real
generated name.

### 4.4 Two test defects that had hidden themselves (cycle 2)

* **`date(2026, 1, 1 + rng.randint(0, 200))`** — a day-of-month where a day *offset* was
  meant, asking January for its 201st day. **The §5A property test — the single most
  important test in M6 — had never once executed.**
* **`information_schema.tables` queried without a schema filter**, matching PostgreSQL's
  own `pg_shmem_allocations` system view. Worse than a false failure: the assertion would
  have failed identically on an empty database, so **C-1 was never actually being tested.**

### 4.5 Two algorithmic defects in the FIFO walk (cycles 3 and 4)

**These are the substantive findings of the milestone, and they are the same mistake
twice.**

**Cycle 3 — annulment was many-to-one.** `_annulled_entry_ids` looked its target up rather
than *claiming* it, so two annullers pointing at one document both matched: **three entries
left the walk where only two should**, and one amount vanished from the total while
remaining in the `SUM`. Fixed by consuming the target on match, and by requiring the pair
to offset — §5A.7's proof excludes annulled entries from both sides, which is sound only
for a matched, zero-sum couple.

**Cycle 4 — over-credit was silently discarded.** A credit note subtracted unconditionally,
so two notes against one invoice could drive `remaining` negative — and step 5 keeps only
positive remainders, dropping the negative amount entirely. Seed 42 reported 11,903.00
against a ledger sum of 11,729.00: **exactly 174.00 of credit lost.** Fixed by spilling
excess into the settling pool, which is also the correct accounting — crediting more than a
document is worth leaves the customer in credit on account.

#### The common root cause

> **`_walk` trusted invariants enforced in other modules instead of holding its own.**

Annulment trusted that `cancel_invoice` and `reverse_payment` never act twice. Reduction
trusted M5's B-7 cap on total credit. **Both assumptions are true in production** — the
services lock and return early, the triggers refuse independently, and B-7 is enforced
under a row lock. Neither was true of the function in isolation.

A read model over a financial ledger cannot borrow its correctness from its callers. The
one thing it must never do is return a number that looks plausible and is wrong, and both
defects did exactly that: no exception, no warning, just a total that was quietly short.

`remaining` is now provably bounded in `[0, original_amount]`, so §5A.7 holds for **any**
input, not merely for inputs the services can produce.

---

## 5. What the milestone delivered

| Area | Delivered |
| --- | --- |
| Table | `payment` — plus `payment_number_seq` and a column-aware immutability trigger |
| Constraint | `uq_cle_one_opening_per_customer` on the existing ledger table |
| Module | `receivables` — layers contract now 13 root packages, `receivables` above `billing` |
| Services | `record_payment`, `reverse_payment`, `write_off`, `load_opening_balance` |
| The walk | `_walk` — classify, annul, reduce, settle. **Pure**, no database access |
| Reads | Outstanding position, receivables report, statement with opening/closing, collections by user |
| API | 6 endpoints (05 §9.6) |
| Screens | Payments, customer outstanding, receivables position |
| Tests | 76 added — 18 for the walk alone, including a five-seed property test |

---

## 6. Known limitations

Each follows from a decision recorded in the design review.

| # | Limitation | Source |
| --- | --- | --- |
| L-1 | **No payment-to-invoice allocation.** A running account, as the client's ledger book already works | C-1, `02A` §13.2 |
| L-2 | Aging is a derived list with 30/60/90 as display constants — no bucket engine | C-2 |
| L-3 | A double-submitted write-off writes two entries. Visible, audited, correctable — the same residual M2 accepted for duplicate manual adjustments | §6.2 |
| L-4 | Field collection is not available on mobile; `device_id` and `client_uuid` exist for M8 | FR-REC-010, v1.1 |
| L-5 | Cash-in-hand accountability per collector is not tracked | FR-REC-013, v1.1 |
| L-6 | A retailer cannot view their own balance | FR-REC-014, v1.2 |

---

## 7. Technical debt

### Closed by M6

**None.** M6 opened three items and closed none. Recorded plainly rather than omitted.

### New

| # | Item | Severity | Due |
| --- | --- | --- | --- |
| **TD-24** | Move `_ImmutableDocument` from `billing` to `core` (D-7, deferred by ruling). `Payment` imports it across a module boundary | Low | M10 |
| **TD-25** | Two new advisory `mypy` diagnostics — `receivables/selectors.py:156,161`, `tuple[str, int \| None]` against `tuple[str, int]`, from the annulment fix. Total is now 17, up from 15 at M5 | Low | M7 |
| **TD-26** | **The three robustness guards in `_walk` — one-to-one claiming, the zero-sum check, and the credit spill — are exercised only by the randomised property test.** No named unit test pins any of them. Changing the seeds could silently remove coverage of branches that took two verify cycles to find | **Medium** | M7 |

> **A deliberate non-defect, recorded so it is not "fixed" later.** The property-test
> generator produces ledger states unreachable in production — double cancellations,
> double reversals, over-credited invoices. That is now an **asset**: it is what found both
> algorithmic defects, and `_walk` is correct on those inputs by construction. A future
> reader tempted to constrain the generator to only-reachable states would remove the
> coverage that earned this milestone.

### Carried

| # | Item | Status |
| --- | --- | --- |
| **TD-21** | Reproducible build — `uv.lock` absent, `make lock` non-functional. **The M5 pins held this run**, which is evidence the stopgap works; the transitive gap remains | **Highest value, open** |
| **TD-11** | SMS / DLT registration — blocks go-live, unbounded external lead time, still not started | Unchanged |
| **TD-2 / TD-18** | Raise `mypy` to blocking. Set for M5, missed. Carried to M6, **missed again.** Recording a second miss rather than a second re-dating | **Missed twice** |
| **TD-14** | `Product._has_history()` still inert. Overdue since M3 | **Overdue** |
| **TD-22 / TD-23** | Advisory mypy items; `billing/selectors.py` authorisation branches under-covered | Open |
| **TD-15** | `offer` has no milestone | Open |

---

## 8. Readiness for M7 — Reporting

M7 is 1.5 units and is largely a consumer of what M6 built:
`receivables_position`, `customer_statement` and `collections_by_user` are the selectors
behind `/reports/receivables` and the Cash/UPI split. No new derivation is required.

**Two items should be settled before or during M7.**

1. **TD-21.** M5 lost a full verify cycle to dependency drift; M6 lost none, because the
   pins held. That is the stopgap working, not the problem solved.
2. **`02` FR-REC-004/006/008 still read "M, v1.0".** §3 of the design review records that
   `02A` §13.2 supersedes them, but **the next person to read `02` cold will conclude that
   Edition 1 allocates payments to invoices.** Owner: Product Architect.

**CF-1 remains open** and grows more expensive with every invoice issued.

---

## 9. Lessons

**1. A read model must hold its own invariants.** Both algorithmic defects came from
`_walk` borrowing correctness from its callers. Service guards and database triggers make
the malformed states unreachable — and neither fact was available to a pure function
handed a list. Robustness at the boundary of a module is not defensive coding; it is the
module being correct.

**2. The property test earned the milestone.** Eighteen example-based tests for the walk
passed while both defects were present. The randomised invariant found them, and it found
them as *arithmetic* — 174.00 missing — which pointed straight at the mechanism. An
algorithmic derived view needs a property, not more examples.

**3. Requiring AR-2 to be specified before implementation was right twice.** Writing §5A
found the *annulling* class, which neither the design nor the self-critique had seen.
Implementing it found two more defects. Stopping at "targeted reduction, obviously" would
have shipped all three.

**4. A test that cannot fail is worse than a missing test.** The allocation-table
assertion would have failed identically on an empty database, and the property test had
never executed at all. Both read as coverage in every prior report.

**5. Five cycles, and only two were domain work.** One went to lint, one to migrations that
by definition could not be generated, and one to test defects of my own. Cycle count
measures milestone difficulty only when everything else holds still.

**6. M6 closed no technical debt.** Three items opened, none retired, and two long-standing
commitments missed again. A milestone can be green and still lose ground on debt.

---

*Verified 2026-08-07. `make verify` 8/8, 525 passed, 93.92% coverage, contracts 3 kept /
0 broken. No implementation code was modified in producing this report.*
