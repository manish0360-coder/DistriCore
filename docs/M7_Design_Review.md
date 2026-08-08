# M7 — Reporting: Design Review

| Field | Value |
| --- | --- |
| Document ID | `M7_Design_Review` |
| Version | **1.2.0** |
| Status | **Signed and independently reviewed — frozen. Implementation authorised.** |
| Date | 2026-08-07 · signed 2026-08-08 · **reviewed 2026-08-08** |
| Milestone | M7 — Reporting |
| Scope | seven report endpoints · CSV export · owner dashboard · report scoping |
| Effort | 1.5 units (`00` §19.1) |
| Depends on | `00` v1.0.0 · `02` v0.2.0 · `02A` v0.2.0 · `03` · `05` · M0–M6 verified |

> Durable record of the M7 design decisions (`00` §10, ADR-0005 §10).
>
> **No ADR is proposed.** M7 changes no milestone boundary and adds no table. §2 resolves
> specification conflicts by applying the existing precedence rule, not by creating new
> authority.

### Changes in v1.1.0 — the sign-off

Four rulings were received from the Product Architect on 2026-08-08. Three were accepted as
given; **one reversed my own recommendation, and the reversal was correct** — working out
*why* it was correct produced D-2, and D-2 is the most substantive addition in this version.

| Ruling | Effect | Where |
| --- | --- | --- |
| **D-1 = option C** — sales are taxable value, net of credit notes, excluding cancelled invoices | M7-1 signed. Task 3 unblocked | §4.1 |
| **Returns get their own report**, not a filter on stock variance | **C-5 reversed.** Forced D-2, I-7, one new endpoint, one new task | §2 C-5, §4.2 |
| **Four core metrics on the dashboard, no extra widgets** | D-4 names them and states why each | §4.4 |
| **Amend the superseded requirement lines** | `02` v0.2.0 §20.1 and §14.1; `05` §9.11 | §15 |

Also added without a ruling, because working through the above exposed them: **D-3** (the
arrangement/derivation line, which §13.1 of v1.0.0 admitted was fuzzy and left fuzzy),
**I-7**, **AR-7**, and **§16** — the brief for independent architecture review.

### Changes in v1.2.0 — the independent review

Full response in **§17**. One finding requiring change, one open question, and one defect
this document had missed that surfaced while evaluating the finding.

| Source | Outcome | Where |
| --- | --- | --- |
| Review **B.1** — the AR-7 footer is an insufficient mechanism | **Partially accepted.** Criticism upheld; the proposed reconciliation screen **rejected on record** — it requires the join D-2 forbids. Need routed to M-12 | §17.1 |
| Review **C** — top-customers query plan at five years | **Accepted as a measurement target**, not as an index commitment | §17.2 |
| **C-7 — stock reports cannot show money. There is no cost basis in Edition 1** | **New conflict, found while evaluating B.1.** Reduces scope; removes two money columns | §2 C-7 |

> **C-7 is the substantive change.** It is more consequential than B.1: B.1 is two numbers
> that are confusingly right, C-7 was a number that would have been wrong. It also
> mitigates AR-7 structurally, because a report in units and a report in rupees do not
> invite comparison in the first place.

---

## 1. The governing principle

Every milestone so far has been organised around refusing to *store* something. M7 is the
first that stores nothing at all — `03` §2.1 gives `reporting` the entry **"owns nothing —
read-only queries."** So its principle cannot be about storage. It is about arithmetic:

> **A report computes nothing. It arranges, filters and totals figures the domain already
> derives.**

Every number on every report must trace to a selector some other module owns —
`inventory.selectors.stock_on_hand`, `ledger.selectors.settled_balance`,
`receivables.selectors.receivables_position`. **If a report needs a figure no domain owns,
that is a signal the domain is missing a selector — not permission for the report to
compute one.**

### 1.1 Why this is the whole design

PO-1 is *single source of truth*. Its most common failure mode is not two tables; it is
**two implementations of one number**. If the sales report sums invoice lines its own way
while the invoice screen sums them another, the owner eventually sees two figures for one
question — and then trusts neither. The data would be perfectly consistent and the system
still useless, which is exactly the state the client is trying to leave (`01` §3.1: the
business is run on recall).

The rule has a sharp practical consequence: **`reporting` may contain no domain logic, and
therefore no `services.py`.** It is the one module in DistriCore that could be deleted
without changing a single stored fact or a single business rule.

### 1.2 Two corollaries

**A report is a question asked at an instant, and the answer must be reproducible.** Same
period, same `as_of`, same answer — forever. The underlying ledgers are append-only, so
this holds by construction, but only if every report takes an **explicit period** and never
resolves "now" implicitly inside a query.

**CSV is a rendering, not a second implementation.** FR-RPT-012 requires every report
exportable. If the export re-queries, the export and the screen can disagree — and the
export is the artefact that leaves the building. One query, two renderings, exactly as M5
does for the invoice: *one template, two outputs*.

---

## 2. Specification conflicts — resolved and signed

**Seven.** More than any previous milestone, and six of them of one kind: `02`'s FR-RPT
block was written against the **frozen baseline**, before `02A` §13 re-validated Edition 1
and demoted whole modules. `02` was never back-updated. `02A` §13 is later, was explicitly
approved, and `04` was designed from its outcome — so it governs.

This is the same precedence applied at M6 C-1/C-2. Recording the supersession, not
inventing authority.

**C-7 is not of that kind, and was missed until independent review** (§17). It is not a
document disagreeing with a later document — it is **three documents agreeing with each
other and all of them disagreeing with the schema.** That is the class of conflict that
survives a careful reading of the corpus, because reading the corpus is exactly what fails
to find it.

### C-1 — FR-RPT-006 Purchase report has no data to report on

| Source | Says |
| --- | --- |
| `02` **FR-RPT-006** | "Purchase report: orders, receipts, variance, supplier balances" — **M, v1.0** |
| **`02A` §6.1** | **"Not in Edition 1: M-11 Purchasing"** |
| `04` | **No `supplier`, `purchase_order` or supplier-ledger table exists** |

**Resolution: out of scope.** The report cannot be built because the entities do not
exist. Stock enters Edition 1 through reason-coded receipts (DV-6); the closest available
figure is `variance_by_reason` filtered to `PURCHASE_IN`, and calling that a purchase
report would misrepresent it.

**`02` FR-RPT-006 should be re-marked v2.0.**

### C-2 — FR-RPT-002 asks for allocated and available stock

| Source | Says |
| --- | --- |
| `02` **FR-RPT-002** | "Stock position report: **on hand, allocated, available**, by product" — M, v1.0 |
| **`02A` §7.4** | **"Stock allocation/reservation — Edition 2."** "At Edition 1 volume, dispatch-time deduction is sufficient" |
| M2 | No allocation exists; on hand is `SUM(stock_movement.quantity)` |

**Resolution: on hand only.** With no reservation mechanism, *allocated* is always zero and
*available* always equals *on hand* — so two of the three columns would be decoration that
implies a control the system does not have. **A column that always reads zero teaches the
owner to ignore it**, which is worse than its absence.

### C-3 — FR-RPT-001 asks for a sales breakdown by category

| Source | Says |
| --- | --- |
| `02` **FR-RPT-001** | "Sales report by period, customer, product, **category** and salesman" — M, v1.0 |
| **`02A` §13.2** | **"Product category hierarchy — demoted to Edition 2.** Search covers a few hundred SKUs" |
| `04` T-10 | `product` has no category field |

**Resolution: period, customer, product and salesman. No category.** `05` §9.11 already
reflects this — its `group_by` accepts `day|product|customer` and does not offer category.
**Salesman is buildable**: `sales_order.assigned_user` exists since M3.

### C-4 — FR-RPT-009 Sync health report precedes sync

`02` FR-RPT-009 is **M, v1.0** and references FR-SYN-015. Sync is **M9**; M7 is two
milestones earlier. This is not a contradiction but a **dependency inversion in the
roadmap** — nothing exists to report on.

**Resolution: deferred to M9**, where it belongs beside the mechanism it describes. `05`
§9.11 does not list it, which corroborates.

### C-5 — FR-RPT-010 Returns report, in reduced form

`02` FR-RPT-010 references FR-RET-009, and structured Returns (M-12) is not in Edition 1.
But **DV-8 made a return a reason-coded stock movement plus a credit note**, and both exist.

**Resolution: buildable, and worth building.** Not as a returns *module* — as the answer to
"what came back and why", which is the question FR-RPT-010 exists to ask.

#### C-5 is a standalone report — *(RULED 2026-08-08, reversing this document's own recommendation)*

v1.0.0 recommended folding returns into the stock variance report (FR-RPT-003) as a
filter, and §13.2 flagged that the only argument for it was tidiness. **The ruling is that
returns get their own report. It is correct, and for a stronger reason than either side
gave at the time.**

**A return leaves two traces, and they are not the same fact.**

| Trace | Table | Written by | Owned by |
| --- | --- | --- | --- |
| **Physical** — goods came back | `stock_movement`, reason-coded, direction IN | delivery failure (M5), manual receipt (M2) | `inventory.selectors.variance_by_reason` |
| **Financial** — money was credited back | `credit_note`, `credit_note_line` | `billing.services.issue_credit_note` (M5) | `billing` |

**ADR-0009 severed them deliberately: a credit note writes no stock movement.** There is no
foreign key between the two, and there is no reliable one to add, because the mapping is
genuinely many-to-many-to-none:

| Real event | Physical trace | Financial trace |
| --- | :-: | :-: |
| Failed delivery of an order not yet invoiced | ✔ movement IN | **none** — no invoice existed to credit |
| Retailer returns damaged goods against a paid invoice | ✔ movement IN | ✔ credit note |
| Invoice priced wrongly, goods kept | **none** | ✔ credit note |
| Goods returned, resold before anyone raised the credit | ✔ movement IN, then OUT | ✔ credit note, later |

**Folding these into one screen would have implied a correspondence the domain does not
have** — the exact failure §1 exists to prevent, arrived at from the opposite direction. A
filtered variance screen would show rows 1 and 2 and silently omit row 3, and the owner
would have had no way to know row 3 was missing.

So the split is not two views of one thing. It is **two reports of two different facts**,
and D-2 states which is which.

### C-6 — How many reports are there?

| Source | Says |
| --- | --- |
| `00` §19.1 | M7 delivers "**Six** plain-table reports, CSV export" |
| `02A` §13.4 | M-13: "**Six** reports plus CSV" |
| `02A` §7.12 | Names **five** Edition-1 reports: sales, stock position, receivables aging, order status, customer statement |
| `05` §9.11 | Lists **five** endpoints — and one of them, `top-customers`, appears in no count |
| `02` §20 | Carries **eight** report lines that survive §2's resolutions |

**Resolution: "six" is not a rigorous count in any source, and M7 will not be sized by it.**
No two of the four sources above enumerate the same six. Reconciling them would mean
choosing which document to believe about a number none of them derived.

The defensible statement is the list, not the total. **M7 builds seven report endpoints and
adds CSV to the customer statement delivered at M6:**

| # | Report | Requirement | Status |
| --: | --- | --- | --- |
| 1 | Sales | FR-RPT-001, reduced by C-3 | New |
| 2 | Stock position | FR-RPT-002, reduced by C-2 | New |
| 3 | Stock variance by reason | FR-RPT-003 | New |
| 4 | **Returns by reason** | FR-RPT-010 | **New — added by the C-5 ruling** |
| 5 | Receivables aging | FR-RPT-004 / FR-REC-008 | New |
| 6 | Top customers | `05` §9.11 | New |
| 7 | Order pipeline | FR-RPT-008 | New |
| 8 | Customer statement | FR-RPT-005 | **Delivered at M6** — M7 adds CSV only |

Reports 3 and 4 are separate endpoints because they have **different row shapes over
different tables** (C-5), and M7-2 makes a CSV column set a contract with a human. Two row
shapes behind one URL is a contract that cannot be honoured.

**This amends `05` §9.11 from five endpoints to seven** (§15). The amendment is purely
additive; no existing path, parameter or field changes.

### C-7 — The stock reports cannot show money *(found 2026-08-08, during §17's review)*

| Source | Says |
| --- | --- |
| `05` §9.11 | `/reports/stock` — "**On-hand valuation**" |
| `02` **FR-RPT-003** | "Stock variance report by reason code **and value**" |
| `02A` §7.12 | Stock position report — "**Working capital** visibility" |
| **The schema** | **`Product.selling_price` is the only money field on a product. No `cost_price`, no `unit_cost`, no valuation column exists anywhere** |
| **`inventory.selectors.variance_by_reason`** | Returns `total_quantity` only. **It has never returned a value, and could not** |

**Resolution: stock position and stock variance report quantity. Neither shows money.**

**This is C-1's consequence, which v1.1.0 failed to trace.** A cost basis is a *purchasing*
artefact — it arrives with goods-received records and supplier invoices. C-1 already ruled
purchasing out of Edition 1 (`02A` §6.1, M-11); the absence of a cost price follows from
that ruling, and this document should have followed it through to the two reports that
depend on it.

#### Why not value the stock at `selling_price`

It is available, so it would work. It was considered and rejected.

1. **It is not what "valuation" means to anyone the owner will show it to.** A bank, an
   accountant and a tax authority all mean cost, or net realisable value where lower.
   Stock valued at selling price is a number the owner cannot use in the conversations
   that make stock valuation worth having.
2. **It overstates working capital by the entire margin**, on the one screen `02A` §7.12
   justifies with the phrase "working capital visibility". A figure that is wrong in the
   direction of comfort is worse than no figure.
3. **M7-1's argument applies with full force, in advance.** A number the owner internalises
   is Severe to redefine — and this one *would* be redefined, on a known schedule, the
   moment purchasing lands and a real cost basis exists. **Deferring a number is cheap.
   Un-teaching one is not.** Choosing to display it now is choosing to break it later.

**Stock valuation is Edition 2, gated on M-11 Purchasing** — the same gate as C-1, for the
same reason. `02` FR-RPT-003's "and value" clause moves with it (§15.1 A-7).

#### The dividend: this is also the structural half of AR-7's mitigation

With stock variance reported in **units** and returns reported in **rupees**, the two
reports no longer present comparable totals. **The collision that generates AR-7 largely
does not arise**, because there is no shared quantity to place side by side. §17.1 relies
on this, and it is the reason a footer plus §17.1's second change is now sufficient where a
footer alone was not.

That this fell out of investigating an unrelated finding is worth recording: **the review's
value was not only its finding.**

---

## 3. Scope

### In

Seven report selectors and endpoints (C-6) · CSV rendering · the four-number owner
dashboard (D-4) · report scoping (FR-RPT-014) · CSV on the existing customer statement ·
performance verification against DR-8.

### Out — by frozen decision

| Excluded | Decision |
| --- | --- |
| Purchase report | C-1 — no entities exist |
| Allocated / available stock columns | C-2 — Edition 2 |
| **Stock valuation — any money column on either stock report** | **C-7 — no cost basis exists. Gated on M-11 Purchasing, same as C-1** |
| **A returns reconciliation screen** | **§17.1 — requires the join ADR-0009 removed. Edition 2, with M-12 structured returns** |
| Sales by category | C-3 — Edition 2 |
| Sync health report | C-4 — M9 |
| Scheme / discount cost report | `02` FR-RPT-007 is priority **S** and schemes are Edition 2 |
| Salesman performance vs targets | FR-RPT-011 is **v1.1**; targets are Edition 2 |
| Charts | `02A` §13.2 — "Four plain numbers, no charts" |
| Scheduled or emailed reports | `02A` §7.12 — Edition 2, requires email infrastructure (A-19) |
| Excel (`.xlsx`) export | `02A` §7.12 — Edition 2. CSV is the Edition 1 escape hatch |

---

## 4. Decisions

D-1 is the only one that was open at v1.0.0. D-2 and D-4 are consequences of the rulings;
D-3 is a rule this document should have stated the first time.

### 4.1 D-1 — **What does "sales" mean?** *(SIGNED — option C, 2026-08-08)*

Every other decision in M7 is mechanical. This one is not, and it is the most expensive
thing here to get wrong.

| Option | Definition | Argument |
| --- | --- | --- |
| **A** | `SUM(invoice.total_amount)` | What the retailer was billed. Matches what the owner sees on the invoice |
| **B** | `SUM(invoice.taxable_amount)` | Excludes GST. **Tax is collected on behalf of the government; it was never the distributor's money** |
| **C** | **B, net of credit notes, excluding cancelled invoices** | What was actually sold and kept |

**Ruled: C.**

GST is not revenue — including it inflates every sales figure by the tax rate and makes the
number incomparable with any margin calculation the owner does by hand. Credit notes reduce
what was sold; a cancelled invoice records a sale that did not happen.

**Why this is Severe to reverse.** The figure is not merely displayed — it is *remembered*.
Once the owner has been reading "August sales were ₹X" for six months, redefining the term
destroys comparability with every prior month, every note they wrote down, and every
conversation they had with a supplier about volume. **No migration fixes a number a human
has already internalised.**

#### 4.1.1 The definition, stated so it can be implemented without interpretation

> **Sales over a period, for a scope** =
> `Σ invoice.taxable_amount` where `invoice.status ≠ CANCELLED` and
> `invoice.invoice_date` falls in the period
> **−** `Σ credit_note.taxable_amount` where `credit_note.credit_note_date` falls in the
> period.

Three consequences that will otherwise be discovered by argument later:

**Credit notes are counted in the period they were *issued*, not the period of the invoice
they credit.** A credit note against a July invoice reduces August sales. The alternative —
restating July — would make a closed period's figure change after the fact, which
contradicts I-6, and I-6 is the property that makes any of these numbers trustworthy. The
report footer must say so in words.

**A cancelled invoice is excluded entirely, in both periods.** It is not a negative in the
month of cancellation; it is a sale that never happened. This differs from a credit note
deliberately: cancellation says the document was wrong, a credit note says the sale was
right and then partly undone.

**Round-off is excluded**, because it lives on the invoice total and not on taxable value
(`04` T-17: *"the difference must be visible on the document, not silently absorbed"*).
Sales figures will therefore not tie to the sum of invoice totals, by design.

The report must **state its own definition on screen and in the CSV header**, so the figure
is self-describing rather than folklore.

### 4.2 D-2 — Which trace does the returns report report? *(NEW — forced by the C-5 ruling)*

C-5 established that a return leaves a physical trace and a financial trace, joined by
nothing. Two reports therefore need two definitions, and neither may quietly claim the
other's territory.

| Report | Reports | Source | Unit |
| --- | --- | --- | --- |
| **Stock variance** (FR-RPT-003) | **The physical trace** — every reason-coded movement, in both directions, returns among them | `inventory.selectors.variance_by_reason` | **Quantity only** (C-7) |
| **Returns** (FR-RPT-010) | **The financial trace** — what was credited back and why | `billing` credit notes, by reason code | **Money**, at taxable value |

**The two reports do not share a unit** (C-7). That is not a coincidence to be tidied away
later — it is the clearest available statement that they measure different things, and it
is load-bearing for AR-7.

**Ruling: the returns report is financial.** Three reasons, in order of weight:

1. **It is the question the owner asks.** "How much did we give back last month, and why"
   is a money question. The physical question — "what is sitting in the warehouse that
   should not be" — is stock variance, and is already answered.
2. **It closes the loop with D-1.** Sales are net of credit notes; the returns report is
   the itemisation of that deduction. That relationship is testable, and is **I-7**.
3. **FR-RPT-010 says "by reason code", and the credit note carries one** —
   `credit_note.reason_code` (`04` T-19), added at M5. The requirement is satisfiable on
   the financial trace without inventing a dimension.

**`credit_note.reason_code` is nullable, and the report must not hide that.** It was made
optional at M5 because it *"drives no behaviour"*, so credit notes issued before the owner
settled on a reason vocabulary will carry none. Those rows group under an explicit
**"Not categorised"** bucket that is always rendered, never filtered out and never folded
into a neighbouring reason. A returns report whose totals silently exclude uncategorised
credits is worse than no returns report, because it is wrong in a direction the reader
cannot see. **This is a test, not a convention** (task 5).

**What this deliberately gives up.** A physical return of goods on an order that was never
invoiced appears in stock variance and *not* in the returns report. That is correct — no
money was credited, because none was ever owed — but it will look like an omission to
someone comparing the two screens. **Both reports carry a one-line footer naming the trace
they report and pointing at the other.** This is the whole mitigation for AR-7, and it is a
sentence of prose rather than a mechanism, which is a weakness stated rather than hidden.

### 4.3 D-3 — The line between *arranging* and *deriving* *(NEW)*

§13.1 of v1.0.0 admitted that "a report computes nothing" is not literally true — a sales
report sums invoice lines, and summing is computation — and then left the line undrawn.
Leaving it undrawn is how M7-5 gets violated by someone acting in good faith. Drawing it:

> **Arranging** — filtering, grouping, counting, ordering, limiting, and totalling rows of
> an **already-scoped queryset a domain selector returned**. Belongs in `reporting`.
>
> **Deriving** — any figure that requires a business rule to compute: a balance, an
> on-hand quantity, an ageing, an exposure, an allocation, anything reached by a walk or a
> sign convention. **Belongs in the owning domain module, always, even when only a report
> wants it.**

The test is not "does it contain arithmetic". It is: **would getting this wrong be a
business-rule defect, or a display defect?** A wrong `SUM` over the right rows is a display
defect. A wrong balance is a business-rule defect, and business rules live in the domain
(N-01).

**Consequence: M7 may add read-only selectors to verified modules.** That is prescribed by
§1, not a violation of it — "if a report needs a figure no domain owns, the domain is
missing a selector". Such an addition must be additive, read-only, and **tested in the
owning module's suite, not in `reporting`'s**, or the domain acquires untested surface.

Auditing the seven reports against this line, the figures already have owners:

| Figure | Owner | Verdict |
| --- | --- | --- |
| On-hand quantity | `inventory.selectors.stock_on_hand` | Exists |
| Variance by reason | `inventory.selectors.variance_by_reason` | Exists |
| Settled balance | `ledger.selectors.settled_balance` | Exists |
| Ageing buckets and oldest item | `receivables.OutstandingItem.bucket`, `receivables_position` | **Exists** — M6 built the buckets and `AGING_BUCKET_DAYS` already |
| Collections in a period | `receivables.selectors.collections_by_user` | Exists — M6's docstring already names M7 as the caller |
| Order counts by status | grouping over `orders.selectors.visible_orders` | **Arrangement.** `reporting` does it |
| Sales under D-1 | none | **Arrangement** over `billing`'s invoices — D-1 is a reporting definition, and this is the one figure `reporting` owns outright |

**No new domain selector is required.** That is a stronger position than §1 anticipated,
and it is a direct dividend of M6 having built ageing properly rather than deferring it.

### 4.4 D-4 — The four dashboard numbers *(RULED: four core metrics, no widgets)*

`02A` §7.12 says "four numbers on a home screen" and `02A` §572 says "four plain numbers,
no charts". Neither says which four. The ruling confirms four and no extras; naming them is
this document's job.

**Selection rule: four numbers, four different questions, no number a slice of another.**

| # | Number | Question it answers | Source |
| --: | --- | --- | --- |
| 1 | **Sales today** | *Did we sell?* | D-1 definition, `date_from = date_to = today` |
| 2 | **Collected today** | *Did the money arrive?* | `collections_by_user`, totalled, today |
| 3 | **Total outstanding** | *How much is out there?* | `Σ ledger.selectors.settled_balance` |
| 4 | **Orders awaiting dispatch** | *What is stuck?* | `visible_orders`, `CONFIRMED` with no dispatched delivery |

**Why these and not the obvious alternatives:**

- **Sales and collections are separate numbers because they are separate events.** M5's
  governing principle split dispatch from invoicing; M6's split payment from invoice. A
  dashboard that showed one "revenue" figure would undo two milestones of that distinction
  on the one screen the owner looks at daily.
- **Stock value on hand is excluded.** It is a working-capital question asked monthly, it
  moves slowly, and it is the whole subject of report 2. A number that rarely changes
  teaches the reader to stop looking — the same argument C-2 used against a column that
  always reads zero.
- **Overdue receivables is excluded**, despite being the most tempting fifth. It is a
  *slice* of number 3. Showing a total and one of its parts side by side invites the reader
  to add them, and the ageing report exists to break the total down properly.
- **Number 4 is a count, not money**, deliberately. Three money figures and one work figure
  is the honest shape of a distribution day.

**Numbers 1 and 2 are "today" and therefore not reproducible** — they are live operational
figures, and I-6 does not apply to them. The dashboard is the one surface in M7 that is a
glance rather than a record, and it must not offer CSV export, or a non-reproducible figure
acquires the authority of a document.

---

## 5. Worked scenario and invariants

### 5.1 One month, one customer

August 2026, customer `C-0142`. Product at ₹100, 18% GST.

| Event | Invoice | Taxable | Tax | Total |
| --- | --- | --: | --: | --: |
| INV/00001, 24 units | issued | 2,400.00 | 432.00 | 2,832.00 |
| INV/00002, 10 units | issued | 1,000.00 | 180.00 | 1,180.00 |
| INV/00003, 5 units | **cancelled** | 500.00 | 90.00 | 590.00 |
| CN/00001 against INV/00002, 2 units | — | (200.00) | (36.00) | (236.00) |

**Sales, under D-1 option C:** 2,400 + 1,000 − 200 = **₹3,200.00**.
Under A it would be 2,832 + 1,180 − 236 = ₹3,776.00 — **18% higher, and not revenue.**

**Returns, over the same month:** ₹200.00 — the credit note's taxable value, and exactly
the deduction inside the sales figure. That equality is I-7.

### 5.1.1 The same month, from the warehouse's point of view

Three physical events happened in August that the financial table above does not mention:

| Event | Movement | Credit note |
| --- | --- | --- |
| The 2 units credited on CN/00001 came back | IN, reason `SALES_RETURN`, 2 units | ✔ CN/00001, ₹200.00 |
| A delivery of an **uninvoiced** order failed; 6 units returned to the van | IN, reason `DELIVERY_FAILED`, 6 units | **none** |
| INV/00003 was cancelled before dispatch | **none** | **none** — cancellation, not a credit |

| Report | August total | Contains |
| --- | --- | --- |
| **Returns** (financial) | **₹200.00** | The credit note only |
| **Stock variance** (physical) | **8 units IN** across two reason codes | Both movements |

**Neither number is wrong and neither can be derived from the other.** This is the concrete
form of C-5 and D-2: two reports, two facts, one deliberately absent join. It is also
exactly the comparison that will generate the first "the reports disagree" question from
the owner, which is why both reports carry the footer D-2 requires.

### 5.2 Invariants the reports must satisfy

| # | Invariant | Why |
| --- | --- | --- |
| **I-1** | Sales report total ≡ sum of its own rows, under every `group_by` | Grouping must not change the total. A `group_by` that alters the answer is a join defect |
| **I-2** | Receivables report total ≡ `Σ settled_balance` over the same customers | The report and M6's ledger must not disagree — this is §5A.7 surfacing at the read layer |
| **I-3** | Stock report on-hand ≡ `inventory.selectors.stock_on_hand` per product | The report adds no arithmetic |
| **I-4** | Order-status counts sum to the number of orders in the period | No order is in two states or none |
| **I-5** | **CSV content ≡ screen content**, row for row and figure for figure | One query, two renderings (§1.2) |
| **I-6** | A report over a closed period returns the same answer on any later day | Append-only inputs plus an explicit period |
| **I-7** | **Returns report total ≡ the credit-note deduction inside the sales report**, over the same period and scope | D-1 nets credit notes; the returns report itemises that deduction (D-2). If they diverge, one of the two reads credit notes wrongly |

**I-5, I-6 and I-7 are the ones that would silently rot.** All three get tests.

### 5.3 One thing that is deliberately *not* an invariant

> **The returns report and the stock variance report are not required to agree, and must
> never be asserted to.**

They measure different traces of the same real-world event (C-5, §5.1.1), and the
population where both exist is only one of four cases. **Writing a test that asserted their
equality would encode a relationship ADR-0009 removed on purpose**, and would then fail
correctly on the first uninvoiced delivery failure — at which point someone would "fix" the
reports to satisfy the test. Recording the non-invariant is cheaper than recovering from
that.

I-6 also does not apply to the dashboard, which reports today (D-4).

---

## 6. Concurrency

**M7 takes no locks, writes no rows and starts no transactions.** There is nothing to
serialise. That is not a claim that concurrency is irrelevant — it is that the only
concurrency concern here is *read tearing*, and it has a precise, bounded shape.

### 6.1 The tearing window, stated exactly

A report issuing several queries can observe writes that land between them, under
PostgreSQL's default `READ COMMITTED`. Customer A's balance may be read before a payment
and customer B's after, so the total matches no single instant.

**The window is bounded by the report's own period:**

| Report period | Exposed? |
| --- | --- |
| A closed period (`date_to` < today) | **No.** Every qualifying row was written before the report began |
| A period including today | Yes, for rows written during execution — measured in milliseconds |

**Resolution: accept, and document it.** Reaching for `REPEATABLE READ` or a snapshot
transaction would guard a race whose entire population is "a salesman recorded a payment
during the two seconds the owner's report was running", and whose consequence is a total
off by one payment that the next refresh corrects.

**M6 §6.2 is the precedent, and it cuts this way deliberately:** a mechanism that appears
to guarantee something it does not is worse than no mechanism. If a snapshot were added, it
would have to cover *every* report and be tested for it, or it would be exactly the
write-off lock again.

### 6.2 What M7 must not do

**No report may take a lock**, including `select_for_update`. A read path that locks can
block a collection being recorded in the field, and no report is worth that.

---

## 7. Database implications

**None.** No table, no column, no index required by design.

**Indexes may be added if — and only if — §10's performance verification proves a need.**
Adding one speculatively is premature optimisation; adding one to fix a measured breach of
FR-RPT-015 is engineering. Any such index is recorded as an M7 decision with the
measurement that justified it.

---

## 8. Module and API boundaries

### 8.1 Module

| Module | Owns | May call | Contains |
| --- | --- | --- | --- |
| `reporting` *(new)* | **Nothing** | all, **read only** | `selectors.py`, `csv.py`. **No `models.py`, no `services.py`, no migrations** |

**Layer graph** — `reporting` sits at the top of the domain, below the delivery layers:

```
api | webadmin  >  reporting  >  receivables  >  billing  >  fulfilment  >  orders
                >  pricing  >  inventory | ledger  >  catalogue | customers
                >  identity  >  core
```

**A structural test must assert `reporting` imports no `*.services` module.** It is a
reader; importing a writer would be the first step toward a report with a side effect. This
is the same read/write distinction drawn for `orders → ledger` (M5) and
`receivables → billing` (M6), and it is now the third time — which is evidence it should be
a stated rule rather than a per-milestone test.

**`reporting` gains no selector that belongs to a domain (D-3), and per §4.3's audit it
needs none** — every derived figure the seven reports require already has an owner. If
implementation discovers one that does not, the selector goes into the owning module and is
tested there. It is not written into `reporting` because that was quicker.

### 8.2 API

Seven endpoints (C-6), plus `?format=csv` on all of them and on the existing statement.
**Five are `05` §9.11 unchanged; two are added, and §15 amends `05` accordingly.**

| Method | Path | Notes | Source |
| --- | --- | --- | --- |
| GET | `/reports/sales` | `?date_from=&date_to=&group_by=day\|product\|customer` | `05` §9.11 |
| GET | `/reports/stock` | On-hand **quantity** by product. **On hand only** (C-2); **no valuation** (C-7) | `05` §9.11 |
| GET | `/reports/stock-variance` | `?date_from=&date_to=&reason_code=` — the **physical** trace (D-2), **in units** (C-7) | **Added** |
| GET | `/reports/returns` | `?date_from=&date_to=&group_by=reason\|customer` — the **financial** trace (D-2) | **Added** |
| GET | `/reports/receivables` | Balance, ageing bucket and oldest unpaid — **reuses M6's `receivables_position`** | `05` §9.11 |
| GET | `/reports/top-customers` | `?limit=10&date_from=` — ranked on the D-1 figure | `05` §9.11 |
| GET | `/reports/order-status` | Pipeline counts by status | `05` §9.11 |

The dashboard is **not** an eighth report endpoint. It is four scalars on a webadmin screen,
each read from the selector D-4 names, and it offers no CSV (D-4). Giving it an endpoint
would make a deliberately non-reproducible figure look like a document.

**Every one of the seven takes an explicit period or `as_of` and never resolves "now"
inside a query** (§1.2). A report endpoint with no date parameters is a defect, not a
convenience.

### 8.3 Scoping — FR-RPT-014

Reports respect the caller's authorisation, and **M6 established that "the caller's scope"
is not one predicate.** A salesman sees payments **they collected** but ledgers for **their
own zones** (`05` §8). M7 must reuse the existing scoped selectors rather than write a
third rule; a report is exactly the place a scoping bug becomes an information leak with a
CSV attached.

---

## 9. Irreversible decisions — signed

**Fewer than any previous milestone, because M7 stores nothing.** That is the point: the
absence of irreversible decisions is what a read-only module should look like.

| # | Decision | Cost to reverse | Signed |
| --- | --- | :-: | :-: |
| **M7-1** | **The definition of "sales" — D-1 option C**, per §4.1.1, including credit notes counted in the period they were issued | **Severe** — no migration fixes a figure a human has already internalised across months | ☑ 2026-08-08 |
| **M7-2** | **CSV column names and order** are a contract with a human | **High** — the owner will build spreadsheets on the export; renaming a header breaks work that lives outside this system | ☑ |
| **M7-3** | **Date bounds are inclusive at both ends**, on business dates, never timestamps | High — changing it invalidates every prior reconciliation the owner performed by hand | ☑ |
| **M7-4** | `reporting` **stores nothing.** No materialised aggregates | Low to add later (additive); **Severe in the other direction** — a stored aggregate that drifts from the ledger is a second source of truth | ☑ |
| **M7-5** | Reports **arrange; domains derive** — the line drawn in D-3 | Medium — a second implementation of a number is cheap to write and expensive to reconcile | ☑ |
| **M7-6** | **No report takes a lock** (§6.2) | Medium | ☑ |
| **M7-7** | **Returns and stock variance are two reports of two traces** (C-5, D-2), joined by nothing | **High** — merging them later destroys a distinction the owner will have learned; splitting them later is easy. **The cheap direction is the one taken** | ☑ 2026-08-08 |
| **M7-8** | **The four dashboard numbers** are sales today, collected today, total outstanding, orders awaiting dispatch (D-4) | Low — a home screen carries no history. **Listed here because it is the most-seen surface in the product, not because it is hard to change** | ☑ 2026-08-08 |

---

## 10. Implementation tasks

Eight, each independently verifiable and committable (ADR-0005 §6.2). **Task 5 is new — the
C-5 ruling split what v1.0.0 had as one task into two**, which is the honest accounting of
what the ruling cost.

| # | Task | Gated by |
| --- | --- | --- |
| 1 | `reporting` module — `selectors.py` and `csv.py` only, layers contract, structural test forbidding `*.services` imports | §8.1, M7-5 |
| 2 | **CSV rendering — one mechanism, all reports.** A renderer over a shared row shape, never per-report | I-5, M7-2 |
| 3 | Sales report — the §4.1.1 definition, three `group_by` modes, definition and the credit-note period rule stated on screen and in the CSV header | **M7-1**, I-1 |
| 4 | Stock position and stock variance — **the physical trace** (D-2), **quantity only, no money column** (C-7) | C-2, **C-7**, I-3 |
| 5 | **Returns report — the financial trace** (D-2), including the "Not categorised" bucket, I-7, and **I-7 rendered on screen as the reconciliation line** (§17.1) | **M7-7**, I-7 |
| 6 | Receivables ageing and top-customers — **reusing M6's `receivables_position` and `OutstandingItem.bucket` unchanged** | I-2, M7-5 |
| 7 | Order pipeline; the four-number dashboard (D-4), **no CSV on the dashboard** | I-4, M7-8 |
| 8 | API, owner screens, scoping tests, **and the DR-8 performance verification** | §8.3, FR-RPT-015 |

### 10.1 Performance verification is a task, not an assumption

FR-RPT-015 and NFR-PER-003 require **under 10 seconds over five years of history**, and
NFR-PER-003's stated method is "load test against a synthesised five-year dataset."

At the DR-8 envelope that is roughly 73,000 invoices and 250,000 invoice lines. **No report
in M7 may be declared done on the strength of a fast test-suite run**, which exercises tens
of rows. Task 8 includes generating the dataset and recording measured timings — **all
seven, individually** — in the verification report. A single aggregate "reports are fast"
claim hides the one that is not.

**Two reports to watch specifically, and the measurement must name them:**

**Receivables** — the only report whose figures come from a **row-by-row walk in Python**
(§5A) rather than a database aggregate, and it walks every ledger entry for every visible
customer. The most likely single breach of FR-RPT-015. If it breaches, the fix is a
`receivables` optimisation — not a reporting shortcut, and not a stored aggregate (M7-4).

**Top customers** — raised by independent review (§17.2). It aggregates `taxable_amount`
across **both** `invoice` and `credit_note`, groups by customer and orders by the result.
The existing indexes are `ix_invoice_customer_date` on `(customer, -invoice_date)` and
`ix_credit_note_cust_date` on `(customer, -credit_note_date)` — **both lead on `customer`,
so neither serves a date-range scan that then groups.** A five-year range may therefore
scan both tables in full.

**No index is committed in advance** (§7). The measurement establishes whether one is
needed, and any index added is recorded with the measurement that justified it.

**This is the one place M7 can fail on its own terms.** Everything else is arrangement.

---

## 11. Technical debt — what belongs here, and what does not

The instruction was to close debt **only if it naturally belongs**. Applying that honestly:

### Belongs in M7

| # | Item | Why it belongs |
| --- | --- | --- |
| **TD-23** | `billing/selectors.py` at 78% — the uncovered lines are the **salesman and retailer scoping branches** | FR-RPT-014 requires M7 to exercise exactly that surface. The tests M7 must write anyway are the tests TD-23 is asking for |

### Does not belong in M7 — stated so it is not smuggled in

| # | Item | Why not |
| --- | --- | --- |
| TD-21 | Build reproducibility | Infrastructure. Deserves its own change with its own verify run |
| TD-2 / TD-18 | `mypy` blocking | **Missed at M5 and again at M6.** It needs a dedicated change, not a third ride on someone else's milestone — that is how it was missed twice |
| TD-26 | `_walk` guards covered only by the property test | Test debt in `receivables`. M7 reading those selectors is adjacency, not ownership |
| TD-14 | `Product._has_history()` | Unrelated |
| TD-24 / TD-25 | `_ImmutableDocument` move; mypy items | M10; unrelated |

> **M7 is budgeted 1.5 units and is the last cheap milestone before M8 changes language and
> platform.** Loading it with four unrelated debts because it looks small is how a small
> milestone stops being small.

---

## 12. Risks

| # | Risk | Severity | Mitigation |
| --- | --- | :-: | --- |
| **AR-1** | ~~D-1 settled wrongly or late~~ | **Closed** | **Ruled 2026-08-08, before task 3. §4.1.1 states the definition to implementation precision** |
| **AR-2** | FR-RPT-015 breached at five years' history | **High** | §10.1 — measurement is a task, with per-report timings. **Receivables and top-customers are the named suspects** (§17.2) |
| **AR-3** | A report re-implements a domain figure and the two drift | High | M7-5 and **D-3's explicit line**, plus I-1…I-4 asserted as tests |
| **AR-4** | CSV and screen diverge | Medium | I-5; one query, two renderings |
| **AR-5** | Scoping leak — a salesman's CSV containing another zone's customers | **High** | §8.3 reuses existing scoped selectors; full role grid tested per report |
| **AR-6** | ~~`02` lists reports M7 will not build~~ | **Closed** | **`02` v0.2.0 §20.1 and §14.1 amended 2026-08-08** (§15) |
| **AR-7** | **The owner compares the returns and stock variance reports, finds them unequal, and concludes one is broken** | Medium | **Three layers after §17.1, no longer a footer alone:** (1) **C-7 — the reports share no unit**, so there is no comparable total to place side by side; (2) **I-7 rendered on the returns report**, which satisfies the "does this tie to anything?" instinct with a reconciliation that is *true*; (3) the cross-referencing footer, kept. §5.1.1 worked; §5.3 records the non-invariant |
| **AR-8** | **The owner asks what their stock is worth and M7 has no answer** (C-7) | Medium | Accepted and stated, not mitigated. A wrong valuation is worse than an absent one; the honest answer arrives with M-11. **This is the cost of C-7 and it is a real cost** |

---

## 13. Self-critique

**1. "A report computes nothing" is still not literally true — but v1.0.0 left the line
undrawn, and D-3 now draws it.** The test is whether getting a figure wrong would be a
*business-rule* defect or a *display* defect. That is a real improvement over v1.0.0, and it
is still a discipline rather than a mechanism: **`lint-imports` can prove `reporting`
imports no writer, but nothing can prove a `SUM` in `reporting` should have been a selector
in `billing`.** Code review is the only enforcement, which means this will be violated
eventually and caught late.

**2. I recommended folding returns into stock variance, and I was wrong.** My own stated
reason was that it kept the count at six, and §13.2 of v1.0.0 admitted tidiness is a weak
argument — but I made the recommendation anyway rather than following that admission to its
conclusion. **The count was never real (C-6 now says so), so I optimised a report structure
against a number no document had derived.** Working out why the reversal was right produced
C-5's four-case table and D-2, neither of which existed when I recommended the merge.

The lesson generalises: **when I flag my own reasoning as weak in a self-critique, that is
evidence the recommendation is wrong, not a disclaimer that makes it safe to keep.**

**3. AR-7's mitigation was a footer, and a footer is not a mechanism.** *(Largely answered
at v1.2.0 — see §17.1. C-7 removed the shared unit and I-7 now renders on screen, so two
of the three layers are structural. The footer remains, and remains untested prose.)*

**3a. I found C-7 only because a reviewer pushed on something else.** C-7 is not subtle: no
`cost_price` field exists, and `variance_by_reason` has never returned a value. I read that
selector while writing D-3's audit table in v1.1.0 — **I looked directly at the evidence and
did not see it, because I was checking whether the figure had an owner, not whether the
figure existed.** The audit answered its own question correctly and the wrong question was
being asked. Reviewing against a checklist finds what the checklist names.

**4. §6 accepts read tearing on the same reasoning M6 used to remove a lock, and the two
situations are not identical.** M6's lock protected nothing at all; here a snapshot
transaction *would* work. I am declining it on cost and consistency, not impossibility.
That is a judgement, and if the owner ever reconciles a receivables report against a bank
statement to the rupee, it is the judgement that will be questioned first.

**5. D-4's four numbers are my selection, not a stakeholder's.** The ruling confirmed *four
core metrics, no extra widgets*; it did not name them. §4.4 argues each one, but the
argument is from first principles about what a distributor asks daily — **not from having
watched this distributor work.** The exclusions I am least sure of are stock value (a real
working-capital question, argued out on the grounds that it moves slowly) and overdue
receivables (excluded as a slice of number 3, which is principled and may still be the
number the owner actually wants). M7-8 is cheap to reverse, which is why I have proceeded
rather than blocked — but it should be the first thing revisited after the owner has used
the screen for a week.

**6. Effort.** 1.5 units, and the C-5 ruling added a report, an endpoint and a task after
that estimate was made. §10.1's five-year dataset is also real work the estimate probably
did not include. M5 was budgeted 3.0 and took four verify cycles; M6 was 1.5 and took five.
**I have no basis for predicting cycles and will not present one.**

---

## 14. Sign-off

| # | Item | Party | Status |
| --- | --- | --- | :-: |
| 1 | **D-1 — the definition of "sales".** The most consequential item here | Product Architect | ☑ **Option C**, 2026-08-08 |
| 2 | **C-1 … C-6** — the six specification resolutions (§2) | Product Architect | ☑ |
| 3 | **C-5 — is the returns view folded into stock variance, or its own report?** | Product Architect | ☑ **Its own report.** Reverses this document's recommendation; see §13.2 |
| 4 | **Which four numbers appear on the dashboard?** | Product Architect | ☑ **Four core metrics, no widgets** — named in D-4 |
| 5 | §6 — read tearing accepted rather than guarded (§13.4) | All | ☑ |
| 6 | M7-1 … **M7-8** irreversible decisions (§9) | All | ☑ |
| 7 | §11 — **TD-23 only**; the other five debts stay out | All | ☑ |
| 8 | **Amend the superseded requirement lines** | Product Architect | ☑ **Done** — `02` v0.2.0 §20.1 and §14.1; `05` §9.11. See §15 |
| 9 | This document accepted | All | ☑ **v1.1.0 frozen 2026-08-08** |
| 10 | **C-7 — stock reports carry no money column** (found at review) | Product Architect | ☑ 2026-08-08 |
| 11 | **Independent architecture review** — findings dispositioned in §17 | All | ☑ **Approved 95/100. v1.2.0 frozen 2026-08-08** |

**All eleven signed. No item blocks implementation.** Tasks 1–8 (§10) may begin in order.

> **What "frozen" means here, in the terms the corpus already uses.** M7-1 … M7-8 do not
> change without a recorded amendment and a version bump on this document. C-1 … C-6 and
> D-1 … D-4 are decisions, not preferences: implementation that finds one of them
> impossible **stops and reports**, exactly as M5 and M6 did — it does not adapt the
> design to what turned out to be convenient.

---

## 15. Amendments made to the corpus under item 8

Recorded here rather than only in the amended files, so the change is auditable from the
milestone that caused it.

### 15.1 `02_Requirements_Specification.md` → v0.2.0

| Line | Was | Now | Authority |
| --- | --- | --- | --- |
| FR-RPT-001 | "…by period, customer, product, **category** and salesman" | Category removed | `02A` §13.2 · C-3 |
| FR-RPT-002 | "on hand, **allocated, available**" | On hand only; allocated/available → **v2.0** | `02A` §7.4 · C-2 |
| FR-RPT-006 | Purchase report, **M / v1.0** | **v2.0** — no supplier entity exists in Edition 1 | `02A` §6.1 · C-1 |
| FR-RPT-007 | Scheme cost report, S / **v1.0** | **v2.0** — schemes are Edition 2 | §3 (out of scope) |
| FR-RPT-009 | Sync health, **v1.0** | v1.0, **delivered at M9** — the mechanism does not exist yet | C-4 |
| FR-RPT-010 | Returns report by reason code | Unchanged in text; **scope narrowed to the financial trace** | **D-2** |
| FR-REC-004 | "Payments MUST be allocatable against **specific invoices**" | **v2.0** — Edition 1 settles FIFO across the ledger | M6 D-9 |
| FR-REC-006 | "Allocated payment MUST NOT exceed… the target invoice" | **v2.0** — follows FR-REC-004 | M6 D-9 |
| FR-REC-008 | "aging analysis over **configurable** buckets" | Buckets are **constants** (`AGING_BUCKET_DAYS`) | M6 C-2 |
| **FR-RPT-003** | "Stock variance report by reason code **and value**" | **Value clause → v2.0 (FR-RPT-018).** No cost basis exists | **C-7** |

Each amended line carries an inline supersession marker, and §20.1 / §14.1 of `02` record
the same table. **Nothing was deleted** — a requirement that moved to v2.0 is still a
requirement, and a reader must be able to see that it was considered and deferred rather
than dropped.

### 15.2 `05_API_Contracts.md` §9.11

Two endpoints added — `/reports/stock-variance` and `/reports/returns` (C-6, D-2). **Purely
additive: no existing path, parameter, response field or role changes**, so the amendment is
backward compatible by construction.

**Amended again at v1.2.0:** `/reports/stock`'s purpose line said *"On-hand valuation"*.
Corrected to on-hand **quantity** (C-7). This is a correction of a description that the
schema never supported, not a contract change — **no field is being removed, because no
implementation ever existed to remove it from.** `05`'s version is not bumped; the section
carries an inline amendment note naming M7 §2 as the authority.

### 15.3 What was deliberately *not* amended

| Document | Still says | Why left alone |
| --- | --- | --- |
| `00` §19.1, `02A` §13.4 | "**Six** reports" | C-6 establishes the count was never derived by any source. Rewriting two documents to agree on a number that governs nothing would be churn. **The list in C-6 governs; the total is descriptive** |
| `02A` §7.12 | Names five Edition-1 reports | Same reason. It is an editions-analysis table, not a specification of scope |
| `01` Vision | — | M7 changes no Vision decision |

---

## 16. For independent architecture review *(brief as issued — review complete, see §17)*

This design is being sent for independent review before implementation. The items below are
where review effort is worth most — not because they are unresolved, but because they are
the places where being wrong is expensive and I cannot check my own reasoning further.

| # | Question | Why it is worth challenging |
| --: | --- | --- |
| 1 | **§4.1.1 — should a credit note reduce the period it was issued in, or the period of the invoice it credits?** | I chose issue-period to protect I-6. The alternative is what an accountant would expect. Both are defensible; only one can be true, and M7-1 is Severe to reverse |
| 2 | **D-2 — is the returns report right to be financial rather than physical?** | FR-RPT-010 traces to FR-RET-009, which is about *goods*. I read the owner's question as a money question. If that reading is wrong, report 4 answers the wrong question in the right format |
| 3 | **D-3 — is the arranging/deriving line drawn in the right place?** | It permits `reporting` to own the D-1 sales figure outright while forbidding it to own a balance. That asymmetry is deliberate and may be wrong |
| 4 | **§6 — is accepting read tearing right for a *receivables* report?** | §13.4 states my own doubt. A snapshot transaction would work and I declined it on cost |
| 5 | **D-4 — are these the right four numbers?** | §13.5 states the exclusions I am least sure of: stock value and overdue receivables |
| 6 | **§10.1 — is the receivables report actually going to meet FR-RPT-015?** | It is the only report driven by a Python walk rather than an aggregate. If review can show it cannot meet 10 s at DR-8, that is worth knowing *before* seven reports are built on the assumption it can |

**What is not open to review:** N-01 … N-12, ADR-0009, and the M5/M6 governing principles.
A finding that requires one of those to change is a finding about M5 or M6, and belongs in
its own change rather than in M7.

> **Outcome, recorded against the brief.** The review answered items 4 and 6 (approved §6;
> raised top-customers alongside receivables) and did not engage items 1, 2, 3 or 5 — it
> approved all four. **Its one finding was on none of the six.** The brief asked where I
> thought I was weakest and the review found a weakness I had not listed, which is the
> argument for briefing a reviewer *and* letting them read past the brief.

---

---

## 17. Independent architecture review — response

Review received 2026-08-08. Approved for implementation at 95/100, conditional on one scope
amendment, with six decisions explicitly approved without change (D-1, D-2, D-3, D-4, §6
read tearing, I-7). Those approvals are recorded and not revisited here.

**Summary of dispositions:**

| Finding | Disposition |
| --- | --- |
| **B.1** — the AR-7 footer is insufficient; add a Returns Reconciliation screen to M7 | **Partially accepted.** Problem upheld and mitigation strengthened. **Screen rejected and recorded** (§17.1) |
| **C** — top-customers query plan over five years | **Accepted** as a named measurement target; **index not pre-committed** (§17.2) |
| — | **C-7 found during evaluation.** Not a review finding; a defect the review's pressure surfaced (§2 C-7) |

### 17.1 B.1 — Returns Reconciliation screen: **partially accepted**

#### The part that is accepted, without reservation

> *"A footer is documentation, not a tool. The owner will not read the footer."*

**Correct, and this document said so first** — §13.3 named the footer as "the weakest point
in the M7 design". The review is right that stating a known weakness is not the same as
mitigating it, and v1.1.0 shipped a self-critique where it should have shipped a change.
AR-7's mitigation is strengthened in three layers (§12), two of them structural.

#### The part that is rejected: the mechanism

**The screen cannot be built in Edition 1 without inventing the relationship D-2 forbids.**

The specification is: *"`stock_movement` rows … for which no matching `credit_note` has been
issued"*, and *"`credit_note` rows where no corresponding physical return movement is
found"*. Both clauses require **`matching`** to be computable. It is not.

**Follow what "matching" would have to mean here:**

| Question the join must answer | Available in Edition 1? |
| --- | --- |
| Which customer did this stock movement come from? | **Only sometimes.** A delivery-failure movement reaches a customer through `delivery → sales_order`. A warehouse return receipt is product + location + reason, and reaches no customer at all |
| Which product line does this credit note line correspond to? | Product matches; **quantity need not** — a credit note may be raised for a rate difference with no quantity at all |
| Within what time window does a movement "correspond" to a credit note? | **Unspecified, and unspecifiable.** C-5 case 4 has the credit raised after the goods were returned *and resold* |
| What if two returns and one credit note, or one return and two credit notes? | **Undefined** |

Every one of those would have to be answered by a **heuristic invented in the reporting
layer** — a tolerance, a window, a matching rule. That is:

- **A violation of D-3**, which the review approved. Matching is *deriving*, not arranging:
  getting it wrong is a business-rule defect, not a display defect.
- **A violation of §1 and M7-5.** `reporting` owns nothing. A matching rule is the largest
  piece of new domain logic anyone has proposed for M7, placed in the only module forbidden
  to hold any.
- **A contradiction of the review's own §A.** It approves D-2 because *"there is no reliable
  1:1 join between physical and financial returns"* and then proposes a screen whose two
  lists are defined by the absence of that join. **You cannot list what has no match without
  first defining a match.**

And the failure mode is severe in exactly the way B.1 is trying to prevent. A heuristic
reconciliation screen produces **false positives** — it shows the owner "uncredited returns"
that were in fact credited, under a rule they cannot see. The review's own argument applies
with more force to its remedy than to the problem: *"once the owner believes the reports are
wrong, every subsequent number is suspect."* **A screen that is confidently wrong destroys
more trust than two screens that are honestly different.**

#### Where the need actually belongs

**The review has independently rediscovered the value of structured returns.** `02A` §7.11
lists *"Invoice-linked structured returns"* as **Edition 2, M-12**, with the note
*"automates what Edition 1 does manually"*.

That feature creates the record — a return linked to the invoice line it reverses — that
makes matching a **stored fact** rather than a guess. **The reconciliation screen is not a
reporting feature. It is the user-facing half of M-12, and it becomes correct, cheap and
testable the moment M-12 exists.**

Building it now means building the *screen* two editions before the *data* it reads. The
sequencing is the whole objection; the idea is right.

> **Recorded so it is not re-proposed.** A returns reconciliation view requires a
> return-to-credit-note link. Edition 1 has none, and ADR-0009 removed the only candidate
> deliberately. **Any future proposal for this screen must first propose the link** — and
> that proposal is M-12, not M7.

#### What changes in M7 instead

Three layers replace the footer-alone mitigation. Cost: **one rendered line and two report
titles.** No new screen, no new endpoint, no new selector.

| # | Change | Why it works |
| --: | --- | --- |
| 1 | **C-7 — the two reports share no unit.** Variance in units, returns in rupees | Removes the comparison rather than explaining it. **The strongest of the three, and it arrived by accident** |
| 2 | **I-7 rendered on the returns report**: *"These credits reduced Sales for this period by ₹X."* | The owner's instinct is "does this number tie to anything?" — a real question, and the reason they reach for the variance report. **Answer it with the reconciliation that is true.** I-7 is already computed for its test; this is a rendering, not a calculation |
| 3 | The cross-referencing footer on both reports, kept | Weakest layer, still worth its zero cost |

**Layer 2 is the one that does the work the review asked for.** It gives the owner a tool
rather than an explanation — it just reconciles against the report that *can* be reconciled
against, instead of the one that cannot.

**Classification, restated:** the review classified this Critical on the grounds that "the
M7 reports are correct but unusable as a pair". After C-7 they are not a pair — they are a
quantity report and a money report, and I-7 gives the money report a partner.

### 17.2 C — top-customers performance: **accepted as a measurement target**

The concern is well founded and the index diagnosis is sharper than this document's was.
Verified against the schema: `ix_invoice_customer_date` is `(customer, -invoice_date)` and
`ix_credit_note_cust_date` is `(customer, -credit_note_date)`. **Both lead on `customer`**,
so neither serves "filter a date range, then group by customer" — the review is right that
a five-year range may scan both tables in full.

**Accepted:** top-customers is named in §10.1 as a second suspect alongside receivables, and
its query plan is examined explicitly during task 8.

**Not accepted:** pre-committing the composite index. §7 states that an index added
speculatively is premature optimisation and an index added to fix a measured breach is
engineering — and the review itself frames this as *"not a blocker … pay specific
attention"*, which is a measurement instruction, not an index instruction. The two positions
agree; only the artefact differs.

### 17.3 What the review did not find, and what that is worth

The review found **no defect in the reporting logic or the accounting**, and approved all six
substantive decisions unchanged. Taken with M5's and M6's reviews, that is now three
milestones where independent review confirmed the domain reasoning and challenged the
*consequences* of it.

**The pattern is worth naming, because it predicts where the next review will land.** M5's
review challenged a double-restock *scenario*, M6's challenged a lock that guaranteed
nothing, and M7's challenges what two correct reports will do to a person. Each was outside
the frame this document was written in. **The reviews are not finding errors in the
reasoning; they are finding the reasoning's blind spot, and it has been the same blind spot
three times: correctness at the boundary, consequences past it.**

---

*No implementation code has been written. No ADR is required. Task decomposition is in
`NEXT_TASK.md`. This document is frozen at v1.2.0; implementation may begin.*
