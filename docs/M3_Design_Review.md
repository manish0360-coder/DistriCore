# M3 — Commercial Operations: Design Review

| Field | Value |
| --- | --- |
| Document ID | `M3_Design_Review` |
| Version | 1.0.0 |
| Status | **Awaiting sign-off — implementation must not begin** |
| Date | 2026-08-05 |
| Milestone | M3 — Commercial Operations |
| Scope | `business_profile` · pricing · sales orders · order lifecycle · credit validation · order totals |
| Depends on | `00` v1.0.0 · `04` v0.1.0 · `02A` v0.2.0 · ADR-0007 |

> Durable record of the M3 design decisions. Decisions must not live in chat history
> (`00` §10, ADR-0005 §10). `NEXT_TASK.md` holds the task queue and points here.
>
> **No code may be written until §7 is signed.**

---

## 1. The governing principle

M2's principle was *stock is derived, never stored*. M3 needs its own, and it is the
boundary ADR-0007 was written to protect:

> **An order is a record of what was agreed, at the moment it was agreed.
> It changes no physical fact and no financial fact.**

Three consequences follow, and every decision in this document is one of them:

| Consequence | Because |
| --- | --- |
| **Lines snapshot what was agreed** — price, product name, tax rate, pack size | An order that renders from current master data is not a record of an agreement; it is a query that silently rewrites history when a price changes |
| **No stock moves** | Stock is physical fact. An order is intent. Stock is issued at dispatch (M5) |
| **No ledger entry** | Money is owed when a customer is *billed*, not when they *ask*. The receivable begins at the invoice (M5) |

An order is therefore the only **mutable** record M3 creates. That single difference from
`stock_movement` and `audit_log` drives the audit rule in §3.4.

### 1.1 Boundary with M2 — stated explicitly

M2 built a ledger whose entire value is that it records physical fact. If an order wrote a
stock movement, the ledger would begin carrying commercial intention, and "what is on the
shelf" would no longer be answerable from it.

**No code path in M3 creates a `StockMovement`.** This is verified by test, not by
convention (§6).

Cancellation makes the argument concrete: an order that had moved stock would need
compensating movements on cancellation, so the ledger would accumulate paired entries for
events that never physically happened. Under the boundary, cancelling an order writes
nothing to inventory at all — because nothing physical ever occurred.

---

## 2. Worked scenario

Seeded: `business_profile` with `max_manual_discount_percent = 10.00`,
`credit_limit_mode = 'WARN'`.
Customer `C-0142`, credit limit ₹10,000.00, opening balance ₹0.00.
Product `P-1001`, `selling_price` ₹65.00, `tax_rate_percent` 18.00, `pack_size` 12.

### Step 1 — Retailer places an order for 2 packs

| Table | Row |
| --- | --- |
| `sales_order` | `id=7001, order_number='SO-00007001', customer=142, status='PLACED', source='PORTAL', subtotal=1560.00, discount=0.00, tax=280.80, total=1840.80` |
| `sales_order_line` | `id=9101, line_number=1, product=41, product_name='Nirma Detergent 1kg' (snapshot), quantity=24.000, pack_quantity=2.000, pack_size_snapshot=12, unit_price=65.00 (snapshot), discount=0.00, tax_rate_percent=18.00 (snapshot), taxable=1560.00, tax=280.80, line_total=1840.80` |
| `audit_log` | `action=CREATE, entity_type='sales_order', entity_id=7001` |
| `stock_movement` | **none** |

On hand: **unchanged**. Credit exposure: ₹0.00 → ₹1,840.80 against a ₹10,000.00 limit — fine.

Arithmetic, at line level (OI-7, half-up, two places): `24 × 65.00 = 1560.00` ·
`18% = 280.80` · `total = 1840.80`.

### Step 2 — Owner applies a 5% discount (₹78.00) to the line

Within the 10% bound, so accepted.

| Table | Row |
| --- | --- |
| `sales_order_line` | `discount=78.00, taxable=1482.00, tax=266.76, line_total=1748.76` |
| `sales_order` | totals recomputed: `subtotal=1560.00, discount=78.00, tax=266.76, total=1748.76` |
| `audit_log` | `action=UPDATE` with before/after totals, **plus** `action=DISCOUNT_APPLIED` naming the actor and amount |
| `stock_movement` | **none** |

A 15% discount would be refused: `ValidationFailed`, bound stated in the message.

### Step 3 — Owner confirms the order

| Table | Row |
| --- | --- |
| `sales_order` | `status='CONFIRMED'` |
| `audit_log` | `action=CONFIRM`, from-state and to-state recorded |
| `stock_movement` | **none — and this is the point.** Confirmation is agreement, not dispatch |

### Step 4 — A second order takes the customer past their limit

A further order of ₹9,000.00 brings exposure to ₹10,748.76 against ₹10,000.00.

Because `credit_limit_mode = 'WARN'` (DV-9), the order is **created** and the response
carries a credit warning. The owner may override; the override is recorded on the order and
audited. Under `'BLOCK'` the same condition returns `409 CREDIT_LIMIT_EXCEEDED` and no order
is created.

### Step 5 — Cancel the first order

| Table | Row |
| --- | --- |
| `sales_order` | `status='CANCELLED', cancelled_reason='Retailer changed mind', cancelled_at, cancelled_by` |
| `audit_log` | `action=CANCEL` with the reason |
| `stock_movement` | **none — nothing physical ever happened** |

Credit exposure drops back to ₹9,000.00 automatically, because exposure is derived from open
orders rather than stored.

### 2.1 What the scenario proves

Five steps, **zero stock movements, zero ledger entries**. Every figure the owner sees is
either snapshotted at agreement or derived at read time. Nothing was overwritten except the
order itself, and every change to it is audited.

---

## 3. Decisions requiring confirmation

### D-1 — Credit exposure formula, and what it means before M6 exists

FR-ORD-020 compares *order value plus current outstanding balance* against the limit.
Outstanding balance is `SUM(customer_ledger_entry)` — and the ledger arrives in **M6**.

**Adopted formula, correct at both stages:**

```
credit_exposure(customer) = outstanding_ledger_balance
                          + value of orders that are open and not yet invoiced
```

| Term | M3 | M6 onwards |
| --- | --- | --- |
| `outstanding_ledger_balance` | `customer.opening_balance_amount` — the ledger has no rows | `SUM(customer_ledger_entry.amount)` |
| open uninvoiced orders | `SUM(sales_order.total_amount)` where status in (PLACED, CONFIRMED) | unchanged |

**Why this shape rather than a simpler one.** Splitting exposure into a settled term and an
in-flight term means the formula does not change at M6 — only the first term's source does,
behind one selector. It also avoids double counting by construction: once an order is
invoiced it leaves the second term and enters the first.

**Honest limitation.** Until M6, the settled term is an opening balance rather than a live
receivable, so exposure understates reality for any customer who has been billed. That is
inherent to the milestone order, not to this design, and it is recorded as a known
limitation rather than hidden.

**R-1 applies:** the selector anchors on `Customer` and coalesces to a typed zero, so a
customer with no orders returns `0.00` rather than vanishing.

### D-2 — Price resolution signature

Edition 1 resolution is `product.selling_price` — one field. The value of a service is not
the computation; it is that **every surface calls the same function** (BR-001, PO-6).

| Option | Argument |
| --- | --- |
| `resolve_price(*, product)` | Minimal. E-11: no parameter before a caller needs it. Keyword-only, so adding `customer` later breaks nothing |
| **`resolve_price(*, product, customer)`** | Customer is the dimension Edition 2 certainly adds (`02A` §7.5), and a resolver that cannot see the customer invites callers to apply customer logic themselves — which is the BR-001 failure |

**Recommended: the second.** The parameter costs nothing and removes the temptation. The
function ignores `customer` in Edition 1 and says so in its docstring.

### D-3 — `order_number` is **not** a gapless series

`04` T-14 describes it as "a human reference. Not a statutory series." Invoice numbers are
gapless and allocated under a row lock (T-06) because tax authorities require it. Order
numbers carry no such obligation.

**Adopted:** `order_number` comes from a database sequence and **may contain gaps**. It is
unique, never reused, and cheap. Introducing the invoice numbering machinery here would buy
a property nobody requires and add lock contention to the most frequent write in the system.

**Recorded because the distinction will be questioned later**, when M5 introduces the
genuinely gapless invoice series two tables away.

### D-4 — Audit scope for orders — the mirror of M2's D-3

M2 decided that routine stock movements are *not* audited, because a `stock_movement` is
immutable, attributed and timestamped: an audit row would duplicate it.

**An order is mutable.** It can be edited before dispatch, discounted, confirmed, overridden
and cancelled. The row shows only its current state. **The audit log is therefore the only
record of what an order used to say.**

**Adopted:** every state-changing operation on an order is audited — `CREATE`, `UPDATE`
(with before/after totals), `CONFIRM`, `CANCEL`, `CREDIT_OVERRIDE`, `DISCOUNT_APPLIED`.

Volume at DR-8: roughly 2,000 orders a day, ~1M audit rows a year — comparable to
`stock_movement`. Justified, because unlike a movement there is no other record.

This generalises into **R-3** (§4).

### D-5 — `otp_expiry_minutes`: settings versus `business_profile`

`04` T-05 places it on `business_profile`; M0 reads it from an environment variable.

| Option | Argument |
| --- | --- |
| **A — wire it through** | Matches the frozen design. Owner-editable, tier-3 (FD-12). Small change to `identity.services` |
| B — leave it in settings and drop the column | It is operational rather than commercial; the owner has no reason to change it |

**Recommended: A**, with the environment variable as a fallback when no profile row exists.
It is a ten-line change and it removes a documented-but-untrue statement from `04`.

---

## 4. Rule adopted from this design

### R-3 — Immutable records are their own audit; mutable records need one

| Record | Mutable? | Audit |
| --- | :-: | --- |
| `stock_movement` | No | **None for routine movements** (M2 D-3) |
| `audit_log` | No | n/a |
| `invoice`, `credit_note` | No (N-04) | Issue only |
| **`sales_order`** | **Yes, before dispatch** | **Every state-changing operation** |
| `customer`, `product` | Yes | Discretionary and financial fields only (M1) |

The test: *if this row changes, is there any other record of what it used to say?* If no,
audit it. This resolves M2's D-3 and M3's D-4 with one rule instead of two judgements, and
it decides the question in advance for M5 and M6.

---

## 5. Irreversible decisions — sign-off required

| # | Decision | Cost to reverse | Signed |
| --- | --- | :-: | :-: |
| **M3-1** | **Order lines snapshot** product name, unit price, tax rate and pack size at capture | **Severe** — the values are simply gone; no migration recovers them | ☐ |
| **M3-2** | **Line quantity always in base units.** `pack_quantity` and `pack_size_snapshot` record what the user typed | **Severe** — mixed units make every historical aggregate wrong, unrecoverably (M2-6) | ☐ |
| **M3-3** | **Invoiced-ness is not a status** — it is the existence of an invoice row | High — a status duplicating a derivable fact will eventually disagree with it | ☐ |
| **M3-4** | **Five states, transitions enforced in `CORE`**, never settable by `PATCH` | High — the state machine leaks into every client | ☐ |
| **M3-5** | `client_uuid UNIQUE` on `sales_order` from the first migration | Medium–High — a window with no duplicate protection on financial rows (BR-012) | ☐ |
| **M3-6** | **Orders write no stock movements.** Stock is issued at dispatch (M5) | High — the ledger would carry commercial intent, and cancellations would need compensating movements for events that never physically happened | ☐ |
| **M3-7** | Order totals denormalised, written in the same transaction as the lines | Medium — D-08's one performance denormalisation; reconciled by an integrity test | ☐ |
| **M3-8** | **Tax and rounding computed at line level**, then summed (OI-7, half-up, 2dp) | High — summing then rounding gives different totals; historical documents would disagree with recomputation | ☐ |
| **M3-9** | Money `NUMERIC(14,2)` via `to_money`; percentages via `to_percent` | High — carried from M1/M2 (I-07) | ☐ |
| **M3-10** | `business_profile` is a **singleton enforced by `CHECK (id = 1)`** | Medium — a second row makes "which profile?" a question every reader must answer | ☐ |

### 5.1 M3-8 deserves its own note

`05` OI-7 specifies half-up at two decimal places **at line level**. Two orders of the same
goods can total differently depending on whether tax is rounded per line and then summed, or
summed and then rounded. Both are defensible; only one can be implemented, and the invoice
in M5 must agree with the order in M3 to the paisa. Fixing it now, in one place
(`core.fields.to_money` already exists), is what prevents that.

---

## 6. Verification the milestone must carry

| Test | Asserts |
| --- | --- |
| **No stock movement is created by any order operation** | M3-6, the M2 boundary. Placed, edited, discounted, confirmed and cancelled — `StockMovement.objects.count()` unchanged throughout |
| Worked scenario §2 executed end to end | Design document and code cannot diverge (M2 lesson 1) |
| Snapshot survives a price change | Change `product.selling_price` after capture; the line and order totals are unchanged |
| Order totals equal the sum of their lines | M3-7 reconciliation (NFR-INT-003) |
| Line-level rounding | A multi-line order whose per-line and whole-order rounding differ |
| Discount above the bound is refused | FR-PRC-017, bound read from `business_profile` |
| Credit warning in `WARN`, refusal in `BLOCK` | DV-9, both modes |
| Every invalid state transition is rejected | M3-4, exhaustively — the M4→M5 gate in `00` §19.2 |
| Cancellation after dispatch is refused | FR-ORD-033 (unreachable in M3; the guard must exist for M5) |
| Duplicate `client_uuid` returns the original order | BR-012, AD-09 |
| Role × capability matrix, direct to the API | Retailer may order for themselves only; salesman may not create orders in Edition 1 (DV-1) |

---

## 7. Sign-off

Implementation may not begin until all four are complete.

| # | Item | Party | Status |
| --- | --- | --- | :-: |
| 1 | **D-1 … D-5** (§3) | Product Architect | ☐ |
| 2 | **M3-1 … M3-10 irreversible decisions** (§5) | All | ☐ |
| 3 | **R-3** adopted as a binding rule (§4) | All | ☐ |
| 4 | This document accepted | All | ☐ |

Outstanding, not blocking design: TD-1 (`uv.lock`), TD-15 (`offer` milestone), TD-17
(trigger escape hatch — due in this milestone).

---

*No code has been written or authorised. Task decomposition follows in `NEXT_TASK.md` once
this document is signed.*
