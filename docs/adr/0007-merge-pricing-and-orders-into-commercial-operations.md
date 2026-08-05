# 0007 — Merge pricing and orders into one milestone: Commercial Operations

Status: Accepted
Date: 2026-08-05
Deciders: Product Architect, Chief Systems Engineer
Amends: `00_Engineering_Foundation.md` §19.1 (milestone roadmap)

## Context

The frozen roadmap splits this work in two:

| # | Milestone | Contents | Depends on | Effort |
| --- | --- | --- | --- | --: |
| M3 | Pricing | Selling price, bounded manual discount, resolution in `CORE` | M1 | 1.0 |
| M4 | Orders (web) | Owner capture, 5-state lifecycle, credit limit, edit, cancel | M2, M3 | 2.0 |

Two problems surfaced when M3 was about to begin.

**1. Pricing has no observable behaviour on its own.**

`02A` §13.2 demoted price lists, customer-specific pricing and effective dating out of
Edition 1. What remains of "pricing" is:

* `product.selling_price` — **already built in M1**
* a bounded manual discount — requires `business_profile`, which does not exist
* "price resolution in `CORE`" — with one price list and no customer override, a single
  field read

A price resolution service with nothing to price can be unit-tested but not *verified*.
PO-6 — "identical price on every surface for identical inputs" — is unprovable while no
surface consumes it. M3 as scoped would ship a service whose only caller is a test, and
`00` §5.1 defines done as demonstrable, not merely passing.

**2. `business_profile` has no milestone.**

`04` T-05 specifies it, and two capabilities depend on it:

* `max_manual_discount_percent` — the bound pricing enforces (FR-PRC-017)
* `credit_limit_mode` — the switch order validation reads (DV-9)

It was deferred to M5 during M1 planning because invoices need the seller identity. Both
halves of this work need it sooner. This is the same class of gap as TD-15 (`offer`): a
table the design specifies that no milestone claims.

## Options

1. **Follow the roadmap.** M3 = pricing + `business_profile`; M4 = orders.
   Respects the frozen plan. Ships a milestone whose verification value is close to zero,
   and defers the only thing that would prove it correct.
2. **Merge into one milestone — Commercial Operations.** Pricing gains a real caller,
   PO-6 becomes verifiable, and `business_profile` has a home. Larger than any milestone
   so far (~3.0 units against M1's 2.5).
3. **Build orders first, pricing after.** Rejected: order lines snapshot a resolved price
   at capture (M3-1). Without resolution, orders would snapshot a raw field read and the
   rule would be retrofitted into an already-populated table.

## Decision

**Option 2.** M3 becomes **Commercial Operations**, comprising:

* `business_profile` — the tier-3 configuration singleton
* price resolution and the bounded manual discount
* `sales_order` and `sales_order_line`
* the order lifecycle
* credit validation
* order totals

M4 in the original numbering is absorbed. Later milestone numbers are unchanged: M5
remains Fulfilment & Billing, M6 Receivables, and so on. The roadmap now runs
M0, M1, M2, **M3 (Commercial Operations)**, M5, M6, M7, M8, M9, M10, M11, M12 — with no M4.

**Renumbering the remaining milestones was considered and rejected.** Every verification
report, ADR, `NEXT_TASK.md` entry and commit message referring to "M5" or "M6" would
become ambiguous, and the documents are immutable. A gap in the sequence is cheaper than
an ambiguity in the record.

### Boundary preserved

**An order represents commercial intent only. Inventory does not change until dispatch.**

No path in M3 writes a `stock_movement`. Stock is issued at dispatch, in M5. This is
stated as irreversible decision M3-6 in `M3_Design_Review.md` and is the boundary M2 was
built to protect: the ledger records physical fact, not commercial intention.

## Consequences

**Positive.** PO-6 becomes verifiable, because pricing has a real caller in the same
milestone. `business_profile` gains a home. One design review covers one complete business
capability rather than half of one.

**Negative.** The largest milestone so far (~3.0 units), so a longer interval between
verified checkpoints. Mitigated by the ADR-0005 task decomposition: the milestone is broken
into independently verifiable tasks, each committed and pushed.

**Also.** The milestone sequence has a gap at 4. Deliberate, per the decision above.

## Migration cost if reversed

*Low* — the work is the same work in either arrangement. Splitting it again would mean
choosing a commit boundary, not undoing anything.
