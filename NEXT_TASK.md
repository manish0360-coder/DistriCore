# Next Task

> Design reasoning: `docs/M3_Design_Review.md` · amendment: ADR-0007.

**Milestone:** M3 — Commercial Operations
**Task:** all 9 implemented — **awaiting `make verify`**

---

## Run this

```bash
cd /mnt/e/Projects/DistriCore && make verify
```

Expected: 8/8 stages, 303 tests, coverage above 80%.

## If green

1. Commit with the message below, push, tag `m3-commercial-operations`.
2. Ask for `docs/M3_Verification_Report.md`.
3. Then M5 — Fulfilment & Billing (no M4; ADR-0007).

```
feat(orders): add commercial operations — pricing, business profile, sales orders

Implements M3 of the roadmap as amended by ADR-0007 (original M3 and M4 merged).

An order is commercial intent: it changes no physical fact and no financial fact.
No path creates a StockMovement (M3-6) or a ledger entry — proven by a dedicated
boundary suite, not by convention.

Design decisions per docs/M3_Design_Review.md:
  D-1 credit exposure = settled balance + open uninvoiced orders; the formula does
      not change at M6, only the first term's source
  D-2 resolve_price accepts customer and ignores it in Edition 1
  D-3 order_number is not a gapless series; invoices are
  D-4 every state-changing operation on an order is audited
  D-5 otp_expiry_minutes reads business_profile, settings as fallback
  R-3 immutable records are their own audit; mutable records need one
  M3-1..M3-10 irreversible, including line snapshots and line-level rounding

Closes TD-17 (append-only escape hatch runbook).

Refs: FR-ORD-001..037, FR-PRC-001..021, 04 T-05 T-14 T-15
```

## If red

Send me the stage number and raw error.

---

## Delivered

| # | Task | State |
| --- | --- | :-: |
| 1 | `business_profile` singleton + owner settings screen (M3-10, D-5) | done |
| 2 | `pricing` module — `resolve_price`, bounded discount, line arithmetic (D-2, M3-8) | done |
| 3 | `sales_order` + `sales_order_line` with snapshots and `client_uuid` (M3-1, M3-2, M3-5) | done |
| 4 | Order capture — line-level rounding, totals in one transaction (M3-7, M3-8) | done |
| 5 | Credit validation — exposure, WARN/BLOCK, override, audit (D-1, DV-9) | done |
| 6 | Lifecycle — 5 states enforced in CORE, cancel with reason (M3-3, M3-4) | done |
| 7 | **Boundary suite — 8 tests proving no order path touches the ledger** (M3-6) | done |
| 8 | API — orders, confirm, cancel, credit status | done |
| 9 | Admin — order list, capture, detail, confirm/cancel. **TD-17 closed** | done |

## To record in the M3 report

- **M6 layering tension:** `credit_exposure` lives in `orders.selectors` because it needs
  open orders. At M6 the settled term becomes the ledger, which `03` §2.1 places in
  `receivables` — a module *above* orders. Resolve before M6; do not paper over it.
- `settled_balance` returns `opening_balance_amount` until M6, so exposure understates
  reality for an already-billed customer. Inherent to milestone order, recorded not hidden.
