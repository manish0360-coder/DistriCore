# Next Task

> The only hand-written handoff artifact (ADR-0005 §5.3). Everything else comes from `make brief`.
> Design reasoning lives in `docs/M3_Design_Review.md`.

**Milestone:** M3 — Commercial Operations *(pricing + orders, merged by ADR-0007)*
**Task:** 0 — **BLOCKED on design sign-off. Do not write code.**

---

## Blocked on

| # | Item | Party | Where |
| --- | --- | --- | --- |
| 1 | **D-1 … D-5** — credit exposure formula, price signature, order numbering, audit scope, OTP config | Product Architect | `M3_Design_Review.md` §3 |
| 2 | **M3-1 … M3-10 irreversible decisions** | All | §5 |
| 3 | **R-3** adopted as binding | All | §4 |
| 4 | `M3_Design_Review.md` accepted | All | §7 |

Non-blocking: TD-1 (`uv.lock`) · TD-15 (`offer` milestone) · TD-17 (trigger escape hatch,
**due in this milestone**).

---

## Provisional task decomposition — refine after sign-off

| # | Task | Delivers |
| --- | --- | --- |
| 1 | `business_profile` | Singleton with `CHECK (id=1)`, seeded, owner screen (M3-10) |
| 2 | Pricing | `resolve_price`, bounded manual discount read from the profile (D-2) |
| 3 | `sales_order` + `sales_order_line` | Models, migration, snapshots, `client_uuid` (M3-1, M3-2, M3-5) |
| 4 | Order capture | Line-level tax and rounding, totals in one transaction (M3-7, M3-8) |
| 5 | Credit validation | `credit_exposure` selector, WARN/BLOCK, override, audit (D-1) |
| 6 | Lifecycle | Five states, transitions enforced in `CORE`, cancel with reason (M3-3, M3-4) |
| 7 | **Boundary test suite** | **Prove no order operation creates a `StockMovement`** (M3-6) |
| 8 | API | `05` §9.3 order endpoints |
| 9 | Admin | Order list, capture form, confirm/cancel. **Close TD-17** |

## Do not

- **Do not write a `StockMovement` from any order path.** M3-6 — stock is issued at
  dispatch (M5). This is the M2 boundary
- Do not write a `customer_ledger_entry` — the receivable begins at the invoice (M5)
- Do not implement schemes, slabs, free goods or customer-specific pricing — Edition 2
- Do not implement approval workflows — Edition 2 (DV-9 is warn-and-override only)
- Do not make `order_number` gapless — D-3
- Do not let salesmen create orders — Edition 1 has no field order capture (DV-1)
