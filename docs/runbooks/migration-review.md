# Runbook — Migration review

Applies to **every** pull request that adds a migration. A migration is the least
reversible artefact in the codebase (`00` §15, MIG-10).

Paste this checklist into the pull request and tick it.

## Every migration

- [ ] One logical change (MIG-1)
- [ ] Not editing a migration that has run anywhere but a developer machine (MIG-2)
- [ ] Schema and data migrations are separate files (MIG-3)
- [ ] `makemigrations --check` passes (MIG-4)
- [ ] **No hardcoded schema name; applies cleanly to an empty schema** (MIG-8, N-09)
- [ ] Destructive change uses expand-and-contract (MIG-5, §15.2)
- [ ] Index on a large table created concurrently (MIG-6)
- [ ] Manual verified backup taken before production apply (MIG-7, B-6)

## If the migration creates a table with money or quantity

- [ ] `MoneyField` / `QuantityField` from `core.fields` — never a float (N-07, I-07)
- [ ] Every timestamp is `DateTimeField` with `USE_TZ` on (N-08, I-08)
- [ ] No `tenant_id` (I-04, ADR-007)

## If the migration creates `stock_movement` — M2

**This is the gate ADR-0004 exists for. CI enforces it; read it anyway.**

- [ ] `location_id`, defaulted to the seeded location (N-10, E-06)
- [ ] `lot_id`, defaulted to the per-product default lot (N-10, E-06)
- [ ] `CHECK (source_document_id IS NOT NULL OR reason_code_id IS NOT NULL)` (BR-007, N-05)
- [ ] `quantity <> 0`
- [ ] Composite index on `(product_id, location_id, lot_id)` — the balance query

> Adding these after stock history exists means re-keying the largest table in the
> system and every balance query over it. Cost today: two columns.

## If the migration touches a financial document

- [ ] No update path exists in any service for an issued document (N-04)
- [ ] Append-only tables carry a database trigger, not only a Python guard
