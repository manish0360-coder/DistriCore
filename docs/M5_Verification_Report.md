# M5 — Fulfilment & Billing: Verification Report

| Field | Value |
| --- | --- |
| Document ID | `M5_Verification_Report` |
| Version | 1.0.0 |
| Status | **VERIFIED** — `make verify` 8/8 |
| Date | 2026-08-06 |
| Milestone | M5 — Fulfilment & Billing |
| Design authority | `docs/M5_Design_Review.md` v1.1.0 · ADR-0008 · ADR-0009 |
| Verify cycles to green | **4** |

> Every figure in this document comes from the single passing `make verify` run. Nothing
> is estimated, and nothing from a failing run is reported as if it had passed.

---

## 1. Executive summary

M5 delivers the two boundaries the milestone exists to separate: **dispatch makes stock
physical, the invoice makes money owed.** Six new tables, three new modules, ten
endpoints, six owner screens, and the first document-driven stock movements in the
system's history.

Four verify cycles. Only two of them were spent on M5 domain logic — one on a production
defect in `issue_invoice`, and one entirely on a dependency that changed underneath
unchanged source. That second cycle is the more instructive of the two and is recorded in
full in §4.4.

**No frozen design decision was revised during implementation.** Three contradictions in
the corpus were found and resolved *before* code, during the design review (C-1, C-2,
C-3), and two further defects — one in `04` T-19, one in shipped M3 code — were found by
the independent review and fixed by D-7 and D-9.

---

## 2. Verification results

Docker is the only authority (N-12). Run of 2026-08-06:

| # | Stage | Result |
| --: | --- | --- |
| 1 | Clean build, `--no-cache` | **PASS** — 147.9s, 27/27 |
| 2 | Start, wait for healthchecks | **PASS** — db 6.1s, app 16.1s |
| 3 | No missing migration | **PASS** — "No changes detected" |
| 4 | Lint (`ruff check`) | **PASS** — all checks passed |
| 5 | Import contracts | **PASS** — 116 files, 205 dependencies, **3 kept / 0 broken** |
| 6 | Type check (`mypy`) | Advisory (`|| true`) — 15 errors in 5 files, 95 checked |
| 7 | Tests + coverage gate | **PASS** — **449 passed**, 0 failed, 49.58s, **94.33%** |
| 8 | Health endpoint | **PASS** — `database.ok` true, `disk.ok` true (2.2% used, 933.3 GB free) |

`backup.ok` is `false` with reason `"no backup stamp yet"`. Expected on a volume created
seconds earlier by stage 2, and asserted as such by a test.

### 2.1 Environment

Pinned and recorded, because M5 proved this matters (§4.4):

| Component | Version |
| --- | --- |
| Python | 3.12.13 |
| Django | 5.1.15 |
| pytest | 9.1.1 |
| **pytest-django** | **4.12.0** |
| pytest-cov | 7.1.0 |
| pluggy · anyio · Faker | 1.6.0 · 4.14.2 · 40.36.0 |

### 2.2 Delta across milestones

| | M0 | M1 | M2 | M3 | **M5** |
| --- | --: | --: | --: | --: | --: |
| Tests | 100 | 192 | 245 | 312 | **449** |
| Coverage | 87.30% | 93.01% | 93.56% | 93.38% | **94.33%** |
| Statements | — | — | — | 2,372 | **3,542** |
| Contracts kept | 3 | 3 | 3 | 3 | **3** |
| Verify cycles | 4 | 4 | 1 | 2 | **4** |

137 tests added. Coverage rose 0.95 points against a 1,170-statement increase — the gate
remains 80% and has never been moved.

### 2.3 Coverage of the new modules

| Module | Stmts | Miss | Cover |
| --- | --: | --: | --: |
| `billing/services.py` | 163 | 0 | **100%** |
| `ledger/services.py` | 37 | 0 | **100%** |
| `api/v1/billing_serializers.py` | 130 | 0 | **100%** |
| `billing/registry.py` · `fulfilment/registry.py` | 5 · 4 | 0 | 100% |
| `fulfilment/services.py` | 114 | 1 | 99% |
| `ledger/models.py` | 46 | 1 | 98% |
| `billing/models.py` | 155 | 5 | 97% |
| `billing/pdf.py` | 30 | 1 | 97% |
| `api/v1/billing_views.py` | 159 | 6 | 96% |
| `fulfilment/models.py` | 33 | 2 | 94% |
| `ledger/selectors.py` | 29 | 2 | 93% |
| `webadmin/fulfilment_views.py` | 98 | 8 | 92% |
| `fulfilment/selectors.py` | 25 | 3 | 88% |
| **`billing/selectors.py`** | 45 | 10 | **78%** |

The three service modules — where every rule lives — are at 100%, 100% and 99%.
`billing/selectors.py` at 78% is the weakest surface in the milestone and is recorded as
TD-23.

---

## 3. Architectural decisions confirmed by the run

| Decision | Evidence in the passing run |
| --- | --- |
| **M5-1** — dispatch writes the ISSUE, not delivery | Scenario A: on hand falls at dispatch and does not move at delivery |
| **M5-2** — documents snapshot themselves | A price change and a product rename after issue leave the invoice and its PDF unchanged |
| **M5-3** — invoices, credit notes and ledger entries are append-only | 20 tests driving **raw SQL** at the triggers; every `UPDATE` and `DELETE` refused |
| **M5-4** — gapless numbering under a row lock | Five sequential invoices number 1–5; a rolled-back document releases its number |
| **M5-5** — the ledger entry is written in the invoice's transaction | Every document writes exactly one entry; balance reconciles |
| **M5-6** — the ledger is its own module (ADR-0008) | Layers contract kept with `inventory \| ledger` as siblings |
| **M5-7** — CGST+SGST XOR IGST | Database refuses a mixed split; intra-, inter-state and no-GSTIN paths all asserted |
| **M5-8** — a credit note is its own document | Independent series, `CN/` prefix, own table |
| **M5-9** — a failed delivery returns stock, never un-issues it | Two movements survive: the goods left, the goods came back |
| **M5-10** — `client_uuid` from the first migration | Dispatch, completion and failure all idempotent |
| **M5-11** — `round_off_amount` is stored | Reconciles: taxable + tax + round-off = payable |
| **M5-12** — a credit note writes no stock (ADR-0009) | **Scenario F**: failed delivery + full credit note leaves stock at 1200, not 1224 |
| **M5-13** — exposure partitions on the ledger | Exposure never dips through the dispatched-but-uninvoiced window |
| **R-2** — validated source instances | `Delivery` registered; the ISSUE carries `source_document_type = DELIVERY`. **Closes TD-16** |
| **M3-6** — orders write no stock and no ledger entry | The M3 boundary suite passes, 9 tests |

### 3.1 The M3 boundary suite

One assertion in it changed, and the change was a strengthening. It previously asserted
that the `customer_ledger_entry` table *did not exist* — true only while no milestone had
created it. M5 creates it, so the proxy would have failed while the guarantee it stood for
remained intact.

Before touching it, the boundary was checked directly: `orders` imports only
`ledger.selectors` (a read D-9 requires), and `record_entry` has exactly three callers,
all in `billing`. The test now runs a full place → amend → confirm → cancel cycle and
asserts zero ledger rows, and a new structural test forbids `orders` from importing
`ledger.services` — the writer — while permitting the reader.

**This is the same class as `OPEN_STATUSES`: a stand-in for a rule, correct only until the
thing it stood in for arrived.**

---

## 4. Defects found during M5

Seven. Two were found by reading before verification ran, three by the first verify cycle,
one by looking for the same class as a defect that had failed, and one by the infrastructure
itself.

### 4.1 `issue_invoice` gated on a caller-supplied stale instance — 40 of 44 failures

`dispatch_delivery` locks the delivery, reads `locked.sales_order`, and transitions **that**
Python object. Every other reference to the order keeps whatever status it last loaded.
`issue_invoice` read `order.status` from its argument and refused with `NOT_DISPATCHED`.

The failure signature identified it: `test_the_full_flow_over_http` **passed** — the API
re-fetches the order per request — while every service-level caller failed.

**This was a production defect, and it failed in the more dangerous direction too.** An
order cancelled in the database, with a caller holding a stale `DISPATCHED` instance, would
have been invoiced. A legal document was gated on a snapshot.

Fixed by re-reading the order under `select_for_update` — a lock the function needed
anyway, since it allocates a gapless statutory number. Two regression tests pin it,
including the cancelled-order direction.

### 4.2 The same class in `assign_delivery` — no failing test

Found by looking rather than by a failure. Its blast radius is small (a stray `PENDING`
delivery for a cancelled order, which dispatch would then refuse), but leaving half a class
of defect fixed is how it returns. Every other M5 service already re-read under lock.

### 4.3 Two test defects in the same cycle

* **Scenario C used `DAMAGE` (direction `OUT`) for an inbound return.** `SALES_RETURN`
  (`IN`, restockable, system) is seeded for exactly this. The reason-code direction rule
  from M2 caught a test that was wrong about the business.
* **Three tests asserted HTTP 400 where the frozen contract is 422.** `05` §4.1 and the
  exception handler are explicit: 422 means understood perfectly and invalid; 400 is
  reserved for an unparseable body. The API was right.

### 4.4 The verification toolchain changed underneath unchanged source

**The most important finding in this milestone, and it is not about M5.**

Two `make verify` runs from the same commit:

| | pytest | pytest-django | pytest-cov | Django | Result |
| --- | --- | --- | --- | --- | --- |
| Run A | 9.1.1 | **4.12.0** | 7.1.0 | 5.1.15 | 447 collected, 403 passed |
| Run B | 9.1.1 | **4.13.0** | 7.1.0 | 5.1.15 | Django `TestCase` failed to initialise; 414 cascading errors, 35 tests ran |

One variable differed, and the crash was inside the package that moved —
`pytest_django/fixtures.py::_django_db_helper`, on the `_pre_setup_ran_eagerly` attribute
4.13.0 introduced when it reworked that fixture. The failure landed on
`test_audit_immutability.py`: M0 code, untouched since M0, on first contact with the `db`
fixture.

**Root cause.** Stage 1 builds `--no-cache` and installs with
`uv pip install -r pyproject.toml`, which resolves from PyPI and reads no lockfile. Every
dev dependency carried a lower bound and no upper bound. `uv.lock` does not exist in the
repository.

**Fix.** The verification toolchain is now pinned in `pyproject.toml`, with the evidence
recorded beside the pins.

**Process note.** The first response to this failure was a diagnosis presented with more
confidence than the evidence supported, and a change to `pyproject.toml` made before the
hypothesis was tested. The Product Architect stopped it and required proof first. The
proof took one command and produced a single-variable result. **The correction was right,
and the sequence — prove, then change — is the one to keep.**

### 4.5 Two defects found by reading, before verification ran

* **`Invoice._mutable_fields` omitted `pdf_media`.** The first PDF request would have
  raised `DocumentImmutable`. Found by cross-checking the Python allow-list against the
  database trigger's — they must agree, and they did not.
* **The immutability suite was marked `transaction=True`**, whose teardown is a TRUNCATE.
  It would have destroyed the reason codes and default stock location seeded by
  migrations, for that test and every test after it, surfacing as *"No default stock
  location is configured"* far from the cause. Changed to per-statement savepoints,
  matching M2's ledger suite.

---

## 5. What the milestone delivered

| Area | Delivered |
| --- | --- |
| Tables | `delivery`, `invoice`, `invoice_line`, `credit_note`, `credit_note_line`, `number_series`, `customer_ledger_entry`; `customer.state_code` added |
| Modules | `ledger`, `fulfilment`, `billing` — layers contract extended to 12 root packages |
| Migrations | 6, including two trigger migrations (`ledger/0002`, `billing/0002`) |
| API | 10 endpoints — deliveries, dispatch, complete, fail, invoices, cancel, PDF, credit notes, ledger, balance |
| Screens | Deliveries, invoice list, invoice document, PDF, receivables, customer ledger |
| PDF | WeasyPrint, one template shared with the web view; rendered on first request and never replaced |
| Tests | 137 added — worked scenarios A/B/C/E/F, adversarial A-1…A-14, regression |

---

## 6. Known limitations

Each is a consequence of a decision recorded in the design review, not an oversight.

| # | Limitation | Source |
| --- | --- | --- |
| L-1 | **Goods on a van are simply "issued".** Between dispatch and delivery, on hand understates by the van load. Edition 1 has one stock location (M2-1) | C-1 |
| L-2 | Partial delivery is not supported — one delivery per order, enforced by a unique constraint | `02A` §7.7 |
| L-3 | A physical return and its credit note are two separate actions for the owner. The cost of D-7, paid deliberately | D-7 |
| L-4 | Negative on hand is permitted at dispatch and reported, never blocked | ADR-0006 |
| L-5 | Buyer state falls back to the seller's when no GSTIN and no explicit code exist. Recorded on the invoice as `buyer_state_assumed` | D-3 |
| L-6 | No e-invoicing (IRN/QR). **CF-1 is still unconfirmed — see §8** | O13 |

---

## 7. Technical debt

### Closed by M5

| # | Item |
| --- | --- |
| **TD-16** | `SOURCE_DOCUMENT_REGISTRY` accept path — `Delivery` is now a production caller, not a monkeypatch |
| **TD-19** | `credit_exposure` layering — resolved by ADR-0008 ahead of M6, as required |

### New

| # | Item | Severity | Due |
| --- | --- | --- | --- |
| **TD-21** | **`uv.lock` does not exist and the mechanism to create it does not work.** `make lock` runs `uv lock` in the dev container, but (a) `uv` is only copied into the `builder` stage, so it is absent from `runtime`/`dev`; (b) `/app` is not bind-mounted, so a generated lock would never reach the host; (c) `uv lock` will likely need `[tool.uv] package = false` to survive setuptools auto-discovery. The pins in §4.4 bound direct dependencies only — transitives still float on every `--no-cache` build | **High** | Next |
| **TD-22** | 15 advisory `mypy` diagnostics. 11 are django-stubs limitations in `inventory/selectors.py` and `ledger/selectors.py`; **4 are ours** — `billing/pdf.py:55,57,69` and `webadmin/fulfilment_views.py:134` (declared `HttpResponse`, returns `FileResponse`) | Low | M6 |
| **TD-23** | `billing/selectors.py` at 78%. The uncovered lines are the salesman and retailer scoping branches on invoices and credit notes — authorisation code, which is where under-testing matters most | Medium | M6 |

### Carried, with an honest note

| # | Item | Status |
| --- | --- | --- |
| **TD-11** | SMS / DLT registration — **blocks go-live**, unbounded external lead time, still not started | Unchanged |
| **TD-2 / TD-18** | Raise `mypy` to blocking. **The M3 report set this for M5. M5 did not do it.** It was explicitly de-scoped during the failure cycles and never picked back up. Recording the miss rather than silently re-dating it | **Missed** |
| **TD-14** | `Product._has_history()` still inert. Both references it should check — order lines and stock movements — have existed since M3 | **Overdue** |
| **TD-15** | `offer` has no milestone | Open |
| **TD-20** | DRF `min_value should be a Decimal instance` warnings, visible in stage 3 | Cosmetic |

---

## 8. Readiness for M6 — Receivables

M6 adds `payment` and the collection side of the ledger. The foundation is in place:
`customer_ledger_entry` exists, is append-only, and `receivables` will register `Payment`
in `ledger.services.SOURCE_DOCUMENT_REGISTRY` exactly as `billing` registered `Invoice`.
`03` §2.1's `receivables` row has already split — `ledger` holds the facts; M6 builds the
payments layer above it.

**Two things should be settled before M6 begins.**

1. **TD-21.** M5 lost a full verify cycle to dependency drift. The pins prevent a repeat
   for direct dependencies; transitives are still unbounded. This is now the highest-value
   debt in the repository and it is cheap to close.
2. **CF-1 — is statutory e-invoicing (IRN/QR) mandatory for this client?** Open since
   `01_Project_Vision.md`. **It is now materially more expensive than it was:** M5 issues
   invoices, so a late *yes* means adding columns *and* re-transmitting historical
   documents rather than only the former. The columns remain additive; the history does
   not.

---

## 9. Lessons

**1. A proxy for a rule expires when the thing it proxies arrives.** Twice in M5 —
`OPEN_STATUSES` gating exposure on order status, and a boundary test asserting a table's
non-existence. Both were correct when written and both silently stopped meaning what they
said the moment a later milestone landed. Assert the rule, not a stand-in that happens to
correlate with it.

**2. A field whose honest answer produces a wrong result is a design defect.** `04` T-19's
`restocked` flag asked "were these goods restocked?" at a moment when the goods genuinely
were back on the shelf. The correct answer inflated stock by 24 units. No amount of
training fixes that; removing the second writer does.

**3. Services must not gate on caller-supplied mutable instances.** Every M5 service
re-reads the row it gates on except one, and that one produced 40 failures. The asymmetry
was the diagnosis.

**4. When the gate itself can change, its verdict is not evidence.** A full cycle was lost
because a test framework upgraded underneath unchanged source. N-12 makes the Docker run
the sole authority on correctness; an authority that answers differently on consecutive
days is not one. TD-21 is the cost of having deferred this since M0.

**5. Prove before changing.** The dependency hypothesis was correct, but it was acted on
before it was tested. Being right by luck is indistinguishable from being right by method
until the one time it isn't.

**6. Two of four verify cycles were not about M5.** M2 took one cycle, M3 two, M5 four —
but only two of M5's were domain work. Cycle count is a proxy for milestone difficulty
only when the environment holds still.

---

*Verified 2026-08-06. `make verify` 8/8, 449 passed, 94.33% coverage, contracts 3 kept /
0 broken. No implementation code was modified in producing this report.*
