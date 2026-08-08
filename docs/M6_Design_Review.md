# M6 — Receivables: Design Review

| Field | Value |
| --- | --- |
| Document ID | `M6_Design_Review` |
| Version | 1.2.0 |
| Status | **Design complete — implementation authorised** |
| Date | 2026-08-06 |
| Milestone | M6 — Receivables |
| Scope | payments · reversal · write-off · derived outstanding · statement · opening balances |
| Effort | 1.5 units (`00` §19.1) |
| Depends on | `00` v1.0.0 · `02` · `02A` v0.2.0 · `04` v0.1.0 · `05` · M5 verified · ADR-0008 |

> Durable record of the M6 design decisions (`00` §10, ADR-0005 §10).
>
> **v1.1.0 — Product Architect ruling of 2026-08-06.** C-1, C-2, C-3, D-4, D-5, D-6 and
> D-8 **approved**. D-7 (moving `_ImmutableDocument` to `core`) **deferred to a hardening
> milestone**; verified M5 code is not to be modified unless M6 requires it. AR-2 was
> required to be fully resolved before implementation — **§5A does that**, and it is now
> decision **D-9**.
>
> **v1.2.0 — independent review of three implementation concerns. All three upheld.**
> **(1)** Deriving `payment_number` from the primary key requires an `UPDATE` that the
> immutability trigger forbids — D-4's mechanism becomes a pre-insert `nextval`.
> **(2)** The write-off lock was a **false guarantee** and is removed; §6.2 states why
> reversal's lock is real and this one was not. **(3)** Opening balances become idempotent
> by natural key — **D-10**, a partial unique index.
>
> **None of the three changes the architecture.** Two correct mechanism errors and one adds
> a constraint. The governing principle, the module graph, the ledger and §5A are untouched.
>
> **No ADR is proposed.** M6 changes no milestone boundary, merges nothing and splits
> nothing, so no roadmap amendment is required. §3 resolves documentation conflicts by
> applying the existing precedence rule, not by creating new authority.

---

## 1. The governing principle

Each milestone so far has been organised around refusing to store something:

| | Refuses to store | Derives instead |
| --- | --- | --- |
| M2 | A quantity on a product | `SUM(stock_movement.quantity)` |
| M5 | A balance on a customer | `SUM(customer_ledger_entry.amount)` |
| **M6** | **Which invoice a payment paid** | **Applied FIFO at read time** |

> **A payment reduces what a customer owes. It does not pay an invoice.**
>
> The distributor keeps a running account — *udhaari* — not an invoice-matched ledger.
> Money arrives against the customer, and *which* invoices are consequently settled is a
> **view**, computed oldest-first when someone asks, and never written down.

### 1.1 Why this is the whole design

The client's founding problem is "who owes me what" (`01` §3.3). That question is answered
by one `SUM`. It does not require knowing which invoice any particular rupee retired, and
the moment the system claims to know that, it has to be **right** about it forever.

An allocation is a decision. A stored allocation is a decision recorded as fact. If it was
made wrongly — a payment matched to the wrong invoice — un-picking it means editing
financial history, which N-04 forbids, or writing compensating allocations, which is
machinery Edition 1 has no use for.

**Deriving costs a query. Storing costs a migration of live financial records, and only
in the direction that cannot be automated.** Edition 2 adds `payment_allocation` on top of
an unchanged ledger (`04` T-21, T-22 future evolution); it cannot remove one.

### 1.2 What M6 must not touch

| | Why |
| --- | --- |
| Stock | A payment is money. It moves no goods (M2 boundary) |
| Invoices | **A payment does not modify the invoice it happens to settle.** Invoices are immutable (M5-3); "paid" is derived, never a column |
| Orders | Exposure changes because the ledger changed, not because M6 touched an order |
| Any stored balance | N-03. There is no balance column and adding one is forbidden |

A boundary suite proves each, in the shape M3 and M5 established.

---

## 2. Scope

### In

`payment` table · record · reverse · write-off · derived outstanding invoices (FIFO) ·
customer statement with opening/closing · opening-balance load · `receivables` module ·
six endpoints · owner screens.

### Out — by frozen decision, not omission

| Excluded | Decision |
| --- | --- |
| Payment-to-invoice allocation | `02A` §13.2 — Edition 2. **See C-1** |
| Configurable aging buckets | `02A` §13.2 — Edition 2. **See C-2** |
| Field collection on the mobile app | FR-REC-010 is v1.1 / S3 — M8. **Structural columns land now** |
| Cash-in-hand accountability per collector | FR-REC-013, priority S, v1.1 |
| Retailer self-service balance view | FR-REC-014 is v1.2 — M12 |
| Receivables *reports* and CSV | M7. M6 provides the selectors they read |
| Supplier payables | Edition 2 — no table exists in `04` |

---

## 3. Conflicts in the frozen corpus — resolve before implementation

Three. Each is a case where `02_Requirements_Specification.md` was **not back-updated**
when `02A` §13 re-validated Edition 1 and demoted features. `02A` §13 is the later
document, it was explicitly approved, and `04` was designed from its outcome — so it
governs. I am recording the supersession rather than inventing new authority.

### C-1 — Is payment-to-invoice allocation in Edition 1?

| Source | Says |
| --- | --- |
| `02` **FR-REC-004** | "Payments MUST be allocatable against one or more specific invoices" — **M, v1.0** |
| `02` **FR-REC-006** | "Allocated payment MUST NOT exceed the outstanding value of the target invoice" — **M, v1.0** |
| `02A` §7.9 | "Allocate payment to invoice — Edition 1: Y" *(the pre-re-validation table)* |
| **`02A` §13.2** | **"Payment-to-invoice allocation — demoted to Edition 2. Distributors keep a running account, not an invoice-matched ledger. Saved 0.5"** |
| **`04` T-21** | **"No invoice allocation in V1. Payment credits the customer's running account, which is how the client's ledger book already works"** |
| `04` T-22 | "Edition 2 adds `allocation_id` for invoice matching" |

**Resolution: no allocation in M6.** `02A` §13.2 supersedes both FR-REC-004 and FR-REC-006
for Edition 1, and `04` — frozen after — encodes that outcome. Building allocation now
would contradict the database design the milestone is implementing.

**This is the single most consequential resolution in M6** and it is why C-1 is first.
Getting it wrong in the *permissive* direction is not symmetrical with getting it wrong in
the restrictive direction: allocation rows added later are additive; allocation rows
removed later are a migration of live financial history.

**Action required:** `02` FR-REC-004 and FR-REC-006 should be re-marked **v2.0**. Until
that edit is made, this document is the record.

### C-2 — Aging: buckets, or a list of unpaid invoices?

| Source | Says |
| --- | --- |
| `02` **FR-REC-008** | "aging analysis over **configurable buckets**" — **M, v1.0** |
| `02` **OI-4** | "Aging bucket definition — **M6** — 0–30 / 31–60 / 61–90 / 90+, configurable" |
| **`02A` §13.2** | **"Aging buckets report — demoted to Edition 2. A list of unpaid invoices with dates shows age without a bucketing engine. Saved 0.3"** |
| **`04` T-21** | **"Aging is computed FIFO against unpaid invoices at read time"** |
| `02A` §13.2 (simplified) | "Receivables: running-account ledger with derived balance and **a list of unpaid invoices**" |

**Resolution: a derived list of unpaid invoices with their age in days.** The four bucket
boundaries become **display constants**, not configuration. OI-4 is answered — the numbers
are 30/60/90 — but no bucket-definition table, no settings screen, no engine.

The collection question the owner actually asks is *"who is oldest and how much?"*, and a
sorted list answers it. A configurable bucketing engine answers the same question with a
configuration surface attached.

### C-3 — A reversal has no actor and no timestamp on the row

`04` T-21 gives `payment` an `is_reversed` boolean and a `reversed_reason`, and **nothing
else**. M5's `invoice` — the same shape of event, a discretionary reversal of a financial
document — carries `cancelled_at` and `cancelled_by` explicitly.

**Resolution: add `reversed_at` and `reversed_by_id`, nullable.** Two columns on a table
being created anyway.

The counter-argument is that `audit_log` already records actor and timestamp, so the
columns are redundant. That is true and insufficient: "who reversed this payment" is a
question asked *of the payment*, and answering it should not require knowing that an audit
subsystem exists and joining to it on a polymorphic key. M5 made exactly this call for
invoice cancellation and the asymmetry is not defensible.

---

## 4. Worked business scenario

Continuing the corpus scenario. Customer `C-0142`, credit limit ₹10,000.

**Opening position, loaded at go-live (ACT-E):** ledger `OPENING +4,500.00`.

| # | Event | Rows written | Ledger balance | Exposure |
| --: | --- | --- | --: | --: |
| 1 | Go-live opening balance | `customer_ledger_entry OPENING +4500.00` | 4,500.00 | 4,500.00 |
| 2 | Order placed & confirmed, ₹2,832 | `sales_order` (no ledger entry — M3-6) | 4,500.00 | **7,332.00** |
| 3 | Dispatch | `stock_movement` ISSUE (no ledger entry — M5) | 4,500.00 | 7,332.00 |
| 4 | Invoice `INV/26-27/00001` | `invoice` + `customer_ledger_entry INVOICE +2832.00` | **7,332.00** | 7,332.00 |
| 5 | **Retailer pays ₹5,000 cash** | `payment PAY-00000001` + `customer_ledger_entry PAYMENT −5000.00` | **2,332.00** | **2,332.00** |
| 6 | Payment keyed twice by mistake — same `client_uuid` | **nothing.** The original is returned | 2,332.00 | 2,332.00 |
| 7 | Owner reverses PAY-00000001 (wrong customer) | `payment.is_reversed = true` + `customer_ledger_entry ADJUSTMENT +5000.00` + `audit_log` | **7,332.00** | 7,332.00 |
| 8 | Payment re-recorded against the right customer | `payment PAY-00000002` on the other customer | 7,332.00 | 7,332.00 |

**Step 5 is the whole milestone.** One payment row, one ledger entry, no allocation, and
the balance falls by exactly the amount received. Credit headroom returns automatically
because D-9 made exposure read the ledger — M6 writes no code to make that happen.

### 4.1 The derived view at step 5

Balance 2,332.00. Applied FIFO, oldest first:

| Document | Date | Amount | Applied | Outstanding |
| --- | --- | --: | --: | --: |
| Opening balance | 01 Apr | 4,500.00 | 4,500.00 | **0.00** — settled |
| `INV/26-27/00001` | 06 Aug | 2,832.00 | 500.00 | **2,332.00**, aged 0 days |

**No row records that ₹4,500 of the payment retired the opening balance.** Ask again
tomorrow and the same walk produces the same answer, because the inputs are immutable.

### 4.2 Step 7 is where the money can be lost

A reversal reads `is_reversed`, decides, and writes. That is a read-then-write on a
mutable row, and it is the only one in M6. Two concurrent reversals that both read `false`
write two compensating entries and credit the customer **twice**. §6 handles it.

---

## 5. Decisions requiring confirmation

### D-1 — A payment is recorded against the customer, never an invoice *(resolves C-1)*
See §3. The running account is the model.

### D-2 — Aging is a derived list, not a bucket engine *(resolves C-2)*
See §3. 30/60/90 are display constants.

### D-3 — `reversed_at` and `reversed_by_id` are added *(resolves C-3)*
See §3. Symmetry with `invoice.cancelled_at` / `cancelled_by`.

### D-4 — `payment_number` is a **reference**, not a statutory series

The system now has two kinds of document number and the distinction should be explicit
rather than incidental:

| Kind | Examples | Gapless? | Lock? | Why |
| --- | --- | :-: | :-: | --- |
| **Statutory** | `invoice`, `credit_note` | **Yes** | Row lock | A gap is a question from a tax authority (M5-4) |
| **Reference** | `sales_order`, **`payment`** | No | None | A human handle. `05` §10.4 shows `PAY-00000812` |

**A receipt is not a statutory series.** The decision — gaps permitted, no lock — is
unchanged. **The mechanism changed in v1.2.0 and the reason is worth recording.**

#### The insert-then-update mechanism does not work on this table *(independent review, upheld)*

M3 derives `order_number` from the primary key in two statements:

```python
order.save()                                    # INSERT — pk assigned
order.order_number = f"SO-{order.pk:08d}"
order.save(update_fields=["order_number", ...])  # UPDATE
```

`sales_order` carries no immutability trigger, so the second statement is permitted.
**`payment` will carry one** (§10), and its permitted set is exactly four reversal
columns. An `UPDATE` writing `payment_number` changes a column outside that set, so **the
trigger raises and every payment fails.**

The reviewer is right, and the M3 precedent cited in v1.1.0 does not transfer. Copying a
pattern from a table without a trigger onto a table with one is precisely the kind of
false analogy a review exists to catch.

#### Adopted: a dedicated sequence read **before** the insert

```sql
CREATE SEQUENCE payment_number_seq;   -- migration
SELECT nextval('payment_number_seq'); -- then ONE INSERT carrying the number
```

Smallest change that preserves everything:

| Property | Held? |
| --- | --- |
| One statement — no `UPDATE`, so the trigger is never engaged | ✅ |
| No lock on the write path | ✅ `nextval` is lock-free and concurrency-safe by design |
| `PAY-00000812` format from `05` §10.4 | ✅ |
| The number is immutable from the instant the row exists | ✅ **stronger than M3's**, where it is briefly empty |

**A sequence is not merely acceptable here — it is the right instrument.** The single
property that disqualified sequences for invoices (M5-4: a rolled-back transaction
consumes a value permanently, leaving a gap) is a property D-4 has *already accepted* for
receipts. What is a defect for a statutory series is correct behaviour for a reference.

**Rejected alternatives.** Exempting `payment_number` from the trigger — it would make a
receipt number permanently mutable to solve a one-time bootstrap problem, and a receipt
number that can change is worse than the problem. A `BEFORE INSERT` trigger computing it
from `NEW.id` — works, but adds a second trigger and an ORM refresh for no gain.

### D-5 — Which acts are audited

Third consecutive application of the same reading, and it should be settled once.

| Act | Audited? | Why |
| --- | :-: | --- |
| Payment recorded | **No** | The `payment` row carries amount, method, date, collector, device and `client_uuid`; the ledger entry carries the rest. Routine, and already fully self-describing |
| **Payment reversed** | **Yes** | Discretionary, owner-only, and it moves money back |
| **Write-off** | **Yes** | Discretionary, owner-only (FR-REC-015) |
| Ledger entry created | No | Immutable — its own audit (R-3) |
| Opening balance loaded | **Yes** | A one-off privileged bulk act at go-live |

> **Process note.** `02A` §13.2 lists "payment" in its audit scope, read literally. M2 D-3,
> M5 D-6 and now M6 D-5 have each read that list as *the discretionary and irreversible
> subset* rather than literally, and each time the reasoning was re-derived from scratch.
> **Recommend amending `02A` §13.2 once** to say what three milestones have concluded,
> instead of reinterpreting it a fourth time at M7.

### D-6 — Write-off is in M6

`00` §19.1 scopes M6 as "customer ledger, payments, derived balance, statement" and does
not name write-off. But `WRITE_OFF` is already a permitted `entry_type` in `04` T-22 with a
sign rule, and FR-REC-015 is v1.0.

**Recommend including it.** It is one service function plus an audit row, and leaving a
declared enum value with no writer is the `restocked` mistake inverted — a mechanism that
exists in the schema, does nothing, and invites a future developer to wire it up without
the owner-only guard.

### D-7 — The immutability machinery moves to `core`

`payment` is **mutable in exactly two fields** and immutable in every other — precisely the
shape M5 built for `invoice` (`_ImmutableDocument`, `_mutable_fields`, plus a
column-aware trigger).

| Option | Verdict |
| --- | --- |
| Duplicate the pattern in `receivables` | Violates "never duplicate logic". Two copies of an immutability guard drift, and the drift is silent |
| Import `billing._ImmutableDocument` | Layer-legal (`receivables → billing`) but reaches across a module boundary for a private class |
| **Move it to `core.models`** | **Recommended.** It is shared behaviour over financial records, `core` is where `TimeStampedModel` already lives, and the move is behaviour-preserving |

**This touches M5 code**, so it is flagged rather than assumed. It is a pure relocation:
no logic changes, and M5's tests must pass unmodified — which is the acceptance test for
the move.

### D-8 — Opening balances load through `ledger.services.record_entry`

No bulk-insert path, no management command writing rows directly. The go-live load (ACT-E)
is a privileged owner action that calls the same single writer everything else calls, so
the sign rules, the source-document registry and the audit all apply to the most
financially sensitive write the system will ever perform.

### D-10 — Opening balances are idempotent by **natural key**, not by a flag

*(Independent review recommendation, adopted.)*

ACT-E is a bulk load, run once at go-live, **by a human, possibly re-run after a partial
failure**. Re-running must not double every customer's opening balance — and this is the
single most financially sensitive write the system will ever perform, so "be careful" is
not a control.

**Adopted: a partial unique index.**

```sql
CREATE UNIQUE INDEX uq_cle_one_opening_per_customer
    ON customer_ledger_entry (customer_id)
    WHERE entry_type = 'OPENING';
```

The deterministic identifier is **the customer**. No new column, no UUID to generate and
carry, no flag to remember to check — because the constraint states a business truth
rather than a mechanism:

> **A customer has exactly one opening balance.** It is the balance at go-live. Two
> opening balances is not a duplicate record; it is a meaningless one.

`load_opening_balance` attempts the insert inside a savepoint and treats a conflict as
"already loaded". Re-running the entire import is a **no-op**, whatever the mix of
already-loaded and not-yet-loaded customers — which is exactly the state a partial failure
leaves behind.

**Why not `client_uuid` on the ledger entry.** It would work, and it would require adding
a column to a frozen table that M5 already writes, plus generating and preserving a UUID
per customer across import runs — external state the natural key does not need.

**Safe to add now.** No `OPENING` row exists: `record_entry` accepts the type, but M5's
only callers write `INVOICE`, `CREDIT_NOTE` and `ADJUSTMENT`. Zero rows can violate the
constraint, so this is an addition to a shared table rather than a change to verified
behaviour — **it modifies no M5 code path.**

### D-7 — **DEFERRED.** The immutability machinery stays in `billing`

Product Architect ruling: verified M5 code is not modified unless M6 requires it. M6 does
not require it — `receivables` may import `billing` (§8), so `Payment` reuses M5's
`_ImmutableDocument` across the module boundary rather than duplicating it.

**One import of a private class is the price, and it is the right one to pay.** The
alternative I proposed would have refactored a milestone verified hours earlier, and my
own §12.4 said the practice has a poor record. Recorded as **TD-24**, due at M10
hardening. Duplicating the guard was never an option (§5 D-7 table); this is the
second-best of two, not a compromise on the first.

---

## 5A. The FIFO application rule — AR-2 resolved *(D-9)*

> **This section was required before implementation and is the resolution of the one hole
> §12.1 admitted.** It specifies the derived outstanding view completely: classification,
> ordering, algorithm, worked examples, edge cases, and the invariant that proves it.

### 5A.1 The question

A credit note reduces the balance but **is not a payment**. It carries `invoice_id` — it is
*about* one document. A payment is about the *customer*. Do they apply the same way?

### 5A.2 First principles

Test the two candidate rules against a fact the retailer can check.

Invoice A ₹1,000 (1 Jan). Invoice B ₹1,000 (1 Feb). Credit note ₹200 **against B** (5 Feb).

| Rule | A outstanding | B outstanding | Balance |
| --- | --: | --: | --: |
| **(a) Uniform FIFO** — every credit oldest-first | 800 | 1,000 | 1,800 |
| **(b) Targeted** — the credit note reduces its own invoice | 1,000 | 800 | 1,800 |

Both give the right *balance*. Only one gives the right *document*.

**A credit note legally reduces the value of invoice B.** If the retailer asks "what do I
owe on B?", the answer is ₹800. Rule (a) answers ₹1,000 — factually wrong about a
statutory document, while coincidentally right about the total.

> **Adopted: a credit note reduces the invoice it references. A payment settles the
> account oldest-first.** They are different instruments and the walk treats them
> differently because the business does.

### 5A.3 Classification — every ledger entry has exactly one role

The classifier reads `entry_type`, sign, and `source_document_type` (R-2's registry
already stores the last). **No new column is required.**

| Entry | Sign | Role | Recognised by |
| --- | :-: | --- | --- |
| `OPENING` | + | **Debit** | type |
| `INVOICE` | + | **Debit**, gross reduced by its credit notes | type |
| `CREDIT_NOTE` | − | **Reducing** — targeted at its invoice | type |
| `ADJUSTMENT` | − | **Annulling** — invoice cancellation | `source_document_type = 'INVOICE'` |
| `ADJUSTMENT` | + | **Annulling** — payment reversal | `source_document_type = 'PAYMENT'` |
| `ADJUSTMENT` | ± | Manual: **+ Debit**, **− Settling** | `source_document_type = ''` |
| `PAYMENT` | − | **Settling** — FIFO | type |
| `WRITE_OFF` | − | **Settling** — FIFO | type |

**Annulling is the third category, and it is the one I had not thought about.** When an
entry is annulled, **both it and its annuller leave the walk entirely.**

#### Why a payment reversal must annul rather than become a new debit

If a reversal were treated as an ordinary positive entry, it would become a fresh debit
dated the day of the reversal. The invoices that payment had settled would stay settled,
and the debt would reappear as a **new, zero-day-old** item.

**That is backwards for a collections tool.** It would launder genuinely aged debt into
fresh debt every time a payment was reversed. Annulment restores the original invoices to
outstanding **at their original ages**, which is what actually happened: the money never
arrived.

### 5A.4 The algorithm

```
inputs:  ledger entries for the customer where entry_date <= as_of
         credit_note.invoice_id mapping (one read into `billing`)

1. ANNUL
   remove each annulling entry together with its target.
   an annulled entry participates in nothing further.

2. DEBITS
   debits := remaining positive entries, ordered by (entry_date, id) ascending
   each debit carries: remaining := amount

3. REDUCE  (targeted, applied BEFORE any settling)
   for each credit note:
       target := the INVOICE debit for credit_note.invoice_id
       target.remaining -= |amount|

4. SETTLE  (untargeted, FIFO)
   pool := sum of |settling credits|
   for debit in debits (oldest first):
       applied      := min(pool, debit.remaining)
       debit.remaining -= applied
       pool            -= applied

5. RESULT
   outstanding        := [d for d in debits if d.remaining > 0]
   age(d)             := as_of - d.entry_date, in days
   credit_on_account  := pool        # > 0 only if the customer has overpaid
```

**Step 3 precedes step 4, and the order is not arbitrary.** A credit note establishes what
an invoice was *ever worth*; a payment settles what is *owed*. Reducing first means the
net value is fixed before any money is applied to it.

### 5A.5 Two properties that make step 3 safe

Both are already guaranteed by M5 and required no new machinery:

1. **`net_invoice ≥ 0` always.** M5's B-7 caps total credited against an invoice at its
   `total_amount`. So step 3 can never drive a debit negative, and there is no overflow to
   carry into step 4.
2. **An invoice is never both credited and cancelled.** `cancel_invoice` refuses an invoice
   with credit notes; `issue_credit_note` refuses a cancelled invoice. The two targeted
   sources are **mutually exclusive per invoice**, so "reducing" and "annulling" never
   contend for the same debit.

*M5's guards turn out to be exactly the preconditions this algorithm needs. That was not
designed for — it is a consequence of both following from the same principle.*

### 5A.6 Ordering and determinism

Debits sort by **`(entry_date, id)`**, both ascending. `entry_date` is the business date;
`id` is monotonic per database and breaks same-day ties.

**Without the `id` tie-break, two invoices on the same date could apply in either order and
the same inputs would produce different views on different days.** Every input to the walk
is immutable, so with the tie-break the view is a pure function of `(customer, as_of)` —
reproducible forever, which is the property a statement needs.

### 5A.7 The invariant

> **Σ outstanding.remaining − credit_on_account ≡ `settled_balance(customer, as_of)`**

Proof: annulled pairs sum to zero and are excluded from both sides; reducing credits are
subtracted from debits; settling credits are subtracted from debits or land in
`credit_on_account`. Every entry is counted exactly once, with its sign.

**This is the property test.** It ties an algorithmic view back to the one number the
system already trusts — the `SUM` — and it is asserted over a randomised sequence of
invoices, credit notes, payments, reversals, cancellations and write-offs.

### 5A.8 Worked example

Customer `C-0142`, `as_of` = 2026-08-31.

| # | Date | Entry | Amount | Role |
| --: | --- | --- | --: | --- |
| 1 | 01 Apr | `OPENING` | +4,500.00 | Debit |
| 2 | 10 Jun | `INVOICE` INV/…/00001 | +2,832.00 | Debit |
| 3 | 05 Jul | `INVOICE` INV/…/00002 | +1,180.00 | Debit |
| 4 | 08 Jul | `CREDIT_NOTE` CN/…/00001 → **INV/00002** | −180.00 | Reducing |
| 5 | 12 Jul | `PAYMENT` PAY-00000001 | −5,000.00 | Settling |
| 6 | 20 Jul | `INVOICE` INV/…/00003 | +900.00 | Debit |
| 7 | 22 Jul | `ADJUSTMENT` cancel of **INV/00003** | −900.00 | Annulling |
| 8 | 02 Aug | `PAYMENT` PAY-00000002 | −1,000.00 | Settling |
| 9 | 06 Aug | `ADJUSTMENT` reversal of **PAY-00000002** | +1,000.00 | Annulling |

**Step 1 — annul.** #7 annuls #6 (invoice cancelled). #9 annuls #8 (payment reversed).
Four entries leave the walk.

**Step 2 — debits**, oldest first: `OPENING 4,500` · `INV/00001 2,832` · `INV/00002 1,180`.

**Step 3 — reduce.** CN 180 targets INV/00002 → net **1,000.00**.

**Step 4 — settle.** Pool = 5,000 (only PAY-00000001 survives).

| Debit | Net | Applied | Remaining |
| --- | --: | --: | --: |
| OPENING (01 Apr) | 4,500.00 | 4,500.00 | **0.00** |
| INV/00001 (10 Jun) | 2,832.00 | 500.00 | **2,332.00** |
| INV/00002 (05 Jul) | 1,000.00 | 0.00 | **1,000.00** |

**Result at `as_of` 31 Aug:**

| Document | Date | Outstanding | Age |
| --- | --- | --: | --: |
| INV/…/00001 | 10 Jun | 2,332.00 | **82 days** |
| INV/…/00002 | 05 Jul | 1,000.00 | **57 days** |
| | | **3,332.00** | |

`credit_on_account` = 0.00.

**Invariant check.** Ledger `SUM` = 4500 + 2832 + 1180 − 180 − 5000 + 900 − 900 − 1000 +
1000 = **3,332.00** ✓

Note what the view got right that a naive walk would not: **INV/00003 does not appear at
all** (cancelled), and **the reversed payment did not create a fresh 6-Aug debt** — the
82-day-old invoice is still shown as 82 days old.

### 5A.9 Edge cases

| # | Case | Specified behaviour |
| --: | --- | --- |
| **E-1** | Customer with no entries | Empty list, balance `0.00`, `credit_on_account` `0.00`. **The customer still appears** in the receivables report (R-1) |
| **E-2** | Only an `OPENING` entry | One outstanding item that is not an invoice. The view is over *debits*, not invoices; label from `narration` |
| **E-3** | Payments exceed all debits | All debits settled; the excess is `credit_on_account` and the balance is **negative**. Reported distinctly (FR-REC-005) |
| **E-4** | Credit note equals its invoice in full | Net 0 → the invoice drops out with `remaining = 0`, without being annulled |
| **E-5** | Invoice cancelled | Annulled — never appears |
| **E-6** | Payment reversed | Annulled — the invoices it settled return **at their original ages** (§5A.3) |
| **E-7** | Two invoices, same `entry_date` | Tie-broken by `id`. Deterministic (§5A.6) |
| **E-8** | Credit note against a **direct counter-sale** invoice (`sales_order_id` NULL) | Works. Targeting resolves through `credit_note.invoice_id`, never through the order |
| **E-9** | Write-off | **Settling, FIFO** — it clears the oldest debt first, which is what writing off bad debt means |
| **E-10** | Manual `ADJUSTMENT`, positive | A debit dated `entry_date`, with no source document |
| **E-11** | Manual `ADJUSTMENT`, negative | Settling, FIFO |
| **E-12** | Entry dated after `as_of` | Excluded entirely. A back-dated entry added later changes a past view — correct, and why a statement is a *derived* document |
| **E-13** | Credit note whose invoice was annulled | **Impossible** (§5A.5 property 2). Asserted by a test rather than assumed |

### 5A.10 Why targeting is resolved through `billing`, not through `sales_order_id`

A credit-note ledger entry carries `source_document_id` (the credit note) and
`sales_order_id`. Matching a credit note to its invoice **via `sales_order_id`** would
avoid a cross-module read — and is rejected:

* it depends on one-invoice-per-order, an **Edition 1 constraint that Edition 2 drops**;
* a direct counter-sale invoice has `sales_order_id = NULL`, so E-8 would not resolve.

`receivables` reads `CreditNote.invoice_id` from `billing`. That read is precisely why
`03` §2.1 places `receivables` above `billing`, and it is **one query for the whole
customer set**, not one per credit note (§5A.11).

### 5A.11 Performance — FR-REC-009

Three queries for the entire receivables position, applied in memory:

1. all ledger entries for the customer set, ordered `(customer_id, entry_date, id)`;
2. `CreditNote.objects.values('pk', 'invoice_id')` for the credit notes appearing in (1);
3. the customer rows themselves (R-1 anchor — a customer with no entries must not vanish).

**No query is per customer and none is per document.** At the DR-8 envelope — roughly
73,000 invoices a year — a single-customer walk is a few hundred entries. The <10 s budget
is not close to being at risk; the risk was always N+1, and the shape above removes it.

---

## 6. Concurrency analysis

M2 established that appends do not contend. M5 established that a decision based on a
prior read needs an anchor. M6 is almost entirely the former, with exactly one of the
latter.

| Path | Read-then-write? | Lock | Reasoning |
| --- | :-: | --- | --- |
| Record payment | No | **None** | Two payments append two rows and two ledger entries. `SUM` sees both. No shared mutable cell exists |
| Allocate `payment_number` | No | **None** | `nextval` on a dedicated sequence (D-4). Lock-free by construction. Contrast `invoice`, which locks because it must be gapless |
| Write the ledger entry | No | **None** | Append-only, unchanged since M5 |
| `client_uuid` idempotency | **Yes** | Unique constraint + savepoint | Check-then-insert races. `uq_payment_client_uuid` is the guarantee; the service must attempt inside a savepoint and re-fetch on conflict, or a legitimate retry becomes a 500 |
| **Reverse payment** | **Yes** | **`SELECT … FOR UPDATE` on the payment row** | **The only lock in M6.** Without it, two concurrent reversals both read `is_reversed = false` and both write a compensating entry |
| Write-off | **No** *(corrected)* | **None** — see §6.2 | v1.1.0 specified a lock. **It was a false guarantee and is removed** |
| Load opening balance | **Yes** | **Partial unique index**, not a lock (D-10) | Deterministic natural key: one `OPENING` per customer |
| Read balance | No | None | Pure `SUM` over immutable rows. No phantom problem — entries never change |
| FIFO outstanding view | No | None | Read-only over immutable inputs. Deterministic for a given `as_of` |

### 6.1 The reversal lock, stated precisely

```
BEGIN
  locked = Payment.objects.select_for_update().get(pk=...)   # the anchor
  if locked.is_reversed: return locked                       # idempotent
  record_entry(ADJUSTMENT, +locked.amount, source=locked)
  locked.is_reversed = True ; save(update_fields=[...])
  record_audit(...)
COMMIT
```

**The service must gate on `locked`, never on the caller's instance.** This is M5 §4.1
restated: `issue_invoice` read `order.status` from its argument and produced 40 failures
and a path to invoicing a cancelled order. M6 is written knowing that.

### 6.2 The write-off lock is removed — a lock only one writer takes protects nothing

*(Independent review, upheld. v1.1.0 §6 was wrong.)*

v1.1.0 said write-off took "a row lock on the customer's latest state … guarded
identically" to reversal. **That is a false guarantee**, for a reason worth stating
precisely:

> **A lock serialises only the writers that take it.** `record_payment`, `issue_invoice`
> and `issue_credit_note` all append to `customer_ledger_entry` **without** taking any
> customer-level lock — by design, since M2. A lock that write-off alone acquires excludes
> nobody, costs a round trip, and reads to a future maintainer as protection that exists.

**A false concurrency guarantee is worse than none**, because the next person to touch the
code will trust it.

#### Why reversal's lock is real and this one is not

| | `reverse_payment` | `write_off` (as specified in v1.1.0) |
| --- | --- | --- |
| What is mutated | `payment.is_reversed` | Nothing — it appends a ledger entry |
| What is locked | **The same row** | A different row |
| Do all writers of that state take the lock? | **Yes** — `reverse_payment` is the only writer | **No** — every other ledger writer ignores it |
| Serialises? | **Yes** | **No** |

The distinction is not "reversal is more important". It is that **reversal's lock target
and mutation target are the same row**, so every writer of that state contends on it.
Write-off mutates nothing; it appends, and appends never contend (M2).

#### What write-off therefore is

**The owner supplies an explicit amount.** A write-off is a deliberate decision about a
specific sum, not "whatever the balance happens to be at this instant" — and had it been
balance-derived, it would carry a genuine read-then-write that **no lock could fix**,
precisely because the other ledger writers are lock-free.

So: a pure append, owner-only, reason mandatory, audited (D-5), no lock.

**Residual, recorded honestly.** A double submission writes two write-offs. There is no
`client_uuid` on `customer_ledger_entry` and adding one is a schema change to a frozen
table M5 depends on. This is the same residual M2 accepted for duplicate manual
adjustments: visible in the statement, audited, and correctable by a compensating entry.
It is not silent.

### 6.3 Cross-milestone interaction

A payment recorded while an invoice is being issued for the same customer: both append to
the ledger, neither reads the other's outcome, `SUM` sees both. **No interaction, by
construction.** This is the dividend of never storing a balance.

---

## 7. Database implications

One new table, one altered enum usage, no changes to any existing column.

| Table | Notes |
| --- | --- |
| **`payment`** *(new)* | Per `04` T-21 plus D-3's two columns. `client_uuid UNIQUE`, `amount > 0` CHECK, method CHECK, `ck_payment_reversed`. **Column-aware immutability trigger** permitting only the four reversal fields |
| **`payment_number_seq`** *(new)* | A plain `SEQUENCE`. Read by `nextval` **before** the insert, so the row is written once and the trigger is never engaged (D-4) |
| `customer_ledger_entry` | **No column changes.** `PAYMENT` and `WRITE_OFF` (both negative) already exist in the type and sign CHECKs; a reversal writes `ADJUSTMENT`. **One addition: the partial unique index of D-10.** No `OPENING` row exists, so nothing can violate it |
| `customer.opening_balance_amount` | Remains documentation. The `OPENING` entry is the truth (`04` T-22) |

### 7.1 Why a reversal is `ADJUSTMENT` and not a new type

`ck_cle_sign` requires `PAYMENT` to be negative, so a reversal — which increases what is
owed — cannot be typed `PAYMENT`. `ADJUSTMENT` is the only bidirectional type.

Adding a seventh `REVERSAL` type would mean altering a CHECK constraint on a live
append-only financial table. **Rejected**; the narration distinguishes it, exactly as it
does for M5's invoice cancellation, which took the same path.

### 7.2 Indexes

`ix_payment_customer_date (customer_id, payment_date DESC)` for the statement ·
`ix_payment_method_date` for the Cash/UPI split (M7) · `ix_payment_received_by` for
collections-by-user (FR-REC-012, v1.1 — the index is free now).

---

## 8. Service boundaries

| Module | Owns | May call | Writers |
| --- | --- | --- | --- |
| `receivables` *(new)* | `Payment` | `billing`, `ledger`, `customers`, `core` | `record_payment`, `reverse_payment`, `write_off`, `load_opening_balance` |
| `ledger` | `CustomerLedgerEntry` | `customers`, `core` | **`record_entry` — unchanged.** Gains `Payment` in `SOURCE_DOCUMENT_REGISTRY` (R-2) |
| `billing` | invoices | — | **Untouched by M6** |

**Layer graph** — `receivables` slots in above `billing`, exactly where `03` §2.1 and M5's
contract comment anticipated:

```
api | webadmin  >  receivables (M6)  >  billing  >  fulfilment  >  orders
                >  pricing  >  inventory | ledger  >  catalogue | customers
                >  identity  >  core
```

`receivables → billing` exists for one reason: the FIFO outstanding view walks invoices.
It is a **read**. `receivables` must not import `billing.services`, and a structural test
will assert that — the same read/write distinction the M5 boundary suite drew for
`orders → ledger`.

---

## 9. API boundaries

Six endpoints, all specified in `05` §9.6.

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| GET | `/payments` | O, S, D, R | **Scope differs from ledger**: S/D see what *they collected*, R sees own |
| POST | `/payments` | O, S, D | Idempotent on `client_uuid`. Returns `balance_after_amount` |
| POST | `/payments/{id}/reverse` | **OWNER** | Reason mandatory |
| GET | `/customers/{id}/ledger` | O, S, D, R | **Exists since M5** |
| GET | `/customers/{id}/balance` | O, S, D, R | **Exists since M5** — gains `as_of` |
| GET | `/customers/{id}/statement` | O, S, D, R | Opening, entries, closing |

### 9.1 Two details from `05` that are not decoration

**`balance_after_amount` on the create response** (`05` §10.4). The salesman is standing in
front of the retailer and the next question is always *"toh ab kitna baaki?"* — one field
that removes a follow-up round trip on a connection that may not survive one.

**A replayed `client_uuid` returns `200`, not `409`** (`05` §5). A retry after a timeout is
correct client behaviour; answering `409` trains clients to treat a successful write as a
failure, "which is exactly how a salesman ends up recording a payment twice."

### 9.2 The scope asymmetry, stated because it is easy to miss

`05` §8 gives **payments read** to S/D as *"◐ collected"* but **ledger/balance** as
*"○ own zones"*. A salesman sees every payment **they** took, and the balance of every
customer in **their zone**. These are different predicates and must not be collapsed into
one helper.

---

## 10. Audit requirements and append-only guarantees

| Record | Mutability | Enforcement | Audit (R-3) |
| --- | --- | --- | --- |
| `customer_ledger_entry` | **Append-only** | Trigger since M5 | None — it is its own audit |
| `payment` | **Mutable in 4 fields only** | **New column-aware trigger** | Reversal audited; creation not (D-5) |
| `invoice`, `credit_note` | Append-only | Trigger since M5 | Unchanged |

The payment trigger mirrors M5's invoice trigger: compare `to_jsonb(OLD)` minus the
permitted keys against the same for `NEW`, so **a column added by a future migration is
immutable by default rather than mutable by omission.** Permitted: `is_reversed`,
`reversed_reason`, `reversed_at`, `reversed_by_id`. Refuse `DELETE` unconditionally, and
refuse any transition out of `is_reversed = true`.

---

## 11. Architectural risks

| # | Risk | Severity | Mitigation |
| --- | --- | :-: | --- |
| **AR-1** | **C-1 resolved permissively.** If allocation is built, removing it later means migrating live financial history | **Severe** | §3 resolution signed before task 1 |
| **AR-2** | **FIFO correctness with credit notes.** A credit note reduces the balance but is not an invoice. Does it consume FIFO capacity, or reduce the invoice it references? | High | **RESOLVED — §5A (D-9).** Reduces its own invoice. Resolving it also surfaced the *annulling* class, which neither the original design nor the review had identified |
| **AR-3** | Reversal race double-credits a customer | High | §6.1 lock, plus a concurrency test |
| **AR-4** | Duplicate collection from a field retry | **Severe** — it is the founding problem inverted | `client_uuid UNIQUE` from the first migration, savepoint on conflict, adversarial test |
| **AR-5** | FR-REC-009 — receivables position in <10s at DR-8 | Medium | FIFO view must not be N+1. One query for invoices, one for the ledger, applied in memory per customer |
| **AR-6** | D-7's move of `_ImmutableDocument` breaks M5 | Medium | Behaviour-preserving relocation; M5's tests must pass **unmodified** |
| **AR-7** | M8 field collection blocked by a missing column | Medium | `device_id` and `client_uuid` land now (structural enablers, E-06) |

---

## 12. Independent self-critique

Written against my own design, before anyone else reviews it.

**1. AR-2 is a genuine hole and I have not closed it.** ~~A credit note against
`INV/26-27/00001` reduces the balance. In the FIFO walk, does that credit note reduce
*that* invoice's outstanding figure, or does it behave like a payment and retire the
oldest document first?~~

> **CLOSED in v1.1.0 by §5A.** Targeted reduction was indeed right. **But writing the
> specification found something the critique had not:** a payment reversal treated as an
> ordinary positive entry would have created a *fresh, zero-day-old* debt and quietly
> laundered aged debt into new debt on every reversal — in a tool whose entire purpose is
> to show which debt is oldest. That produced the **annulling** class (§5A.3), which
> appears nowhere in v1.0.0.
>
> The lesson generalises: **"probably right" concealed a second, worse defect that only
> writing the algorithm out in full exposed.** The instruction to resolve AR-2 before
> implementation was correct, and stopping at "targeted reduction, obviously" would have
> shipped the reversal bug.

**2. "Derived FIFO" is doing more work in this document than it has earned.** M2's derived
stock is a `SUM` — one aggregate, obviously correct. FIFO application is an *algorithm*
with ordering, partial consumption and tie-breaking. Two documents on the same date need a
deterministic tie-break (I propose `entry_date`, then `id`) or the same data yields
different views on different days. **This is the least "obviously correct" derived quantity
in the system so far**, and calling it derivation borrows M2's credibility without having
M2's simplicity.

**3. D-6 (write-off in M6) is scope I am adding.** `00` §19.1 does not name it. My argument
— cheap, enum already exists — is exactly the argument that produces scope creep one
justified item at a time. M6 is 1.5 units, the smallest milestone since M3's original
scoping, and I would not object if the Product Architect cut it.

**4. D-7 asks to modify a verified milestone.** M5 was signed off eight hours ago. Moving
`_ImmutableDocument` to `core` is right on the merits, but "refactor last milestone while
building the next" has a poor track record, and the honest alternative is to accept one
import across a module boundary now and relocate at M10 hardening.

> **Ruled on in v1.1.0: deferred**, exactly as this paragraph proposed. `Payment` imports
> M5's `_ImmutableDocument` across the boundary; the relocation is **TD-24**, due at M10.
> Recorded because a self-critique that never changes an outcome is decoration.

**5. The audit-scope question has now been re-derived three times.** M2 D-3, M5 D-6, M6
D-5 — same conclusion, same reasoning, three separate deliberations. That is not
consistency, it is unamortised cost, and it will happen again at M7 unless `02A` §13.2 is
amended once.

**6. I have not designed the statement's opening balance.** `05` §9.6 specifies
`?date_from=&date_to=` returning "opening, entries, closing". The opening figure is
`SUM(amount) WHERE entry_date < date_from` — cheap, but it is a *second* aggregate with a
different filter, and I have not said whether it must reconcile exactly with the previous
period's closing under concurrent writes. It must. I should have said so in §7.

**7. Effort.** M6 is budgeted 1.5 units. One new table, one lock, one derived view. But M5
was budgeted 3.0 and consumed four verify cycles, two of them on things that were not M5.
**I have no basis for predicting cycles, and the M5 report says so.** I would not present
1.5 units as a schedule.

---

## 12A. Irreversible decisions — sign-off required

| # | Decision | Cost to reverse | Signed |
| --- | --- | :-: | :-: |
| **M6-1** | A payment is recorded against the **customer**, never an invoice (C-1) | **Severe** — allocation rows are additive; removing them is a migration of live financial history | ☐ |
| **M6-2** | `payment_number` is a **reference**, not a statutory series, allocated by `nextval` **before** the insert (D-4) | High — receipts already issued cannot be renumbered |  ☐ |
| **M6-3** | Reversal is a **compensating ledger entry**; the original is never edited | **Severe** — an editable payment makes every historical balance unprovable | ☐ |
| **M6-4** | `payment` is mutable in exactly four fields, trigger-enforced | High | ☐ |
| **M6-5** | **`client_uuid UNIQUE` on `payment` from the first migration** | **Severe** — a double-credited customer is the founding problem inverted | ☐ |
| **M6-6** | A credit note **reduces its own invoice**; payments settle FIFO (D-9, §5A) | High — a stored view would be wrong; a derived one is recomputed, but reports and disputes rest on it | ☐ |
| **M6-7** | A reversal or cancellation **annuls its target**; neither appears in the walk (§5A.3) | High — the alternative launders aged debt into fresh debt | ☐ |
| **M6-8** | Debits order by **`(entry_date, id)`** (§5A.6) | Medium — without the tie-break a statement is not reproducible | ☐ |
| **M6-9** | `device_id` on `payment` from the first migration (structural enabler, E-06) | Medium — M8 field collection would need a migration on a financial table | ☐ |
| **M6-10** | Write-off is a **ledger entry** with an **explicit amount**, owner-only, reason mandatory, audited, **no lock** (D-6, §6.2) | Medium | ☐ |
| **M6-11** | **One `OPENING` entry per customer**, enforced by a partial unique index (D-10) | High — a doubled opening balance at go-live corrupts every derived figure from day one, and the ledger is append-only | ☐ |

---

## 13. Implementation tasks

Seven, each independently verifiable and committable (ADR-0005 §6.2).
**Task 0 is removed — D-7 is deferred (TD-24).**

| # | Task | Gated by |
| --- | --- | --- |
| 1 | `receivables` module: `Payment` model reusing `billing._ImmutableDocument`, migration incl. **`payment_number_seq`**, column-aware trigger, layers contract, `Payment` registered in `SOURCE_DOCUMENT_REGISTRY` | C-3, M6-2, M6-4, §10 |
| 1b | `ledger` migration: **partial unique index**, one `OPENING` per customer | **M6-11**, D-10 |
| 2 | `record_payment` — `nextval` **then one INSERT**, `client_uuid` savepoint, ledger entry in the same transaction, `balance_after_amount` | M6-1, M6-2, M6-5, AR-4 |
| 3 | `reverse_payment` under `SELECT … FOR UPDATE`, compensating entry, audited | M6-3, §6.1, AR-3 |
| 4 | `write_off` — explicit amount, owner-only, reason mandatory, audited, **no lock** | M6-10, §6.2 |
| 5 | `load_opening_balance` through `record_entry`, **idempotent on conflict** | D-8, D-10 |
| 6 | **The §5A walk** — classify, annul, reduce, settle — plus the statement with opening/closing, and the §5A.7 invariant as a property test | **D-9**, M6-6, M6-7, M6-8, AR-5 |
| 7 | API, owner screens, boundary and adversarial suites | §9 |

### 13.1 Test obligations specific to §5A

| Must prove | Where |
| --- | --- |
| The §5A.7 invariant over a **randomised** sequence of all six entry types | Property test |
| Every row of §5A.9 (E-1 … E-13) | Table-driven |
| §5A.8 worked example reproduces exactly, to the paisa | Scenario test |
| A reversed payment leaves its invoices at their **original ages** | Regression — the defect §12.1 found |
| E-13 is unreachable: a credit note against an annulled invoice cannot exist | Adversarial |
| Three queries, not N+1, for a multi-customer position | Query-count assertion |
| **A payment is written in one statement** — no `UPDATE` reaches the trigger | Regression (D-4) |
| **Re-running the full opening-balance import is a no-op**, including after a partial failure | Idempotency (D-10) |
| Raw SQL cannot insert a second `OPENING` for a customer | Adversarial (M6-11) |
| Concurrent reversals of one payment produce **exactly one** compensating entry | Concurrency (§6.1) |

**Also due in M6, carried from M5:** TD-21 (reproducible build — highest-value debt),
TD-2/TD-18 (mypy blocking — **missed at M5**), TD-14 (`Product._has_history`, overdue since
M3), TD-23 (`billing/selectors.py` authorisation branches at 78%).

---

## 14. Sign-off

| # | Item | Party | Status |
| --- | --- | --- | :-: |
| 1 | **C-1 — no allocation in Edition 1** (§3). The most consequential item here | Product Architect | ☑ **Approved** |
| 2 | **C-2 — derived list, not bucket engine** | Product Architect | ☑ **Approved** |
| 3 | **C-3 — add `reversed_at` / `reversed_by_id`** | Product Architect | ☑ **Approved** |
| 4 | **AR-2 — FIFO behaviour for credit notes** | Product Architect | ☑ **Resolved — §5A / D-9** |
| 5 | D-4, D-5, D-8 | Product Architect | ☑ **Approved** |
| 6 | **D-6 — write-off in M6** | Product Architect | ☑ **Approved — in scope** |
| 7 | **D-7 — refactor M5 code** | Product Architect | ☑ **Deferred to hardening (TD-24)** |
| 8 | **M6-1 … M6-10 irreversible decisions** (§12A) | All | ☐ |
| 9 | **Amend `02` FR-REC-004/006/008 to v2.0**, and `02A` §13.2's audit list, once | Product Architect | ☐ |
| 10 | This document accepted | All | ☐ |

**Items 1–7 are settled.** Two remain: the irreversible-decision sign-off in §12A, and the
documentation corrections in item 9.

> Item 9 is the only one that is not a precondition for code. `02` will still say
> "allocatable — M, v1.0" until it is edited, and **the next person to read `02` cold will
> reach the wrong conclusion.** §3 records the supersession, but a design review is a poor
> substitute for correcting the requirement itself.

---

*No code has been written or authorised. No ADR is required. Task decomposition is in
`NEXT_TASK.md`; implementation begins when §12A and §14 item 10 are signed.*
