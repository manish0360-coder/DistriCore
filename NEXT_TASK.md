# Next Task

> The only hand-written handoff artifact (ADR-0005 §5.3). Everything else comes from `make brief`.
> Design reasoning lives in `docs/M2_Design_Review.md` (FROZEN, signed 2026-08-05).

**Milestone:** M2 — Inventory & stock ledger
**Task:** all 9 implemented — **awaiting `make verify`**

---

## Run this

```bash
cd /mnt/e/Projects/DistriCore && make verify
```

Expected: 8/8 stages, 245 tests, coverage above 80%.

## If green

1. Commit with the message below, push.
2. Tag `m2-inventory`.
3. Ask for `docs/M2_Verification_Report.md`.
4. Then M3 — Pricing.

```
feat(inventory): add the stock ledger

Implements M2 of the frozen roadmap. Three tables, no stored quantity anywhere:
stock on hand is SUM(stock_movement.quantity) (N-03, E-01, BR-004).

Design decisions per docs/M2_Design_Review.md (frozen 2026-08-05):
  D-1 select-then-upsert lot creation, savepoint-free
  D-2 negative stock permitted and reported; no locks, no deadlock surface (ADR-0006)
  D-3 audit iff movement_type == ADJUSTMENT
  R-1 aggregate selectors anchor on the dimension, Coalesce to a typed zero
  R-2 polymorphic sources accept validated model instances only
  M2-11 sign-per-type CHECK for RECEIPT and ISSUE

Closes TD-12 (zone screens) and TD-13 (product image upload) from M1.

Refs: FR-STK-001..026, 04 T-08 T-11 T-12 T-13
```

## If red

Send me the stage number and raw error. I will not start M3 until 8/8.

---

## Delivered

| # | Task | State |
| --- | --- | :-: |
| 1 | `stock_location` + seeded default | done |
| 2 | `stock_lot` + select-then-upsert lazy creation (D-1) | done |
| 3 | `stock_movement` + 4 CHECK constraints. **ADR-0004 gate now passes** | done |
| 4 | Append-only trigger + 7 adversarial tests | done |
| 5 | `inventory.services` — the only writer; R-2 registry; D-3 audit rule | done |
| 6 | Derived selectors anchored on `Product` (R-1); `as_of`; negative-stock report | done |
| 7 | Concurrency suite — 10 parallel writers, randomised reconciliation | done |
| 8 | `GET /stock`, `GET/POST /stock/movements` | done |
| 9 | Stock screens + **TD-12** zone form + **TD-13** product image | done |

## Known, to record in the M2 report

- `SOURCE_DOCUMENT_REGISTRY` is empty in M2 by design; `fulfilment.Delivery` registers at M5.
  The accept path is covered by a monkeypatched test, not by a real caller.
- The trigger escape hatch still needs writing into `docs/runbooks/incident-response.md`.
- TD-1 (`uv.lock`) and TD-15 (`offer` milestone) remain open.
