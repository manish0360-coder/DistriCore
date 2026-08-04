# 0004 — Defer the stock structural columns to M2, and enforce them by checklist

Status: Accepted
Date: 2026-08-04
Deciders: Chief Systems Engineer
Clarifies: `00_Engineering_Foundation.md` §15.3, §20.1 item 5, §20.2

## Context

Two frozen statements are in tension:

- `00` §20.1 item 5 — M0 delivers "`0001_initial` satisfying every item of §15.3", and §15.3
  requires `location_id` and `lot_id` on `stock_movement`.
- `00` §20.2 — M0 explicitly contains "No stock."

Django creates one `0001_initial` **per application**. There is no single project-wide initial
migration, so "`0001_initial`" is ambiguous: `core/0001_initial`, `identity/0001_initial` and later
`inventory/0001_initial` are all initial migrations.

Creating an empty `stock_movement` table in M0 would implement a business feature ahead of its
milestone, violating C-2 (one logically complete milestone at a time).

## Options

1. **Read §15.3 as a checklist applying to the initial migration of each affected table**, and bind
   it to M2 with an enforced review gate.
2. Create the inventory tables in M0. Violates §20.2 and C-2, and ships an unused table with no
   service layer, no tests and no meaning.
3. Drop the requirement. Unacceptable — E-06 rates the reversal cost as High.

## Decision

Option 1. §15.3 is a checklist for the first migration that creates each affected table.

M0 satisfies the items that apply to it now:

- no `tenant_id` on any table (I-04)
- no hardcoded schema name in any migration (N-09, I-04)
- every timestamp `timestamptz` (N-08, I-08)
- exact decimal field types defined once in `core.fields` (N-07, I-07)
- `audit_log` append-only, enforced by a database trigger (I-12)

M2 carries the remainder, enforced by:

- `docs/runbooks/migration-review.md`, which the M2 pull request must link to as completed
- a CI check that fails if a migration creates `stock_movement` without `location_id` and `lot_id`

## Consequences

Positive: M0 stays a foundation; the structural obligation becomes an automated gate rather than a
remembered intention. Negative: the requirement now lives in CI rather than in one migration file —
which is stronger, but only if the CI check is written. It is part of M0.

## Migration cost if reversed

High — reversing means adding the dimensions after stock history exists (E-06).
