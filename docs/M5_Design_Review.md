# M5 — Fulfilment & Billing: Design Review

| Field | Value |
| --- | --- |
| Document ID | `M5_Design_Review` |
| Version | 1.1.0 |
| Status | **Awaiting sign-off — implementation must not begin** |
| Date | 2026-08-05 |
| Milestone | M5 — Fulfilment & Billing |
| Scope | dispatch · delivery · proof of delivery · GST invoicing · credit notes · number series · customer ledger |
| Reviewers | Independent (Gemini) · Chief Systems Engineer |
| Depends on | `00` v1.0.0 · `02` · `04` v0.1.0 · `02A` v0.2.0 · M2 and M3 design reviews |

> **v1.1.0** — three concerns from the independent review evaluated in §15. **All three
> accepted**; one of them exposed a defect in the frozen database design and a second
> exposed a latent defect in shipped M3 code. §3, §4, §5, §6, §9, §10, §11 and §12 amended.

> Durable record of the M5 design decisions (`00` §10, ADR-0005 §10).
>
> **No code may be written until §12 is signed.** Three contradictions in the frozen
> corpus are surfaced in §3 and must be resolved before implementation, not during it.

---

## 1. The governing principle

M2's principle was *stock is derived, never stored*. M3's was *an order changes no physical
fact and no financial fact*. **M5 is the milestone that crosses both boundaries — and the
central insight is that they are not one boundary.**

> **Dispatch makes stock physical. The invoice makes money owed.
> They are two separate irreversible events, with different triggers, different documents
> and different reversal mechanisms. Conflating them is the classic error in distribution
> software, and it is unrecoverable once history exists.**

Why they must stay separate:

| | Dispatch | Invoice |
| --- | --- | --- |
| Turns intent into | **Physical** fact — goods leave | **Financial** fact — money is owed |
| Writes | `stock_movement` (ISSUE) | `invoice` + `customer_ledger_entry` |
| Reversed by | A compensating **RETURN** movement | A **credit note** |
| Can occur without the other | Yes — samples, replacements, write-offs | Yes — bill-then-deliver (Edition 2) |
| Owner | `fulfilment` module | `billing` module |

Neither is ever undone by editing. A failed delivery does not delete the issue; it returns
the goods. A wrong invoice is not corrected; it is credited.

### 1.1 The three irreversibility classes now in play

| Record | Mutability | Reversal | Introduced |
| --- | --- | --- | --- |
| `stock_movement` | Append-only (trigger) | Compensating movement | M2 |
| `sales_order` | **Mutable** before dispatch | State transition + audit | M3 |
| `invoice`, `credit_note` | **Append-only (trigger)** | New document, never an edit | **M5** |
| `customer_ledger_entry` | **Append-only (trigger)** | Compensating entry | **M5** |

R-3 (M3) decides the audit rule for each: immutable records are their own audit; mutable
records need one. M5 adds two immutable records, so **neither invoices nor ledger entries
generate `audit_log` rows for their creation** — the document *is* the record. Cancellation
and credit-note issue are discretionary acts and are audited.

---

## 2. Scope

### In

`delivery` (dispatch, POD, failure) · `invoice` + `invoice_line` · `credit_note` +
`credit_note_line` · `number_series` · `customer_ledger_entry` · invoice PDF · owner
screens · API.

### Out — by frozen decision, not omission

| Excluded | Decision |
| --- | --- |
| Partial delivery | `02A` §7.7 — Edition 2. One delivery per order (`uq_delivery_sales_order`) |
| Payments and collections | **M6.** M5 writes the debit side of the ledger only |
| Van as a stock location | M2-1 seeds one location; multi-location is Edition 2 (EP-A) |
| Structured returns module | DV-8 — a return is a reason-coded movement plus a credit note |
| e-invoicing (IRN/QR/portal) | O13 — **blocked on CF-1, see §12** |
| Mobile delivery app | M8. M5 records delivery from the web admin (FR-FUL-006) |
| Batch/lot selection at dispatch | Edition 2 (EP-F). The default lot is used |

---

## 3. Contradictions in the frozen corpus — resolve before implementation

Three. Each was found by reading the documents against each other, and each would have
been decided by accident during implementation if not surfaced now.

### C-1 — Does **dispatch** or **delivery** write the stock issue?

| Source | Says |
| --- | --- |
| `02` FR-FUL-003 | "**Dispatch** MUST generate stock issue movements" |
| `02` §11.1 lifecycle diagram | "DISPATCHED — stock issued; invoiceable" |
| **`04` T-16 business rules** | "Marking **`DELIVERED`** … writes the `ISSUE` stock movements" |

**Recommendation: dispatch writes the issue.** `04` T-16 is wrong.

From first principles — stock leaves the distributor's control when the goods are loaded,
not when a signature is obtained. If issue waited for delivery confirmation:

* a stock count taken while the van is out would **overstate** on hand;
* the owner could promise stock that is physically on a van;
* an overnight delivery would leave stock "available" for a whole night.

Understating (issued at dispatch, on the van, not yet delivered) is the safer error: it can
only cause an unnecessary purchase, never an unfulfillable promise.

**Consequence, stated plainly:** between dispatch and delivery, goods on the van are simply
*issued*. Edition 1 has one stock location (M2-1), so there is no van-stock concept. A
failed delivery writes a **RETURN** movement bringing them back. This is a real limitation
of the single-location design and is recorded as such, not hidden.

### C-2 — `billing` must write a ledger it is not permitted to reach

| Source | Says |
| --- | --- |
| `02` FR-BIL-013 | "Issuing an invoice MUST create a customer ledger entry" |
| `03` §2.1 | `receivables` **owns** `CustomerLedgerEntry`; may call `billing`, `customers` |
| `03` §2.1 | `billing` may call `orders`, `fulfilment`, `customers` — **not `receivables`** |

`billing` is required to write a table owned by a module **above** it in the layer graph.
As written, M5 cannot be implemented without breaking a contract.

This is **TD-19 arriving one milestone earlier than predicted.** The M3 report expected it
at M6; it bites at M5.

**Recommendation *(revised in v1.1.0 after independent review — see §15.1)*: introduce a
dedicated `ledger` module.** Formalised as **ADR-0008** on sign-off.

A ledger entry is a fact about a customer's balance, fed by invoices (M5), credit notes (M5)
and payments (M6) — three modules. A table with three writers belongs beneath all of them.
That much was clear in v1.0.0, which placed it in `customers`. **It belongs in a module of
its own, and the architecture already made this exact decision once:**

| Master data | Append-only fact table over it | Balance |
| --- | --- | --- |
| `catalogue` → `Product` | **`inventory`** → `StockMovement` | `stock_on_hand`, derived (R-1) |
| `customers` → `Customer` | **`ledger`** → `CustomerLedgerEntry` | `settled_balance`, derived (R-1) |

`StockMovement` is not inside `catalogue`. By the same reasoning `CustomerLedgerEntry` does
not belong inside `customers`. **R-1 already specifies the shape** — an aggregate selector
lives with the fact table and anchors on the dimension — and R-1's own text anticipated this
case: *"a customer with no ledger entries must show a zero balance, not vanish."*

| Option | Verdict |
| --- | --- |
| **Dedicated `ledger` module** | **Adopted.** Symmetric with `inventory`. Keeps a high-volume financial fact table out of a master-data module |
| Ledger in `customers` *(v1.0.0)* | Works, but puts a table growing ~200 rows/day beside ~500 slowly-changing customer rows, and puts `record_ledger_entry` beside `set_credit_limit` in one service module. Two lifecycles, two risk profiles, one module |
| Ledger in `billing` | Payments (M6) writing into billing's table is a poor ownership story |
| Ledger in `receivables`, billing calls upward | Breaks the layer graph. Rejected |
| Defer the ledger to M6 | Rejected — FR-BIL-013 requires the entry in the same transaction as the invoice. Backfilling financial records is what this architecture exists to avoid |

`03` §2.1's `receivables` row therefore **splits**: `ledger` holds the facts, and M6's
`receivables` becomes the payments-and-collections layer above it.

**Resulting layer graph** (`inventory` and `ledger` are siblings — neither imports the other):

```
api | webadmin  >  receivables (M6)  >  billing (M5)  >  fulfilment (M5)
                >  orders  >  pricing  >  inventory | ledger
                >  catalogue | customers  >  identity  >  core
```

**This resolves TD-19.** `credit_exposure` stays in `orders.selectors` (it needs open
orders) and its settled term becomes `ledger.selectors.settled_balance()`. No import
inversion.

### C-3 — The buyer's state code has no source

`04` T-17 requires `buyer_state_code` on the invoice and uses it to choose CGST+SGST versus
IGST. **`customer` (T-09) has no `state_code` field.** `business_profile.state_code` is the
*seller's*.

**Recommendation: derive from GSTIN, and add an explicit override column.**

An Indian GSTIN encodes the state in its first two characters, so for a registered buyer the
state is already known. But unregistered retailers have no GSTIN, and **a wrong tax split is
a legal defect, not a cosmetic one** — so guessing silently is not acceptable.

Adopted rule, in order:

1. `customer.state_code` if explicitly set;
2. otherwise the first two characters of `customer.gstin` if present;
3. otherwise the seller's state code — **intra-state assumed, and recorded on the invoice as
   an assumption**.

`customer.state_code` is a nullable `VARCHAR(2)` on a master table: adding it later is an
`ALTER TABLE` with a default and rewrites no history, so by §9.1's own test it is cheap
either way. It is added here because the consequence of getting it wrong is legal.

---

## 4. Worked business scenarios

Continuing the M2/M3 scenario. Seller state `10` (Bihar), GSTIN present.
Customer `C-0142`, no GSTIN, state derived as `10` → intra-state.
Order `SO-00007001`, confirmed, one line: 24 × `P-1001` @ ₹65.00, 18% GST, total ₹1,840.80.
Stock on hand before dispatch: **1,200.000**.

### Scenario A — the happy path

| Step | Rows written | Stock | Ledger |
| --- | --- | --: | --: |
| **A1 Assign** to salesman | `delivery` (`PENDING`), `sales_order.assigned_user` | 1200.000 | 0.00 |
| **A2 Dispatch** | `stock_movement −24.000` (ISSUE, `source_document = Delivery`, **no reason code**), `sales_order.status = DISPATCHED` | **1176.000** | 0.00 |
| **A3 Issue invoice** | `invoice` (`INV/26-27/00001`), `invoice_line` ×1, `customer_ledger_entry +1840.80` | 1176.000 | **1840.80** |
| **A4 Deliver** | `delivery.status = DELIVERED`, POD photo, GPS, `sales_order.status = DELIVERED` | 1176.000 | 1840.80 |

**A2 is the first movement in the system's history to carry a source document rather than a
reason code.** It closes TD-16: `SOURCE_DOCUMENT_REGISTRY` gains its first real entry, and
the R-2 accept path finally has a production caller instead of a monkeypatched test.

**A3 is the first ledger entry ever written.** Note it is created by *invoicing*, not by
delivery: the customer owes money because they were billed.

### Scenario B — delivery fails, goods come back

| Step | Rows written | Stock |
| --- | --- | --: |
| B1–B3 as A1–A3 | | 1176.000 |
| **B4 Delivery fails** — shop shut | `delivery.status = FAILED`, `failure_reason`, `stock_movement +24.000` (**RETURN**, `source_document = Delivery`) | **1200.000** |

**The ISSUE is not deleted and not edited.** Two rows now record what physically happened:
the goods left, and the goods came back. Net zero, fully explained.

The invoice from B3 still stands. Correcting it is a **separate commercial decision** —
scenario C — because the goods may simply be redelivered tomorrow.

### Scenario C — the invoice was wrong

The customer was billed 24 units but only 12 were accepted. Twelve come back to the warehouse.

| Step | Rows written | Stock | Ledger |
| --- | --- | --: | --: |
| C1 Warehouse receives the 12 back | `stock_movement +12.000` (RETURN, reason `SALES_RETURN`) — a **physical** event | 1188.000 | 1840.80 |
| C2 Owner issues a credit note | `credit_note` (`CN/26-27/00001`) → `INV/26-27/00001`, `credit_note_line ×1`, `customer_ledger_entry −920.40` — a **financial** event. **Writes no stock movement** | 1188.000 | **920.40** |

The invoice is untouched. Two events, two documents, each recording one fact.

> **C1 and C2 are deliberately separate, and v1.0.0 had them coupled.** See D-7 (§5) and
> §15.2 — coupling them permits the same physical goods to be restocked twice.

### Scenario F — the double-restock trap *(added v1.1.0)*

The combination that breaks a coupled design. Delivery fails **and** the customer is credited.

| Step | Rows written | Stock |
| --- | --- | --: |
| F1 Dispatch | `stock_movement −24.000` (ISSUE) | 1176.000 |
| F2 Invoice issued at dispatch | ledger `+1840.80` | 1176.000 |
| F3 Delivery **FAILED** — shop shut | `stock_movement +24.000` (RETURN, source `Delivery`) | **1200.000** |
| F4 Owner credits the full invoice so the customer is not billed for goods never received | ledger `−1840.80` — **and nothing else** | **1200.000** ✅ |

Under `04` T-19 as frozen, step F4 would set `restocked = true` and write a *second*
`+24.000`, giving **1224.000 — twenty-four units that do not exist.** Under D-7 the credit
note writes no stock and the ledger is the only thing that moves. Correct by construction.

### Scenario D — same-day mistake

An invoice is raised against the wrong customer and caught before the van leaves.

See D-4 (§5). Whether this is a cancellation or a credit note is the one genuinely open
commercial question in this milestone.

### Scenario E — dispatch when stock is short

On hand 10, order for 24. Per D-2 and ADR-0006 the dispatch **proceeds** and on hand becomes
−14. The stock report surfaces it; the owner reconciles. Blocking would teach the warehouse
to stop recording — the failure the ledger exists to prevent.

---

## 5. Decisions requiring confirmation

### D-1 — Dispatch writes the issue *(resolves C-1)*
See §3. `04` T-16's rule statement is superseded.

### D-2 — `CustomerLedgerEntry` moves to `customers` *(resolves C-2, and TD-19)*
See §3. Formalised as ADR-0008 on sign-off.

### D-3 — Buyer state derived from GSTIN with an explicit override *(resolves C-3)*
See §3. Adds `customer.state_code`, nullable.

### D-4 — Invoice cancellation: does it exist in Edition 1? **OPEN**

`04` T-17 specifies `status ∈ {ISSUED, CANCELLED}` and `cancelled_reason`. But credit notes
already reverse value, so cancellation is a **second mechanism for a similar outcome**, and
two mechanisms invite the question "which do I use?".

| Option | Argument |
| --- | --- |
| **A — credit notes only** | One mechanism, no ambiguity. Every correction leaves a document the customer can be shown. Deviates from `04` T-17, which specifies the status |
| **B — cancellation, tightly guarded** | Matches the frozen schema and a real case: wrong customer, caught in seconds. Guarded to *no credit note issued, no payment applied, same financial year* |

**Recommendation: B, with the guards stated as constraints.** The frozen schema has the
field, the business case is genuine, and a credit note for a 30-second-old typo produces a
document the retailer never should have seen. **Cancellation still writes a compensating
ledger entry** — the ledger is append-only either way.

**Product Architect to decide.** Implementation differs by roughly one service function.

### D-5 — When is the invoice PDF generated?

| Option | Argument |
| --- | --- |
| Eager at issue | The rendered document is preserved exactly. Costs ~3.6 GB/year of storage — and `04` §18 identifies media as the binding constraint on the 80 GB volume |
| Lazy every time | No storage. **But if the template changes, an old invoice re-renders differently from the paper the customer holds** |
| **Generate on first request, then cache forever** | **Recommended.** Any PDF that was ever delivered is preserved byte-for-byte; invoices nobody downloads cost nothing |

The legal document is the *data* (all snapshotted, FR-BIL-008); the PDF is a rendering. But
a rendering that was handed to a retailer must never change. Cache-on-first-render gets both.

### D-6 — Audit scope for M5, under R-3

R-3: immutable records are their own audit. Invoices, credit notes and ledger entries are
immutable and carry actor, timestamp and full content.

**Recommendation:** no `audit_log` row for invoice issue, credit note issue or ledger entry
creation. **Audited:** invoice cancellation (if D-4 = B), delivery failure, and any
discretionary act. Consistent with M2's D-3 and M3's D-4 rather than a third judgement.

### D-7 — A credit note writes **no stock movement** *(new in v1.1.0 — see §15.2)*

**`04` T-19's `restocked` boolean is removed.** It is a defect in the frozen schema, not a
feature: it permits the same physical goods to be restocked twice (Scenario F).

The root cause is that the flag **asks a question whose honest answer produces a wrong
result.** After a failed delivery the goods genuinely are back on the shelf, so an owner
answering "were these restocked?" correctly says *yes* — and inflates stock. The flag reads
as a question about physical reality; it is really a question about *which document should
write the movement*, and only the system can answer that.

This is v1.0.0 contradicting its own §1: **financial reversal and physical return are as
separate as the invoice and the dispatch are.** Coupling them re-creates precisely the
conflation §1 exists to forbid.

* Physical return → a `stock_movement` (RETURN), whatever caused the goods to come back.
* Financial reversal → a `credit_note` and its ledger entry.

`credit_note.reason_code_id` **remains** — it categorises *why* credit was given
(`DAMAGE`, `SHORT_SUPPLY`, `RATE_DIFFERENCE`) and drives no behaviour. Requires
**ADR-0009** (deviates from `04` T-19 and DV-8's stated mechanism).

The owner screen may still offer "also record the stock return" as a **second, disclosed
action** producing a second row — a convenience over two honest facts, not one document
pretending to be two.

### D-8 — Credit exposure is re-validated at **dispatch** *(new in v1.1.0 — see §15.3)*

Exposure at confirmation is a *prediction*; exposure at dispatch is a *fact*. Before
dispatch a customer default costs nothing; after it, the goods are gone. Nothing forces
prompt dispatch, so the confirmation check has an **unbounded staleness window**, and
`set_credit_limit` (M1) can lower the limit inside it.

`fulfilment.services.dispatch_order()` calls **the existing**
`orders.services.evaluate_credit(order=order)` before writing any movement, in the same
transaction. `03` §2.1 already permits `fulfilment → orders`; no contract changes.

**One function, two call sites** — the PO-6 discipline. A second implementation could
diverge from the first, and a credit rule that differs by caller is worse than no rule.

`credit_limit_mode` is honoured: `WARN` warns, `BLOCK` blocks. **In `BLOCK` mode the owner
may override with a mandatory reason, audited.** Refusing outright at the loading bay
teaches staff to dispatch without recording it — the ADR-0006 failure — and unrecorded
dispatches are worse than recorded over-limit ones.

### D-9 — The two exposure terms partition on the **ledger**, not on status *(new in v1.1.0)*

Found while validating D-8. `orders.selectors.OPEN_STATUSES` is `(PLACED, CONFIRMED)`.
M5 makes `DISPATCHED` reachable for the first time, and **a dispatched-but-uninvoiced order
falls out of both exposure terms** — out of the open term (not an open status) and not yet
in the settled term (no ledger entry). It is invisible. That is the *most* exposed state
that exists: goods gone, nothing billed. F-1 makes the window unbounded.

The status list is a proxy that was correct only while invoicing did not exist. The correct
predicate is the one `open_order_value`'s own docstring already states — **"agreed but not
yet billed"**:

> `credit_exposure = ledger balance + value of live orders with no ledger entry`

The two terms are then mutually exclusive **by construction**, and an order moves from one
to the other atomically when the invoice is issued. M3's D-1 promised the formula would not
change when the settled term became the ledger; the status proxy would have broken that
promise silently.

**Implementation:** `customer_ledger_entry` carries a nullable `sales_order_id`. `orders`
may import `ledger` (below it); it may not import `billing` (above it), so joining through
the invoice is not available. Live statuses become `PLACED, CONFIRMED, DISPATCHED,
DELIVERED`, filtered by the absence of a ledger entry.

---

## 6. Database implications

Six new tables, one altered.

| Table | Key points |
| --- | --- |
| `delivery` | One per order (`uq_delivery_sales_order`), `client_uuid` unique, POD photo, GPS, `PENDING/DELIVERED/FAILED`, `failure_reason` required when FAILED |
| `invoice` | Gapless number, series FK, **seller and buyer snapshots**, CGST/SGST/IGST with the XOR `CHECK`, `round_off_amount`, PDF media FK, append-only trigger |
| `invoice_line` | Full snapshots incl. HSN; `product_id` nullable but `product_code` not — *if the two disagree, the snapshot is right*; `ON DELETE RESTRICT`, never CASCADE |
| `credit_note` / `credit_note_line` | Mirror the invoice; `invoice_id` **not null**; `reason` mandatory; own number series. **`restocked` dropped (D-7)**; `reason_code_id` retained as a category |
| `number_series` | `(series_key, financial_year)` unique; allocation under `SELECT … FOR UPDATE` inside the document transaction |
| `customer_ledger_entry` | **Owned by the new `ledger` module** (D-2). Signed amount, `CHECK` on sign-per-type, polymorphic source under R-2, append-only trigger, **nullable `sales_order_id` (D-9)** |
| `customer` *(altered)* | `+ state_code VARCHAR(2) NULL` (D-3) |

`media_file.Purpose.INVOICE_PDF` already exists (M1). `SOURCE_DOCUMENT_REGISTRY` gains
`fulfilment.Delivery`.

---

## 7. API implications

Ten endpoints, all specified in `05` §9.4–9.6.

| Method | Path | Notes |
| --- | --- | --- |
| GET/POST | `/deliveries`, `/deliveries/{id}/complete`, `/deliveries/{id}/fail` | Idempotent on `client_uuid` — the M8 app will use these unchanged |
| POST | `/orders/{id}/assign`, `/orders/{id}/dispatch` | Actions, not status PATCHes (AD-08) |
| POST/GET | `/invoices`, `/invoices/{id}`, `/invoices/{id}/pdf` | Issue request carries almost nothing; everything is derived and snapshotted server-side |
| POST | `/credit-notes` | |
| GET | `/customers/{id}/ledger`, `/customers/{id}/balance` | Balance derived, R-1 shaped |

**`POST /invoices` takes `{client_uuid, sales_order_id, invoice_date}` and nothing else.** A
client that could supply amounts could supply wrong ones.

---

## 8. Interaction with M2 and M3

| Existing guarantee | What M5 does |
| --- | --- |
| **M2** — stock derived from an append-only ledger | Adds the first *document-driven* movements. The table does not change shape: one column moves from the reason side to the document side (E-06 demonstrated) |
| **M2 D-2** — no locks, negatives permitted | Unchanged. Dispatch takes no lock and may drive stock negative (scenario E) |
| **M2 R-2** — validated source instances | **First production use.** `Delivery` registers, closing TD-16 |
| **M3 M3-6** — orders write no stock or ledger | **Still true.** The boundary suite must keep passing untouched. M5 adds *new* services that cross the boundary; it does not relax the order services |
| **M3 M3-3** — invoiced-ness is not a status | Confirmed: `sales_order` gains no invoice status. The invoice's existence is the fact |
| **M3 D-1** — credit exposure | Its settled term switches from `opening_balance_amount` to the ledger, as designed. **But the open term's status filter must change (D-9)** — M3's `OPEN_STATUSES` silently drops dispatched-uninvoiced orders once M5 makes `DISPATCHED` reachable |
| **M3 `evaluate_credit`** | Gains a second call site at dispatch (D-8). **The function itself is unchanged** |
| **M3 M3-1/M3-8** — line snapshots, line-level rounding | Invoice lines copy from order lines. **The invoice must equal the order to the paisa**, which is why M3-8 fixed rounding once |

> **The M3 boundary suite is a regression gate for M5.** If any of its eight tests needs
> changing, the boundary has been eroded — that is the signal, not the inconvenience.

---

## 9. Business rules

| # | Rule | Source |
| --- | --- | --- |
| B-1 | An order below `CONFIRMED` cannot be dispatched | `02` §11.1 |
| B-2 | An invoice cannot be issued for an order below `DISPATCHED` | FR-BIL-002 |
| B-3 | One invoice per order in Edition 1 | `04` T-17 |
| B-4 | Invoice numbers gapless within `(series, financial year)`; never reused by an issued document | FR-BIL-005/006 |
| B-5 | Every invoice value is rendered from the invoice's own snapshot, never from current master data | FR-BIL-008 |
| B-6 | CGST+SGST and IGST are mutually exclusive | `04` T-17 `CHECK` |
| B-7 | Total credited against an invoice never exceeds its value | FR-BIL-016 |
| B-8 | A credit note cannot reference a cancelled invoice | `04` T-19 |
| B-9 | Issuing an invoice creates its ledger entry **in the same transaction** | FR-BIL-013 |
| B-10 | A failed delivery returns stock; it never deletes the issue | D-1 |
| B-11 | Invoices, credit notes and ledger entries are append-only at the database | N-04 |
| B-12 | Delivery is one-per-order and idempotent on `client_uuid` | `04` T-16, BR-012 |
| B-13 | **A credit note never writes a stock movement.** Physical returns are recorded separately | D-7 |
| B-14 | **Credit exposure is re-evaluated at dispatch**, using the same function as at confirmation | D-8 |
| B-15 | **An order contributes to exactly one exposure term** — open until it has a ledger entry, settled after | D-9 |

---

## 10. Failure modes and adversarial cases

### Failure modes

| # | Failure | Required behaviour |
| --- | --- | --- |
| F-1 | Dispatch succeeds, invoicing fails | Order stays `DISPATCHED`, stock issued, **no invoice**. Retrying invoicing is safe and idempotent on `client_uuid` |
| F-2 | Number allocated, insert fails | Both roll back. No dangling number, no dangling document |
| F-3 | Two threads invoice the same order | Exactly one succeeds — `uq_invoice_sales_order` |
| F-4 | Two threads issue any invoices concurrently | Distinct gapless numbers — row lock on `number_series` |
| F-5 | Delivery completed twice | Idempotent: `client_uuid` returns the original; the state machine refuses the second transition |
| F-6 | Failed delivery recorded twice | **Must not inflate stock.** Idempotent on `client_uuid`; the return movement is written once |
| F-7 | PDF generation fails | The invoice exists regardless. PDF is outside the issue transaction (D-5) |
| F-8 | Credit notes exceed the invoice under concurrency | Row lock on the invoice while summing existing credits (B-7) |
| F-9 | Stock goes negative on dispatch | Permitted and reported (ADR-0006) |
| F-10 | Order cancelled after dispatch | Refused — already guarded by M3's state machine |
| **F-11** | **Delivery fails, then the invoice is fully credited** | Stock rises **once**, not twice. The credit note moves money only (D-7, Scenario F) |
| **F-12** | **Dispatch succeeds, invoicing fails, another order is then confirmed** | The dispatched order **still counts** toward exposure. It is the most exposed state there is and must not become invisible (D-9) |
| **F-13** | **Credit limit lowered between confirmation and dispatch** | Detected at dispatch. Warns or blocks per `credit_limit_mode`; owner override is audited (D-8) |

### Adversarial cases the suite must carry

| # | Attack | Asserts |
| --- | --- | --- |
| A-1 | Raw SQL `UPDATE`/`DELETE` on `invoice`, `credit_note`, `customer_ledger_entry` | Trigger refuses. Same treatment as `audit_log` and `stock_movement` |
| A-2 | Change a product's price, then render an old invoice | Unchanged — B-5 |
| A-3 | N threads issuing invoices concurrently | Gapless, no duplicates, no gaps in the series |
| A-4 | Credit note for more than the invoice, concurrently | Refused; total credited never exceeds the invoice |
| A-5 | Dispatch the same order twice | One set of stock movements |
| A-6 | Delete a delivery to "undo" it | Refused; the correct path is a failure record |
| A-7 | Retailer or salesman issuing an invoice | 403 at service and over HTTP |
| A-8 | Retailer reading another customer's invoice or ledger | **404, never 403** (05 §4.1) |
| A-9 | **The M3 boundary suite, unmodified** | Order services still write no stock and no ledger |
| A-10 | Ledger balance vs sum of entries after a randomised sequence | Reconciles exactly (NFR-INT-003) |
| **A-11** | **Scenario F executed end to end** | Exactly **one** RETURN exists for the order. No credit-note path can write a stock movement |
| **A-12** | Randomised sequence of dispatch, invoice, credit and payment | **Total stock returned never exceeds total dispatched**, per product — the physical analogue of B-7 |
| **A-13** | Exposure sampled after every state change in a full order lifecycle | Never double-counts and **never dips** while the order is dispatched-uninvoiced (D-9) |
| **A-14** | Limit lowered below current exposure, then dispatch attempted | Blocked or warned per mode; an override without a reason is refused |

---

## 11. Irreversible decisions — sign-off required

| # | Decision | Cost to reverse | Signed |
| --- | --- | :-: | :-: |
| **M5-1** | **Dispatch writes the stock issue**, not delivery (C-1) | High — movements would carry the wrong timestamp and the wrong document forever | ☐ |
| **M5-2** | Invoice and line **snapshot** seller, buyer and every line value | **Severe** — the values are gone; no migration recovers them | ☐ |
| **M5-3** | Invoices, credit notes and ledger entries are **append-only, trigger-enforced** | **Severe** — no historical financial claim is provable if they were ever editable | ☐ |
| **M5-4** | Gapless numbering per `(series, financial year)` under a row lock | High — issued statutory documents cannot be renumbered | ☐ |
| **M5-5** | The ledger entry is written **in the same transaction** as its document | **Severe** — an invoice without its entry is a corruption, not a delay | ☐ |
| **M5-6** | `CustomerLedgerEntry` owned by a **dedicated `ledger` module** (C-2, ADR-0008) | High — a `SeparateDatabaseAndState` move of a financial table once M6 depends on it. **Free today; no rows exist** | ☐ |
| **M5-7** | CGST+SGST **XOR** IGST, `CHECK`-enforced; buyer state per D-3 | High — legally defective invoices cannot be quietly corrected | ☐ |
| **M5-8** | A credit note is a **separate document with its own series**, never a negative invoice | High — a sign test instead of a table scan, and every report that assumes positive invoices breaks | ☐ |
| **M5-9** | A failed delivery writes a **RETURN**; it never deletes or edits the ISSUE | High — the ledger would stop recording what physically happened | ☐ |
| **M5-10** | `client_uuid UNIQUE` on `delivery` from the first migration | Medium–High — a window with no duplicate protection on stock-moving rows | ☐ |
| **M5-11** | `round_off_amount` is a **stored column on the invoice**, not a display artefact | High — the rounding must be visible on the document and reproducible from it | ☐ |
| **M5-12** | **A credit note writes no stock movement**; `restocked` is dropped (D-7, ADR-0009) | **Severe** — once coupled documents exist, phantom stock is indistinguishable from real stock in history | ☐ |
| **M5-13** | **Exposure terms partition on the ledger, not on order status** (D-9) | High — a credit decision made against understated exposure cannot be undone | ☐ |

---

## 12. Implementation tasks

Eleven, each independently verifiable and committable (ADR-0005 §6.2).

| # | Task | Gated by |
| --- | --- | --- |
| 1 | New **`ledger` module**: `CustomerLedgerEntry`, migration, append-only trigger, `settled_balance` (R-1), `sales_order_id`; add to the layers contract | D-2, M5-6, M5-3 |
| 1b | Repoint `orders.selectors` — settled term to `ledger`, open term filtered by ledger presence (**D-9**), live statuses widened | M5-13 |
| 2 | `customer.state_code` + derivation rule | D-3, M5-7 |
| 3 | `number_series` model, migration, seed, locked allocation | M5-4 |
| 4 | `fulfilment` module: `delivery` model, migration, `client_uuid` | M5-10 |
| 5 | Dispatch service — writes the ISSUE with `source_document = Delivery`; **registers `Delivery` in `SOURCE_DOCUMENT_REGISTRY`, closing TD-16**; calls `evaluate_credit` before any write (**D-8**) | M5-1, R-2, B-14 |
| 6 | Delivery complete / fail — POD, GPS, RETURN on failure | M5-9 |
| 7 | `billing` module: `invoice` + `invoice_line`, GST split, snapshots, triggers | M5-2, M5-3, M5-7, M5-11 |
| 8 | Invoice issue service + ledger entry in one transaction | M5-5, B-9 |
| 9 | `credit_note` + `credit_note_line`, cap enforcement under lock. **No stock path** (D-7) | M5-8, M5-12, B-7, F-8 |
| 10 | Invoice PDF — render, cache on first request | D-5 |
| 11 | API, owner screens, adversarial suite | §7, §10 |

**Also in this milestone:** TD-14 (`Product._has_history()` — order lines and stock
movements both now exist, so the hook can finally be real) and TD-2/TD-18 (make `mypy`
blocking, per the M3 report's strongest lesson).

---

## 13. Verification strategy

| Layer | What it must prove |
| --- | --- |
| **Regression** | **The M3 boundary suite passes unmodified.** If it needs changing, the boundary has eroded |
| Worked scenarios | A, B, C and E from §4 executed as tests — a design document that runs cannot diverge |
| Immutability | Raw SQL against all three new append-only tables |
| Concurrency | N threads issuing invoices; N threads crediting one invoice |
| Reconciliation | Ledger balance equals the sum of entries after a randomised sequence |
| Snapshot | Price change after issue leaves the invoice and its PDF unchanged |
| Authorisation | Full role × capability grid, direct to the API, bypassing clients |
| Tax | Intra-state, inter-state, and the no-GSTIN fallback, each asserted on the persisted split |

---

## 14. Sign-off

| # | Item | Party | Status |
| --- | --- | --- | :-: |
| 1 | **C-1, C-2, C-3 resolutions** (§3) | Product Architect | ☐ |
| 2 | **D-4 — invoice cancellation: A or B** (§5) | Product Architect | ☐ |
| 3 | **D-5, D-6** | Product Architect | ☐ |
| 3b | **D-7, D-8, D-9** — accepted from the independent review (§15) | Product Architect | ☐ |
| 4 | **M5-1 … M5-13 irreversible decisions** | All | ☐ |
| 5 | **ADR-0008** — dedicated `ledger` module | All | ☐ |
| 5b | **ADR-0009** — a credit note writes no stock movement (deviates from `04` T-19) | All | ☐ |
| 6 | **CF-1 — is statutory e-invoicing (IRN/QR) mandatory for this client?** | **Business owner** | ☐ |
| 7 | This document accepted | All | ☐ |

> **CF-1 has been open since `01_Project_Vision.md` and this is the milestone where it
> lands.** If the client's turnover requires e-invoicing, `invoice` needs `irn`,
> `ack_number` and `qr_code_media_id`, and a portal integration enters scope (O13). The
> columns are additive, so a late *yes* is recoverable — but a late discovery after
> invoices exist means re-transmitting historical documents. **Confirm before task 7.**

---

---

## 15. Independent review — evaluation *(added v1.1.0)*

Three concerns raised. **All three accepted.** Two of them found defects that had survived
a frozen design corpus and a verified milestone.

### 15.1 — Should the ledger live in `customers`, or in a dedicated module?

**Verdict: dedicated `ledger` module. v1.0.0 was weaker. Amended.**

v1.0.0 placed it in `customers` because `customers` is below every writer and doing so
resolved TD-19. Both facts are true, and neither is the right question. **The right question
is what the table *is*** — and the answer is that it is a high-volume, append-only,
transactional fact table, while `customers` is slowly-changing master data. Two lifecycles,
two risk profiles, one module: an SRP violation at module scope. `customers.services` would
have held `set_credit_limit` (owner-only master-data mutation) beside `record_ledger_entry`
(financial fact written by three other modules).

**The decisive argument is the project's own precedent, not taste.** The architecture
already faced this exact choice and answered it: `StockMovement` is not inside `catalogue`;
it has `inventory`. `CustomerLedgerEntry` is the same structure over `customers`, so it gets
`ledger`. **R-1 already prescribes the shape** — the aggregate selector lives with the fact
table and anchors on the dimension — and R-1's own text anticipated the ledger case by name.

I reached for the nearest module below `billing` instead of asking what the table was. That
is the error, and the reviewer was right to name it.

**Long-term consequences.** `03` §2.1's `receivables` row splits cleanly: `ledger` holds
facts, M6's `receivables` becomes payments and collections above it. When a supplier ledger
arrives (FR-RET-007, unscheduled and absent from `04`), it has an obvious home instead of
forcing a second awkward placement. Cost of doing this now: **zero — no rows exist.** Cost
at M6: a `SeparateDatabaseAndState` migration on a table holding financial records.

### 15.2 — Can inventory be increased twice? **Yes. Confirmed defect.**

**Verdict: real, and it originates in `04` T-19, not only in this review. Amended (D-7).**

`04` T-19 specifies `restocked BOOLEAN` and states: *"When `restocked = true`, writes
positive stock movements … the DV-8 mechanism by which V1 handles returns without a return
module."* Scenario F (§4) executes it:

```
dispatch      ISSUE   −24   →  1176
delivery FAILS RETURN +24   →  1200   (goods physically back)
credit note, restocked=true
              RETURN +24   →  1224   ← 24 units that do not exist
```

**What makes it dangerous is not carelessness — it is that the honest answer is the wrong
one.** At the moment of crediting, the goods genuinely are on the shelf. An owner asked
"were these restocked?" correctly answers *yes*, and inflates stock. The flag presents as a
question about physical reality; it is really a question about which document should write
the movement, and only the system can answer that. **A field whose correct answer produces
an incorrect result is a design defect, not a training problem.**

And it is v1.0.0 contradicting its own §1. I wrote *"dispatch makes stock physical, the
invoice makes money owed — two separate boundaries"* in §1, then coupled a financial
document to a physical movement in §4. The governing principle was right; Scenario C did
not follow it.

**Corrections considered:**

| Option | Verdict |
| --- | --- |
| Force `restocked = false` when a failed delivery exists | Fixes one path. A manual `SALES_RETURN` followed by a credit note still double-counts. A special case, not a mechanism. **Rejected** |
| Credit note writes stock; failed delivery does not | Stock understates while goods sit unclaimed; redelivery needs a second ISSUE. Contradicts C-1. **Rejected** |
| Cap: cumulative RETURN ≤ cumulative ISSUE per order | A genuine invariant and the physical analogue of B-7 — but enforceable only over document-driven movements, so manual returns escape it. **Kept as a reconciliation check (A-12), not as the fix** |
| Dedicated `sales_return` document | Correct, and explicitly Edition 2 (DV-8). **Deferred** |
| **Credit notes write no stock movement** | **Adopted.** Removes the second writer entirely rather than refereeing between two |

**It is the smallest correction available because it deletes a field and a code path rather
than adding either.** DV-8's intent — no returns module in V1 — is preserved: a physical
return is still just a reason-coded movement. What changes is that the credit note stops
claiming to write it.

**Long-term consequences.** The owner performs two actions instead of one for a normal
return; the screen may offer the second as a disclosed convenience, but it produces its own
row. In exchange, no path in the system can produce phantom stock — and phantom stock is
uniquely corrosive because, once in an append-only ledger, it is indistinguishable from real
stock and can only be removed by a further adjustment that is itself indistinguishable from
a genuine one. Requires **ADR-0009**.

### 15.3 — Should credit exposure be revalidated before dispatch?

**Verdict: yes. Amended (D-8) — and validating it exposed a second defect (D-9).**

First, a correction to the implied premise: M3's exposure formula **already** counts open
orders, so the "several orders confirmed in quick succession" case is handled at
confirmation, and invoicing an earlier order moves value from the open term to the settled
term leaving the total unchanged. Exposure is largely conserved across the events that most
obviously look like drift. The concern is narrower than it first appears.

It survives anyway, for one reason: **exposure at confirmation is a prediction; exposure at
dispatch is a fact.** Before dispatch a default costs nothing. After it, the goods are gone.
Nothing in the design forces prompt dispatch, so the staleness window is unbounded, and
`set_credit_limit` can lower the limit inside it.

Cost of accepting: **one function call.** `evaluate_credit(order=order)` is status-driven,
`CONFIRMED` is already an open status, so calling it at dispatch yields identical semantics
with no double-count and no new logic. `03` §2.1 already permits `fulfilment → orders`.
Cost of declining: an order confirmed a month ago ships to a customer now over limit, and
the mechanism that exists to bound exposure stayed silent.

**Where, and why there.** `fulfilment.services.dispatch_order()`, before any write, inside
the dispatch transaction. Not in `orders`, because dispatch is a fulfilment act; not in the
API or admin layer, because N-01 puts rules in services. **The same function, not a second
implementation** — a credit rule that differs by caller is worse than no credit rule, which
is the PO-6 discipline applied to credit instead of price.

**How it fails matters.** `BLOCK` blocks, but the owner may override with a mandatory
audited reason. Refusing outright at the loading bay teaches staff to dispatch without
recording it, which is the ADR-0006 failure, and an unrecorded dispatch is worse than a
recorded over-limit one.

**The adjacent defect this uncovered.** Checking whether a second call site could
double-count led to `orders.selectors.OPEN_STATUSES = (PLACED, CONFIRMED)`. **M5 makes
`DISPATCHED` reachable for the first time**, and a dispatched-but-uninvoiced order then
belongs to *neither* exposure term — not open (wrong status), not settled (no ledger entry).
It disappears from exposure at exactly the moment the distributor is most exposed, and F-1
makes the window unbounded.

The status list was a proxy that was correct only while invoicing did not exist. D-9
replaces it with the predicate `open_order_value`'s own docstring already claimed —
*agreed but not yet billed* — so the two terms partition on ledger presence and are mutually
exclusive by construction. **This is shipped M3 code that is correct today and becomes wrong
the moment M5 lands.** It would not have been found by testing M5 in isolation.

---

*No code has been written or authorised. Task decomposition moves to `NEXT_TASK.md` once
this document is signed.*
