# DistriCore — Project Vision

| Field | Value |
| --- | --- |
| Document ID | `01_Project_Vision` |
| Product | DistriCore (working title) |
| Version | 0.2.0 |
| Status | **Draft — blocking questions resolved; pending stakeholder sign-off** |
| Date | 2026-08-04 |
| Owner | Product Architecture |
| Audience | Business owner, engineering, QA, future implementation partners |
| Supersedes | 0.1.0 |

**Changes in 0.2.0**

- All ten blocking open questions closed as recorded design decisions (§16.2) or reclassified as project activities.
- Release phasing introduced (§7.4). **No confirmed scope has been removed** — delivery is sequenced across v1.0, v1.1 and v1.2, which together constitute the confirmed scope.
- Capabilities whose requirement is unconfirmed (batch/serial tracking, multi-location operations, multi-tenant activation) moved to version-tagged future releases (§15) with their structural enablers retained in v1.0.

> **Authority.** This document is the single source of truth for *why* DistriCore exists and *what* it is intended to be. It deliberately does not specify implementation. Functional detail belongs in the Requirements Specification; structural detail belongs in the Architecture Document. Where this document and code disagree, this document wins until it is explicitly revised.
>
> **Scope discipline.** Every statement below is traceable to a confirmed decision. Items that are not yet decided are recorded as open questions in §16 and §17 rather than resolved by assumption.

---

## 1. Vision Statement

**DistriCore is the operating system of a distribution business — a single, authoritative system in which every order, every unit of stock, every invoice and every rupee owed is recorded once, reconciled continuously, and visible in real time to the people who need it.**

Distribution businesses fail not for lack of demand but for lack of visibility. Stock is counted on paper, orders arrive by phone, credit is tracked in memory, and the true financial position of the business is knowable only after the fact — if at all. DistriCore exists to close that gap: to make the physical movement of goods and the financial consequences of that movement two views of the same, always-current record.

---

## 2. Mission

To deliver a production-grade Sales and Distribution Management Platform for a single distributor that:

1. **Captures the complete order-to-cash cycle** — from order placement through fulfilment, invoicing, delivery and payment collection — as one continuous, auditable chain of events.
2. **Works where the business works.** Field sales and delivery happen outside the warehouse, frequently outside network coverage. The platform must remain fully operational offline and reconcile deterministically on reconnection.
3. **Serves every participant in the distribution chain** through an interface appropriate to their role: back-office staff, field salesmen, delivery personnel, and the retailers being served.
4. **Is engineered as a commercial product, not an internal tool** — tested, documented, secure, upgradeable, and capable of being deployed for paying customers.

---

## 3. Business Problem

A distributor sits between manufacturers and retailers, and absorbs complexity from both directions. The operational reality that DistriCore addresses:

### 3.1 Fragmented systems of record

Orders live in a salesman's notebook or a messaging app. Stock lives in a spreadsheet. Invoices live in accounting software. Outstanding payments live in the owner's head. No single system knows the true state of the business, so every number must be reconciled manually — and every reconciliation is an opportunity for error.

### 3.2 Disconnected field operations

The people who generate revenue — salesmen on route — are the people furthest from the system of record. Orders taken in the field must be re-entered at the office, introducing delay, transcription errors, and a permanent lag between what was sold and what the business believes was sold. A salesman standing in front of a retailer cannot reliably answer *"is this in stock?"* or *"what do you currently owe?"*.

### 3.3 Uncontrolled credit exposure

Distribution runs on credit. Without enforced credit limits and current outstanding balances at the point of order, credit decisions are made on intuition. Receivables age silently; bad debt is discovered rather than prevented.

### 3.4 Inventory that is trusted less than it is counted

Stock figures diverge from physical reality through unrecorded returns, damages, and fulfilment errors. The organisation compensates with over-stocking (working capital tied up) or discovers shortfalls at the moment of fulfilment (service failure). Neither is a decision — both are symptoms.

### 3.5 Pricing and scheme complexity applied by hand

Trade schemes, slab discounts and customer-specific pricing are applied manually per order. Manual application is inconsistent, unverifiable, and a direct margin leak. Salesman targets and the incentives attached to them are computed retrospectively from the same unreliable data.

### 3.6 Purchasing without demand signal

Procurement from suppliers is driven by habit rather than by sales velocity and current stock position, because that data is not available in usable form at the moment the purchase decision is made.

### 3.7 No usable audit trail

When a figure is disputed — an invoice, a payment, a stock count — there is no reliable way to reconstruct what happened, who did it, and when.

**The compound effect:** the business cannot answer basic operational questions quickly or confidently, cannot scale beyond the owner's personal supervision, and cannot detect margin loss until it appears in annual accounts.

---

## 4. Proposed Solution

DistriCore is an integrated, offline-capable Sales and Distribution Management Platform built around a single authoritative transactional core, accessed through four purpose-built client surfaces.

### 4.1 Solution principles

| Principle | Meaning |
| --- | --- |
| **Single source of truth** | One transactional record. Inventory, receivables and sales figures are *derived from* recorded events, never maintained in parallel. |
| **Offline-first for field operations** | Field clients hold local state, accept transactions without connectivity, and synchronise through an explicit, deterministic reconciliation protocol with defined conflict resolution. Offline is a first-class mode of operation, not a degraded one. |
| **Mechanism over policy** | Pricing rules, schemes, credit rules and approval thresholds are configurable mechanisms operating on data — not behaviour hardcoded for one business. This is what makes the eventual move to multi-tenant viable. |
| **Event-sourced auditability** | Every state-changing action is attributable to an actor and a time, and is retained. Financial documents are immutable once issued; corrections are new documents, never edits. |
| **Role-appropriate interfaces** | Each surface exposes only what its user needs. A salesman's app is not a smaller back-office app. |
| **Tenant-ready from day one** | The domain model carries tenancy boundaries from the outset even though only one tenant will exist at launch. Retrofitting tenancy into a live financial system is prohibitively expensive. |

### 4.2 Solution shape

```
                      ┌──────────────────────────────────┐
                      │   DistriCore Transactional Core   │
                      │  orders · inventory · invoicing   │
                      │  purchasing · receivables ·       │
                      │  pricing & schemes · identity     │
                      └──────────────────────────────────┘
                                     ▲
              ┌──────────────┬───────┴───────┬──────────────┐
              │              │               │              │
      ┌───────┴──────┐ ┌─────┴──────┐ ┌──────┴─────┐ ┌──────┴──────┐
      │  Web         │ │  Field     │ │  Delivery  │ │  Retailer   │
      │  Back-Office │ │  Sales App │ │  / Van App │ │  Portal     │
      │  (online)    │ │ (offline)  │ │ (offline)  │ │  (online)   │
      └──────────────┘ └────────────┘ └────────────┘ └─────────────┘
```

The core owns all business rules and all state. Clients are presentation and capture surfaces; no client is permitted to be the sole holder of a business rule.

---

## 5. Target Users

| # | User | Context | What DistriCore gives them |
| --- | --- | --- | --- |
| U1 | **Business owner / proprietor** | Accountable for margin, cash and credit exposure. Currently relies on personal recall and manual reports. | Current, trustworthy position of sales, stock, receivables and purchases without asking anyone. |
| U2 | **Sales / operations manager** | Manages the salesman team, routes and targets. | Order pipeline visibility, target and scheme performance, exception handling. |
| U3 | **Field salesman** | On route, at the retailer's counter, frequently without connectivity. | Order capture with live product, price, scheme, stock and outstanding-balance context; works offline; no re-entry at the office. |
| U4 | **Delivery / van staff** | Executes physical delivery and, commonly, collection. | Delivery manifest, proof of delivery, cash/payment collection recording, returns capture — offline. |
| U5 | **Warehouse / inventory staff** | Receives goods in, picks and dispatches goods out. | Goods receipt against purchase orders, picking against orders, stock adjustments with reason codes. |
| U6 | **Accounts / billing staff** | Issues invoices, applies payments, chases outstandings. | Invoicing from fulfilled orders, payment application, customer ledgers, aging visibility. |
| U7 | **Purchase officer** | Places and tracks supplier orders. | Purchase orders informed by stock position and sales velocity; supplier ledger. |
| U8 | **Retailer / customer** | Buys from the distributor. | Self-service ordering, order status, own statement of account. |
| U9 | **System administrator** | Operates the deployment. | User and role administration, master data governance, configuration, audit access. |

> Users U1–U7 and U9 are internal to the distributor. U8 is external and reaches the system only through the Retailer Portal, under a distinct trust boundary.

---

## 6. Stakeholders

| Stakeholder | Role in the project | Primary interest |
| --- | --- | --- |
| **Business owner** | Sponsor; final acceptance authority for business behaviour | Correct, deployable software that reflects how the business actually operates |
| **Product Architect / Research Director** (ChatGPT) | Owns requirements, architecture and the `docs/` corpus | Architectural coherence; specification precision |
| **Lead Implementation Engineer** (Claude) | Owns implementation, testing and verification | Buildable specifications; production-quality delivery |
| **Distributor operational staff** | Domain informants and end users | Fitness for daily work; no increase in effort per transaction |
| **Retailers** | External users | Reliable ordering and accurate statements |
| **Suppliers / principals** | Indirect | Accurate purchase and settlement data |
| **Future paying customers** | Downstream commercial target | Configurability, data isolation, reliability |
| **Regulatory / statutory authorities** | Compliance constraint | Compliant tax documents and retained records. *Specific jurisdiction and statutory obligations are open — see §16.* |

---

## 7. Project Scope

The following capabilities are **confirmed in scope** for DistriCore v1.0.

### 7.1 Client surfaces

| ID | Surface | Connectivity model |
| --- | --- | --- |
| S1 | **Web back-office** — administration, master data, inventory, purchasing, invoicing, receivables, reporting | Online |
| S2 | **Mobile field-sales application** — route-based order capture for salesmen | **Offline-first**, synchronising |
| S3 | **Mobile delivery / van application** — delivery execution, proof of delivery, collection, returns capture | **Offline-first**, synchronising |
| S4 | **Retailer self-service portal** — customer-placed orders, order status, statement of account | Online |

### 7.2 Functional domains

| ID | Domain | In scope |
| --- | --- | --- |
| D1 | **Customer management** | Retailer master data, classification, credit terms and limits, statements |
| D2 | **Product & inventory management** | Product master, units of measure, stock positions, receipts, issues, adjustments with reason codes, sales and purchase returns. Stock is keyed by *(product, stock location, lot)* per DR-2 and DR-4; v1.0 operates one location and applies no lot tracking |
| D3 | **Order management** | Order capture across all surfaces, validation, configurable single-level approval (DR-10), fulfilment lifecycle, cancellation and amendment rules |
| D4 | **Invoicing** | Invoice generation from fulfilled orders, credit notes, immutable issued documents, document numbering series, and a configurable tax-rule engine producing a persisted per-line tax breakdown (DR-1) |
| D5 | **Purchase & supplier management** | Supplier master, purchase orders, goods receipt against PO, purchase returns, supplier ledger |
| D6 | **Accounts receivable & collections** | Outstanding balances, credit-limit enforcement at point of order, payment recording and application, aging analysis, collection tracking |
| D7 | **Schemes, discounts & pricing** | Configurable price lists, customer-specific pricing, trade schemes and slab discounts applied automatically at order time |
| D8 | **Sales targets & performance** | Target definition per salesman/period, achievement tracking, commission computation basis |
| D9 | **Identity, roles & access control** | Authentication, role-based authorisation aligned to §5, session and device management |
| D10 | **Synchronisation** | Offline transaction queueing, deterministic sync protocol, conflict detection and resolution, sync observability |
| D11 | **Audit & traceability** | Attributable, timestamped, retained record of all state-changing operations |
| D12 | **Operational reporting** | Reporting over the domains above, sufficient for daily operational decision-making |

### 7.3 Cross-cutting engineering scope

- Automated test coverage including edge and failure cases for every milestone.
- Documented deployment, backup and restore procedures.
- Data model carrying tenancy boundaries in anticipation of multi-tenant operation.
- Security controls per §13.

> The precise feature list within each domain is defined by the Requirements Specification, not by this document. §7.2 defines the *boundary*, not the backlog.

### 7.4 Release phasing

**Nothing in §7.1 or §7.2 has been removed from scope.** Releases v1.0, v1.1 and v1.2 together deliver the entire confirmed scope. Phasing exists to mitigate R-3 (four client surfaces plus twelve domains is substantial concurrent scope for a small team, C-10) and to sequence delivery so that each release is independently valuable and verifiable.

| Release | Contents | Rationale |
| --- | --- | --- |
| **v1.0 — Core distribution platform** | S1 web back-office, S2 field-sales app. Domains D1–D7 (single stock location, no lot tracking), D9 identity, D10 sync, D11 audit, D12 operational reporting. | Establishes the single source of truth and the offline order path — the two objectives (PO-1, PO-2) on which every other benefit depends. Delivers the complete order-to-cash cycle. |
| **v1.1 — Field completion** | S3 delivery / van app. D8 sales targets & performance. | Delivery execution and collection close the physical loop. D8 is a reporting-layer capability over data v1.0 already records, so it carries no dependency risk and is cheap to defer. |
| **v1.2 — Customer channel** | S4 retailer self-service portal. | Deliberately last: portal value depends on the catalogue, pricing, stock and receivables data being demonstrably trustworthy, which only proven v1.0 operation establishes. Also mitigates R-10. |

**Sequencing rule.** A release begins only when the prior release is in production and its §10 metrics are being measured. Surfaces are delivered in sequence rather than in parallel (C-10).

**Structural obligation.** Deferring a *capability* never permits deferring its *structural enabler*. Where a later release requires a change that would be expensive to retrofit — tenancy (C-13), stock location (DR-2), lot tracking (DR-4) — the structure is present in v1.0 even though the behaviour is not. This is the single most important consequence of the phasing decision.

---

## 8. Out of Scope

Explicitly **not** part of the confirmed scope (§7). Exclusion is a scope decision, not a judgement of value; items may be reconsidered under §15.

| # | Excluded | Rationale | Reconsidered at |
| --- | --- | --- | --- |
| O1 | **Full financial accounting / general ledger** | DistriCore is an operational system. It owns receivables and payables *as they arise from distribution activity*, not double-entry bookkeeping, trial balance or statutory financial statements. | v1.3 — as *integration* with accounting software, not as a ledger implementation |
| O2 | **Payroll and HR** | Unrelated domain. Salesman *commission basis* is in scope (D8, v1.1); its disbursement is not. | Not planned |
| O3 | **Manufacturing, production planning or MRP** | The subject is a distributor, not a manufacturer (A-1). | Not planned |
| O4 | **Multi-tenant operation as a live capability** | Tenant provisioning, isolation enforcement, subscription billing and self-service onboarding are not built. The data model is tenant-*ready* from the first migration (C-13). | v2.0 |
| O5 | **Multi-location stock operations** | Inter-location transfers, per-location reservation, location-aware picking and per-location reporting. Requirement unconfirmed. The stock model is location-keyed from the first migration (DR-2), so this is an operational feature, not a re-architecture. | v1.1, subject to business confirmation |
| O6 | **Integrated online payment gateway** | DistriCore records payments; it does not process them. | v1.3 |
| O7 | **Route planning, GPS tracking and geo-optimisation** | Materially distinct problem domain with its own complexity. Route *membership* is in scope (A-4); route *optimisation* is not. | v2.1 |
| O8 | **Automated demand forecasting / replenishment suggestions** | Requires operational history the system does not yet have. Cannot be built before it can be trained. | v2.1 |
| O9 | **Third-party e-commerce or marketplace integration** | No confirmed requirement. | Not planned |
| O10 | **Native iOS applications** | Resolved by DR-3: Android only. Adding iOS is a client-surface decision, not a core change. | v2.0, subject to demand |
| O11 | **Business intelligence / analytics warehouse** | Operational reporting (D12) is in scope; a dimensional analytics platform is not. | v2.1 |
| O12 | **Migration tooling as a product feature** | No legacy software system exists (DR-7). One-time master-data and opening-balance import is an in-scope project activity, not a shipped feature. | Not planned |
| O13 | **Statutory e-invoicing / government portal reporting** | Follows from DR-1: the tax engine produces compliant *documents*, but transmission to any statutory portal is a jurisdiction-specific integration. **This is the residual exposure of R-7 and must be confirmed as non-mandatory before v1.0 go-live.** | v1.1, if legally required |
| O14 | **Batch, lot and expiry tracking as an operating capability** | Requirement unconfirmed (DR-4). The stock ledger is lot-capable from the first migration; the tracking policy, expiry handling and expiry-driven reporting are not implemented. | v1.1, subject to business confirmation |
| O15 | **Serial-number tracking** | As O14. Same structural enabler, same deferral. | v1.1, subject to business confirmation |
| O16 | **Multi-level or parallel approval chains** | DR-10 delivers single-level configurable approval. Chained approvals are a workflow-engine problem and would be premature. | v1.2 |

---

## 9. Product Objectives

| ID | Objective | Description |
| --- | --- | --- |
| PO-1 | **Establish a single source of truth** | Every distribution transaction is recorded once, in DistriCore, and every downstream figure derives from it. Eliminate parallel books. |
| PO-2 | **Eliminate re-entry between field and office** | An order captured in the field is *the* order — never re-keyed. |
| PO-3 | **Make offline operation fully reliable** | No transaction is lost, duplicated or silently altered by a connectivity failure. Sync outcomes are deterministic and observable. |
| PO-4 | **Enforce credit control at the point of decision** | Credit limits and current outstanding balances are applied when the order is taken, not discovered afterwards. |
| PO-5 | **Make inventory trustworthy** | System stock reflects physical stock within an agreed tolerance, with every divergence explained by a recorded, reason-coded event. |
| PO-6 | **Automate pricing and scheme application** | Correct price and scheme applied by the system, identically, on every order regardless of surface. |
| PO-7 | **Give the owner real-time operational visibility** | Sales, stock, receivables and purchase position available on demand without manual compilation. |
| PO-8 | **Provide complete auditability** | Any transaction can be reconstructed: what changed, who changed it, when, and from where. |
| PO-9 | **Achieve commercial-grade quality** | Tested, documented, secure, operable, and supportable by an engineer who did not write it. |
| PO-10 | **Preserve the path to multi-tenant SaaS** | No v1.0 decision may make multi-tenancy unreasonably expensive to introduce. |

---

## 10. Success Metrics

Metrics are the acceptance evidence for §9.

**Baselines are not yet measured.** Per DR-6 this is not a design question but a project activity: *Activity B — Baseline Capture* runs during the requirements phase and records current-state figures for stock variance, receivables aging, order-to-invoice cycle time and pricing-error rate from existing manual operations. Targets below are **proposed** and become **binding on completion of Activity B** and stakeholder confirmation. Metrics marked *non-negotiable* are independent of baseline and binding immediately.

Unless stated otherwise, each metric is measured against the release that first delivers the capability it tests (§7.4).

### 10.1 Product and adoption

| Metric | Traces to | Proposed target |
| --- | --- | --- |
| Share of orders captured directly in DistriCore (all surfaces) | PO-1, PO-2 | ≥ 95% of orders within 90 days of go-live |
| Orders re-keyed manually by back-office staff | PO-2 | 0 |
| Active salesmen using the field app on route, daily | PO-2 | 100% of the field team |
| Retailer orders placed through the portal | PO-1 | Baseline established in first 90 days; growth target set thereafter |

### 10.2 Operational accuracy

| Metric | Traces to | Proposed target |
| --- | --- | --- |
| Stock variance at physical count (system vs. physical) | PO-5 | ≤ 1% by value |
| Unexplained stock variances (no reason-coded event) | PO-5 | 0 |
| Invoices requiring correction due to pricing or scheme error | PO-6 | ≤ 0.5% of invoices issued |
| Orders accepted in breach of credit limit without recorded approval | PO-4 | 0 |
| Order-to-invoice cycle time | PO-1, PO-2 | Measurable and reduced against baseline |

### 10.3 Synchronisation integrity

| Metric | Traces to | Proposed target |
| --- | --- | --- |
| Transactions lost during offline operation | PO-3 | **0 — non-negotiable** |
| Duplicate transactions created by sync | PO-3 | **0 — non-negotiable** |
| Sync conflicts requiring manual intervention | PO-3 | ≤ 1% of synchronised transactions |
| Time from reconnection to full sync (typical daily volume) | PO-3 | ≤ 2 minutes |

### 10.4 Financial control

| Metric | Traces to | Proposed target |
| --- | --- | --- |
| Receivables aged beyond agreed terms | PO-4 | Reduced against baseline |
| Time to produce current receivables position | PO-7 | On demand (< 10 seconds), replacing manual compilation |
| Margin leakage from misapplied schemes | PO-6 | Quantified and reduced to ≈ 0 |

### 10.5 Engineering quality

| Metric | Traces to | Proposed target |
| --- | --- | --- |
| Automated test coverage of business-rule code | PO-9 | ≥ 80% line coverage; 100% of pricing, credit and sync rules covered including failure cases |
| Milestones merged without a green build | PO-9 | 0 |
| Documented modules (`docs/` current with code) | PO-9 | 100% |
| Critical defects in production per quarter | PO-9 | 0 |
| Data-loss incidents | PO-3, PO-9 | **0 — non-negotiable** |

---

## 11. Business Value

### 11.1 Direct value

| Area | Mechanism |
| --- | --- |
| **Margin protection** | Automated pricing and scheme application removes discretionary and erroneous discounting (PO-6). |
| **Working capital release** | Accurate stock enables lower safety stock without service failure (PO-5). |
| **Reduced bad debt** | Credit limits enforced before commitment, not after exposure (PO-4). |
| **Labour recovered** | Elimination of re-entry, manual reconciliation and manual report compilation (PO-2, PO-7). |
| **Revenue protection** | Salesmen answer stock, price and balance questions at the counter, reducing lost and incorrect orders (PO-2). |
| **Faster cash conversion** | Shorter order-to-invoice and invoice-to-collection cycles (PO-1, PO-4). |

### 11.2 Strategic value

- **Scalability of the business.** Operations cease to depend on the owner's personal supervision; volume and headcount can grow without proportional growth in error.
- **Decision quality.** Purchasing, credit and target decisions are made against current data rather than recall.
- **Defensible records.** A complete audit trail supports dispute resolution with retailers, suppliers and authorities.
- **A commercial asset.** Built to product standard and tenant-ready, DistriCore is a potential revenue line serving other distributors — not merely an internal cost (PO-10).

### 11.3 Cost of inaction

Continued manual operation sustains silent, uncapped margin leakage, unbounded credit exposure, and an operational ceiling fixed by one person's attention. These costs are already being paid; they are simply not being measured.

---

## 12. Functional Overview

A narrative view of the confirmed scope in §7. Detailed behaviour is specified in the Requirements Specification.

### 12.1 The core cycle — order to cash

```
  Retailer demand
        │
        ▼
  ORDER CAPTURE ──────────────┐  field app (offline) · portal · back-office
        │                     │  validates: customer status, credit limit,
        │                     │  stock availability, price & scheme
        ▼                     │
  ORDER APPROVAL (conditional)│  triggered by configured exception rules
        │                     │
        ▼                     │
  FULFILMENT ─────────────────┤  pick · dispatch · stock issued
        │                     │
        ▼                     │
  DELIVERY ───────────────────┤  van app (offline): proof of delivery,
        │                     │  returns capture, collection
        ▼                     │
  INVOICING ──────────────────┤  immutable document; credit notes for correction
        │                     │
        ▼                     │
  RECEIVABLE ─────────────────┤  ledger entry, aging, collection tracking
        │                     │
        ▼                     │
  PAYMENT APPLICATION ────────┘  balance and available credit updated
```

Every transition emits an attributable, timestamped event (D11). Stock and receivable positions are consequences of these events, never independently maintained figures.

### 12.2 The replenishment cycle

Stock position and sales velocity inform purchase orders to suppliers; goods receipt against those orders increases stock and creates the supplier payable. Purchase returns reverse both.

### 12.3 Pricing, schemes and targets

Price lists, customer-specific pricing, trade schemes and slab discounts are configured centrally as data and evaluated by the core at order time. Because evaluation lives in the core, a salesman offline, a retailer on the portal and a clerk in the back-office receive the identical price for the identical order. Sales targets are defined per salesman and period; achievement is computed from recorded orders and forms the commission basis.

### 12.4 Offline operation and synchronisation

The field-sales and delivery applications hold the working data set required for a route and accept transactions with no connectivity. Transactions are queued locally with client-assigned identity, transmitted on reconnection, and reconciled by the core under an explicit conflict-resolution policy. Sync state is visible to the user and to administrators; nothing fails silently.

*The conflict-resolution policy — particularly for stock allocated concurrently to two offline salesmen — is a defining architectural decision and is specified in the Architecture Document, not here.*

### 12.5 Identity and access

Every user authenticates and acts under a role that determines permitted operations and visible data. Retailer portal users sit outside the internal trust boundary and can access only their own orders and statements. Devices used for offline operation are individually identifiable and revocable.

### 12.6 Reporting

Operational reporting spans sales, inventory, receivables, purchasing and salesman performance, sufficient for daily decision-making by users U1–U3 and U6.

---

## 13. Non-Functional Goals

| ID | Goal | Statement |
| --- | --- | --- |
| NFR-1 | **Data integrity** | Financial and inventory transactions are atomic and consistent. Issued financial documents are immutable. Corrections are new documents. Loss or silent alteration of a committed transaction is a critical defect. |
| NFR-2 | **Offline reliability** | Field clients remain fully functional without connectivity for a complete working day. Sync is idempotent: replaying a transmission produces no duplicates. |
| NFR-3 | **Performance** | Interactive back-office and portal operations respond within 2 seconds at the 95th percentile under the DR-8 design envelope. Field-app order capture is bounded by local storage, not by network. |
| NFR-4 | **Scalability** | Architecture sustains the **DR-8 three-year design envelope** without redesign: ≤10,000 active SKUs, ≤10,000 retailers, ≤100 concurrent internal users, ≤50 synchronising field devices, ≤10,000 order lines per day, ≤5 years of transaction history retained online. Also supports the later addition of tenants (PO-10) and stock locations (DR-2). |
| NFR-5 | **Security** | Authenticated access, role-based authorisation enforced server-side, validated input, parameterised data access, protection against injection, XSS and CSRF, secure file handling, secrets never in source control, encryption in transit. Field devices hold sensitive commercial data and require device-level protection and remote revocation. |
| NFR-6 | **Auditability** | State-changing operations are attributable, timestamped and retained. Audit records are append-only. |
| NFR-7 | **Availability & recoverability** | Documented and **periodically tested** backup and restore. Per DR-5: **RPO ≤ 15 minutes, RTO ≤ 4 hours** for the transactional core. Restore must be verified by rehearsal, not assumed. Field devices tolerate a longer core outage than these targets because offline operation is unaffected (NFR-2) — the binding constraint is device local-storage capacity, not core availability. |
| NFR-8 | **Maintainability** | SOLID principles, composition over inheritance, no duplicated business logic, strong typing, graceful error handling. A competent engineer new to the codebase can locate and safely change any business rule. |
| NFR-9 | **Testability** | Business rules are testable in isolation. Every milestone ships with edge-case and failure-case coverage. |
| NFR-10 | **Usability** | Field and delivery apps are usable one-handed, at speed, in poor lighting, by non-technical staff. Order capture must be *faster* than the paper process it replaces, or it will not be adopted. |
| NFR-11 | **Configurability** | Business-variable behaviour — pricing, schemes, credit rules, approval thresholds, roles — is configuration, not code (§4.1). |
| NFR-12 | **Observability** | Application health, error rates and synchronisation status are monitorable in production. |
| NFR-13 | **Documentation** | `docs/` remains current with delivered code. Documentation is a deliverable of each milestone, not a follow-up task. |

---

## 14. Risks

Severity reflects impact × likelihood on current information.

| ID | Risk | Severity | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| R-1 | **Offline sync conflicts corrupt inventory or receivables.** Concurrent offline allocation of the same stock is the hardest problem in the system. | **Critical** | Loss of trust in the system; financial error | Design conflict resolution explicitly before implementation; make allocation semantics deliberate; exhaustive automated tests for concurrent-offline scenarios; treat sync as a first-class specified protocol |
| R-2 | **Field adoption failure.** If the app is slower than paper, salesmen route around it and the single source of truth never materialises. | **Critical** | Total loss of PO-1 and PO-2 | NFR-10 as a hard acceptance criterion; salesman participation in design; measure task time against the paper baseline before go-live |
| R-3 | **Scope expansion across four client surfaces.** Four surfaces plus eight functional domains is substantial scope for v1.0. | **High** | Schedule overrun; partially implemented features | Strict milestone discipline (one complete milestone at a time); documented scope boundary (§7, §8); surface delivery sequenced rather than parallel |
| R-4 | **Requirements drawn from assumption rather than the business.** §16.2 decisions were made on architectural reasoning, not on business confirmation. | **High** | Software that does not match how the business operates | Every decision in §16.2 is recorded with its rationale and is falsifiable; each is structured so that being wrong costs configuration rather than redesign. Requirements Specification requires business-owner sign-off before implementation |
| R-5 | **Tenancy retrofit becomes necessary.** If tenant boundaries are omitted, later multi-tenancy requires reworking a live financial system. | **High** | Prohibitive future cost; PO-10 lost | Tenant-ready data model from the first migration (§4.1, C-13) |
| R-6 | **Opening-balance load is incorrect.** Stock, receivables and payables must be established accurately at go-live (DR-7). | **High** | A corrupt starting position undermines every derived figure permanently | Opening-balance load is an explicit milestone with a reconciliation report and business sign-off; go-live is gated on it |
| R-7 | **Statutory reporting obligation discovered late.** DR-1 makes invoice *content* configurable, but a mandatory e-invoicing or government-portal integration (O13) would be new scope. | **High** | Invoices legally insufficient; unplanned integration work | Confirm with the business owner whether any statutory transmission obligation exists **before the D4 invoicing milestone starts**. This is the single highest-value confirmation outstanding |
| R-13 | **Lot-capable stock ledger carried but never used.** DR-4 adds a dimension to every stock movement for a capability deferred to v1.1 and not yet confirmed. | **Low** | Small, permanent carrying cost in v1.0 | Accepted deliberately. The asymmetry is decisive: carrying the dimension costs one nullable key and a default lot; retrofitting it into a live stock ledger with historical movements costs a re-architecture and a data migration of the financial record |
| R-14 | **Phased releases are treated as permission to ship partial features.** | **Medium** | Violates C-2; produces a system that is never coherently done | §7.4 sequences *whole capabilities*, never fragments of one. Each release must independently satisfy the definition of done (C-9) |
| R-8 | **Device loss or theft exposes commercial data.** Field devices hold customer, pricing and balance data. | **Medium** | Competitive and privacy exposure | NFR-5: device-level protection, minimised local data set, remote revocation |
| R-9 | **Key-person dependency in delivery.** A small team building a broad product. | **Medium** | Delivery stalls; knowledge loss | NFR-8 and NFR-13; documentation as a milestone deliverable |
| R-10 | **Retailer portal adoption is low.** Retailers may prefer ordering through a salesman. | **Medium** | Effort invested in a lightly used surface | Sequence the portal after field-sales value is proven; measure and reassess |
| R-11 | **Performance degradation as history accumulates.** Reporting over growing transaction volume. | **Medium** | Slow reports; poor experience | NFR-3 and NFR-4 as design constraints; test against projected multi-year volumes |
| R-12 | **Documentation drifts from code**, breaking the "documentation wins" rule. | **Medium** | Ambiguous source of truth | Documentation updates in the same change as the code (NFR-13) |

---

## 15. Future Vision

Version tags below indicate *intended sequence*, not commitment. Each release beyond the confirmed scope (§7) requires its own approval and its own requirements. Releases v1.0–v1.2 are the confirmed scope and are specified in §7.4, not here.

### v1.1 — Completing the operating picture *(conditional on business confirmation)*

Capabilities whose structural enablers exist in v1.0 but whose requirement is unconfirmed. Each becomes a configuration and feature exercise, not a re-architecture.

| Capability | Enabler already in v1.0 | Confirmation needed |
| --- | --- | --- |
| Batch / lot tracking with expiry management (O14) | Lot-capable stock ledger (DR-4) | Does the industry require it? |
| Serial-number tracking (O15) | As above | Are serialised goods handled? |
| Multi-location stock operations (O5) | Location-keyed stock model (DR-2) | Is there more than one stock location? |
| Statutory e-invoicing / portal transmission (O13) | Configurable tax engine and document model (DR-1) | Is transmission legally mandatory? |

### v1.2 — Control depth

- Multi-level and parallel approval chains (O16), extending the single-level mechanism of DR-10.
- Deeper scheme modelling — combinatorial and cross-product schemes — if realised-margin analysis shows the v1.0 model is insufficient.

### v1.3 — Financial integration

- Accounting-system integration across the O1 boundary. **The intent remains integration, not building a general ledger.**
- Payment gateway integration for digital collection (O6).

### v2.0 — Commercialisation

- **Activation of multi-tenant SaaS operation** — the capability v1.0 is architected to permit (PO-10, C-13): tenant provisioning, isolation enforcement, subscription billing, self-service onboarding.
- Vertical configuration packs, specialising the domain-agnostic core (C-12) per industry without forking the codebase. This is the commercial payoff of the domain-agnostic constraint.
- Public API and partner integration surface.
- iOS client (O10), if customer demand warrants it.

### v2.1 — Intelligence

- Demand forecasting and replenishment suggestions from accumulated history (O8).
- Credit-risk scoring from observed payment behaviour.
- Route and scheme optimisation informed by realised margin (O7, O11).

Every one of these depends on the same precondition: a correct, complete and trusted transactional record. That is what v1.0 must deliver, and it is why v1.0 scope is deliberately narrow.

---

## 16. Assumptions

Assumptions are explicit and falsifiable. **Any assumption proven wrong requires this document to be revised before implementation continues.** Open questions (OQ) are assumptions that have not yet been made — they must be answered, not guessed.

### 16.1 Stated assumptions

| ID | Assumption |
| --- | --- |
| A-1 | The subject is a single distributor business purchasing from suppliers/principals and selling to retailers. It does not manufacture. |
| A-2 | v1.0 serves exactly one distributor organisation; multi-tenancy is architectural readiness only (§4.1, PO-10). |
| A-3 | The business operates on credit terms with retailers, making credit control (D6) essential rather than optional. |
| A-4 | Field sales occurs on defined routes, with salesmen visiting retailers in person. |
| A-5 | Connectivity in the field is unreliable, making offline operation mandatory rather than a convenience. |
| A-6 | Field and delivery staff have access to smartphones capable of running the applications. |
| A-7 | Delivery staff commonly collect payment at the point of delivery. |
| A-8 | The business owner is available as the domain authority and acceptance signatory throughout the project. |
| A-9 | The business will accept process change where the software requires it; DistriCore is not obliged to replicate every existing manual practice. |
| A-10 | Product master data (products, prices, customers, suppliers) exists in some transferable form for initial loading. |
| A-11 | The distributor sells physical goods tracked by discrete units of measure. |
| A-12 | Field and delivery devices are Android smartphones meeting the DR-3 minimum. |
| A-13 | The distributor operates from a single physical stock location at v1.0 go-live. |
| A-14 | Goods handled at v1.0 require no batch, expiry or serial identification. **This is the least certain assumption in this document** and is the reason DR-4 preserves the structural option. |
| A-15 | No statutory obligation exists to transmit invoices to a government portal at go-live (O13, R-7). *Requires confirmation.* |
| A-16 | No incumbent software system exists; current operation is manual or spreadsheet-based (DR-7). |
| A-17 | Salesmen and delivery staff are distinct roles, though one person may hold both. |
| A-18 | The v1.0 device population synchronises against a single core deployment reachable over the public internet. |

### 16.2 Resolved decisions

The ten questions raised as blocking in version 0.1.0 are closed below. **Seven are engineering decisions taken on architectural reasoning; three were not design questions at all and are reclassified as project activities.**

Each decision is recorded with the alternative rejected and the cost of being wrong. Every decision is deliberately structured so that an incorrect business assumption costs *configuration or a deferred feature*, never a re-architecture. That property is what made it defensible to proceed without further business input.

| ID | Closes | Decision | Alternative rejected | Cost if the assumption proves wrong |
| --- | --- | --- | --- | --- |
| **DR-1** | OQ-1 | **Jurisdiction-neutral invoicing with a configurable tax-rule engine.** Tax codes attach to products; rates carry effective dates; tax is computed per line and the resulting breakdown is *persisted on the issued document* rather than recomputed on read. Statutory fields and numbering series are configuration; one jurisdiction profile is configured at v1.0. | Hardcoding one jurisdiction's tax rules — rejected as a direct violation of C-12 and NFR-11, and as the change most expensive to reverse once invoices exist. | Configuration change. **Except** where statutory *transmission* is mandatory (O13, R-7) — that is new scope, and it is the one exposure this decision does not neutralise. |
| **DR-2** | OQ-2 | **Stock is keyed by *(product, stock location, lot)* from the first migration.** v1.0 seeds exactly one location and exposes no location UI. Multi-location *operations* deferred to v1.1 (O5). | Modelling stock as a per-product quantity — rejected: adding a location dimension to a stock ledger with historical movements and derived financial positions is a data migration of the financial record. | Enable an existing dimension and build location-aware operations. No model change. |
| **DR-3** | OQ-3 | **Android only, minimum Android 8.0 (API 26)**, for both S2 and S3. iOS remains out of scope (O10). | Cross-platform support at v1.0 — rejected as scope expansion (R-3) with no confirmed demand. *Native vs. cross-platform framework is an Architecture Document decision, not a vision decision, and is deliberately not taken here.* | A new client surface against an unchanged API. Core untouched. |
| **DR-4** | OQ-4 | **The stock ledger is lot-capable; lot tracking is not operated.** Every stock movement references an inventory lot. Products carry a tracking policy: `NONE` (v1.0 default, movements post to an implicit default lot), `BATCH`, `SERIAL`. v1.0 implements `NONE` only; the others are enabled in v1.1 without schema change (O14, O15). | (a) Omitting lots entirely — rejected: retrofitting lot identity into a live stock ledger is the single most expensive change in this domain. (b) Implementing full batch tracking now — rejected as building an unconfirmed requirement, violating C-3. | Set the tracking policy and implement expiry handling and reporting. See R-13 for the accepted carrying cost. |
| **DR-5** | OQ-5 | **RPO ≤ 15 minutes, RTO ≤ 4 hours** for the transactional core, verified by restore rehearsal. | Leaving the target undefined — rejected: an untargeted backup strategy cannot be tested, and an untested backup is not a backup. | An operations-tier change. No code impact. |
| **DR-6** | OQ-6 | **Not a design question — reclassified as *Activity B, Baseline Capture*,** run during the requirements phase. §10 targets are proposed until it completes. | Inventing plausible baselines — rejected outright: fabricated baselines would make §10 unfalsifiable and the acceptance criteria meaningless. | None. The activity produces the answer. |
| **DR-7** | OQ-7 | **No legacy system assumed (A-16).** Master data and opening balances are loaded once via verifiable CSV import, with a reconciliation report and business sign-off gating go-live. Migration tooling is not a product feature (O12). | Building general-purpose migration tooling — rejected as speculative scope for a system that has not been identified. | A one-time extraction and mapping exercise, absorbed by the same import path. |
| **DR-8** | OQ-8 | **Three-year design envelope stated in NFR-4** and used as the load target for performance testing. | Leaving scale undefined — rejected: NFR-3 and NFR-4 would be untestable assertions. | Re-test against a revised envelope; architecture is designed to scale within an order of magnitude of it. |
| **DR-9** | OQ-9 | **Returns are one mechanism, not several.** Sales returns (at delivery and post-delivery) produce a stock receipt with a reason code and a credit note. Purchase returns to supplier reverse stock and the payable. Damaged and expired goods use the same mechanism with different reason codes. | Separate handling per return type — rejected as duplicated logic, violating the no-duplication standard and §4.1. | Extend the reason-code set. Configuration only. *Expiry-**driven** identification of returnable stock requires DR-4 tracking → v1.1.* |
| **DR-10** | OQ-10 | **Single-level configurable approval.** A rule is *(trigger condition → approver role)*. v1.0 triggers: credit-limit breach, discount above threshold, order value above threshold. Approval events are audited (D11). | Hardcoding credit-limit approval only — rejected as policy embedded in code (C-12, NFR-11). Building a workflow engine — rejected as premature abstraction. | Add trigger conditions (configuration). Chained approvals are v1.2 (O16). |

### 16.3 Outstanding confirmations — non-blocking

These do not block requirements or implementation, but each must be confirmed before the milestone named. **None of them changes the core domain model**; each resolves to enabling an existing structure or to configuration.

| ID | Confirmation required | Confirm before | Consequence if deferred |
| --- | --- | --- | --- |
| CF-1 | **Does a statutory e-invoicing or portal-transmission obligation exist?** (A-15, O13, R-7) | D4 Invoicing milestone | The only outstanding item that could introduce genuinely new v1.0 scope. **Highest priority.** |
| CF-2 | **Are batch, expiry or serial identification required?** (A-14, O14, O15) | v1.1 planning | None for v1.0 — DR-4 preserves the option at known cost |
| CF-3 | **Is there more than one stock location?** (A-13, O5) | v1.1 planning | None for v1.0 — DR-2 preserves the option at negligible cost |
| CF-4 | **Confirmation of the DR-8 design envelope.** | Performance-test milestone | Test targets remain provisional |
| CF-5 | **Confirmation of DR-5 recovery objectives.** | Deployment milestone | Backup strategy remains provisional |
| CF-6 | **Completion of Activity B (baselines).** (DR-6) | v1.0 acceptance | §10 targets remain proposed, not binding |

---

## 17. Constraints

| ID | Constraint | Type | Implication |
| --- | --- | --- | --- |
| C-1 | **Documentation is the single source of truth.** Where code and `docs/` conflict, documentation prevails until explicitly revised. | Process | Specification precedes implementation, without exception |
| C-2 | **One logically complete milestone at a time.** Each milestone must compile, run, validate its inputs, and contain no partially implemented features. | Process | No parallel half-finished workstreams; no speculative scaffolding |
| C-3 | **Business requirements may not be invented.** Where specification is incomplete, work stops and clarification is requested. | Process | This document's §16 exists to make that stopping point explicit rather than silent |
| C-4 | **Offline-first behaviour must be preserved** in any feature touching orders, billing or synchronisation. | Architectural | Constrains every design decision in D3, D4 and D10 permanently |
| C-5 | **Architecture is not restructured without approval.** Better designs are proposed and approved before being built. | Process | Architectural change is a decision, not a side effect |
| C-6 | **Schema changes require justification, migration impact and compatibility analysis.** | Technical | Migrations are reviewed artefacts |
| C-7 | **API backward compatibility is maintained wherever possible.** Field devices may run older client versions after a server release. | Technical | Versioning strategy is mandatory, not optional |
| C-8 | **Production quality is the baseline.** No prototypes, no quick hacks, no code paths knowingly unfit for production. | Engineering | Affects estimation: nothing is "quick" |
| C-9 | **Every milestone ships with tests covering edge and failure cases, and with documentation updated.** | Engineering | Definition of done is fixed and non-negotiable |
| C-10 | **Small team.** Constrains parallelism and argues for sequencing surfaces rather than building four at once (R-3). | Resource |
| C-11 | **Field hardware is consumer-grade** — variable performance, intermittent connectivity, constrained storage and battery. | Environmental | Bounds the local data set and sync payload design |
| C-12 | **The core must remain domain-agnostic** (per current direction) — business-vertical behaviour is configuration, not code (NFR-11, C-3). | Architectural | Prohibits hardcoding any single industry's rules into the core |
| C-13 | **The system must not preclude multi-tenancy** (PO-10). | Architectural | Tenant boundary present in the data model from the first migration |
| C-14 | **Structural enablers may not be deferred with the capabilities they support** (§7.4). Tenancy, stock location and lot identity are present in the v1.0 data model even though the corresponding features are not built. | Architectural | The first migration must carry all three dimensions. Deferring any of them converts a v1.1 feature into a v1.1 re-architecture |
| C-15 | **Decisions DR-1 … DR-10 are binding until explicitly revised** (§16.2). They were taken on architectural reasoning, not business confirmation, and each is falsifiable. | Process | Superseding one requires revising this document first (C-1), not working around it in code |

---

## 18. Glossary

| Term | Definition |
| --- | --- |
| **Aging** | Classification of outstanding receivables by how long they have been due. |
| **Audit trail** | The retained, append-only record of state-changing operations, attributable to actor and time. |
| **Back-office** | Web application used by internal administrative, warehouse and accounts staff. |
| **Credit limit** | Maximum outstanding balance permitted for a customer before further orders require approval or refusal. |
| **Credit note** | Document issued to reduce a previously invoiced amount. Corrections are issued as credit notes; invoices are never edited (NFR-1). |
| **Distributor** | The business operating DistriCore: purchases from suppliers/principals, sells to retailers. |
| **Domain (functional)** | A cohesive area of business capability — e.g. Order Management (§7.2). |
| **Field-sales application** | Offline-first mobile app used by salesmen to capture orders on route. |
| **Fulfilment** | Picking and dispatching goods against an order; the point at which stock is issued. |
| **Goods receipt** | Recording of physical receipt of stock against a purchase order. |
| **Idempotent** | An operation producing the same result whether applied once or repeatedly — a required property of synchronisation (NFR-2). |
| **Master data** | Relatively static reference data: products, customers, suppliers, price lists, users. |
| **Lot** | An identified quantity of a product within a stock location. In v1.0 every movement posts to an implicit default lot; `BATCH` and `SERIAL` tracking policies activate real lot identity in v1.1 (DR-4). |
| **Lot-capable** | A stock ledger carrying lot identity on every movement without operating any lot-tracking policy — the structural enabler required by C-14. |
| **Multi-tenant** | A single deployment serving multiple isolated customer organisations. Out of scope for v1.0 (O4); architecturally anticipated (PO-10, C-13). |
| **Offline-first** | A design in which the application's normal mode assumes no connectivity, treating the network as an enhancement rather than a prerequisite. |
| **Order-to-cash** | The end-to-end cycle from order capture to payment receipt (§12.1). |
| **Outstanding balance** | Amount currently owed by a customer. |
| **Principal** | A manufacturer or brand owner whose products the distributor sells. |
| **Proof of delivery (POD)** | Evidence captured at delivery confirming goods were received. |
| **Purchase order (PO)** | Document instructing a supplier to supply specified goods. |
| **Reason code** | A structured, selectable justification attached to a stock adjustment, so that every inventory divergence is explained (PO-5). |
| **Receivable** | Amount owed to the distributor by a customer. |
| **Retailer** | The distributor's customer; sells to end consumers. Also *customer*. |
| **Retailer portal** | Online self-service surface through which retailers place orders and view their statements. |
| **Route** | A defined sequence of retailers visited by a salesman. |
| **Scheme** | A configurable trade promotion — quantity slab, discount or free-goods offer — applied automatically at order time (D7). |
| **Single-tenant** | A deployment serving exactly one customer organisation. The v1.0 model. |
| **SKU** | Stock Keeping Unit; a distinctly identified sellable product variant. |
| **Slab discount** | A discount whose rate varies by quantity or value band. |
| **Stock adjustment** | A recorded correction to inventory not arising from a sale, purchase or return; always carries a reason code. |
| **Stock location** | A physical place at which stock is held. v1.0 operates exactly one, seeded as the default (DR-2). |
| **Structural enabler** | A data-model dimension carried in v1.0 for a capability delivered later, because retrofitting it would be disproportionately expensive (C-14). Tenancy, stock location and lot identity are the three. |
| **Tracking policy** | A per-product setting — `NONE`, `BATCH` or `SERIAL` — determining how stock is identified within a location (DR-4). v1.0 supports `NONE`. |
| **Surface** | A client application through which users interact with the core (§7.1). |
| **Sync / synchronisation** | The protocol reconciling offline-captured transactions with the transactional core (D10). |
| **Tenant** | An isolated customer organisation within a multi-tenant deployment. |
| **Tenant-ready** | Carrying tenant boundaries in the data model without operating multiple tenants (§4.1). |
| **Trust boundary** | A line across which authorisation must be re-established — notably between internal users and retailer-portal users (§12.5). |
| **Van application** | Offline-first mobile app used by delivery staff for delivery, POD, collection and returns capture. |

---

## Document Control

**Decision coverage** — every section previously blocked is now closed.

| Section | Governed by |
| --- | --- |
| §7 Project Scope | DR-2, DR-3, DR-9; phasing per §7.4 |
| §8 Out of Scope | DR-1, DR-2, DR-3, DR-4, DR-7, DR-10 |
| §10 Success Metrics | DR-6 (baselines), DR-8 (envelope) |
| §12 Functional Overview | DR-1, DR-4, DR-9, DR-10 |
| §13 Non-Functional Goals | DR-3, DR-5, DR-8 |
| §16 Assumptions | DR-7 |
| **Unclosed** | **CF-1 only** — statutory transmission obligation (§16.3) |

**Next documents in the corpus**

1. `docs/02_Requirements_Specification.md` — functional and non-functional requirements per domain. **Unblocked; in progress.**
2. `docs/03_System_Architecture.md` — component architecture, data model, synchronisation protocol, tenancy strategy. Must specify the offline conflict-resolution policy (R-1) before any D10 implementation begins.
3. `docs/04_Milestone_Plan.md` — delivery sequence and definition of done per milestone, derived from §7.4.

**Approval**

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Business Owner (Sponsor) | | ☐ Approved ☐ Changes requested | |
| Product Architect | | ☐ Approved ☐ Changes requested | |
| Lead Implementation Engineer | | ☐ Approved ☐ Changes requested | |

*This document is not a specification. It does not authorise implementation. Implementation begins only after `02_Requirements_Specification.md` is approved.*
