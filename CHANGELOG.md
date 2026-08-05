# Changelog

Generated from Conventional Commits (`00` §6.2). Versions follow SemVer (FD-18).

## [Unreleased]

### M2 — Inventory & stock ledger

**Added**

- `stock_location` — structural enabler (M2-1). One seeded row, no UI. Multi-warehouse
  (EP-A) becomes an Edition 2 feature rather than a migration of live history.
- `stock_lot` — structural enabler (M2-2). Default lot created lazily on first movement by
  select-then-upsert: one query on the hot path, no savepoint, race-free.
- `stock_movement` — **the single source of truth for inventory.** Signed quantity,
  append-only, with four database CHECK constraints: source-or-reason (BR-007),
  non-zero, paired source reference, and sign-per-type for RECEIPT/ISSUE (M2-11).
- Append-only enforced at four layers: instance save, instance delete, queryset
  update/delete, and a PostgreSQL trigger. Seven adversarial tests attack all four.
- `inventory.services` — `receive_stock`, `issue_stock`, `adjust_stock` and
  `record_manual_movement`. The only writer of a stock movement in the codebase.
- Derived on-hand selectors anchored on `Product` with `Coalesce` to a typed zero, so a
  product with no movements returns `0.000` rather than disappearing from the report.
  Includes balance `as_of` any past instant, and a negative-stock report.
- `GET /api/v1/stock`, `GET`/`POST /api/v1/stock/movements`.
- Owner screens: stock on hand, movement ledger, and a single stock-entry form.
- **TD-12 closed** — zone create and edit screens. The customer form's zone dropdown was
  unfillable on a fresh install.
- **TD-13 closed** — product image upload in the admin form.
- 53 tests (192 -> 245); coverage 93.01% -> 93.56%.

**Changed**

- `import-linter` layers corrected to `api|webadmin > inventory > catalogue|customers >
  identity > core`, matching `03` §2.1. The previous contract was stricter than the
  architecture it encoded and forbade `inventory` from calling `catalogue`.
- Movement-type dispatch moved from the API view into
  `inventory.services.record_manual_movement`. The branch was a business rule (sign per
  type) sitting in a delivery layer.
- Media purpose constants re-exported from `core.media` so no delivery layer imports the
  model.

**Decisions**

- ADR-0005 — AI-assisted development workflow.
- ADR-0006 — negative stock permitted in Edition 1; allocation controls deferred to
  Edition 2.
- `M2_Design_Review.md` frozen before implementation: D-1 (lazy upsert lot), D-2 (no locks,
  negatives permitted), D-3 (audit iff ADJUSTMENT), R-1 (dimension-anchored aggregates),
  R-2 (validated source instances), M2-1…M2-11 irreversible.

### M1 — Master data

**Added**

- `customers` module: `Zone` (road, PIN code, panchayat, ward, city) and `Customer`
  (credit terms, coordinates, zone assignment), with scoping selectors.
- `catalogue` module: `Product` with pack size, GST rate, HSN code, selling price and
  image reference; base-unit conversion.
- `inventory` module: `ReasonCode` with 8 seeded rows. Stock ledger deferred to M2.
- `core.MediaFile`: single upload path with content sniffing, size limits, SHA-256, and
  retrieval only through an authorised view.
- Eight API endpoints: products (list/create/read/update), customers (list/create/read/
  update), zones, reason codes, media upload and retrieval.
- Eight owner screens: product and customer lists with search and forms, zone and reason
  code lists.
- `app_user.customer` foreign key — retailer logins are now bound to a shop (closes TD-5).
- 92 tests (100 -> 192); coverage 87.3% -> 93.01%.

**Fixed**

- **Money had no canonical representation.** `MoneyField(default=0)` placed an `int` on
  freshly created instances, so audit records wrote `"0"` where the database returned
  `"0.00"`. Rounding is now defined once in `core.fields` (`to_money`, `to_quantity`,
  `to_percent`, half-up) and applied where values enter the domain. `record_audit()`
  canonicalises `Decimal` recursively. No migration required — only the in-memory value
  was wrong.
- `CheckConstraint` for paired coordinates used `Q == Q`, which evaluates to a Python
  bool rather than an expression.
- `MediaDetailView` imported a model inside a method body, breaking the N-02 import
  contract.

**Security**

- Retailer scoping derived from the token; endpoints accept no `customer_id` (AD-11).
- Scope violations return 404, never 403, so record existence is not disclosed.
- Credit limit and price changes are owner-only with dedicated audit actions.
- Uploads validated on content signature, not on extension or client header.

### M0 — Foundation

**Added**

- Project scaffolding: Docker Compose (dev/prod), multi-stage non-root image, Caddy with
  automatic TLS, Makefile as the sole developer interface, GitHub Actions CI.
- `core` module: `TimeStampedModel`, append-only `AuditLog`, exact numeric field types,
  request-id correlation middleware, role primitives, storage seam, `/healthz`.
- `identity` module: custom user model keyed on mobile number, four seeded roles,
  many-to-many role assignment, OTP request/verify with hashed codes and rate limiting,
  password authentication, SMS provider interface (console / MSG91).
- `api/v1`: six authentication endpoints, RFC 9457 problem+json error handling,
  page-number pagination, scoped throttling.
- `webadmin`: server-rendered login, logout and placeholder shell.
- Structured JSON logging to stdout with request-id correlation; Sentry wiring.
- Runbooks: deploy, restore, rotate secrets, incident response, migration review.
- 47 tests across unit, integration and adversarial suites.

**Security**

- Argon2 password hashing; OTP codes stored hashed, never plaintext.
- `audit_log` immutability enforced in Python, by database trigger, and by test.
- Production settings refuse to start on unsafe configuration.
- Three-layer secret scanning: `.gitignore`, pre-commit, CI.
