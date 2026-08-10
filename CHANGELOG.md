# Changelog

Generated from Conventional Commits (`00` §6.2). Versions follow SemVer (FD-18).

## [Unreleased]

### M8 Phase 2, task 0 — `GET /reports/dashboard`

**Added**

- **`GET /reports/dashboard`** — the four D-4 scalars over HTTP for Owner Companion Mode
  (`docs/M8_Design_Review.md` v1.2.0 §3.4.1), contracted at `05` §9.11.1. Three of the four
  numbers were already reachable from the report endpoints; **`collected_today` was not** —
  only a paginated payment list, which the device would have had to page and sum, deriving a
  figure on the device over 2G.
- **`api.v1.report_views.money_string()`** — AD-02 encoding for a hand-built response dict.

**Design**

- **Not a `_ReportView`.** That base renders a `ReportTable` and honours `?format=csv`; a
  dashboard has neither columns nor rows. Subclassing would mean inheriting a shape in order
  to override both halves of it away.
- **The refusal of CSV is the renderer list, not a branch.** `DashboardView` declares only
  `JSONRenderer`, so DRF's format negotiation has nothing to match `?format=csv` against and
  raises `Http404`. An `if wants_csv: raise` is a rule someone deletes while adding a
  feature; an absent renderer is not.
- **No period parameter.** `dashboard()` accepts `today` so tests can pin the day; exposing
  it would make the two live numbers reproducible for arbitrary past dates — precisely the
  authority M7 §8.2 withholds. `/reports/sales` answers that question, with a CSV.
- **M7 §8.2 is half overturned, deliberately.** It said *"the owner dashboard is not an
  endpoint … it offers no CSV."* Its stated reasoning is that a non-reproducible figure must
  not acquire the authority of a **document** — an argument about export. The export stays
  refused; the read is allowed. `Dashboard`'s docstring was corrected rather than left to
  assert something now false.

**Found**

- **The seven existing report endpoints emit money as JSON floats**, against AD-02 — whose
  stated rationale names Dart, and whose client obligation is C-1. `COERCE_DECIMAL_TO_STRING`
  is set but only reaches `serializers.DecimalField`; `_as_json` hand-builds its dict, so
  DRF's encoder renders `Decimal("1180.00")` as `1180.0`. **Measured, not inferred.**
  - The existing assertion reads `Decimal(str(body["total"]["sales"]))` — **the `str()`
    wrapper makes it pass whichever type arrives**, which is how seven endpoints carried this
    through four reviews and a blocking type gate.
  - **Recorded as TD-36 and not fixed here.** Changing the seven is a breaking change to a
    published response type; it gets its own change and its own verify run. **It blocks M8
    task 8**, which reads `/reports/receivables`.
  - The same recurring shape as M7's four defects: **a rule enforced on one side of a
    boundary and not the other.** AD-02 was enforced in the serializer layer and not in the
    hand-built layer beside it.

**Tests** — 11 new (14 cases), 712 → **726**

- Money is a decimal string at canonical scale, **and non-zero**: a `collected` payment
  fixture exists so the assertion cannot pass against `"0.00"`, which is a string whatever
  the encoder does.
- A count is **not** stringified — over-applying AD-02 until it lies about the type is as
  wrong as under-applying it.
- `?format=csv` → `404`; and the dashboard is asserted **absent** from the seven-report CSV
  suite, so it cannot be handed an export by a parametrisation.
- Scoping proven non-vacuously through the existing `foreign_trade` fixture.
- Equality **against the selector**, not against literals — a hard-coded expectation would
  still pass if the view recomputed a number its own way (D-3). Pinned to the `as_of` the
  response reports rather than reading `date.today()` twice, so it cannot become TD-31's
  fifth instance.

**Verified** — 8/8, **726/726**, **94.88%**, `mypy` clean, **3 import contracts kept**.

---

### Types — the `mypy` gate is blocking (TD-2 / TD-18)

**Fixed**

- **Three signatures that lied about what a function returned.** These were the only errors
  in the set that described a real defect, and they are the reason the milestone was worth
  doing:
  - `inventory.variance_by_reason` declared `QuerySet[StockMovement]` and returned
    `values().annotate()` — **dicts**. One false annotation produced **five** errors: one at
    the return, four in `reporting.selectors` where the caller iterates the dicts.
  - `ledger.settled_order_ids` declared `QuerySet[int]`, claiming a queryset over a model
    called `int`.
  - `webadmin.invoice_pdf` declared `-> HttpResponse` and returned a `FileResponse`, which
    descends from `StreamingHttpResponse` — a **sibling** of `HttpResponse`, not a subclass.
    A caller trusting the annotation and reading `.content` would fail at runtime.
- **Two expression helpers built a heterogeneous kwargs dict**, inferred from its first
  assignment, making the later `kwargs["filter"] = Q(...)` a type error. Replaced with named
  arguments; `filter=None` is `Sum`'s own default, verified attribute by attribute against
  the previous aggregate.
- **Four narrowing gaps** in `order_serializers`, `receivables` and `billing/pdf`.

**Changed**

- `weasyprint.*` added to `ignore_missing_imports`; the now-unnecessary
  `# type: ignore[no-any-return]` removed. The two were **inversely coupled** and had to
  move together — the direction was not predictable in advance.
- `on_hand` typed with django-stubs' `WithAnnotations` under `TYPE_CHECKING`. A hand-rolled
  stub class was rejected: it would make the type system believe **every** `Product` has the
  attribute, including where it does not.
- **`mypy` is now blocking** in `make verify` stage 6 **and** in CI. The stale
  *"advisory until M2; hard gate from M3"* comment is gone — it had been wrong since M3.

**Closed**

- **TD-2 / TD-18**, at the fourth attempt. Missed at M5, M6 and M7, each time for a sound
  reason; the fourth time there was none left.
- **TD-22 / TD-25** — all 24 diagnostics fixed. **None silenced with `Any`.**

**Note**

- Coverage 94.85% -> 94.83%. The `TYPE_CHECKING` block can never execute and so can never be
  covered — a deliberate trade for not lying about `Product`.
- Scope held: **`disallow_untyped_defs` was not turned on globally** and
  `djangorestframework-stubs` was not adopted. Both are separate changes (TD-33), because
  this one was about closing the gate, not raising the bar behind it.

### Build — the build is reproducible for the first time (TD-21)

**Fixed**

- **The pipeline had the shape of a lockfile build and none of its substance.** The
  Dockerfile copied `uv.lock*` — a glob, so a missing lock was a **silent success** — and
  then ran `uv pip install -r pyproject.toml`, which resolves from PyPI against the
  specifiers and **never opens the lock**. Generating a lock was the smaller half of TD-21;
  making the build consume it was the larger half, and it had not been named.

  It was wrong in **three** places, not one: the Dockerfile builder, builder-dev, and
  `.github/workflows/ci.yml`. A green CI that installed different packages from the gate is
  worse than no CI.

- **`make lock` could never have worked.** It ran `uv` inside the app container, where `uv`
  is not installed — it lives only in the `builder` stage — and wrote to `/app`, which is
  not bind-mounted, so the artefact could not have reached the repository.

**Added**

- **`uv.lock` — 91 packages**, generated and committed. The `==` pins bound three *direct*
  dev dependencies; the lock binds every transitive one, which is the surface the
  pytest-django 4.13.0 incident moved through.
- `[tool.uv] package = false` — **an architectural statement, not a workaround.**
  DistriCore's repository root is an application, not a distribution: nothing has ever
  built, installed or imported a `districore` package, and every `districore.*` name in the
  codebase is a logger. It is also what lets the dependency layer work, since D-3 installs
  dependencies *before* copying code and a packaged root would have to be built from a
  context with no source in it. It does not constrain future internal packages — a
  non-package root with workspace members is the recommended uv layout.
- `make lock` now runs in a throwaway uv container against the working tree: no `uv` in the
  app image, no `/app` bind mount, no running stack, and the lock lands owned by the caller.

**Changed**

- All three install sites use `uv sync --frozen`, which **refuses to re-resolve**: a lock
  that disagrees with the manifest fails the build rather than quietly resolving something
  else.
- `COPY pyproject.toml uv.lock ./` — **the glob is gone.** A missing lock is now a hard stop
  at stage 1. `make verify` became its own proof, and no new test was required.

**Closed**

- **TD-21**, deferred through M5, M6 and M7.

**Note**

- The `==` dev pins are now redundant but **deliberately kept**. Retiring them in the same
  change that introduced the lock would move two variables at once — recorded as TD-32.

### Performance — the receivables walk was quadratic (TD-27, FR-RPT-015)

**Fixed**

- **`receivables ageing` took 11.7 seconds at the DR-8 envelope, breaching FR-RPT-015's
  10-second budget.** Step 1 of the §5A FIFO walk read:

  ```python
  live = [e for e in entries if e.pk not in _annulled_entry_ids(entries)]
  ```

  A comprehension re-evaluates its condition for every element, so `_annulled_entry_ids`
  ran **once per entry** — allocating a fresh dict and set each time and rescanning every
  entry. O(n²) where O(n) was intended: ~10.6 million entry-visits across 1,000 customers.

  Fixed by hoisting the call. The function is **pure**, so hoisting an invariant call out
  of a loop is result-preserving by construction — §5A.7's invariant, the FIFO ordering and
  edge cases E-1…E-13 are untouched, and **no test needed changing.**

  Measured 36× faster at the observed shape, and **267× at 400 entries per customer** — the
  defect was getting worse as the ledger grew, which for a distributor it only ever does.

- **`dashboard` took 11.8 seconds** for the same reason: it calls `receivables_position`
  for its total-outstanding metric. One root cause, two breaches.

**Note**

- No index was added, no aggregate stored, no report logic changed. M7 §7 requires a breach
  to be answered by an index or a **domain** optimisation; this was neither — an algorithmic
  defect in the module that owns the rule. `reporting`, the schema and the migrations are
  untouched.
- Every comprehension in production code was swept for the same defect class. **Zero other
  sites.**
- **Top customers — the independent reviewer's suspect (§17.2) — measured 0.221s.** The
  index concern did not materialise at this envelope, and none was added.

**Closed**

- **TD-27.** FR-RPT-015 was the last Edition-1a requirement with no evidence behind it. It
  now has a measurement, a defect that measurement caught, and a fix it verified:
  **0 breach(es)**.

### Fix — the test suite now builds users the way production does (TD-30)

**Fixed**

- **`UserFactory` never reached `UserManager._create`.** `DjangoModelFactory._create` ends
  in `manager.create()`, so no user in 703 tests had ever been built the way production
  builds one. It hid two defects in a row: phone numbers stored uncanonicalised (factory
  phones were already canonical), and the owner-bootstrap deadlock (factory users already
  had roles). **A clean install could fail while the suite stayed green — and did, for
  eight milestones.**

  `_create` now routes through `create_user`, and `password` moves from a `post_generation`
  hook to a plain declaration so it reaches the manager as an argument rather than being
  written over the top afterwards. Six call sites; none passed `phone=`.

  TD-30 had two halves, closed differently and recorded as such: **creation** is closed
  structurally and cannot regress without a test failing; **role granting** is closed by
  direct coverage of `grant_role` and `bootstrap_owner` rather than by routing `roles=`
  through them, which would make every fixture needing a salesman carry an owner and make
  fixtures order-dependent (`docs/TD-30_Factory_Creation_Path_Note.md` §3).

- **Four tests read the wall clock while asserting against a constant.** `receive_stock`
  defaults `occurred_at` to `timezone.now()`; the assertions bounded periods with hard-coded
  August dates. `test_the_last_day_of_a_period_is_included` failed the morning the date
  rolled past its constant — **it had never tested what it claimed**, only that the calendar
  still agreed. Three others would have failed on 1 September.

  Fixed by stating the instant: pinned in both `stocked` fixtures, and in the boundary test
  at the **last microsecond** of the period, so a `time.min` bound excludes it and a
  `time.max` bound includes it. That assertion now discriminates between the two
  implementations, which it never did before. Recorded as **TD-31** — the class matters more
  than the four instances.

**Added**

- `backend/tests/unit/test_factories.py` — 9 tests of the test infrastructure. The
  load-bearing one gives the factory a non-canonical phone and asserts it comes back
  canonical: the smallest statement of *"the factory takes the production path"*, and it
  fails the moment anyone reverts `_create`.

**Note**

- No production file changed. The entire diff is confined to `backend/tests/`.

### Fix — the system can now reach its own first authorised user (FR-IAM-014)

**Fixed**

- **A clean installation could not sign in to the admin at all.** `grant_role` requires an
  OWNER to act; a fresh database has none; and it was the **only** non-test writer of
  `user_role`. No management command, fixture or seed script existed. So no user could ever
  be granted the first role through any supported interface — an unreachable state whose
  only exit was a raw `INSERT` into `user_role`, an unaudited write into authorisation data
  and precisely what ADR-0003 exists to prevent.

  `createsuperuser` produced an account that authenticated correctly and was then refused
  with "This account cannot sign in here". `is_superuser` does not help and is not meant
  to: it feeds only `has_perm`, `has_module_perms` and `is_staff`, none of which DistriCore
  consults, because ADR-0003 excluded `django.contrib.admin`.

  Together with the phone defect above, the same class at two layers — **a rule enforced on
  one side of a boundary and not the other.**

**Added**

- `identity.services.bootstrap_owner` and `manage.py bootstrap_owner` — **FR-IAM-014's
  break-glass procedure**, priority `S` and unbuilt since `02` was written. Creates or
  promotes a user and grants OWNER. A third delivery surface that parses and delegates:
  every rule stays in `services.py` (N-01) and the command imports no model.
- `AuditLog.Action.OWNER_BOOTSTRAP` — FR-IAM-014's *"distinct high-severity event"*.
  `audit_log` has no severity column, so a distinct action code is the only way break-glass
  use is findable without a JSON containment query. `core/0005` is a state-only `AlterField`,
  third of its kind.
- `make owner PHONE=... [NAME=...] [REASON=...]`, and `make superuser` now says out loud
  that a login is not an authorisation.
- `docs/runbooks/first-owner.md` — the documented recovery procedure FR-IAM-014 requires.
- 18 regression tests (685 -> 703), including **one that asserts the deadlock itself**: with
  an empty `user_role` table `grant_role` refuses every actor. Without it, a later reader
  sees that `grant_role` "already does this", deletes the bootstrap as redundant, and
  restores the lockout with a green suite.

**Behaviour worth knowing**

- Refuses while any **active** owner exists — the ordinary path is then `grant_role`, which
  records who granted it. *Active*, not *any*: a deactivated sole owner **is** the recovery
  case, and a stricter guard would lock the business out permanently.
- Refuses a **deactivated target** rather than granting silently: `has_role` checks
  `is_active` first, so the grant would succeed and the login would still fail.
- `--reason` is **optional and never required**. A mandatory field on a break-glass path
  fails closed at the worst possible moment.
- The `FIRST_BOOT` / `RECOVERY` mode is classified by the service **from the database**, and
  the audit row carries the counts it was derived from alongside the label.
- `actor_user` and `user_role.granted_by` are **NULL**. Nobody authorised this grant; the
  truthful actor is an operator with shell access, who is unidentifiable.

**Closed**

- **`00` §20.3 criterion 2** — *"a user can log in ... by password on web"* — is satisfiable
  on a clean machine for the first time, and is now asserted end-to-end through the
  supported path.

### Fix — one canonical phone number

**Fixed**

- **A freshly created superuser could not log in.** `UserManager._create` stored the phone
  number verbatim while every lookup — `authenticate_password`, `request_otp`, `verify_otp`
  — normalised first. A user created as `7903324153` was stored as `7903324153` and
  searched for as `+917903324153`, so the row was never found. `check_password` was never
  reached: `if user is None or not user.check_password(...)` short-circuits, which is why
  the password verified in a shell and failed in a browser, and why the screen said
  "Incorrect phone number or password" while both were correct.

  The same class as the canonical-decimal defect M1 fixed — **a canonical representation
  enforced on read and not on write.**

**Added**

- `identity/phone.py` — `normalise_phone`, the canonical form of the login identity,
  defined once and placed below both the reader and the writer so a manager never has to
  reach up into the service layer. `identity.services._normalise_phone` re-exports it, so
  no existing call site changed.
- `identity/0004_normalise_user_phone` — data migration correcting rows already stored
  verbatim. It **copies** the rule rather than importing it, so a later change to the
  canonical form cannot rewrite history. **It refuses rather than merges:** two rows
  colliding on one canonical number raises with both user IDs and both raw values, because
  `phone` is `UNIQUE` and is the login identity (`04` T-01) — picking a winner would orphan
  a real account and its audit trail.
- 20 regression tests (665 -> 685): the manager and the `createsuperuser` command store the
  canonical form; login succeeds through the browser for `7903324153`, `917903324153` and
  `+917903324153`; a wrong password still fails for all three; and the three spellings can
  no longer become three users.

**Known limitation**

- **`UserFactory` bypasses `UserManager._create`** — `DjangoModelFactory` calls
  `Manager.create()`. No factory-built user has ever exercised the write path, which is why
  665 green tests missed this. The new tests build users through `create_user` on purpose.
  Recorded as TD-30; the factory itself is unchanged.

### M7 — Reporting

A report computes nothing. **It arranges, filters and totals figures the domain already
derives.** `reporting` is the only module in DistriCore that could be deleted without
changing a single stored fact or a single business rule.

**Added**

- `reporting` module — `selectors.py`, `csv.py`, `tables.py`. **No models, no services, no
  migrations, and absent from `INSTALLED_APPS`**, because it has nothing to install. Four
  AST tests assert that, including that it imports no `*.services` and no first-party
  `*.models`: `lint-imports` proves the layering but cannot forbid one submodule while
  allowing its sibling.
- **Seven reports** — sales (grouped by day, customer, product or salesman), stock position,
  stock variance, returns, receivables ageing, top customers, order pipeline. Plus CSV on
  the customer statement M6 already delivered.
- **The definition of "sales", stated on every screen and in every export** — invoice
  taxable value excluding cancelled invoices, less credit note taxable value. GST is not
  revenue; a credit note reduces the period it was *issued* in, not the period of the
  invoice it credits, because restating a closed period destroys every reconciliation the
  owner has already done by hand.
- **Returns and stock variance as two reports of two traces.** A credit note writes no stock
  movement (ADR-0009), so the financial and physical traces have no join and their totals
  legitimately differ. One report answers *what did we credit back*, the other *what came
  back* — and a test asserts they are **not** required to agree, so nobody later writes its
  opposite and then "fixes" the reports to satisfy it.
- **One CSV mechanism for all eight exports**, over one row shape. The screen and the file
  render the same object, so they cannot disagree. Each file carries its own definition in
  a comment header — a figure whose meaning lives only on a screen becomes folklore the
  first time it is emailed.
- **A four-number dashboard** — sales today, collected today, total outstanding, orders
  awaiting dispatch. Four questions, no number a slice of another, and **no export**: two of
  them describe today and are not reproducible, and an exportable figure acquires the
  authority of a document.
- `billing.selectors.issued_invoices` and `orders.selectors.awaiting_dispatch` — two
  predicates that turned out to have no owner. They went into the domain modules that own
  the meaning, not into `reporting`.
- Report scoping asserted per endpoint **and per export** for owner, salesman and retailer.
  A report is where a scoping bug becomes an information leak with a CSV attached.
- CSV formula-injection guard on text columns, and deliberately not on numeric ones — a
  leading `-` there is arithmetic, and quoting it would corrupt the figure the guard exists
  to protect.
- `ops/report_performance.py` — the DR-8 five-year harness for FR-RPT-015. **Written, not
  yet run.**
- 140 tests (525 -> 665); coverage 93.92% -> 94.47%.

**Changed**

- `02` -> v0.2.0. Ten requirement lines corrected in place with the reasoning recorded
  beside them (§14.1, §20.1); nothing deleted, deferred lines carry `Rel = v2.0`.
- `05` §9.11 — two endpoints added, and `/reports/stock` corrected from "valuation" to
  quantity. Purely additive; no existing path, parameter or field changed.

**Removed**

- **Stock valuation, from both stock reports.** `02`, `05` and `02A` all described one and
  the schema never supported it: `Product.selling_price` is the only money field on a
  product, and a cost basis is a purchasing artefact that arrives in Edition 2. Valuing at
  selling price would overstate working capital by the entire margin, on the one screen
  justified as "working capital visibility". Deferring a number is cheap; un-teaching one
  is not.

**Fixed**

- **Every CSV endpoint returned 404, and it was not a routing fault.** `format` is DRF's
  `URL_FORMAT_OVERRIDE`: `select_renderer` filters the view's renderers to those whose
  `format` matches and `filter_renderers` raises `Http404` when none do. With `JSONRenderer`
  configured alone, `?format=csv` filtered the list to nothing **inside `APIView.initial()`**
  — so the view never ran and eight endpoints looked missing rather than unacceptable.
  Fixed by registering a CSV renderer that passes through text the one CSV mechanism
  already produced.
- **The CSV writer quoted the header block.** `csv.writer` quotes any field containing a
  comma and the sales definition contains three, so those lines began with `"` instead of
  `#` and stopped being recognisable as comments. Header lines are prose, not a one-column
  row, and are now written verbatim behind a shared `COMMENT_PREFIX` the tests read rather
  than restate.
- **A scoping test that could not fail.** The out-of-zone customer had no transactions, so
  it was absent from every report whether the scoping worked or not. Every scoping test now
  asserts the owner *can* see the data before asserting the salesman cannot.

**Known limitation**

- **FR-RPT-015 is unverified.** 665 green tests say the reports are correct at ten rows;
  they say nothing about ten seconds at five years. The harness exists and has not been run
  (TD-27).

### M6 — Receivables

A payment reduces what a customer owes. **It does not pay an invoice.** The distributor
keeps a running account — udhaari — so which invoices are consequently settled is derived
FIFO at read time and never written down.

**Added**

- `receivables` module — `Payment`, recorded against the customer. No allocation table and
  no allocation column: allocation rows added later are additive, whereas allocation rows
  *removed* later would be a migration of live financial history (C-1, `02A` §13.2).
- **The §5A FIFO walk** — a pure function that classifies every ledger entry as *reducing*,
  *settling* or **annulling**, then applies credits to debits oldest-first. Nothing it
  produces is stored; it is the third derived quantity in the system after stock on hand
  and the settled balance.
- Reversal as a compensating ledger entry, under the **only lock in the milestone** — real
  because it locks the row it mutates, unlike the write-off lock that was specified and
  then removed for serialising nothing.
- Write-off with an explicit amount, owner only, reason mandatory, audited. Explicit
  because a balance-derived amount would carry a race no lock could fix, every other
  ledger writer being lock-free by design since M2.
- **Idempotent opening balances** — one `OPENING` entry per customer, enforced by a partial
  unique index. Re-running the go-live import after a partial failure is a no-op, whatever
  mix of loaded and unloaded customers it left behind.
- `payment_number` from a dedicated sequence read *before* the insert, so a payment row is
  written once and the immutability trigger is never engaged. Gaps are expected: a receipt
  is a reference, not a statutory series.
- Customer statement whose closing figure is the next period's opening figure by
  construction — both are the same `SUM` over the same immutable rows.
- 6 API endpoints, 3 owner screens, collections-by-collector selector for M7.
- 76 tests (449 -> 525); coverage 94.33% -> 93.92%.
- **A five-seed property test asserting `Σ outstanding - credit_on_account ≡
  settled_balance`** across all six entry roles.

**Fixed**

- **The FIFO walk lost money in two independent ways, and both were the same mistake:
  `_walk` trusted invariants enforced in other modules instead of holding its own.**
  - *Annulment was many-to-one.* Two annullers pointing at one document both matched it, so
    three entries left the walk where only two should and one amount vanished from the
    total while remaining in the `SUM`. Targets are now claimed on match, and the pair must
    offset.
  - *Over-credit was silently discarded.* A credit note subtracted unconditionally, so two
    notes against one invoice drove `remaining` negative — and only positive remainders are
    kept. Excess now spills into the settling pool, which is also the correct accounting:
    crediting more than a document is worth leaves the customer in credit on account.

  Both are unreachable through the services, and neither was reachable-proof in isolation.
  `remaining` is now provably bounded in `[0, original_amount]`, so the invariant holds for
  any input.
- **The §5A property test had never executed** — it built dates as `date(2026, 1, 1 + N)`,
  asking January for its 201st day. It read as coverage in every prior estimate.
- **The allocation-table assertion could not fail.** It queried
  `information_schema.tables` without a schema filter, matching PostgreSQL's own
  `pg_shmem_allocations`, and would have failed identically on an empty database.

**Changed**

- Layers contract extended to 13 root packages; `receivables` sits above `billing` for one
  reason — the walk resolves a credit note to its invoice, and that is a **read**. A
  structural test forbids importing `billing.services`.
- `customer_ledger_entry` gains one constraint. No column changes; `PAYMENT` and
  `WRITE_OFF` already existed in the type and sign CHECKs.

**Decisions**

- No ADR. M6 amends no milestone boundary.
- C-1/C-2/C-3 — `02A` §13 supersedes `02` on allocation and aging buckets; `reversed_at`
  and `reversed_by` added for symmetry with M5's invoice cancellation.
- D-4 — `payment_number` is a reference, not a statutory series.
- D-9 / §5A — the FIFO application rule, specified in full before implementation.
- D-10 — opening balances idempotent by natural key.
- D-7 **deferred** — `_ImmutableDocument` stays in `billing` until M10 (TD-24).

**Documentation**

- `docs/M6_Design_Review.md` v1.2.0 — including §5A, the FIFO specification.
- `docs/M6_Verification_Report.md` — verified results, nine defects, technical debt.

---

### M5 — Fulfilment & Billing

Dispatch makes stock physical; the invoice makes money owed. M5 exists to keep those two
boundaries separate, because conflating them is unrecoverable once history exists.

**Added**

- `ledger` module — `CustomerLedgerEntry`, append-only and trigger-enforced. A balance is
  `SUM(amount)`; nothing is stored. Given its own module rather than folded into
  `customers` because the architecture already answered this: `StockMovement` does not
  live inside `catalogue` (ADR-0008).
- `fulfilment` module — `Delivery`, one per order, with proof of delivery, GPS and
  `client_uuid` idempotency. **Dispatch writes the ISSUE movements**, carrying
  `source_document = Delivery` — the first document-driven stock in the system's history,
  which closes TD-16.
- `billing` module — GST tax invoice, credit note and `number_series`. Seller and buyer
  identity and every line value are snapshotted at issue, so a later price change cannot
  rewrite a document already issued.
- Gapless per-financial-year numbering under a row lock. A locked counter rather than a
  PostgreSQL sequence, because sequences are explicitly not gapless and a gap is a
  question from an auditor.
- CGST + SGST versus IGST, mutually exclusive and enforced by a database CHECK. Buyer
  state derived from GSTIN with an explicit override; where neither exists, intra-state is
  assumed **and recorded on the invoice** as `buyer_state_assumed`.
- `round_off_amount` stored on the document, not absorbed by whatever renders the total.
- Invoice PDF via WeasyPrint from the same template as the web view — rendered on first
  request, cached, and refused replacement by the database. A rendering handed to a
  retailer must not change because a template did.
- Credit exposure now partitions on ledger presence rather than order status, so every
  live order contributes to exactly one term and moves between them atomically at issue.
- 10 API endpoints, 6 owner screens, `customer.state_code`.
- 137 tests (312 -> 449); coverage 93.38% -> 94.33%.
- **20 adversarial tests driving raw SQL at the immutability triggers**, and Scenario F —
  a failed delivery followed by a full credit note — proving stock rises once, not twice.

**Fixed**

- **`issue_invoice` gated on a caller-supplied stale instance.** `dispatch_delivery`
  transitions the order through its own locked object, so every other reference kept
  saying `CONFIRMED`. This failed both ways: it refused invoices for orders that had
  shipped, and it would have invoiced an order cancelled in the database while the caller
  held a stale `DISPATCHED` snapshot. Services now re-read the row they gate on, under the
  lock they need. The same class was found and closed in `assign_delivery`.
- **`04` T-19's `restocked` flag permitted the same physical goods to be restocked
  twice.** After a failed delivery the goods really are back on the shelf, so an owner
  answering "were these restocked?" honestly would inflate stock. A field whose correct
  answer produces an incorrect result is a design defect; the flag is removed and a credit
  note writes no stock movement (ADR-0009).
- **`orders.selectors.OPEN_STATUSES` dropped dispatched-but-uninvoiced orders from credit
  exposure** — invisible at the moment the distributor is most exposed. Correct M3 code
  that became wrong the instant M5 made `DISPATCHED` reachable.
- `Invoice._mutable_fields` omitted `pdf_media`, so the first PDF request would have
  raised. Found by cross-checking the Python allow-list against the database trigger's.

**Changed**

- The verification toolchain is **pinned**, not bounded. Two `make verify` runs from the
  same commit produced 403 passing tests and then a dead test framework, differing only in
  `pytest-django` 4.12.0 → 4.13.0. Stage 1 builds `--no-cache` and resolves from PyPI with
  no lockfile, so the gate's own toolchain could change underneath unchanged source.
- The M3 boundary test asserting that `customer_ledger_entry` *does not exist* now asserts
  the rule it stood for — orders write no ledger entry — plus a structural check that
  `orders` may import the ledger's reader but never its writer.
- Layers contract extended to 12 root packages; `inventory | ledger` are siblings.

**Decisions**

- **ADR-0008** — `CustomerLedgerEntry` belongs to a dedicated `ledger` module. Resolves
  TD-19 a milestone before it was due.
- **ADR-0009** — a credit note writes no stock movement, deviating from `04` T-19.
- D-1/C-1 — dispatch writes the ISSUE, not delivery. `04` T-16 superseded.
- D-3/C-3 — buyer state derived from GSTIN with an explicit override column.
- D-8 — credit exposure re-evaluated at dispatch, reusing `evaluate_credit` unchanged.

**Documentation**

- `docs/M5_Design_Review.md` v1.1.0 — including §15, the independent review evaluation.
- `docs/M5_Verification_Report.md` — verified results, seven defects, technical debt.

---

### M3 — Commercial Operations

Pricing and orders merged into one milestone by ADR-0007: a pricing service with nothing
to price cannot verify PO-6. There is no M4.

**Added**

- `core.BusinessProfile` — tier-3 configuration singleton enforced by `CHECK (id = 1)`.
  Seller identity for GST invoices, the manual-discount ceiling, credit-limit mode and OTP
  validity. Created on demand so a fresh database, a restored backup and a test database
  behave identically.
- `pricing` module — `resolve_price`, the bounded manual discount, and line arithmetic.
  Owns no tables: it exists so every surface resolves a price through one function.
- `orders` module — `SalesOrder` and `SalesOrderLine`. Lines snapshot product name, unit
  price, tax rate and pack size at capture, so a later price change cannot rewrite an
  agreement already made.
- Five-state order lifecycle enforced in `CORE`, never settable by PATCH. Confirm and
  cancel are action endpoints, not status writes.
- Credit validation — exposure derived as settled balance plus agreed-but-unbilled orders.
  Warn-and-override or refuse, per `business_profile.credit_limit_mode`.
- `client_uuid` idempotency on orders: replaying a key returns the original order.
- Five API endpoints and six owner screens, including business settings.
- **Eight adversarial tests proving the M2 boundary**: place, amend, discount, confirm and
  cancel all leave the stock ledger untouched, and the `orders` package imports no
  `inventory` module.
- 67 tests (245 -> 312); coverage 93.56% -> 93.38%.

**Fixed**

- **`Product.to_base_units()` silently truncated fractional quantities.** It returned
  `int` and did `int(quantity)`, so ordering 2.5 kg would have stored 2. `QuantityField`
  is NUMERIC(14,3) precisely so fractional units work. Found by fixing the ambiguous
  quantity contract; `mypy` had flagged the exact line in an earlier advisory run.
- Order line input admitted two encodings of one fact — `quantity` plus an `in_packs` flag
  *and* `pack_quantity` — which could disagree and produced `Decimal("None")`. The caller
  now supplies exactly one; ambiguous input is refused, not resolved by default.
- The order/inventory boundary test asserted on raw source text and matched the word
  `StockMovement` inside the docstring explaining that stock is never moved. It now parses
  each module's AST across the whole `orders` package.

**Changed**

- `import-linter` layers extended to
  `api|webadmin > orders > pricing > inventory > catalogue|customers > identity > core`,
  matching `03` §2.1.
- `otp_expiry_minutes` now reads `business_profile` with the environment variable as a
  fallback, as `04` T-05 always specified.

**Decisions**

- ADR-0007 — merge pricing and orders into Commercial Operations; M4 retired, not reused.
- `M3_Design_Review.md`: D-1 credit exposure formula · D-2 price signature · D-3 order
  numbers are not gapless · D-4 audit every state change · D-5 OTP config source ·
  **R-3 immutable records are their own audit, mutable records need one** · M3-1…M3-10
  irreversible.

**Documentation**

- TD-17 closed: the append-only escape hatch is documented in
  `docs/runbooks/incident-response.md` with two-person authorisation, a verified backup
  first, and a usage log.

### M2 — Inventory & stock ledger

**Added**

- `stock_location` — structural enabler (M2-1). One seeded row, no UI. Multi-warehouse
  (EP-A) becomes an Edition 2 feature rather than a migration of live history.
- `stock_lot` — structural enabler (M2-2). Default lot created lazily on first movement by
  select-then-upsert: one query on the hot path, no savepoint, race-free.
- `stock_movement` — **the single source of truth for inventory.** Signed quantity,
  append-only, with four database CHECK constraints: source-or-reason (BR-007),
  non-zero, paired source reference, and sign-per-type for RECEIPT/ISSUE (M2-11).
- Append-only enforced at four layers: instance save, instance delete, queryset
  update/delete, and a PostgreSQL trigger. Seven adversarial tests attack all four.
- `inventory.services` — `receive_stock`, `issue_stock`, `adjust_stock` and
  `record_manual_movement`. The only writer of a stock movement in the codebase.
- Derived on-hand selectors anchored on `Product` with `Coalesce` to a typed zero, so a
  product with no movements returns `0.000` rather than disappearing from the report.
  Includes balance `as_of` any past instant, and a negative-stock report.
- `GET /api/v1/stock`, `GET`/`POST /api/v1/stock/movements`.
- Owner screens: stock on hand, movement ledger, and a single stock-entry form.
- **TD-12 closed** — zone create and edit screens. The customer form's zone dropdown was
  unfillable on a fresh install.
- **TD-13 closed** — product image upload in the admin form.
- 53 tests (192 -> 245); coverage 93.01% -> 93.56%.

**Changed**

- `import-linter` layers corrected to `api|webadmin > inventory > catalogue|customers >
  identity > core`, matching `03` §2.1. The previous contract was stricter than the
  architecture it encoded and forbade `inventory` from calling `catalogue`.
- Movement-type dispatch moved from the API view into
  `inventory.services.record_manual_movement`. The branch was a business rule (sign per
  type) sitting in a delivery layer.
- Media purpose constants re-exported from `core.media` so no delivery layer imports the
  model.

**Decisions**

- ADR-0005 — AI-assisted development workflow.
- ADR-0006 — negative stock permitted in Edition 1; allocation controls deferred to
  Edition 2.
- `M2_Design_Review.md` frozen before implementation: D-1 (lazy upsert lot), D-2 (no locks,
  negatives permitted), D-3 (audit iff ADJUSTMENT), R-1 (dimension-anchored aggregates),
  R-2 (validated source instances), M2-1…M2-11 irreversible.

### M1 — Master data

**Added**

- `customers` module: `Zone` (road, PIN code, panchayat, ward, city) and `Customer`
  (credit terms, coordinates, zone assignment), with scoping selectors.
- `catalogue` module: `Product` with pack size, GST rate, HSN code, selling price and
  image reference; base-unit conversion.
- `inventory` module: `ReasonCode` with 8 seeded rows. Stock ledger deferred to M2.
- `core.MediaFile`: single upload path with content sniffing, size limits, SHA-256, and
  retrieval only through an authorised view.
- Eight API endpoints: products (list/create/read/update), customers (list/create/read/
  update), zones, reason codes, media upload and retrieval.
- Eight owner screens: product and customer lists with search and forms, zone and reason
  code lists.
- `app_user.customer` foreign key — retailer logins are now bound to a shop (closes TD-5).
- 92 tests (100 -> 192); coverage 87.3% -> 93.01%.

**Fixed**

- **Money had no canonical representation.** `MoneyField(default=0)` placed an `int` on
  freshly created instances, so audit records wrote `"0"` where the database returned
  `"0.00"`. Rounding is now defined once in `core.fields` (`to_money`, `to_quantity`,
  `to_percent`, half-up) and applied where values enter the domain. `record_audit()`
  canonicalises `Decimal` recursively. No migration required — only the in-memory value
  was wrong.
- `CheckConstraint` for paired coordinates used `Q == Q`, which evaluates to a Python
  bool rather than an expression.
- `MediaDetailView` imported a model inside a method body, breaking the N-02 import
  contract.

**Security**

- Retailer scoping derived from the token; endpoints accept no `customer_id` (AD-11).
- Scope violations return 404, never 403, so record existence is not disclosed.
- Credit limit and price changes are owner-only with dedicated audit actions.
- Uploads validated on content signature, not on extension or client header.

### M0 — Foundation

**Added**

- Project scaffolding: Docker Compose (dev/prod), multi-stage non-root image, Caddy with
  automatic TLS, Makefile as the sole developer interface, GitHub Actions CI.
- `core` module: `TimeStampedModel`, append-only `AuditLog`, exact numeric field types,
  request-id correlation middleware, role primitives, storage seam, `/healthz`.
- `identity` module: custom user model keyed on mobile number, four seeded roles,
  many-to-many role assignment, OTP request/verify with hashed codes and rate limiting,
  password authentication, SMS provider interface (console / MSG91).
- `api/v1`: six authentication endpoints, RFC 9457 problem+json error handling,
  page-number pagination, scoped throttling.
- `webadmin`: server-rendered login, logout and placeholder shell.
- Structured JSON logging to stdout with request-id correlation; Sentry wiring.
- Runbooks: deploy, restore, rotate secrets, incident response, migration review.
- 47 tests across unit, integration and adversarial suites.

**Security**

- Argon2 password hashing; OTP codes stored hashed, never plaintext.
- `audit_log` immutability enforced in Python, by database trigger, and by test.
- Production settings refuse to start on unsafe configuration.
- Three-layer secret scanning: `.gitignore`, pre-commit, CI.
