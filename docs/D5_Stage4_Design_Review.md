# D5 Stage 4 — Design and Decision Review

| | |
| --- | --- |
| Document | `D5_Stage4_Design_Review.md` |
| Version | **2.0.0** |
| Date | 2026-08-27 |
| Status | **DECISIONS FROZEN. BD-1, BD-3, BD-4, BD-5, FR-PUR-015 and Q5 are ruled and closed.** Design of record for Stage 4. No code, no migration, no schema change. Stages 1–3 are closed and untouched |
| Covers | **BD-1**, **BD-3**, **BD-4 / DR-10**, **BD-5**, the FR-PUR-015 reporting map, and **Q5 supplier payment idempotency** |
| Requirements | FR-PUR-004, FR-PUR-012, FR-PUR-014, FR-PUR-015 |
| Supersedes | Nothing. **Closes** `D5_Design_Review` §7 — every business decision it tabled is now resolved |
| Predecessor | `D5_Design_Review` v0.8.0 — design of record for Stages 1–3 |

### Version history

| Version | Date | Change |
| --- | --- | --- |
| **1.0.0** | 2026-08-27 | Initial design and decision review. Four recommendations tabled with five business questions (Q1…Q5) outstanding |
| **2.0.0** | 2026-08-27 | **Rulings applied. Decisions frozen.** BD-1 = Option A · BD-3 = V3 with all four dimensions fixed · BD-4 = FR-PUR-014 not in v1.0 · BD-5 = build the capability · FR-PUR-015 = received spend with the reconciliation invariant · **Q5 ruled: duplicate-payment protection is REQUIRED**, converting R-3 from an accepted risk into a design obligation on S4.3. Q1…Q4 closed. §8 implementation order frozen. **Major, not minor: the recommendations became binding, and Q5 and BD-5 both landed differently from the recommendation** — see §12 |

> **Verification baseline.** Stage 3 closed VERIFIED on 2026-08-27: 44 targeted tests, 988/988 full
> suite, 94.40% coverage, migrations clean, ruff clean, 3/3 import contracts kept, mypy clean.
> Every ruling below is written against **that** repository state and cites it.

> **Reading this document at v2.0.0.** The analysis in §§1–5 is retained **unchanged** as the
> record of what was weighed. Each section now opens with the ruling that was made. Where a ruling
> differs from the recommendation that preceded it, the difference is called out in place and
> collected in **§12**.

---

## 0. Method, and one thing this review refuses to do

Each decision below is argued from **three sources and no others**: the requirement text in `02` /
`02A`, the code as it exists at the Stage 3 baseline, and the rulings already recorded in
`D5_Design_Review`. Where a generic distribution-industry practice would point one way and this
repository points another, **the repository wins and the divergence is stated**.

That constraint is not decoration. `D5_Design_Review` §5.2 already had to reject one independent
review's Critical Defect #1 because it argued from *"A/P clerks frequently need to…"* in a system
that seeds four roles and has no A/P clerk. The same trap is live in every decision below, and
BD-1 is where it is most dangerous.

**Two decisions in this review are answered from the corpus rather than referred onward.** BD-4 is
one of them, and the reason is given in §3.1: the question as tabled (*"what threshold?"*)
presupposes an answer to a prior question that `02A` has already given.

---

## 1. BD-1 — Supplier payment allocation

> **The question, as tabled:** *Must a supplier payment be explicitly allocated by a user to
> specific outstanding receipt(s), or is deterministic oldest-outstanding-first settlement
> acceptable?*

### 1.1 Ruling — **FROZEN 2026-08-27**

> ## **BD-1 = Option A. Deterministic oldest-outstanding-first derived settlement.**
>
> **No allocation table and no allocation column in V1.**

**BD-1 is closed.** The recommendation was accepted **unconditionally** — the business confirmation
tabled at §1.6 was not made a precondition of the ruling. §1.6 is retained below as the question
whose *answer would reopen* this decision, not as a gate on starting work.

The architectural prerequisite at §1.5 stands and is sequenced as **S4.2**.

**What this ruling forbids, so that it cannot be softened by degrees:**

1. No `SupplierPaymentAllocation` table.
2. No allocation column on `SupplierPayment` — including a nullable `goods_receipt` FK.
3. No free-text "paid against" field standing in for one (alternative A′, §1.7).
4. No stored settled/unsettled flag on `GoodsReceipt`. Which receipts are open is a **view**,
   recomputed on every read, exactly as it is for customers.

### 1.2 What the existing receivables model actually does

This is the load-bearing evidence, and it is not an analogy — it is the same question, already
answered, in the mirror-image domain, with a tested mechanism behind the answer.

`backend/receivables/models.py`, module docstring, verbatim:

> *"A payment reduces what a customer owes. It does not pay an invoice (M6 §1). **There is no
> allocation table and no allocation column**: which invoices are consequently settled is derived
> FIFO at read time (`receivables.selectors`, M6 §5A) and never written down."*

`backend/receivables/selectors.py` implements that as a **pure walk** — `_walk()` touches no
database — classifying every ledger entry into three roles:

| Role | Entry | Effect in the walk |
| --- | --- | --- |
| **Annulling** | `ADJUSTMENT` pointing at an `INVOICE` or `PAYMENT` it offsets exactly | both members of the pair **leave the walk**, restoring settled invoices at their *original ages* |
| **Reducing** | `CREDIT_NOTE` targeting a specific invoice | reduces that invoice first, before any money is applied; the excess spills into the settling pool |
| **Settling** | `PAYMENT`, `WRITE_OFF` | applied **oldest-first** across open debits |

and holds itself to an invariant asserted over randomised sequences:

```
Σ outstanding.remaining − credit_on_account  ≡  settled_balance(customer, as_of)
```

### 1.3 Why the supplier case is the *easier* half of a question already answered

The supplier ledger built in Stage 3 (`ledger.SupplierLedgerEntry`) has five entry types.
Mapping them onto the three walk roles shows the payables walk is a **strict subset** of the
receivables walk in v1.0:

| Supplier entry type | Walk role | Reachable in v1.0? |
| --- | --- | --- |
| `GOODS_RECEIPT` | debit | **yes** — the only debit producer |
| `PAYMENT` | settling | **yes** (Stage 4) |
| `OPENING` | debit **or** credit | **yes** (BD-5, §4) |
| `ADJUSTMENT` | annulling — supplier payment reversal | **yes** (Stage 4, §1.5) |
| `DEBIT_NOTE` | **reducing** — targets a specific receipt | **no producer exists** |

`DEBIT_NOTE` is the payables analogue of `CREDIT_NOTE`, and **nothing in v1.0 can create one**:
`purchase_return` is Edition 2 (DV-8, untouched by D-PUR-6), and `04` T-32 states that *"posted
goods receipts are immutable; correction mechanisms are outside Stage 3 and require a separately
approved design."*

So the **targeted-reduce branch — the hardest and subtlest part of the receivables walk — is
unreachable on the supplier side.** If the harder case did not need an allocation table, the
strictly simpler case does not either. That is not an appeal to symmetry; it is an argument from
which of the two problems is larger.

### 1.4 The three arguments for Option B, and what happens to each

Option B is not a straw man. Each argument is answered on evidence, and the third is answered
only conditionally — which is why §1.6 exists.

**B-argument 1 — "an allocation record proves intent; a derived walk only proves order."**

True, and it is Option B's real strength. But an allocation record is a **stored derivation of
exactly the kind this project has ruled against three times**: no stored balance (N-03/E-01), no
cached stock on hand, no stored receipt variance (D-PUR-4). An allocation amount is derivable
from *(payment amount, entry ordering, outstanding amounts)*, and storing it creates a second
figure that can disagree with `SUM(amount)`. The project's own rule for that class of column is
not "weigh it case by case" — it is "do not".

**B-argument 2 — "back-dating silently rewrites history."**

Real, and **worse on the supplier side than the customer side.** Both walks order by
`(entry_date, id)`, and both take a caller-supplied date. A customer payment is collected in the
field and keyed the same day; a supplier payment is keyed from a bank statement days later, so a
back-dated supplier payment is the *likely* case, not the exotic one. Under Option A, inserting a
payment dated before an existing one **changes which receipts the earlier payment is reported as
having settled.**

This is a genuine cost of Option A and it is accepted here for one reason: **the balance never
changes.** `SUM(amount)` is order-independent, so the number the business actually acts on — what
we owe this supplier — is unaffected. What moves is the *presentation* of which document is open,
and that presentation is explicitly a view, recomputed on every read, in both ledgers. It is
recorded as **Risk R-2** (§9) rather than dismissed.

**B-argument 3 — "the owner will want to withhold payment on a disputed receipt."**

This is the argument that would carry Option B, and it fails on a fact about v1.0 rather than on
a judgement about businesses:

> **In v1.0 a dispute has no expression in the system at all.** There is no debit note, no
> purchase return, no GRN correction, no dispute flag. `GoodsReceipt` is immutable from the
> instant it exists.

An allocation table would therefore give the owner a screen on which to record an intent —
*"this payment settles GRN-14 and deliberately not GRN-9"* — that **no other part of the system
can act on, explain, or ever contradict.** The disputed receipt would still sit in the payables
balance at full value; the ledger would still say we owe it; only the allocation row would hint
that something was wrong, with no field to say what.

**Explicit allocation is only meaningful once the system can represent the reason for departing
from oldest-first. v1.0 cannot.** Build the reason first, then the allocation — not the reverse.

### 1.5 Architectural prerequisite — extract the walk, do not copy it

Option A needs a payables position walk: *which receipts are open, and how old.* Written naively
that is ~150 lines of `receivables/selectors.py` copied into `purchasing`, and the annulment
pairing logic is subtle enough that two copies **will** diverge.

**Recommendation: extract the pure algorithm into `ledger`, below both consumers.**

```
ledger/walk.py            ← pure, no ORM, no module above it
    ▲                ▲
    │                │
receivables.selectors   purchasing.selectors
  (customers)             (suppliers)
```

`ledger` sits at the `inventory | ledger` layer, beneath both `receivables` and `purchasing`, so
the import direction is legal under the existing contract and needs no change to
`pyproject.toml`. The walk operates on a list of *(entry_date, id, type, amount,
source_document_type, source_document_id)* tuples and is already pure — `_walk()` has no database
access today, which is what makes the extraction mechanical rather than a rewrite.

> **This must ship as its own isolated change, before any Stage 4 feature work, and it must not
> be bundled with `SupplierPayment`.** It touches verified M6 code whose randomised invariant test
> is one of the strongest guarantees in the repository. The sequence is: extract → re-run the
> existing customer invariant test unchanged → add the same randomised invariant for suppliers →
> `make verify` → only then build on it. Recorded as **Risk R-1** (§9).

Option A also requires **supplier payment reversal**, modelled exactly on
`receivables.services.reverse_payment`: a row lock on the payment, idempotent second call, and a
compensating `ADJUSTMENT` of the original amount pointing at the payment — which is precisely the
annulling pair the extracted walk already understands.

### 1.6 The question that would reopen this ruling — **no longer blocking**

> **Superseded by the ruling at §1.1.** BD-1 is frozen as Option A and Stage 4 does not wait on
> this. It is retained because it names the single circumstance under which Option A becomes the
> wrong answer, and whoever revisits this should ask it in exactly this form rather than
> re-deriving it.

One question, and it is not "do you want allocation?" — that answer is always yes in the
abstract. It is:

> **When you pay a supplier, do you ever deliberately pay a *later* delivery in full while leaving
> an *earlier* one unpaid — and if so, why?**

- **"No, I just pay down the account"** → Option A stands as recommended. Close BD-1.
- **"Yes, when a delivery was short, damaged or wrongly priced"** → the answer is **not** Option B.
  It is that v1.0 is missing a supplier debit note, and *that* is the requirement to write. BD-1
  then reopens **after** the dispute mechanism exists, not instead of it.

### 1.7 Alternatives considered and rejected

| | Considered | Rejected because |
| --- | --- | --- |
| **B** | `SupplierPaymentAllocation` (payment FK, goods_receipt FK, amount) | §1.4 — a stored derivation (N-03/E-01) recording an intent v1.0 cannot act on |
| **A′** | Option A plus a free-text "paid against" note on `SupplierPayment` | A fake allocation: unstructured, unqueryable, and it would be read as authoritative. The ledger `narration` already carries the owner's note onto the statement |
| **A″** | Option A now, allocation rows written retrospectively later | Historic payments have no recoverable intent, so the backfill is unsound. Going *forward* the addition is additive and remains available |
| **C** | Defer FR-PUR-012 to Edition 2 | FR-PUR-012 is `M`, v1.0. Deferring it would leave the supplier ledger able to accrue liability with no way to discharge it |

---

## 2. BD-3 — Sales velocity

> **FR-PUR-004** (`M`, v1.0): *"Purchase order creation MUST present current stock position and
> recent sales velocity for each product being ordered."*

### 2.1 Ruling — **FROZEN 2026-08-27**

> ## **BD-3 = V3 demand velocity, measured from `SalesOrderLine`.**
>
> | Dimension | **Ruled** |
> | --- | --- |
> | Basis | **V3 — demand, from `SalesOrderLine`** |
> | Trailing window | **90 days** |
> | Divisor | **actual available history when fewer than 90 days exist** |
> | Unit | **base units** |
> | Cancelled orders | **excluded** |
> | Returns | **excluded** |
> | Zero sales | **`0.00/day`** and **`— no history`** rendered **distinctly** |

**BD-3 is closed. All four open dimensions are fixed; nothing about FR-PUR-004 now awaits the
business.** `D5_Design_Review` D-PUR-5 is thereby discharged — the V3 recommendation it marked
*"BUSINESS CONFIRMATION REQUIRED"* is confirmed, and the four dimensions it left open are ruled.

The reasoning is retained below unchanged.

`D5_Design_Review` D-PUR-5 marked V3 as the recommendation pending confirmation. This review
**confirms it on new evidence from the code**, which the earlier document did not cite:

| | Measure | Source | Suppressed by a stockout? |
| --- | --- | --- | --- |
| V1 | Fulfilment velocity | `StockMovement` ISSUE via `DELIVERY` | **yes** |
| V2 | Revenue velocity | invoice lines | **yes** |
| **V3** | **Demand velocity** | **`SalesOrderLine`** | **no — see below** |

The decisive fact is that in this system **an order can be placed for stock that does not exist.**
`orders.services` performs a credit check and an active-product check and **no availability
check**; `inventory.services.issue_stock` states outright: *"Takes no lock and does not check
availability: negative on hand is permitted and reported (D-2, ADR-0006)."*

So unfilled demand **is** captured in `SalesOrderLine` and is **not** captured in V1 or V2. That
is what makes V3 measurable here rather than merely desirable — and reordering against V1 or V2
would mean reordering least aggressively at exactly the moment stock ran out.

> **Stated limit, not hidden.** V3 measures *recorded* demand. A salesman who knows an item is out
> of stock and therefore never keys the order suppresses V3 too. No measure available in this
> system captures that, and the screen should not imply otherwise.

### 2.2 The four dimensions — **ruled definitions**

**Trailing window — 90 days, with an honest divisor.**

```
velocity_per_day = Σ quantity over the window ÷ D
D = min(90, days since the earliest sales_order in the system), floor 1
```

- **90 rather than 30.** Reorder cycles in this trade are weekly to monthly; a 30-day window is a
  single cycle and is dominated by noise on slow movers, which are exactly the products where an
  over-order sits as capital for a year.
- **The divisor is the reason this is written as a formula and not a constant.** At go-live there
  are not 90 days of history. Dividing by a flat 90 would show a product selling 10/day for its
  first 5 days as `0.55/day` — an under-statement of ~18×, on the screen whose entire job is to
  size a purchase order. Capping the divisor at the data actually available removes that artefact.
- **The window is a constant in `reporting`, not `BusinessProfile` configuration.** `02A` §13.2
  demoted a configurable bucket engine to Edition 2, and `receivables.selectors` records the
  consequence: *"Display constants, not configuration (M6 C-2)… OI-4's boundaries live here as
  three integers."* The same treatment applies. One integer.
- The screen labels the basis when `D < 90` — *"based on 42 days"* — so a thin figure is never
  mistaken for a settled one.

**Units or packs — compute in base units, display both.**

`SalesOrderLine.quantity` is *always* base units (M3-2), with `pack_quantity` recording what the
user typed and `pack_size_snapshot` frozen alongside. `PurchaseOrderLine.quantity_ordered` is
likewise base units. So the arithmetic has exactly one correct unit and no conversion is needed.

Display base units, and append the pack equivalent when `product.pack_size > 1` — *"42.0/day
(3.5 cases)"* — because the owner orders in cases and would otherwise divide by hand on the
screen that exists to prevent hand arithmetic.

**Cancellations — excluded.**

A cancelled order is demand withdrawn, and reordering against it buys stock for a sale that will
not happen.

> **The known imprecision, stated:** `SalesOrder.cancelled_reason` is **free text**, not a coded
> reason (`orders/models.py:77`). So an order cancelled *because the item was out of stock* — which
> **is** real demand — is indistinguishable from one cancelled because the retailer changed their
> mind. Excluding both slightly under-states V3 in exactly the stockout case V3 exists to capture.
> Coding cancellation reasons would fix it and is an Edition-2 refinement, not a v1.0 change.

**Returns — excluded from the numerator.**

A return reverses *fulfilment*, not *demand*: the customer did ask for the goods. Netting returns
off velocity would mix a fulfilment fact into a demand measure and make the number mean neither.

The counter-argument — a chronically returned product should not be reordered at its demand rate —
is real, and it is **already served by a different report**: `reporting.selectors.returns_report`
(FR-RPT-010) groups credits by reason code and by customer. That is where a quality problem
belongs. Recorded as an alternative rather than dismissed.

**Zero sales — two distinct renderings, never blank.**

| Situation | Render | Why |
| --- | --- | --- |
| Product has history in the window, sold nothing | **`0.00/day`** | A fact, and the single most actionable number on a reorder screen |
| Product has no history in the window at all | **`— no history`** | Not the same claim. A new or newly-listed product must not read as a dead one |

Blank is refused for both: on a screen of numbers a blank cell reads as a rendering failure.

### 2.3 Where it lives, and what is not blocked

The velocity figure is a **read**, derived from `orders`, consumed by the purchase-order form.
`orders` and `purchasing` are **siblings** in the layer contract (`"orders | purchasing"`), and
siblings may not import each other — so `purchasing.selectors` cannot call `orders.selectors`.

**The correct home is `reporting`**, which sits above the whole domain, owns nothing, and already
reads from every layer beneath it. The purchase-order *view* composes the two reads; neither
domain module learns about the other. This is the same shape `webadmin` already uses to put a
customer balance beside an order.

> **The stock half of FR-PUR-004 is not blocked by BD-3 and never was.** Current stock position is
> one call to `inventory.selectors.on_hand_for()`. If velocity confirmation is delayed, ship the
> column-less screen — `D5_Design_Review` D-PUR-5 already rules this.

---

## 3. BD-4 / DR-10 — Purchase order approval

> **FR-PUR-014** (`S`, v1.0): *"Purchase orders exceeding a configurable value threshold SHOULD
> require `OWNER` approval before issue."*

### 3.1 Ruling — **FROZEN 2026-08-27**

> ## **BD-4 = FR-PUR-014 is NOT in v1.0.**
>
> 1. **No purchase-specific approval is built, under any circumstances.**
> 2. **DR-10 remains a future shared core capability.**
> 3. **DR-10 is not Stage 4 work**, in whole or in part.

**BD-4 is closed.** The recommendation was accepted in full, and the ruling adds one binding
consequence the recommendation only implied: **DR-10 is out of Stage 4's scope entirely.** No part
of the shared mechanism specified at §3.3 may be built during Stage 4 as groundwork, as a stub, or
as "the table only" — the same prohibition `D5_Design_Review` §6 placed on `issue_purchase_order`:
*"not a placeholder, not a stub, not a `TODO` branch."*

`purchasing.services.issue_purchase_order` therefore stays exactly as Stage 2 shipped it, and its
existing docstring — which already records why there is no approval call — needs no amendment.

§3.2 and §3.3 are retained as the record of why, and as the contract for whoever builds DR-10 later.

### 3.1.1 The question is answered by the corpus, and the answer is no

BD-4 was tabled as *"Is DR-10 in v1.0 at all? If so, the threshold value and who decides."* The
first half is **already decided**, in the document that governs edition membership:

`02A_Product_Editions.md` §5, **DV-9**, verbatim:

> | **DV-9** | **No approval workflow in Edition 1.** | DR-10; FR-ORD-020…027 | Acceptable only
> because the owner personally sees every order at this scale. | **Accept with one exception:**
> keep the credit-limit *check* (a warning and an owner override), since it is a conditional and
> an audit row, **not a workflow**. |

and `02A` §14 — the very amendment that returned D5 to v1.0 — closes the door explicitly:

> **"5. DV-9 is untouched.** *'No approval workflow in Edition 1'* remains accepted. FR-PUR-014
> (`S`) stays deferred pending the shared DR-10 approval contract. **This amendment reinstates
> purchasing, not approvals."**

`02` still lists FR-PUR-014 as v1.0 `S`. `02A` governs edition membership (D-PUR-6.3: *"`02A` is
where membership changes"*). **There is no conflict to resolve and nothing left for BD-4 to
decide** — except whether to *overturn* DV-9, which is a `02A` amendment requiring the Product
Architect and the business, not an engineering ruling.

> **Recommendation as tabled at v1.0.0** *(accepted in full — see the ruling at §3.1)*:
> FR-PUR-014 is not in v1.0; close BD-4 as *"already answered by DV-9"*.

### 3.2 Two further reasons, in case the business wishes to overturn DV-9 anyway

**Reason 1 — DR-10 has four consumers, and FR-PUR-014 is the least of them.**

| Requirement | Priority | Trigger |
| --- | :-: | --- |
| **FR-ORD-021** | **M** | *"An order breaching the credit limit MUST NOT be silently accepted or silently rejected; it MUST enter `PENDING_APPROVAL`"* |
| FR-ORD-022…027 | M | configurable *(trigger → approver role)*; single-level only; approver notification |
| FR-PRC-017 | M | manual discount above a threshold |
| FR-STK-024 | S | stock adjustment above a threshold |
| **FR-PUR-014** | **S** | **purchase order above a threshold** |

Building the shared mechanism for FR-PUR-014 alone would be building a **CORE subsystem for its
lowest-priority consumer**, while three `M` requirements — one of which, FR-ORD-021, is
currently unimplemented (`orders.services` implements WARN/BLOCK plus owner override, and
`SalesOrder.Status` has no `PENDING_APPROVAL` member) — continue to wait. If DR-10 is reinstated,
it is a **core milestone with all four consumers**, sequenced by `02A`, and D5 consumes it. It is
not Stage 4 work under any circumstances.

**Reason 2 — `PENDING` is degenerate with one privileged actor.**

The repository seeds four roles: `OWNER`, `SALESMAN`, `DELIVERY`, `RETAILER`. Only `OWNER` may
create, amend or issue a purchase order (`purchasing.services`, every entry point). FR-PUR-014
names `OWNER` as the *approver*. So the requester and the decider are **the same person**, and a
`PENDING` state would be entered and left by one actor.

That is not segregation of duties. It is a confirmation dialogue with a database row behind it —
and this system already has the right shape for that, chosen deliberately, in
`orders.services._apply_credit_policy`: the owner overrides their own credit-limit breach and the
act is recorded as a `CREDIT_OVERRIDE` audit row. DV-9's own words for it: *"a conditional and an
audit row — **not** a workflow engine."*

**Building `PENDING` under a single privileged actor also introduces a state with no independent
exit.** A purchase order parked in `PENDING` waits for the person who parked it.

### 3.3 The shared mechanism, specified — **NOT FOR v1.0**

Specified because it was asked for and because whoever builds it should not re-derive it. **Every
line below is Edition-2 scope and must be built once, in `core`, with all four DR-10 consumers in
view.** Nothing here may be read as authorising a purchase-specific approval; `D5_Design_Review`
D-PUR-2 forbids that outright and this review does not relax it.

**Ownership.** One shared `core.Approval` table, generic over documents — *one table, not one per
domain*. `purchasing` must never learn what an approval is beyond a single call and four possible
answers.

**Shape.**

| Column | Notes |
| --- | --- |
| `entity_type`, `entity_id` | polymorphic, validated through a registry, exactly as R-2 governs source documents today |
| `threshold_key`, `threshold_amount`, `amount` | the threshold **as it was at the moment of request**, snapshotted — a later change to `BusinessProfile` must not rewrite why something needed approval |
| `requested_by`, `requested_at` | |
| `decision` | `PENDING` · `APPROVED` · `REJECTED` |
| `decided_by`, `decided_at`, `reason` | `reason` mandatory on `REJECTED`, by CHECK constraint — the shape `ck_order_cancel_reason` already uses |

**State machine.** `PENDING → APPROVED` · `PENDING → REJECTED`. **Both terminal.** No re-open, no
re-request against a live approval; a rejected document that changes is a *new* request. Enforced
by a `_transition`-style guard, never by direct assignment — the rule `purchasing._transition`
already embodies.

**Request semantics.** A **precondition, never a post-issue flag.** A document that reached its
issued state before approval has already escaped the control.

**The four outcomes, each distinguishable:**

| Outcome | Caller sees | Document result |
| --- | --- | --- |
| `BELOW_THRESHOLD` | proceed | issued |
| `APPROVED` | proceed | issued |
| `PENDING` | a **distinct, non-exception** return value | unchanged; an approval request now exists |
| `REJECTED` | `ApprovalRejected` domain exception carrying the reason | unchanged |

> **`PENDING` must not be an exception.** *"Awaiting a decision"* is a normal outcome; modelling it
> as an error forces every caller into exceptions for control flow.

**Threshold configuration.** A typed column on `BusinessProfile`, looked up by key — never a
constant in a domain module, never a purchase-specific settings table, and never an `app_setting`
key/value row (`04` §2.2 rejects that EAV shape outright). Default `0` meaning **no approval
required**, so an unconfigured system behaves exactly as today. This is the same
default-is-the-decision posture D-PUR-4 took for `over_receipt_tolerance_percent`.

**Actor authorisation.** The decider must hold the approver role for the trigger, resolved through
`core.permissions.require_roles`. Whether a requester may decide their own request is
**business policy, not an engineering default** — and under §3.2's role analysis, forbidding it in
v1.0 would make every threshold breach permanently un-actionable.

**Atomicity.** The approval record and the state change it authorises commit or roll back together,
in the caller's transaction — the rule `record_audit` already follows.

**Audit.** Request and decision are **two** `record_audit` events, each carrying actor, entity and
reason, written in the same transaction. Two new `AuditLog.Action` members
(`APPROVAL_REQUESTED`, `APPROVAL_DECIDED`) — `Action` is a fixed `TextChoices` enum and extending
it is a migration.

**Rejection semantics.** Terminal. The document stays in its pre-issue state, the reason is stored
on the approval row and surfaced on the document screen. **No automatic cancellation** — deciding
what happens to a rejected purchase order is the owner's, and cascading a cancel would destroy a
draft they may want to amend and resubmit.

**Interaction with `PurchaseOrder.status` — and the one thing that must not happen.**

```
issue_purchase_order(actor, purchase_order)          @transaction.atomic
    guard: status is DRAFT and at least one line exists
    │
    ├── decision = core.services.request_approval(   ← THE ONLY CALL SITE
    │       actor=actor, entity_type="purchase_order", entity_id=po.pk,
    │       threshold_key="purchase_approval_threshold", amount=po.total_amount)
    │
    ├── BELOW_THRESHOLD → continue
    ├── APPROVED        → continue
    ├── PENDING         → return po, still DRAFT. Not an exception
    └── REJECTED        → raise ApprovalRejected. Still DRAFT
    │
    _transition(DRAFT → ISSUED); set issued_at / issued_by
    record_audit(Action.ISSUE)
```

> **No `PENDING_APPROVAL` member is added to `PurchaseOrder.Status`.** The approval state lives on
> the approval record; the purchase order stays `DRAFT` until it is genuinely issued. Adding a
> status would put the same fact in two places and force `ALLOWED_TRANSITIONS` — *"the lifecycle,
> and the whole of it"* — to encode a concern that is not the purchase order's.

The gate sits **inside** the atomic block and **before** the transition, so a pending or rejected
order changes no status and the approval record rolls back with whatever it refused. `po_number`
is unaffected either way: it is allocated at creation (D-PUR-8), so an approval outcome can never
consume or waste one.

**Cost if reinstated:** one `core` model, one migration, one service, two `AuditLog.Action`
members, one `BusinessProfile` column per trigger, one decision screen, and — the real cost —
retrofitting FR-ORD-021 onto `SalesOrder`, which today has no `PENDING_APPROVAL` status and a
credit path that resolves synchronously.

---

## 4. BD-5 — Supplier opening balances

> **Does the distributor carry existing supplier payables into the system at go-live, as customer
> opening balances were carried (M6-11)?**

### 4.1 Ruling — **FROZEN 2026-08-27**

> ## **BD-5 = build the supplier opening-balance capability in V1.**
>
> | Property | **Ruled** |
> | --- | --- |
> | Authorisation | **owner only** |
> | Cardinality | **one `OPENING` entry per supplier** |
> | Mutability | **immutable** |
> | Balance | **derived, never stored** |
> | Negative amount | **allowed** — an advance paid is a real opening position |
> | Zero amount | **rejected** |
> | Entry date | **caller-supplied** |
>
> **Actual opening values are business / go-live data. Engineering does not invent them.**

**BD-5 is closed, and the ruling differs from the recommendation in one respect that matters.**

The recommendation made the *capability* conditional on Q2 — *"if the answer is 'start at zero',
`load_supplier_opening_balance` is not built at all."* **The ruling separates the two questions and
builds the capability unconditionally.** That is the better split, and the reason is worth stating:
whether the distributor has pre-existing payables is a **data** question answered on go-live day,
while whether the system can accept an opening position is a **capability** question answered now.
Deciding the second from the first would mean discovering on go-live morning that the answer was
"yes" and needing a migration against a live ledger — the precise retrofit `D5_Design_Review` §7
raised BD-5 to avoid.

**The consequence for implementation, stated so it cannot be misread:**

- **S4.1 builds the service and the screen.** It ships whether or not a single opening balance is
  ever entered.
- **No opening value is seeded, fixtured into production, migrated, or inferred.** Tests construct
  their own amounts, as every other test does; nothing in `migrations/` writes an opening balance.
  A data migration could not name an actor, and an opening balance with no author has no provenance
  (§4.2).
- **A supplier with no `OPENING` entry is correct and complete**, not incomplete. `supplier_balance`
  already returns `0.00` for a supplier with no entries at all — R-1's trap, in its scalar form,
  and already tested.

Everything below was specified before the ruling and stands unchanged.

**Stage 3 already built the hard half of this**, and this recommendation is largely a statement of
what is already true in the schema rather than a request for new structure:

| BD-5 requirement | Status at the Stage 3 baseline |
| --- | --- |
| One opening balance per supplier | **Already enforced** — `uq_sle_one_opening_per_supplier`, partial unique index on `entry_type = 'OPENING'` |
| An opening position may be a **credit** (advance paid) | **Already permitted** — `ck_sle_sign` deliberately leaves `OPENING` unsigned; `_SUPPLIER_SIGN_RULES` omits it |
| Immutability | **Already enforced** — `save()`, `delete()`, `QuerySet.update`, `QuerySet.delete` |
| Balance is derived | **Already true** — `supplier_balance()` is `SUM(amount)`; there is no `outstanding_balance` column |

What Stage 4 adds is **one service function** and its screen. No model change, no constraint, no
migration to `supplier_ledger_entry`.

### 4.2 The specification

**Entry path.** `purchasing.services.load_supplier_opening_balance(*, actor, supplier, amount,
entry_date=None)` — modelled line for line on the customer version, which is the most financially
sensitive write the system performs and is therefore worth copying exactly rather than improving.

**Who may create one.** `require_roles(actor, Role.OWNER)`. Not the go-live engineer, not a
management command with no actor: `created_by` must name a person, because the audit row is the
only provenance an opening balance has.

**Idempotency — the property that matters most.** The deterministic identifier is the supplier
itself. A re-run returns the existing entry rather than raising, so a partial import that failed
halfway can simply be re-run:

1. check for an existing `OPENING` entry → return it if found;
2. write inside a **savepoint**, because two concurrent import runs both pass step 1;
3. on `IntegrityError`, re-read and return the winner.

> The database is the guarantee, not the pre-check. That is the exact structure of
> `load_opening_balance`, and the comment there says so.

**One divergence from the customer version, and it is deliberate.** `load_opening_balance` rejects
`amount <= 0` — *"a customer who owes nothing needs no entry."* The supplier version must accept a
**negative** amount, because an advance paid to a supplier before go-live is a real opening
position that `ck_sle_sign` already permits. It must still reject **zero**, for the customer
version's reason and because `ck_sle_amount_non_zero` would refuse it anyway.

**Audit and provenance.**

- `narration`: `"Opening balance carried at go-live"` — written once, and it is what the supplier
  statement shows.
- `created_by`: the owner.
- **One `record_audit` at the service level**, `entity_type="supplier_ledger_entry"`.

> **This is the single sanctioned exception to R-3, and it is worth stating precisely so it is not
> read as a contradiction.** R-3 says `record_entry` writes no audit row — and it does not. What
> the customer version audits is **the caller's own act**: *"the owner loaded an opening balance"*,
> which is a business event with no other record. `create_goods_receipt` follows the same rule from
> the other side: it audits the receipt, not the ledger entry the receipt caused. The supplier
> version must match the customer version exactly.

**Migration and go-live implications.**

- **No data migration.** This is a service call driven by the owner from a screen — the same shape
  as the customer import, and for the same reason: a Django data migration cannot name an actor, so
  the audit row would have no author.
- **Ordering at go-live:** suppliers (FR-PUR-001) → opening balances → live trading. An opening
  balance is refused for a supplier that does not exist, which is correct.
- **Dating — one improvement over the customer side, at zero cost.** The service already takes
  `entry_date`. Recommend the screen **allows a date earlier than go-live**, defaulted to go-live
  but editable. Under BD-1 = Option A the walk ages every open item from `entry_date`, so an
  opening balance dated at go-live makes every pre-existing payable appear zero days old and
  understates ageing on day one. The customer side accepted that; there is no reason to inherit it.
- **Deliberately not built:** per-receipt opening detail. An opening balance is **one number per
  supplier**. If the owner wants ageing of pre-go-live payables, that means keying historic goods
  receipts, which v1.0 does not support and should not — it would create `StockMovement` rows for
  stock that arrived before the system existed.

### 4.3 The go-live data question — **no longer a code question**

> **Superseded by the ruling at §4.1.** The capability is built regardless. What remains is a
> go-live **data** decision, taken by the business on go-live day, with no engineering dependency.

> **At go-live, do you owe money to any supplier — and do you want that carried in, or do you want
> the supplier ledger to start at zero and run alongside your existing records until it clears?**

Starting at zero remains a legitimate answer, and it is cheaper: no import, no reconciliation, and
every figure in the system is one the system itself produced. It costs an incomplete payables
position for the first payment cycle. **Under the ruling, that answer costs no code either way** —
it decides only whether the screen is used, not whether it exists.

---

## 5. FR-PUR-015 — Reporting

> **FR-PUR-015** (`M`, v1.0): *"The system MUST report purchase order status, receipt variance and
> supplier outstanding balances."*

### 5.0 Ruling — **FROZEN 2026-08-27**

> ## **FR-PUR-015 reports derive entirely from authoritative procurement and ledger facts.**
>
> 1. **No second source of truth.** No new table, no new column, no cached aggregate.
> 2. **Purchase spend = RECEIVED spend, not ordered commitment.**
> 3. **The reconciliation invariant is preserved exactly**, and asserted:
>    `Σ goods_receipt.total_amount ≡ Σ supplier_ledger_entry.amount where entry_type = 'GOODS_RECEIPT'`, over the same period.
> 4. **The free-goods / zero-value receipt case must be tested**, explicitly, as part of that
>    invariant.

**FR-PUR-015 is closed and Q4 is answered: received.** The invariant at (3) is not a documentation
note — it is a required **adversarial** test, holding the same role for procurement that
`Σ outstanding.remaining − credit_on_account ≡ settled_balance` holds for receivables.

Point (4) is the ruling being deliberately more careful than the recommendation. A zero-value
receipt contributes zero to **both** sides, so the invariant holds — but it holds for a reason
(`create_goods_receipt` skips the ledger write when `total_amount == 0`, because
`ck_sle_amount_non_zero` refuses a zero entry) that a future change could remove without any test
noticing. **Testing the case that passes trivially today is what stops it failing silently later.**

### 5.1 The governing constraint

Every report below is a `ReportTable` over facts **already written by Stages 1–3**. No new table,
no new column, no cached aggregate. `reporting` sits at the top of the domain and owns nothing —
no models, no services, no migrations — and a structural test already asserts it imports no
`*.services` and no `*.models`. Procurement reporting must not be the thing that breaks that.

### 5.2 The map

| # | Report | Derived entirely from | New fact needed? |
| :-: | --- | --- | :-: |
| 1 | **Purchase order status** (pipeline by status, count and value) | `purchase_order.status`, `total_amount`, `order_date` | **no** |
| 2 | **Receipt variance** | `purchase_order_line.quantity_ordered − Σ goods_receipt_line.quantity_received` — the expression `purchasing.selectors.outstanding_lines` already computes | **no** |
| 3 | **Supplier outstanding balances** | `SUM(supplier_ledger_entry.amount)` — `ledger.selectors.supplier_balance` already computes | **no** |
| 4 | **Purchase spend** by period / supplier / product | `goods_receipt` + `goods_receipt_line` | **no** — but see §5.3 |
| 5 | **Received quantities** by product / supplier | `goods_receipt_line` joined to the `purchase_order_line` snapshots | **no** |
| 6 | **Supplier ageing** (open items by bucket) | the payables walk | **depends on BD-1** — §1.5 |
| 7 | **Supplier performance** (fill rate, on-time) | ordered vs received; `expected_date` vs `receipt_date` | **no**, with a caveat — §5.4 |

Reports 1–3 are the literal text of FR-PUR-015. Reports 4–7 are the *"what else falls out for
free"* the brief asked for; 4 and 5 are near-free, 6 is gated on BD-1, and 7 carries a data-quality
caveat that must be shown on the report itself.

### 5.3 The one definition that must be pinned before anything is built

> **"Purchase spend" must be defined as goods RECEIVED, not goods ORDERED.**

`SUM(purchase_order.total_amount)` counts **intentions** — including drafts never issued, orders
cancelled, and orders short-delivered at full ordered value. `SUM(goods_receipt.total_amount)`
counts what arrived and is owed for.

The decisive property is that the received definition **reconciles exactly** with a figure the
system already holds:

```
Σ goods_receipt.total_amount over a period
    ≡  Σ supplier_ledger_entry.amount  where entry_type = 'GOODS_RECEIPT'  over that period
```

That identity is the whole anti-second-source-of-truth guarantee for procurement reporting, it is
true by construction of `create_goods_receipt`, and it **must be asserted as an adversarial test**
alongside the reports — the same role `Σ outstanding.remaining − credit_on_account ≡
settled_balance` plays for receivables.

> **Zero-value receipts are a real case and must not break the identity.** `create_goods_receipt`
> skips the ledger entry when `total_amount == 0` (free goods; `ck_sle_amount_non_zero` refuses a
> zero entry). Both sides of the identity contribute zero, so it holds — but the test must include
> that case explicitly, or a later change will break it invisibly.

If the owner wants committed-but-not-yet-received value, that is a **second, separately titled
report** — *"Purchase commitments"* — never the same column under the same name. `ReportTable`
carries its `definition` into the CSV precisely so a figure cannot become folklore once emailed.

### 5.4 Caveats each report must carry

- **Supplier performance / on-time.** `PurchaseOrder.expected_date` is **nullable** and the form
  does not require it. Orders with no expected date have no on-time answer and must appear in an
  explicit *"no expected date"* row that is always rendered and never filtered out — the treatment
  `returns_report` already gives to credits with no reason code (`UNCATEGORISED`). A percentage
  computed over a silently reduced denominator is wrong in a direction the reader cannot see.
- **Fill rate under an over-receipt.** With `over_receipt_tolerance_percent > 0` a line can be
  received *above* ordered, so a naive `received ÷ ordered` exceeds 100%. Report it as it is —
  do not clamp. `inventory` already takes this posture on negative stock (D-2, ADR-0006), and a
  clamped 100% hides the over-shipper the report exists to find.
- **Supplier ageing.** Reuse `AGING_BUCKET_DAYS = (30, 60, 90)` from `receivables.selectors`
  rather than declaring a second set of integers. Two ageing reports with different buckets is a
  support call.

### 5.5 TD-29 is live here, and this is the scenario it predicted

> **TD-29:** *"Nothing asserts a newly added report is wired into `REPORT_MENU`, the API router
> and the CSV path. The eighth report will be added by someone who forgets one of the three."*

There are **seven** reports today. FR-PUR-015 adds three to seven more. This is not a hypothetical
eighth report — it is three-to-seven of them, added at once, by one person.

**Recommendation: close TD-29 as part of Stage 4, before the first procurement report is added.**
One structural test that enumerates `REPORT_MENU`, the `webadmin` URL names and the API router and
asserts the three sets agree. Written first, it protects every report added after it; written
after, it documents whatever was already forgotten.

---

## 5A. Q5 — Supplier payment duplicate protection

### 5A.1 Ruling — **FROZEN 2026-08-27**

> ## **Supplier payments MUST have duplicate-payment protection.**
>
> 1. **Do not copy the mobile `client_uuid` mechanism blindly.**
> 2. **Design a server-side idempotency identity appropriate for web-admin financial submission.**
> 3. **The design is due at S4.3. It is not designed here and it is not implemented yet.**

**This is the one place the ruling went further than the recommendation, and it went the right
way.** v1.0.0 recorded duplicate supplier payments as **R-3, an accepted risk** mitigated by a
confirm screen. The ruling rejects that: a duplicate supplier payment is a **financial** error in
a ledger that is append-only and has no correction mechanism, and the confirm screen is the same
mitigation `D5_Design_Review` D-PUR-4 already conceded is *"asymmetric"* and incomplete for
duplicate goods receipts. R-3 is reclassified in §9 from an accepted risk to a **design
obligation**.

### 5A.2 Why "do not copy `client_uuid` blindly" is the correct instruction

`receivables.Payment.client_uuid` exists for a scenario named in M6-5 and quoted in the model
itself:

> *"**the most important constraint in this milestone.** A salesman on a weak connection retrying
> a collection is the exact scenario that double-credits a customer, and 'who owes what' is the
> client's founding problem."*

That mechanism solves **client-generated retry over an unreliable link**. The client mints a UUID,
holds it across retries, and the unique index makes the second arrival a no-op. It works because
**the client persists the identity between attempts.**

A supplier payment has none of those properties:

| | Customer collection | Supplier payment |
| --- | --- | --- |
| Origin | Field app, offline-capable | Web admin, online |
| Actor | Salesman | Owner |
| Duplicate cause | **Network retry** — same intent, resent | **Human re-submission** — double-click, browser back, refreshed POST, second tab |
| Identity available | Client mints and persists a UUID | **Nothing is persisted between the two submissions** |

`D5_Design_Review` §2.1 declined `client_uuid` for D5 on sound reasoning — *no offline surface
originates a purchase* — and that reasoning is still correct. **It just does not follow that no
protection is needed**, because the *cause* of duplication is different, not absent. Bolting
`client_uuid` onto a web form would produce a field the browser regenerates on every render, which
is a unique index that never collides: protection in name only, and worse than none because it
would look solved.

### 5A.3 What the S4.3 design must satisfy — acceptance criteria, not a mechanism

Recorded now so the S4.3 design is judged against a fixed bar rather than an improvised one. **No
mechanism is selected here.**

1. **Server-side identity.** The distinguishing value must be established by the server, or
   derived from data the server already holds — never trusted from a field the client is free to
   regenerate.
2. **It must survive the actual duplicate causes**: double-click, browser back-then-resubmit, page
   refresh on a POST result, and a second tab.
3. **It must not refuse a legitimate second payment.** Two genuine payments to the same supplier,
   for the same amount, on the same day, are ordinary — a distributor paying two invoices in one
   morning. **A naive natural key over (supplier, amount, date) is therefore disqualified**, and
   this is the criterion most likely to be failed by an otherwise plausible design.
4. **Refusal must be a distinguishable, non-destructive outcome.** The second submission returns
   the *first* payment — idempotent, as `load_opening_balance` and `reverse_payment` both are —
   rather than raising an error the owner might resolve by trying again.
5. **The guarantee must be in the database, not only in a service check.** Two concurrent
   submissions both pass any pre-check; a unique index or equivalent decides.
6. **It must survive an unclean exit.** A duplicate arriving after the first request's connection
   dropped is precisely the case a purely in-request guard misses.
7. **It must not create a second source of truth** (N-03 / E-01) and must not weaken
   `SupplierPayment`'s immutability.
8. **It must be recorded as a decision** with its rejected alternatives, in the same form as
   D-PUR-1…D-PUR-10.

> **Scope discipline.** This obligation is scoped to `SupplierPayment` alone. It is **not** licence
> to retrofit idempotency onto `GoodsReceipt` — D-PUR-4 examined that, ruled *"no idempotency
> mechanism is added in Stage 3"*, and recorded the residual. Reopening it needs its own ruling.

---

## 6. Requirement mapping

| Requirement | Pri | Decision it depended on | **Status — all frozen 2026-08-27** | Stage |
| --- | :-: | --- | --- | :-: |
| **FR-PUR-004** Velocity | M | **BD-3** | **CLOSED** — V3, 90-day window, available-history divisor, base units, cancellations and returns excluded, two distinct zero renderings. **Nothing outstanding** | S4.5 |
| **FR-PUR-012** Supplier payment | M | **BD-1**, **Q5** | **CLOSED** — Option A, unconditional. Carries the **Q5 idempotency design obligation** (§5A) | S4.3 |
| **FR-PUR-014** PO approval | S | **BD-4 / DR-10** | **CLOSED — not in v1.0.** No purchase-specific approval. DR-10 is future shared core and **not Stage 4 work** | — |
| **FR-PUR-015** Reporting | M | **BD-1** (report 6 only), **Q4** | **CLOSED** — received spend, reconciliation invariant asserted, zero-value case tested | S4.4 |
| **BD-5** Opening balances | — | **BD-5** | **CLOSED** — capability built **unconditionally**; actual values are go-live data | S4.1 |

> **`D5_Design_Review` §7 is now fully discharged.** BD-2 closed 2026-08-27 (D-PUR-4, Option C);
> BD-1, BD-3, BD-4 and BD-5 close here. No business decision tabled by the D5 design remains open.

**Already closed, unchanged by this review:** FR-PUR-001, 002 (Stage 1) · FR-PUR-003, 005
(Stage 2) · FR-PUR-006, 007, 008, 009, 010, 011, 013 (Stage 3).

---

## 7. Exact remaining dependencies

**Blocking, business — NONE. All five questions are resolved.**

| # | Question | Disposition |
| :-: | --- | --- |
| **Q1** | Deliberate out-of-order payment? (§1.6) | **Closed.** BD-1 frozen as Option A unconditionally. Q1 is retained only as the trigger that would reopen it |
| **Q2** | Pre-existing supplier payables at go-live? (§4.3) | **Closed as a code question.** The capability is built regardless; the value is go-live **data** |
| **Q3** | Velocity window? (§2.2) | **Closed.** 90 days, with the available-history divisor |
| **Q4** | Spend = received or ordered? (§5.3) | **Closed. Received**, with the reconciliation invariant asserted |
| **Q5** | Supplier payment duplicate protection? (§5A) | **Ruled: REQUIRED.** Converted from a business question into an **engineering design obligation on S4.3** |

**Blocking, engineering — three prerequisites, none of them a feature:**

| # | Item | Blocks | Note |
| :-: | --- | --- | --- |
| **E1** | Extract the FIFO walk into `ledger` (§1.5) | report 6, supplier ageing | Isolated change, own `make verify`. **Confirmed required** — BD-1 = A |
| **E2** | Close TD-29 (§5.5) | nothing, but must precede report 1 | One structural test |
| **E3** | **Design the supplier payment idempotency identity (§5A.3)** | **S4.3 implementation** | **New at v2.0.0.** Design first, against the eight criteria, then implement |

**Not blocking anything, and explicitly out of Stage 4** — the ruling at §3.1 makes the first item
binding rather than merely unscheduled: **DR-10 in whole or in part** · FR-ORD-021…027 ·
FR-PRC-017 · FR-STK-024 · supplier debit notes · `purchase_return` (Edition 2, DV-8) · GRN
correction · GRN idempotency (§5A.3, scope discipline).

---

## 8. Stage 4 implementation order — **FROZEN 2026-08-27**

Ruled as proposed. Ordered by dependency and by blast radius, smallest and most isolated first.
**One logically complete milestone at a time; each compiles, runs, and ships with its own
verification.**

| Step | Scope | Depends on | Why here |
| :-: | --- | --- | --- |
| **S4.0** | **TD-29 contract** — one structural test asserting `REPORT_MENU`, the URL names and the API router agree | — | Costs an hour. Written *before* three-to-seven new reports, it protects all of them |
| **S4.1** | **Supplier opening balance** — `load_supplier_opening_balance` + screen | — | Smallest real change; no model, no migration. Unblocks go-live data entry, which has the longest lead time of anything here |
| **S4.2** | **Isolated FIFO-walk extraction** into `ledger/walk.py`, **preserving the customer invariant**; then add the supplier invariant | — | **Refactor only. No feature.** Touches verified M6 code and must not share a commit with anything that could mask a regression |
| **S4.3** | **Supplier payment + reversal + idempotency** — `SupplierPayment`, its sequence, `record_supplier_payment`, `reverse_supplier_payment`, the supplier position selector, and the **§5A.3 idempotency identity** | S4.2 | The largest step. **Reversal and idempotency both ship *with* the payment, never after** — an un-reversible or un-protected financial document is a defect from its first row |
| **S4.4** | **Procurement reporting** — reports 1–5 and 7, then 6 | S4.3, S4.0 | Reports 1–3 are the literal FR-PUR-015 text |
| **S4.5** | **Demand velocity** — FR-PUR-004, stock column and velocity column together | — | Independent of everything above. **BD-3 is frozen, so both halves ship together**; the D-PUR-5 fallback of shipping the screen without the column is no longer needed |

> **Every step is unblocked.** With BD-1, BD-3, BD-4, BD-5, Q4 and Q5 all ruled, no step in this
> sequence waits on a business answer. **S4.3 waits on its own design (E3), not on the business.**

---

## 9. Risks

| # | Risk | Severity | Mitigation |
| :-: | --- | :-: | --- |
| **R-1** | **Extracting the walk (S4.2) regresses verified M6 receivables logic.** The annulment pairing is subtle — one annuller claims one target, and the pair must offset — and a silent break would corrupt the outstanding position, the ageing report and the dashboard | **High** | Isolated change, no feature in the same commit. The existing randomised invariant test runs **unchanged** against the extracted walk; the supplier invariant is added only after it passes. If extraction proves harder than expected, the fallback is two implementations plus a test asserting they agree on identical input — worse, but bounded |
| **R-2** | **Back-dated supplier payments reorder history** under Option A, changing which receipts a *previous* payment is reported as settling (§1.4) | Medium | Accepted, and recorded rather than hidden. The **balance is unaffected** — `SUM` is order-independent. The supplier statement shows entries in date order, so the reordering is visible rather than silent |
| **R-3** | ~~**Duplicate supplier payment**, mitigated only by a confirm screen~~ **RETIRED at v2.0.0.** Q5 ruled that duplicate protection is **required**, so this is no longer a risk being carried — it is **design obligation E3**, specified at §5A.3 and due in S4.3. It is listed here only so the transition is traceable | — | Superseded. See §5A |
| **R-4** | **TD-29 bites during S4.4** — three-to-seven reports added at once, one wired to the menu but not the CSV | Medium | S4.0 sequenced first, deliberately |
| **R-5** | **Supplier performance reports mislead** because `expected_date` is nullable and often blank | Low-Medium | Explicit *"no expected date"* row, always rendered, never filtered (§5.4) |
| **R-6** | **Coverage gate.** Stage 4 adds report selectors and screens; the gate is 80% and the repository sits at 94.40% | Low | Report selectors are highly testable. `webadmin/purchasing_views.py` is already the weakest file at 85% — Stage 4 should raise it, not dilute it |
| **R-7** | **Option A proves wrong after go-live** and explicit allocation is needed | Low | Adding allocation later is **additive going forward**. Historic payments cannot be back-allocated — intent is not recoverable — so the migration would carry a stated cut-over date. Recorded so the cost is known now, not discovered later |
| **R-8** | **New at v2.0.0 — the idempotency design refuses a legitimate payment.** The failure mode of a duplicate guard is not "misses a duplicate"; it is **blocking a real second payment** to the same supplier, for the same amount, on the same day. A distributor settling two invoices in one morning is ordinary, and a guard that refuses the second one is a worse defect than the duplicate it prevents, because the owner cannot work around it | **Medium** | Criterion 3 of §5A.3 states it as a disqualifier, so a design that fails it fails review rather than fails in production. The S4.3 test suite must contain the **two-legitimate-identical-payments** case as a *positive* test — proving the guard permits it — not only duplicate-rejection cases |
| **R-9** | **New at v2.0.0 — S4.3 grew.** It now carries the payment, the reversal, the position selector *and* the idempotency identity. That is the largest step in Stage 4 by some margin, and the step where "one logically complete milestone" is most at risk of becoming three half-milestones | Medium | The **design** (E3) completes and is ruled *before* implementation begins, so S4.3 starts with a settled mechanism rather than discovering one mid-build. If S4.3 still proves too large, split on the **document/derivation** seam — payment + reversal + idempotency first, position selector second — never on the idempotency seam, which would ship a financial writer without its guard |

---

## 10. Requirement ambiguity — **NONE OUTSTANDING**

All five questions raised at v1.0.0 are resolved. **No requirement ambiguity blocks Stage 4.**

| # | Question | Ruling |
| :-: | --- | --- |
| **Q1** | Deliberate out-of-order supplier payment? | **Closed.** BD-1 = Option A, unconditional. Retained at §1.6 as the trigger that would reopen it — a *"yes"* would call for a **supplier debit note**, not an allocation table |
| **Q2** | Pre-existing supplier payables at go-live? | **Closed as a code question.** Capability built unconditionally; the value is go-live data the business supplies |
| **Q3** | Velocity window? | **Closed.** 90 days, divisor = available history when shorter |
| **Q4** | Spend = received or ordered? | **Closed. Received**, with the reconciliation invariant asserted and the zero-value case tested |
| **Q5** | Supplier payment duplicate protection? | **Ruled REQUIRED.** Now engineering obligation E3 (§5A.3), not a business question |

### 10.1 What could still reopen a frozen decision

Recorded so that reopening is a deliberate act with a named trigger, rather than drift:

| Decision | Reopens only if |
| --- | --- |
| **BD-1** | A supplier **debit note / dispute mechanism** is introduced, giving the system something for an allocation to point at (§1.6) |
| **BD-3** | The owner reports the velocity figure is systematically wrong for how they reorder — a window change is one integer; a **basis** change is a new review |
| **BD-4** | `02A` is amended to overturn **DV-9**. That is a Product Architect + business act, and it reinstates **all four** DR-10 consumers, not FR-PUR-014 alone |
| **BD-5** | Nothing. The capability is built; usage is a data decision |
| **FR-PUR-015** | A *"purchase commitments"* report is requested — which is an **addition**, not a change to the spend definition |

---

## 11. Rulings that differed from the recommendation

Two, and both tightened the design rather than relaxing it. Recorded in one place because a review
whose recommendations were all simply rubber-stamped would not have been worth commissioning.

| # | Recommendation at v1.0.0 | Ruling at v2.0.0 | Why the ruling is better |
| :-: | --- | --- | --- |
| **1** | **BD-5** capability conditional on Q2 — *"if the answer is 'start at zero', `load_supplier_opening_balance` is not built at all"* | **Build the capability unconditionally.** Actual values are go-live data | Separates a **capability** question, answerable now, from a **data** question answered on go-live day. The recommendation risked discovering on go-live morning that the answer was "yes" and needing a migration against a live ledger — the exact retrofit BD-5 was raised to avoid |
| **2** | **Q5** duplicate supplier payment carried as **R-3, an accepted risk**, mitigated by a confirm screen | **Duplicate protection is REQUIRED.** Design a server-side idempotency identity in S4.3 | A confirm screen is the mitigation D-PUR-4 already conceded is *"asymmetric"* for goods receipts. A duplicate **payment** lands in an append-only ledger with no correction mechanism, so the residual is not comparable. The instruction *"do not copy `client_uuid` blindly"* is also correct: the mobile mechanism solves **network retry**, and the web-admin failure is **human re-submission** (§5A.2) |

---

## 12. Sign-off — **COMPLETE 2026-08-27**

| # | Item | Ruling | ☑ |
| :-: | --- | --- | :-: |
| 1 | §1 **BD-1** | **Option A** — deterministic oldest-outstanding-first derived settlement; no allocation table or column in V1 | ☑ |
| 2 | §2 **BD-3** | **V3** from `SalesOrderLine`; 90-day window; available-history divisor; base units; cancellations and returns excluded; `0.00/day` vs `— no history` distinct | ☑ |
| 3 | §3 **BD-4** | **FR-PUR-014 not in V1.** No purchase-specific approval. DR-10 is future shared core and **not Stage 4 work** | ☑ |
| 4 | §4 **BD-5** | **Build the capability**: owner-only · one `OPENING` per supplier · immutable · derived balance · negative allowed · zero rejected · caller-supplied date. Values are go-live data | ☑ |
| 5 | §5 **FR-PUR-015** | Derived entirely from authoritative facts. **Spend = received.** Reconciliation invariant preserved and asserted. Zero-value case tested | ☑ |
| 6 | §5A **Q5** | **Duplicate protection REQUIRED.** Server-side idempotency identity, designed in S4.3, not copied from mobile `client_uuid` | ☑ |
| 7 | §8 **Implementation order** | S4.0 → S4.1 → S4.2 → S4.3 → S4.4 → S4.5 | ☑ |

### 12.1 State at the close of this document

- **Stages 1–3: CLOSED and VERIFIED.** Untouched by this review.
- **All D5 business decisions: CLOSED.** BD-1…BD-5 resolved; `D5_Design_Review` §7 discharged.
- **Working tree: unchanged except this document.** No code, no migration, no test, no commit.
- **Next action: S4.0**, the TD-29 three-way wiring contract — the smallest step, and the only one
  that gets cheaper the earlier it is taken.

> **S4.1 and later are not authorised by this document.** It records the rulings; it does not start
> the work.
