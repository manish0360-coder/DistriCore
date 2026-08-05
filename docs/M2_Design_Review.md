# M2 — Inventory & Stock Ledger: Design Review

| Field | Value |
| --- | --- |
| Document ID | `M2_Design_Review` |
| Version | 1.2.0 |
| Status | **FROZEN — signed off 2026-08-05. Implementation authorised** |
| Date | 2026-08-05 |
| Milestone | M2 — Inventory & stock ledger |
| Reviewers | Product Architect (ChatGPT) · Independent (Gemini, 95/100) · Chief Systems Engineer |
| Depends on | `00` v1.0.0 · `04` v0.1.0 · `02A` v0.2.0 |

> Durable record of the M2 design decisions. Written because decisions must not live in
> chat history (`00` §10, ADR-0005 §10). `NEXT_TASK.md` holds the task queue and points
> here; this document holds the reasoning.
>
> **No code may be written until §6 is signed.**

---

## 1. The governing principle

Stock on hand is **not a stored number**. It is `SUM(stock_movement.quantity)` filtered by
product, location and lot (N-03, E-01, BR-004). Every decision below follows from refusing to
keep a mutable quantity anywhere.

The corollary: `stock_movement` is append-only. A correction is a compensating movement, never
an edit — the same property `audit_log` has, for the same reason.

### 1.1 Worked scenario (summary)

Product `P-1001`, `pack_size = 12`.

| Step | Rows written | Derived on hand |
| --- | --- | --: |
| Owner creates product | `product` + `audit_log`. **No lot** — lots are created on first movement | 0.000 |
| Warehouse receives 100 cases | `stock_lot` (on demand) + `stock_movement +1200.000` (RECEIPT, reason `PURCHASE_IN`) | 1200.000 |
| Issue 12 cases | `stock_movement −144.000` (ISSUE). In M2 by reason code; from M5 by `source_document = Delivery` | 1056.000 |
| Owner adjusts −2 damaged | `stock_movement −2.000` (ADJUSTMENT, reason `DAMAGE`) | 1054.000 |

Three movement rows, three facts, nothing overwritten. The M5 transition changes one column
from the reason side to the document side — no migration, no re-architecture (E-06).

### 1.2 Why not a stored quantity

A read-modify-write on `product.quantity_on_hand` loses updates under `READ COMMITTED`:
two concurrent dispatches each read 1200, each write their own result, and one movement
vanishes with no error and no row to prove it happened (NFR-INT-002).

The ledger has no such window: two `INSERT`s do not contend. **Concurrency safety is
structural, not defensive** — there is no shared mutable cell to race for.

A ledger can always produce a cached balance later (EP-E, reconstructible). A stored quantity
can never produce the ledger. Cost: a `SUM` today · **Severe** to reverse.

---

## 2. Decisions requiring confirmation

### D-1 — Default lot creation: **select-then-upsert** *(revised after review)*

Lots are created lazily by `inventory.services`, not eagerly by `catalogue.services`. This
avoids a layer dependency **and removes the need for a backfill migration** for products M1
already created.

**Revision.** The original proposal used `get_or_create`. That is *not* race-prone — the
`uq_stock_lot (product_id, lot_code)` constraint plus Django's savepoint-and-retry handles
contention correctly. But the reviewer was right that an upsert is preferable, for reasons the
review stated differently:

| | `get_or_create` | Bare `ON CONFLICT DO NOTHING` | **Adopted: select-then-upsert** |
| --- | --- | --- | --- |
| Savepoint on the write path | Yes | No | **No** |
| Queries, hot path (lot exists) | 1 | 2 (insert attempt + select) | **1** |
| Returns the row on conflict | Yes | **No** | **Yes** |
| Poisoned-transaction risk | Non-zero | None | **None** |

**Adopted:** plain `SELECT` first; on miss, `bulk_create(..., update_conflicts=True,
unique_fields=["product_id","lot_code"])`, which returns the primary key on PostgreSQL.
Race-free, savepoint-free, one query in the common case.

### D-2 — Negative on hand is **permitted and reported**, not blocked

M2 takes **no locks**. A rule that refuses to issue more than on hand is a read-then-write
across rows and requires a lock anchor.

Reasons for permitting, in order of weight:

1. **The frozen design already decided.** Allocation and reservation are Edition 2
   (`02A` §7.4). FR-STK-013 produces an outcome, not a rejection.
2. **Blocking produces worse data.** A distributor's paperwork lags physical reality. A system
   that refuses a dispatch the warehouse has already made teaches staff to stop recording —
   and unrecorded movements are the failure the ledger exists to prevent.
3. **Negative on hand is a signal, not a corruption.** It means paperwork is behind. The stock
   report surfaces it; the owner reconciles.

**On the proposed `allow_negative_allocation` flag: rejected for M2. See ADR-0006.**

Should enforcement ever be wanted, the anchor already exists: `SELECT ... FOR UPDATE` on the
`stock_lot` row serialises writers per product-lot, then `SUM`, then `INSERT`. It is a
one-function change and the same anchor M5 allocation will use.

### D-3 — Audit scope for stock events **— DECIDED: Option A**

`stock_movement` is *already* an immutable, attributed, timestamped, reason-bearing record. A
parallel `audit_log` row for every document-driven issue duplicates it and roughly doubles the
write volume of the largest table in the system.

| Option | Rows/year at DR-8 | Argument |
| --- | --: | --- |
| **A — discretionary only** (movements carrying a `reason_code`) | ~50k | The document *is* the record for document-driven movements. `02A` §13.2 read as "the irreversible subset" |
| **B — every movement** | ~500k | `02A` §13.2 read literally as "stock events". Uniform, no judgement call at the call site |

**DECIDED — Option A** (Product Architect, 2026-08-05):

> Audit only *discretionary* stock movements — manual adjustments, administrative
> corrections, exceptional inventory operations. Routine ledger entries (receipts, issues,
> returns, opening balance) are already immutable inside `stock_movement` and must not
> generate duplicate audit records.

**Implementation rule, stated crisply so no call site has to judge:**

> **A movement is audited if and only if `movement_type == 'ADJUSTMENT'`.**

`RECEIPT`, `ISSUE`, `RETURN` and `OPENING` are routine and write no `audit_log` row. The
movement itself carries actor, timestamp, reason and immutability — everything an audit row
would have duplicated.

---

## 3. Rules adopted from the independent review

Both generalise beyond M2 and are binding from here on.

### R-1 — Aggregate selectors anchor on the **dimension**, never on the fact table

Anchoring a stock query on `stock_movement` with a `GROUP BY` makes products with zero
movements **disappear from the result set**. A `None` is visibly wrong; a silently shorter
stock report is not — the owner reads it, believes it, and orders against it.

**Required form:**

```
Product.objects.annotate(
    on_hand=Coalesce(Sum("movements__quantity"),
                     Value(Decimal("0.000")),
                     output_field=QuantityField())
)
```

`Coalesce` to a **typed** zero. A bare `0` returns an `int` and reintroduces the exact
canonical-representation defect fixed in M1 (`M1_Verification_Report` §4.3).

**The same trap waits in M6:** a customer with no ledger entries must show a zero balance, not
vanish from the receivables report.

### R-2 — Polymorphic sources accept **validated model instances only**

`04` T-13 relaxes D-06 (no foreign key on `source_document_type` / `source_document_id`) and
states that integrity "is enforced in `inventory.services`" — without specifying how. Accepting
`(type: str, id: int)` means one typo produces an orphan the database cannot catch: the full
cost of the relaxation with no compensating control.

**Required form:** services accept `source_document=<model instance>`. The service derives type
and id from the instance, verifies it is persisted, and rejects any model outside an explicit
registry of permitted source types.

"Trust the caller" becomes "the caller must possess the thing". **This is what makes M2-9
defensible rather than merely documented.**

---

## 4. Irreversible decisions — sign-off required

Each takes physical effect in the M2 migration. After it has run against real data, none is
cheaply reversible.

| # | Decision | Cost to reverse | Signed |
| --- | --- | :-: | :-: |
| **M2-1** | `location_id` on every movement, defaulted to the seeded location (I-03, E-06) | High | **Signed** |
| **M2-2** | `lot_id` on every movement, defaulted to the per-product lot (I-03) | High | **Signed** |
| **M2-3** | **Derived balance — no `quantity_on_hand` column anywhere** (I-05) | **Severe** | **Signed** |
| **M2-4** | Append-only, enforced by trigger | **Severe** | **Signed** |
| **M2-5** | Signed `quantity`, not separate in/out columns | High | **Signed** |
| **M2-6** | Base units only; `pack_size` converts at capture | **Severe** | **Signed** |
| **M2-7** | `NUMERIC(14,3)` quantity via `to_quantity()` (I-07) | High | **Signed** |
| **M2-8** | `CHECK (source_document_id IS NOT NULL OR reason_code_id IS NOT NULL)` (BR-007) | **Severe** | **Signed** |
| **M2-9** | Polymorphic source, no FK — **compensated by R-2** (`04` T-13) | Medium | **Signed** |
| **M2-10** | `occurred_at` separate from `created_at` (offline capture, M9) | High | **Signed** |
| **M2-11** | **Sign-per-type `CHECK`** — see below | High | **Signed** |

### M2-11 — sign-per-type check *(added by the Chief Systems Engineer; not raised in review)*

Nothing currently prevents a `RECEIPT` with negative quantity or an `ISSUE` with positive.
That is a whole class of sign error the database can reject for free:

```
CHECK (
  (movement_type = 'RECEIPT' AND quantity > 0) OR
  (movement_type = 'ISSUE'   AND quantity < 0) OR
  (movement_type IN ('ADJUSTMENT', 'RETURN', 'OPENING'))
)
```

The three unconstrained types are legitimately bidirectional — a sales return is inbound, a
purchase return outbound. **Free to add in the M2 migration; High to add once a sign error is
already in the ledger.**

---

## 5. Review provenance

Independent review scored the design 95/100 and raised five observations.

| # | Observation | Outcome |
| --- | --- | --- |
| 1 | Atomic upsert for lot creation | **Accepted**, rationale corrected, refined to select-then-upsert (D-1) |
| 2 | Configurable `allow_negative_allocation` | **Rejected for M2** — ADR-0006 |
| 3 | Trigger vs test/CI coexistence | **Confirmed**, plus an escape hatch neither party specified (§5.1) |
| 4 | LEFT JOIN anchored on `Product` | **Accepted and generalised** — R-1 |
| 5 | Validated instances for polymorphic sources | **Accepted** — R-2 |
| — | Sign-per-type check | **Added by the Chief Systems Engineer** — M2-11 |

### 5.1 Trigger coexistence — confirmed, with the escape hatch

Empirically settled: M0's `audit_log` trigger passed `make verify` 8/8 twice alongside seven
adversarial tests including raw-SQL `UPDATE` and `DELETE`.

- pytest-django rolls back per test — no `DELETE` is ever issued, so the trigger is never in
  the cleanup path.
- Django's flush uses `TRUNCATE ... CASCADE`, and **row-level triggers do not fire on
  `TRUNCATE`** — `--reuse-db` and `TransactionTestCase` are unaffected.
- The migration carries `reverse_sql`.
- **No test may bypass it.** A test that needs to delete a movement is a wrong test.

**Escape hatch, not previously specified.** If a movement is ever genuinely wrong, the answer
is a compensating movement. If a true emergency demands otherwise, `ALTER TABLE ... DISABLE
TRIGGER` requires table ownership and is a **runbook step with written justification**, never a
code path. To be added to `docs/runbooks/incident-response.md` in task 4, so nobody improvises
it during an incident.

---

## 6. Sign-off

Implementation may not begin until all four are complete.

| # | Item | Party | Status |
| --- | --- | --- | :-: |
| 1 | **D-3 — audit scope for stock events** (§2) | Product Architect | **Signed — Option A, 2026-08-05** |
| 2 | **M2-1 … M2-11 irreversible decisions** (§4) | All | **Signed — 2026-08-05** |
| 3 | **I-02 … I-12** carried from `04` §17 | All | **Signed — 2026-08-05, via M2-1…M2-11** |
| 4 | This document accepted | All | **Signed — 2026-08-05** |

Also outstanding, not blocking design but blocking a clean start: TD-1 (`uv.lock` committed)
and TD-15 (`offer` assigned a milestone).

---

*Architecture frozen 2026-08-05. Implementation authorised. Task decomposition in `NEXT_TASK.md`.*
