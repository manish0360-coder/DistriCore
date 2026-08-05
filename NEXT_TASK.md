# Next Task

> The only hand-written handoff artifact (ADR-0005 §5.3). Rewritten at the end of every task.
> Everything else a session needs comes from `make brief`.
> **Design reasoning lives in `docs/M2_Design_Review.md`, not here.**

**Milestone:** M2 — Inventory & stock ledger
**Task:** 0 of 9 — **BLOCKED. Do not write code.**

---

## Blocked on — all four must be signed

| # | Item | Party | Where |
| --- | --- | --- | --- |
| 1 | **D-3 — audit scope for stock events** (Option A discretionary vs B every movement) | Product Architect | `M2_Design_Review.md` §2 |
| 2 | **M2-1 … M2-11 irreversible decisions** | All | `M2_Design_Review.md` §4 |
| 3 | **I-02 … I-12** carried from `04` §17 | All | `04_Database_Design.md` §17 |
| 4 | `M2_Design_Review.md` accepted | All | §6 |

Non-blocking but wanted before a clean start: TD-1 (`uv.lock` committed) · TD-15 (`offer`
assigned a milestone).

> **D-3 blocks task 5 only.** Tasks 1–4 are unaffected by it, but items 2–4 gate everything.

---

## Task decomposition — 9 tasks, each independently verifiable

Per ADR-0005 §6.2: commit and push after **each**. A session must never span more than one.

| # | Task | Delivers | Gated by |
| --- | --- | --- | --- |
| 1 | `stock_location` | Model, migration, one seeded default row, no UI | M2-1 |
| 2 | `stock_lot` | Model, migration, **select-then-upsert** lazy creation (D-1) | M2-2, D-1 |
| 3 | `stock_movement` | Model, migration, `CHECK` source-or-reason (M2-8), **sign-per-type `CHECK`** (M2-11). **`ops/check_structural_columns.py` becomes blocking here** | M2-1…M2-11 |
| 4 | Append-only | Trigger migration with `reverse_sql`; adversarial tests for raw `UPDATE`/`DELETE`; **escape-hatch runbook entry** in `incident-response.md` | M2-4 |
| 5 | `inventory.services` | `receive_stock` / `issue_stock` / `adjust_stock` — the only writers. **Accept validated model instances for `source_document` (R-2)** | D-3 |
| 6 | Derived selectors | On-hand per product. **Anchored on `Product`, `Coalesce` to a typed `Decimal("0.000")` (R-1)** | M2-3, R-1 |
| 7 | Concurrency suite | Adversarial: N concurrent movements sum correctly; randomised sequence reconciles | NFR-INT-002/003 |
| 8 | API | `GET /stock`, `GET /stock/movements`, `POST /stock/movements` | `05` §9.7 |
| 9 | Admin + debt | Stock list, stock-in and adjustment forms. **Close TD-12 (zone form) and TD-13 (product image)** | — |

---

## Design changes folded in since the review

| Change | Source | Task |
| --- | --- | :-: |
| Select-then-upsert for lot creation, savepoint-free | D-1 revised | 2 |
| **R-1** — aggregate selectors anchor on the dimension; `Coalesce` to a typed zero | Review #4 | 6 |
| **R-2** — polymorphic sources accept validated model instances only | Review #5 | 5 |
| **M2-11** — sign-per-type `CHECK` for `RECEIPT` / `ISSUE` | Chief Systems Engineer | 3 |
| Trigger escape hatch documented as a runbook step, not a code path | Review #3 | 4 |
| `allow_negative_allocation` **rejected for M2**, deferred to Edition 2 | ADR-0006 | — |

---

## Constraints binding on every task

- **Irreversible:** M2-1 … M2-11 (`M2_Design_Review.md` §4)
- **Non-negotiable:** N-03, N-05, N-10, BR-004, BR-007
- **Rules:** R-1 (dimension anchor), R-2 (validated instances)
- Structural gate `ops/check_structural_columns.py` becomes blocking at task 3

## Do not

- Do not add a cached balance table — EP-E, only if measured
- Do not implement allocation or reservation — Edition 2
- Do not implement `allow_negative_allocation` — ADR-0006
- Do not implement a physical count workflow — Edition 2
- Do not write a `stock_movement` anywhere outside `inventory.services`
- Do not take a lock on the stock path — M2 is deliberately lock-free (D-2)
