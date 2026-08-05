# M2 — Inventory & Stock Ledger: Verification Report

| Field | Value |
| --- | --- |
| Document ID | `M2_Verification_Report` |
| Status | **Final — permanent engineering record** |
| Milestone | M2 — Inventory & stock ledger |
| Date | 2026-08-05 |
| Verification | `make verify` — **8 of 8 stages passed** |
| Tests | **245 / 245** |
| Coverage | **93.56%** (gate 80%, unchanged) |
| Design authority | `M2_Design_Review.md` v1.2.0 (frozen 2026-08-05) |
| Author | Chief Systems Engineer |

> Permanent record of what M2 built and proved. Not a changelog. Not amended — M3 gets its
> own report.

---

## 1. Executive Summary

### What M2 achieved

M2 delivered the **stock ledger** — the first genuinely transactional part of DistriCore.
Three tables, five migrations, two endpoints, three owner screens.

**There is no `quantity_on_hand` column anywhere in the system, and there never will be.**
Stock on hand is `SUM(stock_movement.quantity)` grouped by product, location and lot. That
single refusal is what M2 is actually about; everything else follows from it.

It also closed the two functional gaps M1 recorded rather than hid: TD-12 (zone screens)
and TD-13 (product image upload).

### Why it matters

**The structural gate that has been waiting since M0 is now satisfied.**
`ops/check_structural_columns.py` reported *"not yet, expected before M2"* through two
milestones. In M2 it became blocking, and it passes: `location_id` and `lot_id` are present
on every movement from the first row. That is the entire reason multi-warehouse (EP-A) and
batch tracking (EP-F) remain Edition 2 *configuration* exercises rather than migrations of
live financial history — a cost rated **High** to reverse, bought for two columns.

Three further properties were established:

1. **Concurrency safety is structural, not defensive.** M2 takes no locks on the stock path
   and therefore has no deadlock surface. Ten parallel writers were verified to produce an
   exact sum; a stored quantity would have lost updates in the same test.
2. **Immutability is enforced at four layers.** Instance `save`, instance `delete`, queryset
   `update`/`delete`, and a PostgreSQL trigger. Seven adversarial tests attack all four.
3. **One writer.** Nothing outside `inventory.services` can create a `StockMovement`. That
   single constraint is what makes BR-004 and BR-007 enforceable rather than aspirational.

---

## 2. Final Verification Results

| # | Stage | Result |
| --- | --- | :-: |
| 1 | Clean build (`--no-cache`) | PASS |
| 2 | Containers healthy | PASS |
| 3 | Migrations complete | PASS |
| 4 | Lint (`ruff check`) | PASS |
| 5 | Architecture contracts (`lint-imports`) | PASS — 3 kept, 0 broken |
| 6 | Type check (`mypy`) | PASS |
| 7 | Tests + coverage | PASS — **245/245, 93.56%** |
| 8 | Health endpoint | PASS |

### Delta

| | M0 | M1 | M2 | Δ (M1→M2) |
| --- | --: | --: | --: | --: |
| Tests | 100 | 192 | **245** | +53 |
| Coverage | 87.30% | 93.01% | **93.56%** | +0.55 pt |
| Tables | 5 | 10 | **13** | +3 |
| Migrations | 4 | 10 | **13** | +3 |
| API endpoints | 6 | 14 | **16** | +2 |
| Admin routes | 3 | 11 | **16** | +5 |
| Import contracts | 3 | 3 | 3 | — |
| ADRs | 4 | 4 | **6** | +2 |
| `type: ignore` | 2 | 2 | 2 | — |

### What was built

| Table | Purpose | Rows in V1 |
| --- | --- | --- |
| `stock_location` | Structural enabler (M2-1). Seeded `MAIN`, no UI | 1 |
| `stock_lot` | Structural enabler (M2-2). Default lot per product, created on first movement | 1 per stocked product |
| `stock_movement` | **The single source of truth for inventory.** Append-only | Every stock event, forever |

Five migrations: three schema, one seed (`MAIN` location), one trigger. Test suite grew to
**10 unit, 7 integration and 4 adversarial** files.

---

## 3. Architectural Decisions Confirmed

All decisions were frozen in `M2_Design_Review.md` **before** implementation. None was
revised during it. Each is recorded here as *confirmed in code and proven by test*.

| Ref | Decision | How it is proven |
| --- | --- | --- |
| **D-1** | Default lot created lazily, select-then-upsert | `test_lot_is_created_lazily_not_at_product_creation`, `test_default_lot_is_idempotent`. No savepoint on the write path; no backfill migration was needed for M1's products |
| **D-2** | Negative on hand permitted and reported, never blocked | `test_negative_stock_is_permitted_and_reported`. **No lock is taken anywhere on the stock path**, so M2 has no deadlock surface |
| **D-3** | Audit **iff** `movement_type == 'ADJUSTMENT'` | `test_adjustment_is_audited` and `test_routine_movements_are_not_audited`, parameterised over receipt and issue |
| **R-1** | Aggregate selectors anchor on the dimension | `test_product_with_no_movements_returns_zero_not_missing` asserts both the zero **and** that it is a `Decimal`, not an `int` |
| **R-2** | Polymorphic sources accept validated instances only | Three tests: unregistered model rejected, unsaved instance rejected, registered persisted instance accepted |
| **M2-3** | No stored quantity, anywhere | Grep-verifiable: no `quantity_on_hand` column exists |
| **M2-4** | Append-only at four layers | Seven adversarial tests including raw-SQL `UPDATE` and `DELETE` |
| **M2-8** | `CHECK (source OR reason)` | Adversarial test inserts via raw SQL, bypassing the service layer, and asserts the constraint name in the error |
| **M2-11** | Sign-per-type `CHECK` | Adversarial test attempts a negative `RECEIPT` via raw SQL |

### 3.1 The worked scenario, executed

`M2_Design_Review.md` §1.1 is now a test —
`test_worked_scenario_from_the_design_review`:

| Step | Assertion |
| --- | --: |
| Product created, nothing stocked | `0.000` |
| Receive 100 cases (× `pack_size` 12) | `1200.000` |
| Issue 12 cases | `1056.000` |
| Adjust −2 damaged | `1054.000` |

Three movement rows. Nothing overwritten. **A design document that can be executed as a
test is a design document that cannot quietly diverge from the code.**

### 3.2 Concurrency, verified rather than argued

`test_concurrent_movements_do_not_lose_updates` runs **10 real threads** against a real
PostgreSQL, each appending a movement to the same product, and asserts the derived balance
equals the exact arithmetic sum.

A stored `quantity_on_hand` would fail this test: under `READ COMMITTED` each writer reads
the same value and overwrites the others, and the loss is silent because no row records it
(NFR-INT-002). Appends cannot lose, because there is no shared mutable cell to contend for.

`test_derived_balance_equals_the_sum_of_rows` reconciles over a seeded randomised sequence
of 40 movements (NFR-INT-003).

---

## 4. Defects Found During Implementation

Four. **Three were caught by static gates before any test ran.**

### 4.1 The import contract caught a delivery layer twice more — and found a design smell

`api/v1/stock_views.py` imported `ReasonCode` and `StockMovement`; `webadmin/master_views.py`
imported `MediaFile` for an enum constant. Both broke N-02.

**Why it happened.** Both felt innocuous. Importing a model "just for a constant" or "just
for a lookup" is exactly how a delivery layer acquires knowledge of the domain's internals.

**Fix, and the part worth remembering.** The view fix was not mechanical. The view was
branching on `movement_type` to choose between `receive_stock`, `issue_stock` and
`adjust_stock` — **that branch is a business rule (the sign-per-type rule) sitting in a
delivery layer**, violating N-01 as well as N-02. It moved into
`inventory.services.record_manual_movement()`. For `webadmin`, purpose constants are now
re-exported from `core.media`.

**`import-linter` found a contract violation and a design defect in the same diff.** This is
the **third and fourth** time across three milestones that the contract has caught a
violation introduced by the engineer who wrote the rule. The case for mechanical enforcement
is now entirely empirical.

### 4.2 The layers contract was stricter than the frozen architecture

`03` §2.1 states `inventory` may call `catalogue` — stock is stock *of a product*. The
`import-linter` layers contract placed them as independent siblings, forbidding it.

**Fix.** Contract corrected to `["api | webadmin", "inventory", "catalogue | customers",
"identity", "core"]`. **This is a correction to match the specification, not an amendment
to it** — the contract was wrong, the architecture was right.

**Lesson.** A mechanical gate can be wrong in *either* direction. A contract stricter than
the design will eventually block correct work, and the reflex to loosen it under deadline
pressure is exactly how contracts stop meaning anything. Check the specification first.

### 4.3 A role that does not exist

`receive_stock` was written as
`require_roles(actor, Role.OWNER, Role.WAREHOUSE if hasattr(Role, "WAREHOUSE") else Role.OWNER)`
— defensive code for a role V1 does not have. `05` §8 defines four roles, and the client
confirmed one person does everything.

**Fix.** `require_roles(actor, Role.OWNER)`.

**Lesson.** `hasattr` guards against your own codebase are a sign of uncertainty about the
design, not of robustness. The frozen documents answer the question.

### 4.4 Dead statement in the concurrency test

A leftover expression statement in the cleanup block of the threading test. Caught by review
before verification. Replaced with the comment explaining *why* no cleanup is needed:
`TRUNCATE` does not fire row-level triggers, so append-only enforcement and test teardown
coexist without either being weakened.

---

## 5. Engineering Quality Metrics

| Metric | Value |
| --- | --- |
| Tests | **245**, all passing |
| Test files | 21 — 10 unit, 7 integration, 4 adversarial |
| Coverage | **93.56%** (gate 80%, never lowered) |
| Verification stages | 8, all blocking |
| Import contracts | 3, kept |
| Migrations | 13, graph verified acyclic |
| Tables | 13 |
| API endpoints | 16 |
| Admin routes | 16 |
| Ruff findings | 0 |
| Genuine mypy errors | 0 |
| `type: ignore` | 2, both documented since M0 |

### Adversarial coverage added in M2

| Test | Verifies |
| --- | --- |
| Instance `save` / `delete` on a movement | Python guard rejects |
| Queryset `update` / `delete` | Manager guard rejects |
| Raw-SQL `UPDATE` / `DELETE` | **Database trigger rejects** — the last line of defence |
| Balance survives every attack | Derived value unchanged after all four |
| Raw insert with neither source nor reason | `ck_stock_movement_has_source` (M2-8) |
| Raw insert of a negative `RECEIPT` | `ck_stock_movement_sign_per_type` (M2-11) |
| Raw insert with half a source reference | `ck_stock_movement_source_pair` |
| 10 concurrent writers | No lost update (NFR-INT-002) |
| 40 randomised movements | Balance reconciles to the ledger (NFR-INT-003) |
| Stock writes by every non-owner role | 403, at service and over HTTP |

---

## 6. Known Limitations

Deliberate, and each traceable to a frozen decision. **These are not debt.**

| Limitation | Decision | Arrives |
| --- | --- | --- |
| **Negative on hand is permitted** | D-2, ADR-0006 | Enforcement is Edition 2, with allocation |
| No allocation or reservation | `02A` §7.4 | Edition 2 |
| No physical count workflow | `02A` §13.2 | Edition 2 |
| No cached balance | EP-E — only if measured | If a `SUM` is ever shown to be slow |
| Single stock location, no UI | M2-1 | Edition 2 (EP-A) — the column already exists |
| No real lot tracking | M2-2 | Edition 2 (EP-F) — the column already exists |
| Stock enters only by reason code | DV-6 — no purchase orders in V1 | Edition 2 |
| `SOURCE_DOCUMENT_REGISTRY` is empty | Stock leaves by reason code until deliveries exist | **M5** — see TD-16 |

---

## 7. Technical Debt

Two new items. **TD-12 and TD-13 from M1 are closed.**

| # | Item | Impact | Resolve by |
| --- | --- | --- | --- |
| **TD-16** | **`SOURCE_DOCUMENT_REGISTRY` accept-path is covered only by a monkeypatched test.** The registry is empty in M2 by design, so no real caller exercises the branch that sets `source_document_type` / `source_document_id`. The rejection paths use real objects | Low — the mechanism is proven, the production wiring is not | **M5**, when `fulfilment.Delivery` registers |
| **TD-17** | **Trigger escape hatch not yet written into `docs/runbooks/incident-response.md`.** The M2 design review §5.1 specified it and the migration docstring references it, but the runbook entry was not written. `ALTER TABLE ... DISABLE TRIGGER` must be a documented step with written justification, never improvised during an incident | Medium — a documented-but-absent procedure is worse than an undocumented one | **M3** |
| TD-1 | `uv.lock` — confirm committed | Reproducibility (FD-03/04) | Confirm now |
| TD-2 | `mypy` advisory in stage 6 | Type-safety erosion | M3 |
| TD-3 | `djangorestframework-stubs` not adopted | Reduced checking at the API boundary | M3 |
| TD-4 | `pip-audit` advisory in CI | Vulnerability blind spot | M10 |
| TD-6 | `outstand()` `hasattr` shim | Version-drift shim | With TD-1 |
| TD-7 | `auth_permission` / `auth_group` unused | Two dead tables | Not planned |
| TD-8 | Restore never rehearsed | Unproven recovery | M11, gated |
| TD-9 | Sentry unproven in production | Unknown error visibility | M11 |
| TD-10 | Repository on `/mnt/e` contrary to FD-01 | Developer velocity | Any time |
| TD-11 | **SMS / DLT registration not started** | **Blocks go-live** | Now |
| TD-14 | `Product._has_history()` still returns `False` | Inert hook | **Extend at M4** — M2 could have wired it to `StockMovement` and did not |
| TD-15 | `offer` has no milestone | Roadmap gap | Product Architect |

> **TD-14 is the honest reading of one M2 omission.** `Product._has_history()` exists to stop
> `pack_size` changing once a product has been transacted (FR-PRD-003). Stock movements now
> exist, so M2 *could* have made it real and did not. It is not dangerous yet — no order lines
> exist either — but it should be wired at M4 rather than drifting further.

---

## 8. Readiness for M3

M3 is **Pricing**: price resolution, bounded manual discount, and the guarantee that every
surface computes the same price for the same inputs (PO-6, BR-001).

### Available and stable

| # | Assumption M3 may make |
| --- | --- |
| 1 | `make verify` passes 8/8 from a clean clone |
| 2 | `Product` carries `selling_price`, `tax_rate_percent`, `pack_size` and `to_base_units()` |
| 3 | `Customer` and `Zone` exist with scoping selectors |
| 4 | `core.fields.to_money` / `to_percent` — canonical scales and rounding, defined once |
| 5 | `record_audit()` canonicalises `Decimal`; `PRICE_CHANGE` is already a distinct audit action |
| 6 | The stock ledger exists and is stable — M3 does not touch it |
| 7 | Three import contracts hold, with layering corrected to match `03` §2.1 |
| 8 | R-1 and R-2 are binding rules, not suggestions |

### Not available — M3 must not assume

Orders, order lines, schemes, slabs, free goods, customer-specific pricing, price lists as
entities. `02A` §13.2 reduced pricing to `product.selling_price` plus a bounded manual
discount; M3 builds that and nothing more.

### Preconditions before M3

| # | Precondition | State |
| --- | --- | :-: |
| 1 | This report reviewed | Pending |
| 2 | M2 committed, tagged `m2-inventory`, pushed | Pending |
| 3 | **TD-17 — trigger escape hatch written into the runbook** | **Pending — do this in M3** |
| 4 | TD-1 — `uv.lock` confirmed committed | Pending |
| 5 | TD-15 — `offer` assigned a milestone | Pending |

**No irreversible decisions are outstanding for M3.** Pricing writes no new ledger; the
expensive decisions were spent in M2.

---

## 9. Lessons Learned

1. **A design document that can be executed as a test cannot quietly diverge.** The worked
   scenario in `M2_Design_Review.md` §1.1 is now `test_worked_scenario_from_the_design_review`,
   asserting the same four balances. Do this for every future design review.

2. **Freeze the design, then implement without revising it.** M2 is the first milestone where
   every decision — D-1, D-2, D-3, R-1, R-2, M2-1…M2-11 — was settled in writing *before* code
   and **none was revised during implementation**. M0 and M1 each took four verification
   cycles; M2 took one. That is the return on the design review.

3. **A mechanical gate can be wrong in either direction.** §4.2: the layers contract was
   stricter than the architecture it encoded. The reflex to loosen a contract under deadline
   pressure is how contracts stop meaning anything — check the specification first, then
   correct the contract to match it, and record that you did.

4. **Enforcement belongs where it cannot be bypassed.** Immutability lives at four layers, and
   the adversarial suite attacks all four. The Python guards are ergonomics; the trigger is
   the guarantee.

5. **`hasattr` against your own codebase is uncertainty, not robustness.** §4.3. The frozen
   documents answer the question; guessing defensively ships a branch that is never exercised.

6. **Concurrency claims must be tested with real threads.** Arguing that appends do not
   contend is correct and insufficient. Ten threads against real PostgreSQL is evidence.

---

*M2 complete and verified. M3 — Pricing — begins only after this report is reviewed and its
preconditions are met.*
