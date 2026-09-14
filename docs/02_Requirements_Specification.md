# DistriCore — Requirements Specification

| Field | Value |
| --- | --- |
| Document ID | `02_Requirements_Specification` |
| Product | DistriCore (working title) |
| Version | **0.4.0** |
| Status | **Draft — pending stakeholder sign-off** |
| Date | 2026-08-04 · amended 2026-08-08 · **amended 2026-08-21** |
| Owner | Product Architecture |
| Depends on | `01_Project_Vision.md` v0.2.0 |
| Audience | Engineering, QA, business owner |

> **Amendment in v0.4.0, recorded 2026-09-14.** **S-9** — FR-SYN-010's 2-minute bound is
> **foreground-scoped for Edition 1/V1**. The requirement named no application state; a Product
> Architect ruling (`M9_Design_Review.md` §6 D-M9-12) resolves that silence: the bound applies
> while the application is in the foreground and connectivity has been restored, and background
> / suspended / Doze / App Standby synchronisation is best-effort in V1, not part of the
> acceptance criterion. **No `WorkManager`/`JobScheduler`/foreground-service mechanism is added.**
> `NFR-PER-004`'s existing device measurement (B1, PASSED 2026-09-06, foreground) is therefore
> the complete V1 verification, not a partial one awaiting a background counterpart. **Priority
> `M` and release `v1.0` unchanged; requirement text unchanged; nothing deleted.** See §18.1 S-9.
>
> **Amendment in v0.4.0, recorded 2026-09-14.** **S-8** — FR-SYN-007's stock-snapshot clause
> moves to `Rel = v2.0`; customers, products, prices and schemes in the same requirement are
> unaffected. `02A` §5's DV-1 removed field order capture from Edition 1, and no remaining
> Edition-1 mobile workflow checks stock availability or contends for it — the requirement's
> own justification has no subject. This is an **Architect ruling** (D-M9-11), closing `05`
> D-M9.4-1's recorded CONTRACT GAP by removing what it was gapped against. **Priority `M`
> unchanged; the rest of FR-SYN-007's text unchanged; nothing deleted.** See §18.1 S-8.
>
> **Amendment in v0.4.0, recorded 2026-09-14.** **S-6** — FR-SYN-009 moves to `Rel = v2.0`.
> The gap the previous paragraph names — *"an independent `S1` gap awaiting its own
> ruling"* — was closed the same day it was written: `M9_Design_Review.md` §6 D-M9-7
> (v1.2.0) ruled it later on 2026-08-21 than D-M9-6 (v1.1.0), which is what this document had
> been amended against. This row is that later ruling, transcribed. **Priority `M` unchanged;
> requirement text unchanged; nothing deleted.** See §18.1 S-6.
>
> **Amendment in v0.4.0.** **S-5** — FR-SYN-008's third field read *"count of unresolved
> conflicts"*, a phrase this document used twice and defined nowhere, and which the existing
> implementation already represented as `rejected_count`. It now reads *"count of operations the server
> has rejected"*, which names a quantity `05` §11.5 already specifies as `rejected_count` and
> `05` §11.2 already requires be flagged to the user. **Priority `M` and release `v1.0`
> unchanged; no API field is added or renamed.** Authority: `docs/M9_Design_Review.md` §6
> D-M9-6 (v1.1.0). **FR-SYN-009 carried the same undefined phrase and was deliberately not
> amended here** — it was, at the time this paragraph was written, an independent `S1` gap
> awaiting its own ruling. **Now closed — see the S-6 paragraph above.**
>
> **Amendments in v0.3.0.** M9 established that the synchronisation block, like the
> receivables and reporting blocks before it, was written against the frozen baseline and
> never back-updated after `02A` §5 / DV-1 removed field order capture from Edition 1.
> **§18.1** records four amendments — **S-1** (FR-SYN-005, `M`/`v1.0` unchanged), **S-2**
> (FR-SYN-013 and FR-SYN-014 → `v2.0`), **S-3** (BR-014's Edition-1 vehicle), **S-4** (§5.3's
> four human classes are Edition 2, and FR-SYN-006 quarantine is distinct from that taxonomy).
> Authority: `docs/M9_Design_Review.md` §6, signed 2026-08-21.
>
> **Minor, not patch.** `M8_Design_Review` 1.6.1 states the corpus rule when it declines a
> minor bump — *"Patch version, not minor: **no architectural decision changed**"*. S-2 moves
> two `M`/`v1.0` requirements to `v2.0`, which is the same class of change that took this
> document from 0.1.0 to 0.2.0.
>
> **Amendments in v0.2.0.** Implementation through M6 established behaviour that eight
> requirement lines in this document no longer described. They are corrected in place, with
> the reasoning recorded beside the block it affects: **§14.1** (receivables — FR-REC-004,
> 006, 008) and **§20.1** (reporting — FR-RPT-001, 002, 006, 007, 009, 010). §26 OI-4 is
> closed and OI-6 re-dated.
>
> **No requirement was deleted.** Deferred lines carry `Rel = v2.0` and remain readable, so
> that scope which was considered and postponed cannot be mistaken for scope that was
> overlooked.

> **Authority.** This document specifies *what* DistriCore must do. It does not specify *how*. Component structure, technology choices, database schema and the synchronisation wire protocol belong to `03_System_Architecture.md`.
>
> **Precedence.** Where this document and the Project Vision conflict, the Vision governs scope and the decisions DR-1 … DR-10 (Vision §16.2, C-15); this document governs behaviour. Where either conflicts with code, the documents win (C-1).
>
> **No invented requirements.** Every requirement traces to confirmed scope (Vision §7) or to a recorded decision. Where behaviour genuinely cannot be derived, it is listed in §16 as an open item rather than specified speculatively (C-3).

---

## 1. Introduction

### 1.1 Purpose

To define the complete set of functional and non-functional requirements for DistriCore releases v1.0, v1.1 and v1.2, at a level of precision sufficient for architecture, implementation, test design and acceptance.

### 1.2 Scope of this document

Covers the confirmed scope of Vision §7: four client surfaces (S1–S4) and twelve functional domains (D1–D12), allocated across releases per Vision §7.4. Excludes everything in Vision §8.

### 1.3 How to read a requirement

Each requirement is atomic, testable and independently verifiable. A requirement that cannot be failed by a test is not a requirement — it is an aspiration, and does not belong here.

---

## 2. Conventions

### 2.1 Identifiers

| Prefix | Meaning |
| --- | --- |
| `FR-<DOM>-<nnn>` | Functional requirement, within a domain |
| `NFR-<CAT>-<nnn>` | Non-functional requirement |
| `BR-<nnn>` | Business rule — an invariant referenced by multiple requirements (§14) |
| `PO-n`, `DR-n`, `C-n`, `NFR-n`, `R-n`, `O-n`, `CF-n` | References into `01_Project_Vision.md` |

Domain codes:

| Code | Domain | Vision ref |
| --- | --- | --- |
| `IAM` | Identity, roles & access control | D9 |
| `CUS` | Customer management | D1 |
| `PRD` | Product master data | D2 |
| `STK` | Inventory & stock movement | D2 |
| `PRC` | Pricing, schemes & discounts | D7 |
| `ORD` | Order management | D3 |
| `FUL` | Fulfilment & delivery | D3 |
| `BIL` | Invoicing & credit notes | D4 |
| `REC` | Receivables & collections | D6 |
| `PUR` | Purchasing & suppliers | D5 |
| `RET` | Returns | D2, D5 |
| `TGT` | Sales targets & performance | D8 |
| `SYN` | Synchronisation | D10 |
| `AUD` | Audit & traceability | D11 |
| `RPT` | Reporting | D12 |

**Identifiers are permanent.** A withdrawn requirement is marked `WITHDRAWN` and its number is never reused, so that test suites and commit messages referencing it remain unambiguous.

### 2.2 Priority

| Level | Meaning |
| --- | --- |
| **M** | Must — the release is not acceptable without it |
| **S** | Should — high value; may be descoped only by explicit decision |
| **C** | Could — included if it does not jeopardise M and S |

Priority is scoped to the release in the *Rel* column. An `M` at v1.1 does not make the release v1.0 unacceptable.

### 2.3 Surfaces

`S1` back-office · `S2` field-sales app · `S3` van app · `S4` retailer portal · `CORE` server-side, surface-independent.

**Rule BR-001 applies throughout: business rules are enforced in `CORE`.** A rule implemented only in a client surface is a defect regardless of whether the client behaves correctly.

### 2.4 Keywords

**MUST** / **MUST NOT** denote absolute requirements. **SHOULD** denotes a requirement that may be traded off only with recorded justification. **MAY** denotes optionality.

---

## 3. Actors and Authorisation

### 3.1 Actors

Per Vision §5. `SYSTEM` is added for scheduled and internally triggered operations, which are audited identically to human actors (BR-002).

| Code | Actor | Vision | Primary surface |
| --- | --- | --- | --- |
| `OWNER` | Business owner / proprietor | U1 | S1 |
| `SALESMGR` | Sales / operations manager | U2 | S1 |
| `SALESMAN` | Field salesman | U3 | S2 |
| `DELIVERY` | Delivery / van staff | U4 | S3 |
| `WAREHOUSE` | Warehouse / inventory staff | U5 | S1 |
| `ACCOUNTS` | Accounts / billing staff | U6 | S1 |
| `PURCHASE` | Purchase officer | U7 | S1 |
| `RETAILER` | Retailer (external) | U8 | S4 |
| `ADMIN` | System administrator | U9 | S1 |
| `SYSTEM` | Automated operation | — | CORE |

### 3.2 Authorisation matrix

Default v1.0 role definitions. Roles are **data, not code** (NFR-11) — this matrix is the seeded default, and `ADMIN` may vary it within the permission model.

Legend: ● full · ◐ own records only · ○ read-only · — no access

| Capability | OWNER | SALESMGR | SALESMAN | DELIVERY | WAREHOUSE | ACCOUNTS | PURCHASE | RETAILER | ADMIN |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| Customer master | ● | ● | ○ | ○ | — | ○ | — | — | ● |
| Customer credit limit | ● | ○ | — | — | — | ○ | — | — | ○ |
| Product master | ● | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● |
| Price lists & schemes | ● | ● | ○ | — | — | ○ | — | ○ | ○ |
| Order — create | ● | ● | ◐ | — | — | ● | — | ◐ | — |
| Order — approve | ● | ● | — | — | — | — | — | — | — |
| Order — cancel | ● | ● | ◐ | — | — | ● | — | ◐ | — |
| Stock — view | ● | ● | ○ | ○ | ● | ○ | ● | — | ● |
| Stock — adjust | ● | — | — | — | ● | — | — | — | ○ |
| Fulfilment (pick/dispatch) | ● | ○ | — | ○ | ● | ○ | — | — | ○ |
| Delivery & POD | ● | ○ | — | ◐ | ○ | ○ | — | ○ | ○ |
| Invoice — issue | ● | — | — | — | — | ● | — | — | — |
| Credit note — issue | ● | — | — | — | — | ● | — | — | — |
| Payment — record | ● | ○ | — | ◐ | — | ● | — | ○ | — |
| Receivables & aging | ● | ● | ◐ | — | — | ● | — | ◐ | ○ |
| Purchase orders | ● | ○ | — | — | ○ | ○ | ● | — | ○ |
| Goods receipt | ● | — | — | — | ● | ○ | ● | — | ○ |
| Sales targets *(v1.1)* | ● | ● | ◐ | — | — | — | — | — | ○ |
| Users, roles, devices | ● | — | — | — | — | — | — | — | ● |
| Audit log | ● | ○ | — | — | — | ○ | — | — | ● |
| System configuration | ● | — | — | — | — | — | — | — | ● |

> **Note on `ADMIN`.** The administrator manages identity and configuration but has no authority over financial documents or credit limits. This is a deliberate separation of duties: the person who can grant access must not also be able to alter what money is owed. `OWNER` is the only role with unrestricted authority, and its actions are audited without exception (BR-002).

> **Note on `RETAILER` (◐).** External actors are constrained to their own records by a `CORE` authorisation check on every request, never by the portal's navigation (BR-003). The portal is outside the internal trust boundary (Vision §12.5).

---

## 4. Conceptual Domain Model

Entities and relationships only. **No physical schema, no keys, no types** — those belong to `03_System_Architecture.md`.

### 4.1 Entity groups

**Identity** — `Tenant`, `User`, `Role`, `Permission`, `Device`, `Session`

**Party** — `Customer`, `CustomerCategory`, `Route`, `Supplier`

**Catalogue** — `Product`, `ProductCategory`, `UnitOfMeasure`, `UomConversion`, `TaxCode`, `TaxRate`

**Inventory** — `StockLocation`, `Lot`, `StockMovement`, `ReasonCode`

**Pricing** — `PriceList`, `PriceListItem`, `CustomerPrice`, `Scheme`, `SchemeSlab`

**Selling** — `SalesOrder`, `SalesOrderLine`, `ApprovalRule`, `ApprovalRequest`

**Fulfilment** — `Shipment`, `ShipmentLine`, `ProofOfDelivery`

**Billing** — `Invoice`, `InvoiceLine`, `InvoiceTaxLine`, `CreditNote`, `NumberSeries`

**Settlement** — `Payment`, `PaymentAllocation`, `CustomerLedgerEntry`, `SupplierLedgerEntry`

**Procurement** — `PurchaseOrder`, `PurchaseOrderLine`, `GoodsReceipt`, `GoodsReceiptLine`

**Returns** — `SalesReturn`, `SalesReturnLine`, `PurchaseReturn`, `PurchaseReturnLine`

**Performance** *(v1.1)* — `SalesTarget`, `TargetPeriod`

**Synchronisation** — `SyncBatch`, `SyncTransaction`, `SyncConflict`

**Audit** — `AuditEvent`

### 4.2 Structural enablers

Per C-14, three dimensions are present in the v1.0 model although the capabilities they support are not built. **Omitting any of them converts a later feature into a re-architecture.**

| Dimension | Present on | v1.0 behaviour | Enables |
| --- | --- | --- | --- |
| `Tenant` | Every tenant-scoped entity | Exactly one tenant, seeded | Multi-tenant activation (v2.0, C-13) |
| `StockLocation` | Every `StockMovement` | Exactly one location, seeded as default | Multi-location operations (v1.1, DR-2) |
| `Lot` | Every `StockMovement` | Implicit default lot per product; `Product.trackingPolicy = NONE` | Batch/serial tracking (v1.1, DR-4) |

### 4.3 Ledger invariants

These four invariants define the system's integrity model. Every requirement in this document is consistent with them, and any design that violates one is rejected regardless of other merit.

| ID | Invariant |
| --- | --- |
| **BR-001** | All business rules — pricing, credit, stock, tax, approval — are evaluated in `CORE`. Clients may replicate a rule for responsiveness or offline operation, but the client result is never authoritative (Vision §4.1). |
| **BR-002** | Every state-changing operation records an `AuditEvent` bearing actor, role, timestamp, surface, device (where applicable) and the before/after state. Audit records are append-only and are never deleted or edited. |
| **BR-003** | Authorisation is evaluated in `CORE` on every request against the acting user's role and record ownership. Client-side hiding of a control is a usability measure, never an access control. |
| **BR-004** | **Stock on hand is derived, never stored as an independently mutable figure.** The balance for any *(product, location, lot)* is the sum of its `StockMovement` records. A cached balance is permissible for performance only if it is reconstructible from movements and reconciled automatically. |
| **BR-005** | **Customer and supplier balances are derived, never stored as an independently mutable figure.** A balance is the sum of that party's ledger entries. The same caching condition as BR-004 applies. |
| **BR-006** | **Issued financial documents are immutable.** An `Invoice` or `CreditNote`, once issued, is never edited or deleted. Correction is by issuing a further document (Vision NFR-1). |
| **BR-007** | Every `StockMovement` references a source document (order, shipment, goods receipt, return) or a `ReasonCode`. **A movement with neither is rejected.** This is what makes PO-5 ("every divergence explained") achievable rather than aspirational. |

---

## 5. Offline and Synchronisation Semantics

This section governs every requirement marked `S2` or `S3`. It resolves R-1 — the highest-severity risk in the programme — and is placed before the functional domains because those domains cannot be read correctly without it.

### 5.1 The governing principle

> **An order captured offline is a request, not a commitment. Authority to confirm rests solely with `CORE`.**

Every consequence below follows from this one sentence. Attempting to make an offline client authoritative over stock or credit is the failure mode that corrupts inventory and receivables, and it is prohibited (BR-001).

### 5.2 Consequences

| ID | Rule |
| --- | --- |
| **BR-010** | **Offline clients do not reserve stock.** Stock availability displayed on `S2`/`S3` is an *advisory snapshot* from the last successful sync and MUST be labelled as such in the interface, with the snapshot time visible. |
| **BR-011** | **Prices and schemes computed offline are quoted, not agreed.** The client stores the computed price on the order line as `quotedUnitPrice`. `CORE` recomputes on sync (BR-001). Where the recomputed price differs, `CORE` MUST record both values and raise a variance — it MUST NOT silently substitute either. |
| **BR-012** | **Every offline-created record carries a client-generated identifier**, assigned at creation on the device. `CORE` treats this identifier as the idempotency key. Re-transmission of an already-accepted record is acknowledged as accepted and creates nothing. |
| **BR-013** | **Sync is idempotent and ordered per device.** Replaying a batch produces no duplicates. Transactions from one device are applied in the order the device created them. |
| **BR-014** | **No transaction is discarded.** A transaction that fails server-side validation is persisted as a `SyncConflict` in `PENDING_RESOLUTION`, never dropped. Silent loss is a critical defect (Vision §10.3, non-negotiable). **[S-3 — Edition-1 vehicle: `sync_operation` with `status = 'REJECTED'`, retained `payload` and a non-empty `error_code`, enforced by `ck_sync_operation_rejected` (`04` T-26). The no-discard guarantee is unchanged; only the named artefact.]** |
| **BR-015** | **Conflict resolution is explicit, never automatic**, except for the deterministic classes in §5.3. Anything else is routed to a human with sufficient context to decide. |

### 5.3 Conflict taxonomy

Detected by `CORE` at sync time. Every class has a defined, testable outcome.

| Class | Condition at sync | Resolution | Automatic? |
| --- | --- | --- | --- |
| `SC-DUPLICATE` | Client identifier already accepted (BR-012) | Acknowledge as accepted; create nothing | Yes — deterministic |
| `SC-STOCK` | Ordered quantity exceeds available stock at sync time | Order accepted into `CONFIRMED_SHORT`; shortfall flagged for `SALESMGR`/`WAREHOUSE`. **The order is never silently reduced or rejected** | No |
| `SC-CREDIT` | Order breaches credit limit against the balance current at sync time | Routed to `PENDING_APPROVAL` per DR-10 | No |
| `SC-PRICE` | `quotedUnitPrice` differs from recomputed price (BR-011) | Order held in `PRICE_VARIANCE`; both prices retained; `SALESMGR` decides | No |
| `SC-MASTER` | Customer or product deactivated after the device's last sync | Order held in `MASTER_STALE`; `SALESMGR` decides | No |
| `SC-SEQUENCE` | Transaction depends on a prior transaction not yet accepted | Held; retried automatically once its dependency is accepted | Yes — deterministic |

> **Design note.** `SC-STOCK` deliberately does not reject the order. A salesman standing in front of a retailer has made a commercial commitment; the correct response to a stock shortfall is a business decision (partial fulfilment, substitution, backorder), not silent data loss. This is the practical meaning of BR-014.

> **Amendment S-4, 2026-08-21.** **The four non-automatic classes — `SC-STOCK`, `SC-CREDIT`,
> `SC-PRICE`, `SC-MASTER` — are Edition 2.** Each is defined over an offline-captured *order*,
> and `02A` §5 / DV-1 removes field order capture from Edition 1: the taxonomy collapses to
> `SC-DUPLICATE` and `SC-SEQUENCE`, both deterministic and both automatic. `04` T-26 carries
> the four forward as future `status` values plus a `conflict_type` column. **The table above
> is unchanged and nothing is deleted** — a class deferred is still a class, and Edition 2
> restores all four with the capability that creates them.
>
> **FR-SYN-006 quarantine is not part of this taxonomy.** Every class above describes a
> transaction that is well-formed and authorised but **contends with server state that has
> moved on** — stock, credit, price, master data, ordering, or a prior acceptance. A
> malformed, invalid or unauthorised operation contends with nothing, and FR-SYN-006 already
> covers it separately: *"quarantined and reported rather than dropped"*. Its reason is
> carried in `sync_operation.error_code`, which is **not** an `SC-*` value. **No new class is
> created by this amendment.**
>
> **This distinction is a ruling, not a restatement.** `M9_Design_Review` §6 D-M9-3 records
> that this document did not previously draw it, that FR-SYN-005's *"every rejected
> transaction"* read wider than this taxonomy can support, and that the ambiguity was
> resolved by choosing rather than by discovery.

### 5.4 Sync observability

Nothing fails silently (Vision §12.4). Sync state MUST be visible to the device user and to `SALESMGR`/`ADMIN` in `S1`.

---

## 6. Identity, Roles & Access Control (D9 — `IAM`)

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-IAM-001 | Every user MUST authenticate with a unique identifier and a secret before any other operation. | M | v1.0 | ALL | NFR-5 |
| FR-IAM-002 | Passwords MUST be stored using a current, deliberately slow password-hashing function with a per-user salt. Reversible encryption or general-purpose hashes MUST NOT be used. | M | v1.0 | CORE | NFR-5 |
| FR-IAM-003 | The system MUST enforce a configurable password policy: minimum length, complexity, and rejection of a maintained list of common passwords. | M | v1.0 | CORE | NFR-5, NFR-11 |
| FR-IAM-004 | Repeated failed authentication attempts MUST trigger progressive rate limiting, and MUST NOT reveal whether the identifier exists. | M | v1.0 | CORE | NFR-5 |
| FR-IAM-005 | The system MUST support role assignment per user; a user MUST hold at least one role. | M | v1.0 | S1 | §3.2 |
| FR-IAM-006 | Roles MUST be defined as data, comprising a named set of permissions. Adding a role MUST NOT require code change. | M | v1.0 | S1 | NFR-11, C-12 |
| FR-IAM-007 | `CORE` MUST authorise every request against the acting user's permissions and record ownership, independently of the requesting surface. | M | v1.0 | CORE | BR-003 |
| FR-IAM-008 | Sessions MUST expire after a configurable period of inactivity, and MUST be revocable by `ADMIN` and `OWNER` with immediate effect. | M | v1.0 | CORE | NFR-5 |
| FR-IAM-009 | Every device used for offline operation MUST be individually registered, bound to one user, and uniquely identifiable in every transaction it produces. | M | v1.0 | CORE, S2 | NFR-5, BR-002 |
| FR-IAM-010 | `ADMIN` and `OWNER` MUST be able to revoke a device, after which `CORE` rejects its sync attempts and the device MUST erase its local business data at the next contact. | M | v1.0 | CORE, S2 | NFR-5, R-8 |
| FR-IAM-011 | A user MUST be deactivable without deletion; deactivation MUST NOT remove or alter any transaction the user created. | M | v1.0 | S1 | BR-002, BR-006 |
| FR-IAM-012 | `RETAILER` accounts MUST be provisioned against exactly one `Customer` and MUST NOT be able to access any other customer's data under any request. | M | v1.2 | CORE, S4 | BR-003 |
| FR-IAM-013 | Users MUST be able to change their own password; changing it MUST invalidate all other active sessions for that user. | M | v1.0 | ALL | NFR-5 |
| FR-IAM-014 | The system MUST support a break-glass procedure for recovering `OWNER` access, and every use of it MUST be audited as a distinct high-severity event. | S | v1.0 | CORE | NFR-5, BR-002 |
| FR-IAM-015 | Authentication credentials MUST NOT be written to logs, audit records, error messages or crash reports. | M | v1.0 | ALL | NFR-5 |
| FR-IAM-016 | Offline surfaces MUST authenticate the user locally against cached credential material for a configurable maximum offline period, after which sync is required to continue. | M | v1.0 | S2, S3 | NFR-2, NFR-5 |

**Verification focus.** FR-IAM-007 is verified by attempting every capability in §3.2 with every role via direct API calls, bypassing the client entirely. A test that exercises authorisation only through the UI does not verify this requirement.

---

## 7. Customer Management (D1 — `CUS`)

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-CUS-001 | The system MUST maintain a customer master: identifying code, legal and trading name, contact details, addresses, and tax registration identifiers where applicable. | M | v1.0 | S1 | D1 |
| FR-CUS-002 | Customers MUST be assignable to a `CustomerCategory`, which is usable as a determinant in pricing and scheme eligibility. | M | v1.0 | S1 | D7 |
| FR-CUS-003 | Customers MUST be assignable to a `Route`. A customer MAY belong to at most one route at a time. | M | v1.0 | S1 | A-4 |
| FR-CUS-004 | Each customer MUST carry credit terms: a credit limit amount and a payment period in days. | M | v1.0 | S1 | PO-4 |
| FR-CUS-005 | Only `OWNER` MUST be permitted to set or change a credit limit. Every change MUST be audited with previous and new value. | M | v1.0 | CORE | §3.2, BR-002 |
| FR-CUS-006 | The system MUST derive each customer's outstanding balance from ledger entries and MUST NOT maintain it as an independently editable field. | M | v1.0 | CORE | BR-005 |
| FR-CUS-007 | The system MUST expose, for any customer: credit limit, current outstanding balance, and available credit (limit less outstanding). | M | v1.0 | CORE | PO-4 |
| FR-CUS-008 | Customers MUST be deactivable. A deactivated customer MUST NOT accept new orders, MUST retain full transaction history, and MUST remain visible in reporting. | M | v1.0 | S1 | BR-006 |
| FR-CUS-009 | Deleting a customer with any transaction history MUST be rejected. Deactivation (FR-CUS-008) is the only permitted disposition. | M | v1.0 | CORE | NFR-1 |
| FR-CUS-010 | `SALESMAN` MUST see, on `S2`, only customers on routes assigned to that salesman. | M | v1.0 | CORE, S2 | BR-003 |
| FR-CUS-011 | The system MUST produce a customer statement of account for any date range: opening balance, transactions, closing balance. | M | v1.0 | S1 | D6, D12 |
| FR-CUS-012 | `RETAILER` MUST be able to view their own statement of account. | M | v1.2 | S4 | U8 |
| FR-CUS-013 | Customer master data MUST be replicated to `S2` for assigned routes only, minimising data resident on field devices. | M | v1.0 | S2 | NFR-5, R-8 |
| FR-CUS-014 | The system MUST prevent creation of two active customers sharing the same identifying code. | M | v1.0 | CORE | NFR-1 |
| FR-CUS-015 | A customer MUST support a distinct billing address and delivery address. | S | v1.0 | S1 | D1 |

---

## 8. Product & Catalogue Master Data (D2 — `PRD`)

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-PRD-001 | The system MUST maintain a product master: identifying code, description, category, base unit of measure, and active status. | M | v1.0 | S1 | D2 |
| FR-PRD-002 | Products MUST support multiple units of measure with defined conversion factors to the base unit (e.g. case → piece). All stock MUST be held internally in the base unit. | M | v1.0 | CORE | A-11 |
| FR-PRD-003 | Conversion factors MUST be immutable once any transaction references the product in a non-base unit. Changing a factor retrospectively would silently alter historical quantities. | M | v1.0 | CORE | NFR-1 |
| FR-PRD-004 | Each product MUST carry a `TaxCode` used by the tax engine (FR-BIL-010). | M | v1.0 | S1 | DR-1 |
| FR-PRD-005 | Each product MUST carry a `trackingPolicy` with values `NONE`, `BATCH`, `SERIAL`. v1.0 MUST accept only `NONE`; the field MUST exist and be persisted. | M | v1.0 | CORE | DR-4, C-14 |
| FR-PRD-006 | The system MUST reject an attempt to set `trackingPolicy` to `BATCH` or `SERIAL` in v1.0, with an explicit "not enabled in this release" error rather than a generic validation failure. | M | v1.0 | CORE | DR-4 |
| FR-PRD-007 | Changing `trackingPolicy` on a product with existing stock movements MUST be rejected. | M | v1.0 | CORE | NFR-1, DR-4 |
| FR-PRD-008 | Products MUST be deactivable; a deactivated product MUST NOT be orderable but MUST retain history and remain reportable. | M | v1.0 | S1 | BR-006 |
| FR-PRD-009 | Deleting a product with any stock movement or transaction history MUST be rejected. | M | v1.0 | CORE | NFR-1 |
| FR-PRD-010 | Products MUST be organisable into a category hierarchy usable for reporting and scheme eligibility. | S | v1.0 | S1 | D7, D12 |
| FR-PRD-011 | The product catalogue MUST be replicated to `S2` and `S3` for offline operation. | M | v1.0 | S2, S3 | NFR-2 |
| FR-PRD-012 | The system MUST prevent creation of two active products sharing the same identifying code. | M | v1.0 | CORE | NFR-1 |
| FR-PRD-013 | Products MUST support an optional supplier association for purchasing (FR-PUR-002). | S | v1.0 | S1 | D5 |
| FR-PRD-014 | `RETAILER` MUST see, on `S4`, only active products for which a price is resolvable for that customer. | M | v1.2 | CORE, S4 | D7 |

> **On FR-PRD-005 / FR-PRD-006.** These two requirements are the entire v1.0 cost of DR-4 at the catalogue level: one persisted field and one explicit rejection. That is the price of keeping batch and serial tracking a v1.1 configuration exercise rather than a v1.1 re-architecture (R-13, C-14).

---

## 9. Inventory & Stock Movement (D2 — `STK`)

### 9.1 Model

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-STK-001 | Every stock change MUST be recorded as an immutable `StockMovement` bearing product, stock location, lot, signed quantity in base unit, timestamp, actor, and source document or reason code. | M | v1.0 | CORE | BR-004, BR-007 |
| FR-STK-002 | Stock on hand for any *(product, location, lot)* MUST be derived from the sum of its movements. No independently mutable quantity field may exist. | M | v1.0 | CORE | BR-004, PO-5 |
| FR-STK-003 | A `StockMovement` MUST NOT be edited or deleted. A correction is a further, compensating movement carrying a reason code. | M | v1.0 | CORE | BR-006, NFR-1 |
| FR-STK-004 | Every movement MUST reference a `StockLocation`. v1.0 seeds exactly one and applies it by default; no location selection is exposed. | M | v1.0 | CORE | DR-2, C-14 |
| FR-STK-005 | Every movement MUST reference a `Lot`. For `trackingPolicy = NONE`, movements post to an implicit default lot created per product. | M | v1.0 | CORE | DR-4, C-14 |
| FR-STK-006 | A movement with neither a source document nor a reason code MUST be rejected. | M | v1.0 | CORE | BR-007 |
| FR-STK-007 | A cached stock balance MAY be maintained for query performance only if it is fully reconstructible from movements, and a reconciliation routine detecting divergence MUST exist and be runnable on demand. | S | v1.0 | CORE | BR-004, NFR-3 |

### 9.2 Availability and allocation

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-STK-010 | The system MUST distinguish **on hand** (sum of movements), **allocated** (committed to confirmed, unfulfilled orders) and **available** (on hand less allocated). | M | v1.0 | CORE | PO-5 |
| FR-STK-011 | Allocation MUST occur when an order reaches `CONFIRMED` in `CORE`, and never at capture on an offline client. | M | v1.0 | CORE | BR-010, R-1 |
| FR-STK-012 | Cancelling a confirmed, unfulfilled order MUST release its allocation in full. | M | v1.0 | CORE | FR-ORD-032 |
| FR-STK-013 | Where available stock is insufficient at confirmation, the system MUST apply the `SC-STOCK` outcome (§5.3) rather than rejecting or silently reducing the order. | M | v1.0 | CORE | BR-014 |
| FR-STK-014 | `S2` and `S3` MUST display stock as an advisory snapshot with its capture time visible, and MUST NOT present it as a guarantee of availability. | M | v1.0 | S2, S3 | BR-010 |

### 9.3 Adjustments and counts

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-STK-020 | The system MUST support stock adjustment, which MUST require a `ReasonCode` selected from a configurable list. Free-text alone MUST NOT be accepted. | M | v1.0 | S1 | PO-5, BR-007 |
| FR-STK-021 | `ReasonCode` MUST be maintainable as data, each with a code, description and direction (increase / decrease / either). | M | v1.0 | S1 | NFR-11 |
| FR-STK-022 | The system MUST support a physical stock count: recording counted quantities, computing variance against derived on-hand, and posting the variance as reason-coded adjustment movements. | M | v1.0 | S1 | PO-5 |
| FR-STK-023 | A stock count MUST record who counted, who approved, and when, and MUST be retained after posting. | M | v1.0 | CORE | BR-002 |
| FR-STK-024 | Adjustments exceeding a configurable value threshold SHOULD require `OWNER` approval before posting. | S | v1.0 | CORE | DR-10 |
| FR-STK-025 | The system MUST produce a stock variance report by product, value and reason code over any period. | M | v1.0 | S1 | PO-5, §10.2 |
| FR-STK-026 | Adjustment MUST NOT be usable to alter stock without a movement record. There is no privileged path that bypasses FR-STK-001. | M | v1.0 | CORE | BR-004 |

> **Design note on FR-STK-011.** This requirement is the single most consequential line in the inventory domain. Allowing an offline device to allocate stock makes two salesmen able to sell the same unit with no possibility of detection at the time of sale — the corruption mode described in R-1. Allocation is therefore a `CORE`-only operation, and the acknowledged cost is that a field order may encounter `SC-STOCK` at sync. That cost is deliberate and preferred: a visible, resolvable exception is strictly better than an invisible, unresolvable inconsistency.

---

## 10. Pricing, Schemes & Discounts (D7 — `PRC`)

### 10.1 Price resolution

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-PRC-001 | The system MUST maintain price lists, each with an effective-from and optional effective-to date. | M | v1.0 | S1 | D7 |
| FR-PRC-002 | The system MUST resolve a unit price for a *(product, customer, date, quantity)* by a single, deterministic resolution order: customer-specific price → customer-category price list → default price list. The first match wins. | M | v1.0 | CORE | PO-6 |
| FR-PRC-003 | Price resolution MUST be implemented once, in `CORE`, and MUST return an identical result for `S1`, `S2`, `S3` and `S4` given identical inputs. | M | v1.0 | CORE | BR-001, PO-6 |
| FR-PRC-004 | Where no price resolves for a product and customer, order capture MUST be refused for that line with an explicit error. A zero or null price MUST NOT be substituted. | M | v1.0 | CORE | NFR-1 |
| FR-PRC-005 | Price list changes MUST NOT alter any already-issued document. | M | v1.0 | CORE | BR-006 |
| FR-PRC-006 | Historical price resolution MUST be reproducible: resolving for a past date MUST return the price then in effect. | M | v1.0 | CORE | BR-002, NFR-6 |

### 10.2 Schemes and discounts

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-PRC-010 | The system MUST support schemes defined as data: eligibility (product, product category, customer, customer category), a validity period, and a benefit. | M | v1.0 | S1 | NFR-11, C-12 |
| FR-PRC-011 | The system MUST support these benefit types: percentage discount, fixed-amount discount, and free-goods (quantity of a nominated product). | M | v1.0 | CORE | D7 |
| FR-PRC-012 | The system MUST support slab schemes, in which the benefit varies by ordered quantity or line value band. | M | v1.0 | CORE | D7 |
| FR-PRC-013 | Scheme evaluation MUST be automatic at order capture. Manual application of a scheme MUST NOT be possible. | M | v1.0 | CORE | PO-6 |
| FR-PRC-014 | Where multiple schemes are eligible for one line, the system MUST apply a single, configured resolution strategy (best-for-customer, or explicit scheme priority) and MUST record which scheme was applied and why. | M | v1.0 | CORE | PO-6, BR-002 |
| FR-PRC-015 | The applied scheme identifier and computed benefit MUST be persisted on the order line and carried to the invoice line. | M | v1.0 | CORE | NFR-6 |
| FR-PRC-016 | Free-goods issued by a scheme MUST generate stock movements identical in kind to sold goods, and MUST be identifiable as scheme-issued in reporting. | M | v1.0 | CORE | BR-004, PO-6 |
| FR-PRC-017 | Manual discount MUST be permitted only where the acting role holds the permission, MUST be bounded by a configurable maximum, and MUST trigger approval above a configurable threshold. | M | v1.0 | CORE | DR-10, PO-6 |
| FR-PRC-018 | Every manual discount MUST be audited with actor, amount, and the order line affected. | M | v1.0 | CORE | BR-002, PO-6 |
| FR-PRC-019 | Scheme definitions MUST be replicated to `S2` for offline evaluation, and offline evaluation MUST use the same rule semantics as `CORE`. | M | v1.0 | S2 | BR-011 |
| FR-PRC-020 | Changing or expiring a scheme MUST NOT alter benefits already applied to captured orders or issued documents. | M | v1.0 | CORE | BR-006 |
| FR-PRC-021 | The system MUST report realised discount and scheme cost by scheme, product and period. | S | v1.0 | S1 | §10.4, PO-6 |

> **Design note on FR-PRC-003.** Identical price for identical inputs across all four surfaces is the operational definition of PO-6. It is also the reason scheme evaluation cannot be a client feature: an offline client evaluates the same *rules*, but `CORE` produces the *answer* (BR-011). Where the two differ, `SC-PRICE` surfaces the difference rather than concealing it — which is precisely how the margin leakage identified in Vision §3.5 becomes measurable.

---

## 11. Order Management (D3 — `ORD`)

### 11.1 Order lifecycle

```
                    ┌──────────┐
                    │  DRAFT   │  (S2 local, S4 basket)
                    └────┬─────┘
                         │ submit
                         ▼
                  ┌─────────────┐
                  │  SUBMITTED  │  received by CORE; validation runs
                  └──┬───────┬──┘
        needs approval│       │clean
                      ▼       ▼
        ┌──────────────────┐  │
        │ PENDING_APPROVAL │  │
        └───┬──────────┬───┘  │
     approve│          │reject│
            ▼          ▼      │
            │      ┌────────┐ │
            │      │REJECTED│ │
            │      └────────┘ │
            └──────────┬──────┘
                       ▼
                ┌─────────────┐
                │  CONFIRMED  │  stock allocated (FR-STK-011)
                └──────┬──────┘   │
                       │          └─ CONFIRMED_SHORT (SC-STOCK)
                       ▼
                ┌─────────────┐
                │   PICKED    │
                └──────┬──────┘
                       ▼
                ┌─────────────┐
                │ DISPATCHED  │  stock issued; invoiceable
                └──────┬──────┘
                       ▼
                ┌─────────────┐
                │  DELIVERED  │  POD recorded (S3 from v1.1; S1 in v1.0)
                └──────┬──────┘
                       ▼
                ┌─────────────┐
                │  INVOICED   │
                └──────┬──────┘
                       ▼
                ┌─────────────┐
                │   CLOSED    │
                └─────────────┘

  CANCELLED  reachable from DRAFT, SUBMITTED, PENDING_APPROVAL, CONFIRMED only.
  Exception states (PRICE_VARIANCE, MASTER_STALE) hold a SUBMITTED order
  pending human resolution per §5.3 and rejoin the flow on resolution.
```

### 11.2 Capture

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-ORD-001 | The system MUST support order capture on `S1`, `S2` and `S4`, producing an identical order record irrespective of origin. | M | v1.0¹ | S1, S2, S4 | PO-1 |
| FR-ORD-002 | Every order MUST record its originating surface, user, device (where applicable) and capture timestamp, distinct from its `CORE` receipt timestamp. | M | v1.0 | CORE | BR-002 |
| FR-ORD-003 | An order MUST reference exactly one customer and contain one or more lines. | M | v1.0 | CORE | D3 |
| FR-ORD-004 | Each order line MUST record product, quantity, unit of measure, resolved unit price, applied scheme and computed line value. | M | v1.0 | CORE | FR-PRC-015 |
| FR-ORD-005 | Order capture MUST reject a line with non-positive quantity, an inactive product, or an unresolvable price (FR-PRC-004). | M | v1.0 | CORE | NFR-1 |
| FR-ORD-006 | Order capture MUST reject an order for a deactivated customer. | M | v1.0 | CORE | FR-CUS-008 |
| FR-ORD-007 | `S2` MUST present the salesman, at capture, with the customer's outstanding balance, available credit and advisory stock (FR-STK-014). | M | v1.0 | S2 | PO-2, PO-4 |
| FR-ORD-008 | `S2` MUST allow complete order capture with no network connectivity, persisting locally until sync. | M | v1.0 | S2 | NFR-2, C-4 |
| FR-ORD-009 | Every order created on `S2`/`S3` MUST carry a client-generated identifier serving as its idempotency key. | M | v1.0 | S2, S3 | BR-012 |
| FR-ORD-010 | `S2` order capture MUST NOT require more user actions than the paper process it replaces, measured by task-time comparison at acceptance. | M | v1.0 | S2 | NFR-10, R-2 |
| FR-ORD-011 | `S4` MUST allow a `RETAILER` to place an order for their own customer account only. | M | v1.2 | S4 | BR-003 |

¹ `S4` capture at v1.2 per Vision §7.4.

### 11.3 Validation, credit and approval

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-ORD-020 | `CORE` MUST evaluate credit at `SUBMITTED`, comparing order value plus current outstanding balance against the credit limit. | M | v1.0 | CORE | PO-4 |
| FR-ORD-021 | An order breaching the credit limit MUST NOT be silently accepted or silently rejected; it MUST enter `PENDING_APPROVAL`. | M | v1.0 | CORE | PO-4, DR-10 |
| FR-ORD-022 | Approval rules MUST be configurable as *(trigger condition → approver role)*. v1.0 MUST support triggers: credit-limit breach, discount above threshold, order value above threshold. | M | v1.0 | S1 | DR-10, NFR-11 |
| FR-ORD-023 | v1.0 MUST implement single-level approval. Chained or parallel approval MUST NOT be implemented (O16). | M | v1.0 | CORE | DR-10, C-3 |
| FR-ORD-024 | Approval and rejection MUST record approver, timestamp, decision and an optional reason, and MUST be audited. | M | v1.0 | CORE | BR-002 |
| FR-ORD-025 | An order MUST NOT reach `CONFIRMED` while any approval trigger is unresolved. | M | v1.0 | CORE | PO-4 |
| FR-ORD-026 | The count of orders reaching `CONFIRMED` in breach of credit limit without a recorded approval MUST be zero, and MUST be independently reportable as an assurance measure. | M | v1.0 | CORE | §10.2 |
| FR-ORD-027 | Approvers MUST be notified of pending approvals within `S1`; approval MUST NOT depend on an out-of-band channel. | S | v1.0 | S1 | DR-10 |

### 11.4 Amendment, cancellation and exceptions

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-ORD-030 | An order MUST be amendable only in `DRAFT`, `SUBMITTED` or `PENDING_APPROVAL`. | M | v1.0 | CORE | NFR-1 |
| FR-ORD-031 | Amending an order MUST re-run price, scheme, credit and approval evaluation in full. Partial re-evaluation MUST NOT occur. | M | v1.0 | CORE | PO-6, PO-4 |
| FR-ORD-032 | Cancellation MUST be permitted only from `DRAFT`, `SUBMITTED`, `PENDING_APPROVAL` and `CONFIRMED`, MUST release any allocation (FR-STK-012), and MUST require a reason. | M | v1.0 | CORE | FR-STK-012 |
| FR-ORD-033 | An order at or beyond `PICKED` MUST NOT be cancelled. The correct disposition is fulfilment followed by a return (§16). | M | v1.0 | CORE | BR-006 |
| FR-ORD-034 | Orders held in `PRICE_VARIANCE` or `MASTER_STALE` MUST present the resolving user with both the captured and the recomputed values, and MUST require an explicit decision. | M | v1.0 | S1 | BR-011, BR-015 |
| FR-ORD-035 | An order in `CONFIRMED_SHORT` MUST show ordered, available and shortfall quantities per line, and MUST support partial fulfilment or cancellation of the shortfall. | M | v1.0 | S1 | SC-STOCK |
| FR-ORD-036 | Every state transition MUST be audited with actor, timestamp, from-state and to-state. | M | v1.0 | CORE | BR-002 |
| FR-ORD-037 | Transitions not present in the §11.1 state machine MUST be rejected by `CORE`. The state machine is enforced, not documentary. | M | v1.0 | CORE | NFR-1 |

---

## 12. Fulfilment & Delivery (D3 — `FUL`)

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-FUL-001 | The system MUST produce a picking list for confirmed orders, showing product, quantity in base and ordering units, and location. | M | v1.0 | S1 | D3 |
| FR-FUL-002 | Picking MUST record actual picked quantity per line, which MAY be less than ordered. | M | v1.0 | S1 | D3 |
| FR-FUL-003 | Dispatch MUST generate stock issue movements equal to picked quantities, and MUST convert allocation into issue atomically. | M | v1.0 | CORE | BR-004, NFR-1 |
| FR-FUL-004 | A `Shipment` MUST be created at dispatch, linking order lines to picked quantities, with its own identifier. | M | v1.0 | CORE | D3 |
| FR-FUL-005 | One order MUST support multiple shipments (partial fulfilment). | M | v1.0 | CORE | FR-ORD-035 |
| FR-FUL-006 | Delivery confirmation MUST be recordable on `S1` in v1.0, and on `S3` from v1.1. | M | v1.0 | S1, S3 | §7.4 |
| FR-FUL-007 | `S3` MUST present the delivery user with a manifest of shipments assigned to them, and MUST function offline. | M | v1.1 | S3 | NFR-2 |
| FR-FUL-008 | `S3` MUST capture proof of delivery: recipient name, timestamp, and a signature or photograph. | M | v1.1 | S3 | U4 |
| FR-FUL-009 | `S3` MUST support recording goods refused or returned at the point of delivery, generating a `SalesReturn` (FR-RET-001). | M | v1.1 | S3 | DR-9 |
| FR-FUL-010 | `S3` MUST support recording payment collected at delivery (FR-REC-010). | M | v1.1 | S3 | A-7 |
| FR-FUL-011 | Proof-of-delivery media MUST be stored securely, MUST NOT be publicly addressable, and MUST be retrievable only by authorised roles. | M | v1.1 | CORE | NFR-5 |
| FR-FUL-012 | `S3` transactions MUST follow the same offline semantics as `S2` in every respect (§5). | M | v1.1 | S3 | BR-010 … BR-015 |
| FR-FUL-013 | A shipment MUST NOT be dispatched for a quantity exceeding the confirmed order line quantity. | M | v1.0 | CORE | NFR-1 |
| FR-FUL-014 | Media captured on `S3` MUST be queued for upload independently of transactional sync, so that a large photograph never blocks a financial transaction. | S | v1.1 | S3 | NFR-2, NFR-3 |

---

## 13. Invoicing & Credit Notes (D4 — `BIL`)

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-BIL-001 | The system MUST generate an invoice from one or more shipments of a single customer. | M | v1.0 | S1 | D4 |
| FR-BIL-002 | An invoice MUST NOT be generated for an order below `DISPATCHED`. | M | v1.0 | CORE | §11.1 |
| FR-BIL-003 | An issued invoice MUST be immutable: never edited, never deleted, never renumbered. | M | v1.0 | CORE | BR-006, NFR-1 |
| FR-BIL-004 | Correction of an issued invoice MUST be by credit note only. | M | v1.0 | CORE | BR-006 |
| FR-BIL-005 | Invoice numbers MUST be allocated from a configurable `NumberSeries`, MUST be gapless within a series, and MUST NOT be reusable. | M | v1.0 | CORE | DR-1, NFR-1 |
| FR-BIL-006 | Invoice number allocation MUST be safe under concurrency: two simultaneous issues MUST NOT receive the same number. | M | v1.0 | CORE | NFR-1 |
| FR-BIL-007 | An invoice MUST persist, at issue: customer identity and addresses, per-line product, quantity, unit price, discount, applied scheme, tax breakdown, and totals. | M | v1.0 | CORE | BR-006 |
| FR-BIL-008 | Invoice content MUST be reproduced from persisted values, never recomputed from current master data. Later master-data change MUST NOT alter a rendered historical invoice. | M | v1.0 | CORE | BR-006, FR-PRC-005 |
| FR-BIL-009 | Tax MUST be computed by a configurable tax-rule engine using the product's `TaxCode` and the rate in effect on the invoice date. | M | v1.0 | CORE | DR-1 |
| FR-BIL-010 | Tax rates MUST carry effective dates; rate changes MUST NOT alter previously issued invoices. | M | v1.0 | CORE | DR-1, BR-006 |
| FR-BIL-011 | The tax breakdown MUST be persisted per line and per tax code on the issued invoice. | M | v1.0 | CORE | DR-1 |
| FR-BIL-012 | Jurisdiction-specific statutory fields MUST be configuration, not code. Adding a jurisdiction MUST NOT require a code change to the invoicing module. | M | v1.0 | CORE | DR-1, C-12 |
| FR-BIL-013 | Issuing an invoice MUST create a customer ledger entry increasing the receivable (FR-REC-001). | M | v1.0 | CORE | BR-005 |
| FR-BIL-014 | Credit notes MUST reference the invoice they correct, MUST use their own number series, and MUST be immutable once issued. | M | v1.0 | CORE | BR-006 |
| FR-BIL-015 | A credit note MUST create a customer ledger entry reducing the receivable. | M | v1.0 | CORE | BR-005 |
| FR-BIL-016 | The total credited against an invoice MUST NOT exceed its value. | M | v1.0 | CORE | NFR-1 |
| FR-BIL-017 | Invoices MUST be renderable as a printable document and exportable as PDF. | M | v1.0 | S1 | U6 |
| FR-BIL-018 | `RETAILER` MUST be able to view and download their own invoices. | S | v1.2 | S4 | U8 |
| FR-BIL-019 | The system MUST report the count and value of invoices corrected by credit note, attributed to cause. | S | v1.0 | S1 | §10.2 |
| FR-BIL-020 | Statutory transmission of invoices to any external portal MUST NOT be implemented in v1.0 (O13). Should CF-1 confirm an obligation, it enters scope as a change request, not as an undocumented addition. | M | v1.0 | — | O13, R-7, CF-1 |

> **Design note on FR-BIL-008.** Rendering an invoice by recomputing from current master data is among the most common and most damaging defects in distribution software: a price list update silently rewrites financial history, and the business loses the ability to defend any historical document. Persisting the computed result at issue is not redundancy — it is the mechanism that makes BR-006 real.

---

## 14. Receivables & Collections (D6 — `REC`)

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-REC-001 | The system MUST maintain a customer ledger in which every invoice, credit note, payment and adjustment is an immutable entry. | M | v1.0 | CORE | BR-005, BR-006 |
| FR-REC-002 | Customer outstanding balance MUST be derived from ledger entries only. | M | v1.0 | CORE | BR-005 |
| FR-REC-003 | The system MUST record payments with amount, date, method, and receiving user. | M | v1.0 | S1 | D6 |
| FR-REC-004 | Payments MUST be allocatable against one or more specific invoices. **[B-1 — superseded in v1.0 by FR-REC-016]** | M | **v2.0** | S1 | D6 |
| FR-REC-005 | The system MUST support unallocated (on-account) payments and MUST report them distinctly. | M | v1.0 | S1 | D6 |
| FR-REC-006 | Allocated payment MUST NOT exceed the outstanding value of the target invoice. **[B-1]** | M | **v2.0** | CORE | NFR-1 |
| FR-REC-007 | Reversing a payment MUST create a compensating ledger entry; the original entry MUST NOT be edited or deleted. | M | v1.0 | CORE | BR-006 |
| FR-REC-008 | The system MUST produce an aging analysis over fixed buckets of 0–30 / 31–60 / 61–90 / 90+ days, by customer and in total. **[B-2]** | M | v1.0 | S1 | PO-4, §10.4 |
| FR-REC-009 | Current receivables position MUST be produced on demand in under 10 seconds at the DR-8 envelope. | M | v1.0 | CORE | §10.4, NFR-3 |
| FR-REC-010 | `S3` MUST support recording payment collected at delivery, offline, following §5 semantics. | M | v1.1 | S3 | A-7 |
| FR-REC-011 | `S2` MUST display the customer's outstanding balance and aging summary at the point of order capture. | M | v1.0 | S2 | PO-2, PO-4 |
| FR-REC-012 | Collections against a customer MUST be attributable to the collecting user, and MUST be reportable by collector. | M | v1.1 | CORE | U4, BR-002 |
| FR-REC-013 | Cash collected and not yet deposited MUST be trackable per collecting user, so that accountability for physical cash is not lost between collection and banking. | S | v1.1 | S1 | A-7 |
| FR-REC-014 | `RETAILER` MUST be able to view their own outstanding balance and aging. | M | v1.2 | S4 | U8 |
| FR-REC-015 | Write-off of a receivable MUST require `OWNER` authority, MUST require a reason, and MUST be audited. | S | v1.0 | CORE | BR-002 |
| FR-REC-016 | A payment MUST reduce the customer's outstanding balance by settling the oldest unsettled debits first. Settlement MUST be derived on read and MUST NOT be stored. **[B-1]** | M | v1.0 | CORE | BR-005 |

### 14.1 Amendment log — 2026-08-08

Recorded when M7's design review found these lines still describing behaviour M6 had
already decided against and verified (`M6_Design_Review.md` v1.2.0; `M6_Verification_Report.md`).

| Ref | Change | Authority |
| --- | --- | --- |
| **B-1** | **Edition 1 does not allocate a payment to an invoice.** A payment reduces what the customer *owes*; it does not pay a document. Settlement is derived FIFO across the whole ledger and is stored nowhere. FR-REC-004 and FR-REC-006 move to **v2.0**; the Edition-1 behaviour they were standing in for is now stated positively as **FR-REC-016**, a new number rather than an edit, because §2.1 makes identifiers permanent | M6 §5A (D-9) |
| **B-2** | Ageing buckets are **fixed constants**, not configuration. `AGING_BUCKET_DAYS` = 30 / 60 / 90, matching OI-4's stated values. Configuration was removed because a bucket boundary that can change makes two ageing reports run a month apart incomparable, with nothing on either report to say why | M6 §2 C-2 |

> **B-1 is a definition change, not a deferral.** A cold reader of the unamended lines
> would have concluded Edition 1 allocates payments to invoices, built a mental model on
> it, and been wrong about the single most important behaviour in the receivables module.
> FR-REC-016 exists so that reading only the v1.0 lines still yields the truth.

---

## 15. Purchasing & Suppliers (D5 — `PUR`)

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-PUR-001 | The system MUST maintain a supplier master: code, name, contact details, addresses, tax identifiers and payment terms. | M | v1.0 | S1 | D5 |
| FR-PUR-002 | Products MUST be associable with one or more suppliers. | S | v1.0 | S1 | FR-PRD-013 |
| FR-PUR-003 | The system MUST support creating purchase orders with supplier, expected date, and lines of product, quantity, unit of measure and agreed cost. | M | v1.0 | S1 | D5 |
| FR-PUR-004 | Purchase order creation MUST present current stock position and recent sales velocity for each product being ordered. | M | v1.0 | S1 | Vision §3.6, PO-7 |
| FR-PUR-005 | Purchase orders MUST follow a lifecycle: `DRAFT` → `ISSUED` → `PARTIALLY_RECEIVED` → `RECEIVED` → `CLOSED`, with `CANCELLED` reachable from `DRAFT` and `ISSUED` only. | M | v1.0 | CORE | NFR-1 |
| FR-PUR-006 | Goods receipt MUST be recorded against an issued purchase order, capturing received quantity per line. | M | v1.0 | S1 | D5 |
| FR-PUR-007 | Goods receipt MUST generate stock receipt movements (FR-STK-001) referencing the receipt as source document. | M | v1.0 | CORE | BR-007 |
| FR-PUR-008 | Received quantity MAY differ from ordered quantity; the variance MUST be recorded and reportable. | M | v1.0 | CORE | D5 |
| FR-PUR-009 | Receipt against a cancelled or draft purchase order MUST be rejected. | M | v1.0 | CORE | NFR-1 |
| FR-PUR-010 | Goods receipt MUST create a supplier ledger entry increasing the payable. | M | v1.0 | CORE | BR-005 |
| FR-PUR-011 | The system MUST maintain a supplier ledger with derived balance, on the same terms as the customer ledger (BR-005). | M | v1.0 | CORE | BR-005 |
| FR-PUR-012 | Payments to suppliers MUST be recordable and allocatable against receipts. | M | v1.0 | S1 | D5 |
| FR-PUR-013 | Multiple goods receipts against one purchase order MUST be supported. | M | v1.0 | CORE | FR-PUR-008 |
| FR-PUR-014 | Purchase orders exceeding a configurable value threshold SHOULD require `OWNER` approval before issue. | S | v1.0 | CORE | DR-10 |
| FR-PUR-015 | The system MUST report purchase order status, receipt variance and supplier outstanding balances. | M | v1.0 | S1 | D12 |

> **Scope boundary.** FR-PUR-010 through FR-PUR-012 record payables *as they arise from distribution activity*. This is the O1 boundary: DistriCore owns the supplier ledger, not double-entry bookkeeping.

---

## 16. Returns (D2, D5 — `RET`)

Per DR-9, returns are **one mechanism differentiated by reason code**, not several parallel implementations.

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-RET-001 | The system MUST support sales returns from a customer, referencing the originating invoice where known. | M | v1.0 | S1 | DR-9 |
| FR-RET-002 | Every return line MUST carry a `ReasonCode`. A return without one MUST be rejected. | M | v1.0 | CORE | BR-007, DR-9 |
| FR-RET-003 | A sales return MUST generate stock receipt movements, except where the reason code is configured as non-restockable (e.g. damaged), in which case no stock is received and the disposition is recorded. | M | v1.0 | CORE | BR-004, BR-007 |
| FR-RET-004 | A sales return against an invoiced order MUST generate a credit note (FR-BIL-014). | M | v1.0 | CORE | BR-006 |
| FR-RET-005 | Returned quantity MUST NOT exceed the quantity invoiced for that product on the referenced invoice. | M | v1.0 | CORE | NFR-1 |
| FR-RET-006 | Returns captured at delivery on `S3` MUST use the same mechanism and produce the same records as returns captured on `S1`. | M | v1.1 | S3 | DR-9, BR-001 |
| FR-RET-007 | The system MUST support purchase returns to a supplier, generating stock issue movements and a supplier ledger entry reducing the payable. | M | v1.0 | CORE | DR-9, BR-005 |
| FR-RET-008 | Return reason codes MUST be maintainable as data, each flagged restockable or non-restockable. | M | v1.0 | S1 | NFR-11 |
| FR-RET-009 | The system MUST report returns by reason code, product, customer and period. | M | v1.0 | S1 | D12 |
| FR-RET-010 | Expiry-driven identification of returnable stock MUST NOT be implemented in v1.0; it requires `trackingPolicy = BATCH` (O14). Returns of expired goods in v1.0 are handled by reason code alone. | M | v1.0 | — | DR-4, DR-9 |

---

## 17. Sales Targets & Performance (D8 — `TGT`) — v1.1

Deferred to v1.1 per Vision §7.4: this domain reads data v1.0 already records and creates no new transactional structure, making it the lowest-risk deferral in the programme.

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-TGT-001 | The system MUST support defining sales targets per salesman per period, by value and optionally by product category. | M | v1.1 | S1 | D8 |
| FR-TGT-002 | Target periods MUST be configurable (monthly, quarterly, custom). | M | v1.1 | S1 | NFR-11 |
| FR-TGT-003 | Achievement MUST be computed from recorded orders, and the computation basis (order value, invoiced value or collected value) MUST be a configured choice, applied consistently. | M | v1.1 | CORE | D8 |
| FR-TGT-004 | `SALESMAN` MUST be able to view their own target and achievement on `S2`. | M | v1.1 | S2 | U3 |
| FR-TGT-005 | `SALESMGR` and `OWNER` MUST be able to view target achievement across the team. | M | v1.1 | S1 | U2 |
| FR-TGT-006 | The system MUST compute a commission basis from achievement using configurable rules. **Disbursement is out of scope (O2).** | M | v1.1 | CORE | D8, O2 |
| FR-TGT-007 | Changing a target after its period has begun MUST be audited with previous and new value. | M | v1.1 | CORE | BR-002 |

---

## 18. Synchronisation (D10 — `SYN`)

Governed by §5. These requirements make those semantics testable.

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-SYN-001 | Offline surfaces MUST maintain a durable local outbox of created transactions, surviving application restart and device reboot. | M | v1.0 | S2, S3 | BR-014 |
| FR-SYN-002 | Sync MUST transmit outbox transactions in creation order per device (BR-013). | M | v1.0 | S2, S3 | BR-013 |
| FR-SYN-003 | `CORE` MUST treat the client identifier as an idempotency key; a re-transmitted accepted transaction MUST be acknowledged without creating a duplicate. | M | v1.0 | CORE | BR-012 |
| FR-SYN-004 | Sync MUST be resumable: an interrupted batch MUST NOT lose, duplicate or partially apply transactions. | M | v1.0 | CORE, S2 | §10.3 |
| FR-SYN-005 | `CORE` MUST classify every rejected transaction into a §5.3 class and persist it as a `SyncConflict` in `PENDING_RESOLUTION`. **[S-1 — in Edition 1 the §5.3 taxonomy reduces to the two automatic classes (`02A` §5); persistence is discharged by `sync_operation` (`04` T-26). `SyncConflict` is a §4.1 conceptual entity name, not a schema requirement.]** | M | v1.0 | CORE | BR-014, BR-015 |
| FR-SYN-006 | A transaction MUST NOT be discarded under any circumstance, including malformed payloads, which MUST be quarantined and reported rather than dropped. | M | v1.0 | CORE | BR-014 |
| FR-SYN-007 | Sync MUST deliver master-data updates to the device: customers on assigned routes, products, prices, schemes and stock snapshot. **[S-8 — the stock-snapshot clause moves to `v2.0`; customers, products, prices and schemes are unaffected and remain `v1.0`. DV-1 (`02A` §5) removed field order capture from Edition 1, and stock snapshot has no other Edition-1 consumer — no V1 mobile workflow checks availability or contends for stock. Returns with field order capture, the same event that returns FR-SYN-013/014 (S-2).]** | M | v1.0 / **v2.0 (stock only)** | CORE, S2 | FR-CUS-013 |
| FR-SYN-008 | The device MUST display its last successful sync time, count of pending transactions, and count of operations the server has rejected. **[S-5 — the third field previously read *"count of unresolved conflicts"*, a phrase defined nowhere in this document. Edition 1's smallest truthful quantity is `sync_operation.status = 'REJECTED'`, which `05` §11.2 already requires be flagged to the user. `DEFERRED` is excluded: it auto-retries, so it belongs to the owner's exception list (`04` T-26) and not to the device's count.]** | M | v1.0 | S2, S3 | §5.4 |
| FR-SYN-009 | `SALESMGR` and `ADMIN` MUST be able to view, per device: last sync time, pending transaction count and unresolved conflicts. **[S-6 — Edition 2. Three Edition-1 prerequisites are absent at once: no admin console exists for it to live in (`02A` §7.12), Edition 1 has no `SALESMGR`/`ADMIN` role to gate it (§7.1 — four fixed roles, neither among them), and there is no registered `device` entity to view (`04` §13.2). Any one would be sufficient; all three hold. Priority `M` and requirement text unchanged; nothing deleted.]** | M | **v2.0** | S1 | §5.4 |
| FR-SYN-010 | Full sync of a typical daily volume MUST complete within 2 minutes of reconnection at the DR-8 envelope. **[S-9 — foreground-scoped for Edition 1/V1: the bound applies while the application is in the foreground and connectivity has been restored. Background/suspended/Doze/App Standby sync is best-effort in V1 and is not part of this acceptance criterion. Priority `M` and release `v1.0` unchanged; requirement text unchanged.]** | M | v1.0 | CORE | §10.3 |
| FR-SYN-011 | Sync MUST occur over an encrypted transport and MUST authenticate both user and device. | M | v1.0 | CORE | NFR-5, FR-IAM-009 |
| FR-SYN-012 | Sync MUST transmit only records the device's user is authorised to hold, minimising data at rest on the device. | M | v1.0 | CORE | NFR-5, R-8 |
| FR-SYN-013 | Conflicts MUST be resolvable on `S1` with sufficient context to decide: captured values, current values, customer, salesman and capture time. **[S-2 — Edition 2. No Edition-1 conflict class requires human resolution (`02A` §5), so this requirement has no subject. Moved to v2.0 exactly as FR-REC-004 (B-1) and FR-RPT-006 (A-3) were: still a requirement, not deleted.]** | M | **v2.0** | S1 | BR-015, FR-ORD-034 |
| FR-SYN-014 | Resolution of a conflict MUST be audited with resolver, decision and timestamp. **[S-2 — Edition 2. No resolution action exists in Edition 1, so there is nothing to audit. Returns with FR-SYN-013.]** | M | **v2.0** | CORE | BR-002 |
| FR-SYN-015 | The system MUST report the proportion of synchronised transactions that raised a conflict, as the measure for Vision §10.3. | M | v1.0 | S1 | §10.3 |
| FR-SYN-016 | Local device storage MUST be encrypted at rest. | M | v1.0 | S2, S3 | NFR-5, R-8 |
| FR-SYN-017 | Sync MUST degrade gracefully on intermittent connectivity: partial progress MUST be retained and retried, never restarted from the beginning. | M | v1.0 | S2, S3 | C-11 |

> **Verification focus.** FR-SYN-003, FR-SYN-004 and FR-SYN-006 carry the two non-negotiable metrics in Vision §10.3 (zero transactions lost, zero duplicates). They MUST be verified by adversarial testing — connection severed mid-batch, duplicate batch replay, device clock skew, application killed mid-write, storage exhausted — not by happy-path integration tests. A green happy-path suite is not evidence for these requirements.

### 18.1 Amendment log — 2026-08-21

This block was written against the frozen baseline, **before `02A` §5 / DV-1 removed field
order capture from Edition 1**, and was never back-updated. `02A`'s own standing clause is
the authority: it *"does not add requirements; it **partitions** the confirmed ones and, where
the new Edition 1 direction departs from the frozen baseline, **records the departure
explicitly rather than absorbing it silently**."* `03`, `04` and `05` derived from it; this
document did not, and **S-1 … S-4** close that gap.

**S-5 is of a different kind and is recorded here for locality, not because it shares that
cause.** It corrects a term this document never defined, rather than a departure `02A` had
already decided — see the row itself and `M9_Design_Review` §6 D-M9-6.

**Nothing here was deleted.** A requirement moved to v2.0 is still a requirement; a reader
must be able to see it was considered and deferred rather than forgotten.

> **A new prefix, deliberately.** `A-` is §20.1's Reporting series and `B-` is §14.1's
> Receivables series — every existing row in both concerns the block it sits in. `S-` keeps
> that property for Synchronisation. It also avoids a collision `A-8` would have created:
> FR-REC-010 already traces an **assumption** called `A-7`, and the two namespaces are
> distinct. *(`M9_Design_Review` §11 proposed `A-8…A-11` before §14.1 had been read; the
> renumbering is recorded here rather than left as a silent divergence.)*

| Ref | Change | Authority |
| --- | --- | --- |
| **S-1** | **FR-SYN-005 stays `M`, `v1.0`, and is discharged as written.** In Edition 1 the §5.3 taxonomy reduces to `SC-DUPLICATE` and `SC-SEQUENCE`, both automatic, so nothing is left unclassified. Its persistence clause is satisfied by `sync_operation` — `status = 'REJECTED'` with retained `payload` — which `04` T-26 already claims for FR-SYN-003…006. **`SyncConflict` is a §4.1 conceptual entity name, not a schema mandate**; `SyncBatch` and `SyncTransaction` beside it are equally unmodelled, and a `PENDING_RESOLUTION` state would have no exit in an edition with zero human-resolvable classes | `02A` §5 · `04` T-26 · `M9_Design_Review` §6 D-M9-2 |
| **S-2** | **FR-SYN-013 and FR-SYN-014 → `v2.0`**, priority `M` unchanged. Both take their subject from the four non-automatic classes, which are order-borne; Edition 1 has none, so neither requirement has anything to resolve or to audit. They return with field order capture, which `02A` §5 and `04` T-26's *"Future evolution"* both already commit to | `02A` §5, §6.2, §7.12 · `04` T-26 · `M9_Design_Review` §6 D-M9-4 |
| **S-3** | **BR-014's guarantee is unchanged; only the named artefact.** The Edition-1 vehicle is `sync_operation` with retained `payload` and a non-empty `error_code`, enforced by `ck_sync_operation_rejected` — a rejection with no reason is refused by the database. Nothing is discarded, and `04` T-26 states it is *"the table that makes 'no transaction is ever lost' true rather than aspirational"* | `04` T-26 · `03` §6.2 · `M9_Design_Review` §6 D-M9-2 |
| **S-4** | **§5.3's four non-automatic classes are Edition 2, and FR-SYN-006 quarantine is distinct from the taxonomy.** Recorded as a ruling: this document did not previously draw that distinction, and FR-SYN-005's *"every rejected transaction"* read wider than §5.3 can support. **No `SC-*` class is created** | `02A` §5 · `M9_Design_Review` §6 D-M9-3 |
| **S-5** *(2026-08-21)* | **FR-SYN-008's third field reworded; nothing else in the requirement changes.** *"Count of unresolved conflicts"* was undefined — the phrase appeared twice before this amendment, both in this document, and neither §5.4 (its only trace) nor `05` §11.5 defines it. The Edition-1 quantity is `sync_operation.status = 'REJECTED'`, which `05` §11.2 already obliges the client to *"flag to the user"*. **No API field is added or renamed: the existing `rejected_count` (`05` §11.5) satisfies the amended quantity**, and no schema, contract or logic changes. `DEFERRED` stays out of the device count because it auto-retries. **Priority `M` and release `v1.0` are unchanged**; FR-SYN-009, FR-SYN-006 and BR-014 are untouched by this row | `05` §11.2, §11.5 · `04` T-26 · `M9_Design_Review` §6 D-M9-6 |
| **S-6** *(2026-08-21, written 2026-09-14)* | **FR-SYN-009 → `v2.0`**, annotated in place; priority `M` and requirement text unchanged, nothing deleted. Ruled the same day as S-1…S-5, by a later decision (D-M9-7, v1.2.0) than the one this document had been updated against (D-M9-6, v1.1.0) — this row closes that gap. `02A` §7.12 places the admin console in Edition 2; Edition 1 has no `SALESMGR`/`ADMIN` role (§7.1); `04` has no registered `device` entity until §13.2's Edition-2 activation. Returns in Edition 2 with all three | `02A` §7.1, §7.12 · `04` §13.2 · `M9_Design_Review` §6 D-M9-7 |
| **S-8** *(2026-09-14)* | **FR-SYN-007's stock-snapshot clause → `v2.0`.** The rest of the requirement — customers on assigned routes, products, prices, schemes — is untouched and stays `v1.0`; only the named clause moves, priority `M` unchanged, nothing deleted. DV-1 removed field order capture from Edition 1; the requirement's own reason for existing (a salesman checking availability before committing an offline order) has no subject when no order is committed offline. Closes `05` D-M9.4-1's CONTRACT GAP by removing the requirement it was gapped against, rather than by building against it. Returns with field order capture, the same event that returns S-2 | `02A` §5 · `05` §11.1 D-M9.4-1, D-M9-11 |
| **S-9** *(2026-09-14)* | **FR-SYN-010 and NFR-PER-004 annotated in place: the 2-minute bound is foreground-scoped for Edition 1/V1.** Neither requirement named an application state; TD-47 (`PROJECT_STATE.md`) flagged that silence as a scope question no engineering measurement could settle alone. Ruled: the bound applies in the foreground with connectivity restored; background/suspended/Doze/App Standby sync is best-effort in V1, not an acceptance criterion. **No `WorkManager`/`JobScheduler`/foreground-service mechanism is added**; the existing `D-M9-9` `SyncScheduler` (60 s cadence, `onResume`/`onDetach` only) is unchanged and is now confirmed correct as built. B1's foreground-only measurement (PASSED 2026-09-06, 67 046 ms of 120 000 ms) is the complete V1 acceptance evidence. **Priority `M` and release `v1.0` unchanged; requirement text unchanged; nothing deleted** | `M9_Design_Review` §6 D-M9-9, D-M9-12 |

> **S-4 is the one to read twice.** S-1, S-2 and S-3 record departures `02A` had already
> decided and this document had merely never been told about. **S-4 decides something the
> corpus genuinely left open** — whether a malformed or unauthorised operation is a §5.3
> conflict or an FR-SYN-006 quarantine. A different reader could have concluded that Edition 1
> owes a class for validation failures. It does not, and the reasoning is in
> `M9_Design_Review` §6 D-M9-3 and §13.3.

> **Still unmet after these amendments: FR-SYN-006's *"and reported"* clause.** `04` T-26 calls
> its partial index *"the owner's exception list"* and `03` §6.2 says rejections are *"surfaced
> to the owner"*, but no endpoint or screen consumes it, and `05` specifies none.
> **FR-SYN-006 remains `M`, `v1.0`, and is not amended here** — recorded as open contract work
> at `M9_Design_Review` §8 OC-3.

---

## 19. Audit & Traceability (D11 — `AUD`)

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-AUD-001 | Every state-changing operation MUST write an `AuditEvent` bearing actor, role, timestamp, surface, device where applicable, entity, operation and before/after state. | M | v1.0 | CORE | BR-002 |
| FR-AUD-002 | Audit records MUST be append-only. No interface — including administrative — may edit or delete them. | M | v1.0 | CORE | BR-002, NFR-6 |
| FR-AUD-003 | `SYSTEM`-initiated operations MUST be audited identically to user-initiated ones. | M | v1.0 | CORE | BR-002 |
| FR-AUD-004 | Audit records MUST be queryable by entity, actor, date range and operation. | M | v1.0 | S1 | PO-8 |
| FR-AUD-005 | Any transaction MUST be reconstructible from audit records: what changed, who changed it, when, and from which surface and device. | M | v1.0 | CORE | PO-8 |
| FR-AUD-006 | Audit records MUST NOT contain credentials, password material or full payment instrument data. | M | v1.0 | CORE | NFR-5, FR-IAM-015 |
| FR-AUD-007 | Audit retention MUST be at least as long as transaction retention (DR-8: five years online). | M | v1.0 | CORE | DR-8, NFR-6 |
| FR-AUD-008 | Failed authorisation attempts MUST be audited. | M | v1.0 | CORE | NFR-5 |
| FR-AUD-009 | Credit limit changes, manual discounts, stock adjustments, approvals, write-offs and conflict resolutions MUST be individually reportable from the audit record as a control review. | M | v1.0 | S1 | PO-8 |

---

## 20. Reporting (D12 — `RPT`)

Operational reporting only. A dimensional analytics platform is out of scope (O11).

| ID | Requirement | Pri | Rel | Surface | Traces |
| --- | --- | :-: | :-: | --- | --- |
| FR-RPT-001 | Sales report by period, customer, product and salesman. **[A-1 — category carried to FR-RPT-016]** | M | v1.0 | S1 | PO-7 |
| FR-RPT-002 | Stock position report: on hand, by product. **[A-2 — allocated/available carried to FR-RPT-017]** | M | v1.0 | S1 | PO-5 |
| FR-RPT-003 | Stock variance report by reason code, in quantity (FR-STK-025). **Reports the physical trace only. [A-6] [A-7 — value carried to FR-RPT-018]** | M | v1.0 | S1 | §10.2 |
| FR-RPT-004 | Receivables aging report (FR-REC-008). | M | v1.0 | S1 | §10.4 |
| FR-RPT-005 | Customer statement of account (FR-CUS-011). | M | v1.0 | S1 | D6 |
| FR-RPT-006 | Purchase report: orders, receipts, variance, supplier balances. **[A-3]** | M | **v2.0** | S1 | D5 |
| FR-RPT-007 | Scheme and discount cost report (FR-PRC-021). **[A-4]** | S | **v2.0** | S1 | §10.4 |
| FR-RPT-008 | Order pipeline report by state, including orders held in exception states. | M | v1.0 | S1 | U2 |
| FR-RPT-009 | Sync health report (FR-SYN-015). **Delivered at M9 with the mechanism it reports on. [A-5]** | M | v1.0 | S1 | §10.3 |
| FR-RPT-010 | Returns report by reason code (FR-RET-009). **Reports the financial trace only. [A-6]** | M | v1.0 | S1 | D12 |
| FR-RPT-011 | Salesman performance report against targets. | M | v1.1 | S1 | D8 |
| FR-RPT-012 | Every report MUST be exportable to CSV. | M | v1.0 | S1 | U1 |
| FR-RPT-013 | Reports MUST reflect committed data only; uncommitted or unsynchronised transactions MUST NOT appear. | M | v1.0 | CORE | NFR-1 |
| FR-RPT-014 | Reports MUST respect the requesting user's authorisation; `SALESMAN` reporting MUST be scoped to their own customers and orders. | M | v1.0 | CORE | BR-003 |
| FR-RPT-015 | Reports MUST return within 10 seconds at the DR-8 envelope over five years of retained history. | M | v1.0 | CORE | NFR-3, DR-8 |
| FR-RPT-016 | Sales report MUST additionally break down by product category. **[A-1]** | M | **v2.0** | S1 | PO-7 |
| FR-RPT-017 | Stock position report MUST additionally show allocated and available quantity. **[A-2]** | M | **v2.0** | S1 | PO-5 |
| FR-RPT-018 | Stock position and stock variance reports MUST value stock at cost. **[A-7]** | M | **v2.0** | S1 | PO-5 |

### 20.1 Amendment log — 2026-08-08

This block was written against the frozen baseline, **before `02A` §13 re-validated Edition
1 and demoted whole modules**, and was never back-updated. `02A` §13 is later, was
explicitly approved, and `04` was designed from its outcome, so it governs (C-1, §2 of
`M7_Design_Review.md` v1.1.0).

**Nothing here was deleted.** A requirement moved to v2.0 is still a requirement; a reader
must be able to see it was considered and deferred rather than forgotten.

| Ref | Change | Authority |
| --- | --- | --- |
| **A-1** | `category` removed from FR-RPT-001 and carried to **FR-RPT-016, v2.0**. No category field exists (`04` T-10) | `02A` §13.2 · M7 §2 C-3 |
| **A-2** | `allocated` and `available` removed from FR-RPT-002 and carried to **FR-RPT-017, v2.0**. No reservation mechanism exists; both columns would read zero and available would equal on hand | `02A` §7.4 · M7 §2 C-2 |
| **A-3** | FR-RPT-006 → **v2.0**. No `supplier`, `purchase_order` or supplier-ledger table exists in Edition 1 | `02A` §6.1 · M7 §2 C-1 |
| **A-4** | FR-RPT-007 → **v2.0**. Priority was already `S`; schemes are Edition 2, so the report has no subject | M7 §3 |
| **A-5** | FR-RPT-009 stays v1.0 but is **delivered at M9**, beside the sync mechanism. Not a scope change — a roadmap-order correction | M7 §2 C-4 |
| **A-6** | **FR-RPT-003 and FR-RPT-010 report two different traces of a return and are two separate reports.** A credit note writes no stock movement (ADR-0009), so the physical and financial traces have no join and must not be presented as one | M7 §4.2 (D-2), M7-7 |

| **A-7** | **Stock cannot be valued in Edition 1.** `Product.selling_price` is the only money field on a product; no `cost_price` exists, because a cost basis is a *purchasing* artefact and purchasing is Edition 2 (A-3). FR-RPT-003's `and value` clause is carried to **FR-RPT-018, v2.0**, and both stock reports show quantity. **Valuing at selling price was considered and rejected**: it is not what "valuation" means to a bank or an accountant, and it overstates working capital by the entire margin | M7 §2 C-7 |

> **A-6 is the one to read twice.** It is not a scope reduction — it is a statement that
> two requirements which look like near-duplicates are answering different questions, and
> that their totals will legitimately differ.
>
> **A-7 was found by independent architecture review, not by reading this document.** Three
> documents — `02` FR-RPT-003, `05` §9.11 and `02A` §7.12 — all described a stock valuation,
> agreed with each other, and all of them disagreed with the schema. **A corpus can be
> internally consistent and still wrong**, which is the argument for checking requirements
> against the database rather than only against each other.

## 21. Non-Functional Requirements

Vision §13 states goals. This section makes them testable. **A non-functional goal without a measurement method is not a requirement**, so each entry below names how it is verified.

### 21.1 Data integrity (`INT`) — Vision NFR-1

| ID | Requirement | Verified by |
| --- | --- | --- |
| NFR-INT-001 | Any operation spanning multiple ledger or stock records MUST be atomic: it commits wholly or not at all. | Fault-injection test killing the process mid-transaction; assert no partial state |
| NFR-INT-002 | Concurrent operations on the same stock or ledger position MUST NOT produce lost updates. | Concurrency test issuing simultaneous conflicting operations |
| NFR-INT-003 | Derived balances (BR-004, BR-005) MUST equal the sum of their source records at all times. | Reconciliation routine run as an assertion in the integration suite |
| NFR-INT-004 | Issued financial documents MUST be immutable at the persistence layer, not only in application logic. | Attempt direct mutation through every available path; assert rejection |
| NFR-INT-005 | Monetary values MUST use an exact decimal representation. Binary floating point MUST NOT be used for money or quantity. | Static check plus rounding-accumulation test over 10⁵ transactions |
| NFR-INT-006 | Rounding rules MUST be defined once, applied consistently, and documented. | Golden-value test over the rounding boundary cases |

### 21.2 Offline reliability (`OFF`) — Vision NFR-2, C-4

| ID | Requirement | Verified by |
| --- | --- | --- |
| NFR-OFF-001 | `S2` and `S3` MUST remain fully functional for a complete working day with no connectivity. | Soak test: 8 hours offline at representative transaction volume |
| NFR-OFF-002 | Zero transactions MUST be lost across any connectivity failure mode. | Adversarial suite per §18 verification note |
| NFR-OFF-003 | Zero duplicate transactions MUST be created by sync. | Batch replay and interrupted-batch tests |
| NFR-OFF-004 | Local storage MUST accommodate at least three days of transactions without sync. | Capacity test at DR-8 per-device volume |
| NFR-OFF-005 | Application termination — crash, force-close, battery exhaustion — MUST NOT lose a committed local transaction. | Kill-test at each write boundary |

### 21.3 Performance (`PER`) — Vision NFR-3

| ID | Requirement | Verified by |
| --- | --- | --- |
| NFR-PER-001 | Interactive `S1` and `S4` operations MUST complete within 2 seconds at the 95th percentile under the DR-8 envelope. | Load test at envelope |
| NFR-PER-002 | `S2` order capture actions MUST respond within 500 ms, bounded by local storage and independent of network state. | Device test on the minimum-specification handset |
| NFR-PER-003 | Reports MUST return within 10 seconds over five years of history (FR-RPT-015). | Load test against a synthesised five-year dataset |
| NFR-PER-004 | Sync of typical daily volume MUST complete within 2 minutes (FR-SYN-010). **[S-9 — verified in the foreground only; B1 (foreground, PASSED 2026-09-06) is the complete V1 evidence. Background/Doze behaviour is not a V1 acceptance gate.]** | Timed sync at representative volume, foreground |
| NFR-PER-005 | Performance MUST be re-measured against the five-year projected dataset before each release, not only against a fresh database. | Release gate |

### 21.4 Scalability (`SCA`) — Vision NFR-4, DR-8

| ID | Requirement | Verified by |
| --- | --- | --- |
| NFR-SCA-001 | The system MUST sustain the DR-8 three-year envelope without architectural change. | Load test at envelope |
| NFR-SCA-002 | The data model MUST carry `Tenant`, `StockLocation` and `Lot` from the first migration (C-14, §4.2). | Schema review at the first migration; this is a release gate, not a recommendation |
| NFR-SCA-003 | No query may degrade worse than linearly with retained history. | Query plan review against the five-year dataset |

### 21.5 Security (`SEC`) — Vision NFR-5

| ID | Requirement | Verified by |
| --- | --- | --- |
| NFR-SEC-001 | All network traffic MUST use current TLS. Plaintext transport MUST be rejected, not merely discouraged. | Configuration test; downgrade attempt |
| NFR-SEC-002 | All data access MUST be parameterised. String-concatenated queries MUST NOT exist. | Static analysis gate plus injection test suite |
| NFR-SEC-003 | All input MUST be validated server-side against an explicit schema, irrespective of client validation. | Malformed-input suite issued directly to the API |
| NFR-SEC-004 | Output MUST be encoded contextually to prevent XSS. | Automated scan plus stored-payload test |
| NFR-SEC-005 | State-changing requests MUST carry CSRF protection where the surface is cookie-authenticated. | CSRF test suite |
| NFR-SEC-006 | Uploaded files (proof of delivery, imports) MUST be type-validated, size-limited, stored outside the web root, and served only through authorised, non-guessable references. | Upload abuse suite |
| NFR-SEC-007 | Secrets MUST NOT appear in source control. Configuration MUST be supplied by environment or a secret store. | Repository scanning in CI as a blocking check |
| NFR-SEC-008 | Device local storage MUST be encrypted at rest (FR-SYN-016). | Device inspection test |
| NFR-SEC-009 | Dependencies MUST be scanned for known vulnerabilities in CI; a critical finding MUST block release. | CI gate |
| NFR-SEC-010 | Error responses MUST NOT disclose stack traces, query text, or internal identifiers to any client. | Error-path review |
| NFR-SEC-011 | Authorisation MUST be verified at the API boundary for every request, tested independently of any client (FR-IAM-007). | Role × capability matrix test issued directly to the API |

### 21.6 Auditability, availability, maintainability

| ID | Requirement | Verified by |
| --- | --- | --- |
| NFR-AUD-001 | Audit records MUST be append-only at the persistence layer (FR-AUD-002). | Attempted mutation through every path |
| NFR-AVA-001 | RPO ≤ 15 minutes; RTO ≤ 4 hours (DR-5). | Restore rehearsal measuring both, scheduled and recorded |
| NFR-AVA-002 | Backups MUST be restore-tested on a schedule. **An untested backup does not satisfy this requirement.** | Rehearsal record |
| NFR-MNT-001 | Business rules MUST have exactly one implementation. Duplicated rule logic is a defect regardless of correctness. | Code review gate; duplication analysis |
| NFR-MNT-002 | Domain logic MUST be independent of surface and framework, and testable without a running client or HTTP layer. | Unit tests execute with no web server |
| NFR-MNT-003 | Public interfaces MUST be strongly typed. | Static analysis gate |
| NFR-MNT-004 | Errors MUST be handled explicitly; silent catch-and-continue MUST NOT occur. | Code review gate; static analysis |
| NFR-TST-001 | Business-rule code MUST reach ≥ 80% line coverage; pricing, credit, tax and sync rules MUST reach 100% including failure paths. | Coverage gate in CI |
| NFR-TST-002 | Every milestone MUST include edge-case and failure-case tests, not only happy paths (C-9). | Review gate |
| NFR-USA-001 | `S2` order capture MUST be demonstrably faster than the paper process, measured by timed task comparison with actual salesmen before go-live. | Timed usability test — **an acceptance gate for v1.0, not a nicety** (R-2) |
| NFR-USA-002 | `S2` and `S3` MUST be operable one-handed, with touch targets and contrast usable in variable outdoor lighting. | Field usability test |
| NFR-CFG-001 | Roles, schemes, price lists, reason codes, approval rules, tax rules and number series MUST be configurable without code change. | Configuration test per item |
| NFR-OBS-001 | Application health, error rate and per-device sync status MUST be observable in production. | Monitoring review |
| NFR-DOC-001 | `docs/` MUST be updated in the same change as the code it describes (C-9, NFR-13). | Pull-request checklist gate |

---

## 22. Business Rules Catalogue

Consolidated from §4.3 and §5.2. These are invariants, not features: **a design that violates one is rejected regardless of other merit.**

| ID | Rule | Origin |
| --- | --- | --- |
| BR-001 | Business rules are evaluated in `CORE`; client results are never authoritative | Vision §4.1 |
| BR-002 | Every state change is audited, append-only, with actor and before/after state | Vision NFR-6 |
| BR-003 | Authorisation is evaluated in `CORE` on every request | Vision NFR-5 |
| BR-004 | Stock on hand is derived from movements, never independently stored | Vision PO-5 |
| BR-005 | Party balances are derived from ledger entries, never independently stored | Vision NFR-1 |
| BR-006 | Issued financial documents are immutable; correction is by further document | Vision NFR-1 |
| BR-007 | Every stock movement carries a source document or a reason code | Vision PO-5 |
| BR-010 | Offline clients do not reserve stock; displayed availability is advisory | R-1, DR-2 |
| BR-011 | Offline prices are quoted, not agreed; `CORE` recomputes and flags variance | R-1, PO-6 |
| BR-012 | Every offline record carries a client-generated idempotency key | Vision §10.3 |
| BR-013 | Sync is idempotent and ordered per device | Vision §10.3 |
| BR-014 | No transaction is ever discarded. In Edition 1 a rejected or malformed transaction is **retained and quarantined** with its reason and payload; **human conflict resolution is not an Edition-1 mechanism** (S-4, §18.1) | Vision §10.3 |
| BR-015 | Conflict resolution is explicit except for deterministic classes | R-1 |

---

## 23. Release Allocation

Per Vision §7.4. **Nothing is removed from confirmed scope** — v1.0, v1.1 and v1.2 together deliver it.

| Release | Domains | Surfaces | Functional requirements |
| --- | --- | --- | --: |
| **v1.0** | IAM, CUS, PRD, STK, PRC, ORD, FUL (partial), BIL, REC (partial), PUR, RET (partial), SYN, AUD, RPT | S1, S2 | 206 |
| **v1.1** | FUL (S3 delivery, POD, collection), REC (field collections), RET (S3 capture), TGT | + S3 | 19 |
| **v1.2** | IAM (retailer accounts), CUS, BIL, REC, ORD (portal capture) | + S4 | 6 |
| | | **Total** | **231** |

The 44 non-functional requirements of §21 apply to every release. They are not deferrable: a release that meets its functional requirements but not §21 does not satisfy PO-9.

**Distribution by domain**

| Domain | Total | v1.0 | v1.1 | v1.2 | | Domain | Total | v1.0 | v1.1 | v1.2 |
| --- | --: | --: | --: | --: | --- | --- | --: | --: | --: | --: |
| `ORD` | 26 | 25 | — | 1 | | `CUS` | 15 | 14 | — | 1 |
| `BIL` | 20 | 19 | — | 1 | | `PUR` | 15 | 15 | — | — |
| `STK` | 19 | 19 | — | — | | `REC` | 15 | 11 | 3 | 1 |
| `PRC` | 18 | 18 | — | — | | `RPT` | 15 | 14 | 1 | — |
| `SYN` | 17 | 17 | — | — | | `FUL` | 14 | 7 | 7 | — |
| `IAM` | 16 | 15 | — | 1 | | `PRD` | 14 | 13 | — | 1 |
| | | | | | | `RET` | 10 | 9 | 1 | — |
| | | | | | | `AUD` | 9 | 9 | — | — |
| | | | | | | `TGT` | 7 | — | 7 | — |

> **Reading the distribution.** 89% of functional requirements land in v1.0. This is the honest cost of the structural-enabler rule (C-14): the deferred releases are thin because almost everything they need must already exist for them to be cheap. Phasing reduces *concurrent* risk (R-3), not total work — and it was never claimed to.

### 23.1 v1.0 milestone sequence

Derived from dependency, not preference. Each milestone must independently compile, run, validate and be tested (C-2, C-9).

| # | Milestone | Delivers | Depends on |
| --- | --- | --- | --- |
| M0 | Foundation | Tenant, audit, identity, roles, device registration, first migration carrying all three structural enablers (NFR-SCA-002) | — |
| M1 | Master data | Customers, products, UoM, tax codes, suppliers, reason codes | M0 |
| M2 | Inventory core | Stock movements, derived balances, adjustments, counts | M1 |
| M3 | Pricing engine | Price lists, resolution, schemes, slabs, manual discount | M1 |
| M4 | Order management (S1) | Capture, validation, credit, approval, lifecycle | M2, M3 |
| M5 | Fulfilment & invoicing | Picking, dispatch, shipments, tax engine, invoices, credit notes | M4 |
| M6 | Receivables | Customer ledger, payments, allocation, aging | M5 |
| M7 | Purchasing & returns | Purchase orders, goods receipt, supplier ledger, returns | M2, M6 |
| M8 | Field-sales app (S2) | Offline capture, local outbox, device auth | M4 |
| M9 | Synchronisation | Sync protocol, conflict detection and resolution, observability | M8 |
| M10 | Reporting | All v1.0 reports | M6, M7, M9 |
| M11 | Hardening & go-live | Performance, security review, restore rehearsal, opening-balance load, baseline comparison | All |

> **M0 is the highest-consequence milestone in the programme** and is deceptively small. It carries the tenancy, stock-location and lot dimensions (C-14). Every later milestone writes data through that schema; omitting a dimension at M0 makes it a migration of live financial records later, not a schema addition.
>
> **M9 carries the highest technical risk** (R-1) and MUST NOT begin before `03_System_Architecture.md` specifies the conflict-resolution protocol.
>
> **M11 gates go-live on the opening-balance load** (R-6, DR-7) and on the NFR-USA-001 timed comparison (R-2). Both are pass/fail, not advisory.

---

## 24. Traceability

### 24.1 Objectives → requirements

| Objective | Primary requirements |
| --- | --- |
| PO-1 Single source of truth | FR-ORD-001, FR-STK-002, FR-REC-002, BR-004, BR-005 |
| PO-2 No re-entry | FR-ORD-008, FR-SYN-001…004, FR-ORD-007 |
| PO-3 Offline reliability | §5 in full, FR-SYN-001…017, NFR-OFF-001…005 |
| PO-4 Credit control at decision | FR-CUS-004…007, FR-ORD-020…026, FR-REC-008 |
| PO-5 Trustworthy inventory | FR-STK-001…007, FR-STK-020…026, BR-007 |
| PO-6 Automated pricing | FR-PRC-001…021, BR-011 |
| PO-7 Real-time visibility | FR-RPT-001…015, FR-REC-009 |
| PO-8 Complete auditability | FR-AUD-001…009, BR-002 |
| PO-9 Commercial quality | §21 in full |
| PO-10 Path to multi-tenant | NFR-SCA-002, §4.2, C-14 |

### 24.2 Vision decisions → requirements

| Decision | Realised by |
| --- | --- |
| DR-1 Configurable tax engine | FR-BIL-009…012, FR-PRD-004 |
| DR-2 Location-keyed stock | FR-STK-004, NFR-SCA-002, §4.2 |
| DR-3 Android, API 26+ | NFR-PER-002, §2.3 |
| DR-4 Lot-capable ledger | FR-PRD-005…007, FR-STK-005, FR-RET-010 |
| DR-5 RPO/RTO | NFR-AVA-001, NFR-AVA-002 |
| DR-6 Baseline capture | §25.3 |
| DR-7 One-time import | M11, §25.3 |
| DR-8 Design envelope | NFR-PER-001…005, NFR-SCA-001, FR-RPT-015 |
| DR-9 One return mechanism | FR-RET-001…010 |
| DR-10 Single-level approval | FR-ORD-022…027, FR-PRC-017, FR-STK-024, FR-PUR-014 |

### 24.3 Risks → mitigating requirements

| Risk | Mitigated by |
| --- | --- |
| R-1 Sync corrupts inventory/receivables | §5 in full, FR-STK-011, BR-010…BR-015, §18 verification note |
| R-2 Field adoption failure | FR-ORD-010, NFR-USA-001 *(acceptance gate)*, NFR-USA-002 |
| R-3 Scope expansion | §23 release allocation and milestone sequence |
| R-5 Tenancy retrofit | NFR-SCA-002, §4.2 |
| R-6 Opening-balance error | M11 gate |
| R-7 Statutory obligation | FR-BIL-020, CF-1 |
| R-8 Device loss | FR-IAM-010, FR-SYN-012, FR-SYN-016, NFR-SEC-008 |
| R-13 Unused lot dimension | Accepted; cost bounded to FR-PRD-005, FR-PRD-006, FR-STK-005 |

---

## 25. Verification & Acceptance

### 25.1 Definition of done

A requirement is done when it is implemented, covered by automated tests including failure cases, documented, and demonstrable to the business owner. **Passing tests alone do not constitute done** (C-9).

### 25.2 Requirements demanding adversarial verification

Ordinary testing is insufficient for these. Each carries a non-negotiable metric or an irreversible failure mode.

| Requirement | Why | Method |
| --- | --- | --- |
| FR-SYN-003, 004, 006 | Zero loss and zero duplicates are non-negotiable (§10.3) | Fault injection: severed connections, replayed batches, killed processes, clock skew, exhausted storage |
| FR-STK-011 with BR-010 | The R-1 corruption mode | Concurrent offline capture of the same scarce stock across multiple devices, then simultaneous sync |
| FR-BIL-003, 008 | Immutability of the financial record | Attempted mutation through every path, including direct persistence access |
| FR-IAM-007, NFR-SEC-011 | Authorisation bypass | Full role × capability matrix issued directly to the API, bypassing all clients |
| NFR-INT-002, 003 | Lost updates and balance divergence | Concurrency suite plus reconciliation assertion |
| NFR-USA-001 | R-2, the second-highest risk | Timed task comparison with real salesmen against the current paper process |

### 25.3 Project activities (not requirements)

| ID | Activity | Timing | Gates |
| --- | --- | --- | --- |
| ACT-A | Business-owner review and sign-off of this document | Before M0 | All implementation (C-1) |
| ACT-B | Baseline capture (DR-6) | During requirements phase | Vision §10 targets becoming binding |
| ACT-C | Confirmation of CF-1, statutory transmission obligation | Before M5 | M5 scope (R-7) |
| ACT-D | Master data extraction and mapping (DR-7) | Before M11 | Opening-balance load |
| ACT-E | Opening-balance load and reconciliation | M11 | Go-live (R-6) |
| ACT-F | Restore rehearsal (NFR-AVA-002) | M11 | Go-live |

---

## 26. Open Items

**None blocking.** Every item below resolves to configuration, an enabled structure, or a scheduled activity — none alters the domain model of §4.

| ID | Item | Needed before | Default if unanswered |
| --- | --- | --- | --- |
| OI-1 | Statutory transmission obligation (CF-1, ACT-C) | M5 | Proceed per A-15: no obligation. **The one item that could add v1.0 scope** |
| OI-2 | Scheme conflict strategy for FR-PRC-014: best-for-customer or explicit priority | M3 | Best-for-customer, configurable — the safer commercial default |
| OI-3 | Achievement basis for FR-TGT-003: ordered, invoiced or collected value | v1.1 | Invoiced value |
| OI-4 | ~~Aging bucket definition for FR-REC-008~~ | ~~M6~~ | **CLOSED at M6.** 0–30 / 31–60 / 61–90 / 90+ days, **fixed** — see §14.1 B-2 |
| OI-5 | Maximum offline period for FR-IAM-016 | M8 | 7 days, configurable |
| OI-6 | Non-restockable reason codes for FR-RET-003 | ~~M7~~ **Edition 2 (M-12)** | Seeded set, maintainable by `OWNER`. **Re-dated 2026-08-08:** restockability is a property of *structured* returns, and ADR-0009 removed the only Edition-1 path that would have consumed it — a credit note writes no stock movement. M7 reports on returns and writes nothing, so it neither needs nor can answer this |
| OI-7 | Rounding convention for NFR-INT-006 | M3 | Half-up at 2 decimal places, applied at line level |

---

## Document Control

**Approval**

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Business Owner (Sponsor) | | ☐ Approved ☐ Changes requested | |
| Product Architect | | ☐ Approved ☐ Changes requested | |
| Lead Implementation Engineer | | ☐ Approved ☐ Changes requested | |

**Next document**

`docs/03_System_Architecture.md` — component architecture, data model, and the synchronisation and conflict-resolution protocol. **M9 must not begin before it exists** (R-1).

*Implementation begins after ACT-A. No milestone starts before its dependencies in §23.1 are complete.*

