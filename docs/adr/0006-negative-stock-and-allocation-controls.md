# 0006 — Negative stock permitted in Edition 1; allocation controls deferred to Edition 2

Status: Accepted
Date: 2026-08-05
Deciders: Chief Systems Engineer, Product Architect
Related: `M2_Design_Review.md` D-2 · `02A` §7.4 · ADR-0013 (outbox sync)

## Context

An independent review of the M2 design proposed a configurable
`allow_negative_allocation` flag, to "re-evaluate the interaction between negative stock
and `SC-STOCK`" and avoid operational deadlocks for this distributor.

The proposal names two things that do not exist in Edition 1:

* **`SC-STOCK` does not exist in Edition 1.** Per ADR-0013 and `05` §11.4, only
  `SC-DUPLICATE` and `SC-SEQUENCE` exist, because field order capture was deferred
  (DV-1, `02A` §5). `SC-STOCK` arises when an *offline-captured order* meets insufficient
  stock at sync; there is no offline order capture in Edition 1. The review appears to
  have reasoned from `02` §5.3 — the frozen baseline — rather than from the `02A` §13
  Edition 1 re-validation that removed it.
* **Allocation does not exist in Edition 1.** `02A` §7.4 defers stock allocation and
  reservation to Edition 2. A flag governing allocation behaviour has nothing to govern.

## Options

1. **Permit negative on hand; report it; take no locks.** The Edition 1 design.
2. **Add `allow_negative_allocation` to `business_profile` now**, defaulting to permissive.
3. **Enforce non-negative stock unconditionally.**

## Decision

**Option 1 for Edition 1. Option 2 is deferred to Edition 2, where it belongs alongside
allocation.**

Three arguments, in order of weight.

**The frozen design already decided it.** `02A` §7.4 defers reservation; FR-STK-013
produces an outcome rather than a rejection.

**Blocking produces worse data than permitting.** A distributor's paperwork lags physical
reality. A system that refuses a dispatch the warehouse has already made teaches staff to
stop recording — and unrecorded movements are precisely the failure the ledger exists to
prevent. Negative on hand is a *signal* that paperwork is behind; the stock report surfaces
it and the owner reconciles.

**The deadlock argument inverts.** Edition 1 takes no locks on the stock path, so it has
**no deadlock surface at all**. Enforcing non-negative stock requires `SELECT ... FOR UPDATE`
on a lock anchor. The flag proposed to *avoid* deadlocks is the only thing that would create
the possibility of them.

Implementing the flag in M2 would additionally mean building Edition 2's allocation
machinery to service a switch nobody has asked to flip, and shipping a code path that is
never exercised — contrary to E-11 and D-01.

## Consequences

**Positive.** M2 stays lock-free and therefore deadlock-free. No untested branch ships. The
owner sees negative balances and reconciles them, which is the intended workflow.

**Negative.** An owner who wants hard enforcement has no option in Edition 1. Accepted: at
Edition 1 volume, dispatch is manual and owner-driven, and the reconciliation path is the
stock report.

**Deferred, not lost.** When Edition 2 adds allocation, the flag belongs on
`business_profile` (T-05) as tier-3 configuration (FD-12), and the lock anchor is the
`stock_lot` row — already present, because M2-2 carries `lot_id` from the first migration.
Adding a column to a config singleton later is an `ALTER TABLE` with a default: it fails the
§9.1 irreversibility test, so carrying it now would be speculative engineering.

## Migration cost if reversed

*Low* — one column on `business_profile`, plus the enforcement path in
`inventory.services`, which Edition 2 builds regardless.
