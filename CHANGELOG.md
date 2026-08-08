# Changelog

Generated from Conventional Commits (`00` §6.2). Versions follow SemVer (FD-18).

## [Unreleased]

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
