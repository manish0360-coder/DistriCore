# DistriCore — Product Editions & Commercial Roadmap

| Field | Value |
| --- | --- |
| Document ID | `02A_Product_Editions` |
| Product | DistriCore (working title) |
| Version | 0.2.0 |
| Status | **Approved in principle; Edition 1 re-validated — see §13** |
| Date | 2026-08-04 |
| Owner | Product Management / Solution Architecture |
| Depends on | `01_Project_Vision.md` v0.2.0, `02_Requirements_Specification.md` v0.1.0 |
| Governs | Edition membership of every feature. Architecture, database and API documents derive their scope from this document. |

> **Standing.** The Vision and Requirements Specification define *what the product is*. This document defines *what is built first, and what is sold later*. It does not add requirements; it partitions the confirmed ones and, where the new Edition 1 direction departs from the frozen baseline, records the departure explicitly rather than absorbing it silently (C-1, C-3).

---

## 1. Purpose

To convert 231 confirmed functional requirements into three commercially coherent editions, such that:

1. **Edition 1 is genuinely usable.** The distributor can run their business daily without discovering that an essential workflow is missing.
2. **Edition 1 is cheap to build.** Complexity that does not solve a confirmed problem today is removed, not deferred into the code as unused abstraction.
3. **Editions 2 and 3 are extensions, not rewrites.** Every deferral is structured so the upgrade adds behaviour to an existing model rather than replacing it.

The third point is the one that costs money if it is got wrong, and it is the constraint this document optimises hardest against.

---

## 2. Inputs and Standing Assumptions

### 2.1 Confirmed direction

| # | Direction | Source |
| --- | --- | --- |
| 1 | All four business surfaces retained; depth minimised rather than surfaces removed | Client |
| 2 | **Delivery is a role inside the salesman application**, not a separate application | Client |
| 3 | **One Flutter application with role-based interfaces** for Salesman, Delivery and Retailer; responsive web for Owner | Client |
| 4 | Hosting-agnostic; single low-cost VPS as recommended production deployment; Docker Compose for local development | Client |
| 5 | Modular monolith, single backend, single database, REST | Client |
| 6 | No event sourcing, microservices, brokers, Kubernetes, CQRS, distributed architecture, plugin systems or workflow engines | Client |
| 7 | Upgrade trigger is business growth, approximately 1,000 retailers | Client |

### 2.2 Edition 1 feature direction as stated

| Role | Stated Edition 1 scope |
| --- | --- |
| Owner | Products, Customers, Stock, Orders, Bills, Basic Reports |
| Salesman | Assigned Orders, Delivery Status, Customer Visit, GPS during visit, Photo Upload |
| Delivery | Reuses the Salesman application as a role |
| Retailer | Login, Browse Products, Place Order, View Bills, View Order Status |

### 2.3 Open assumption — commercial envelope

**The ₹10,000–20,000 figure was not clarified.** This document proceeds on the most constrained reading, which is safe under every interpretation:

> **A-19.** ₹10,000–20,000 is the client's *annual* envelope covering hosting, domain, backups and any third-party services. Development labour is in-house and is not billed against it.

**Consequence:** recurring infrastructure must stay under roughly ₹800/month, which rules out managed databases, managed object storage and paid third-party tiers for Edition 1. If A-19 is wrong — in particular if the figure is a one-time licence fee covering development — tell me, because it changes the effort ceiling in §8, though not the edition boundaries in §7.

---

## 3. Deviation Register — Edition 1 vs. Frozen Baseline

The baseline is frozen. The Edition 1 direction departs from it in ten places. **Each requires sign-off (C-1); none may be absorbed silently.** My recommendation is given for each, and I disagree with the stated direction in two of them.

| ID | Deviation | Baseline position | Impact | Recommendation |
| --- | --- | --- | --- | --- |
| **DV-1** | **Salesmen no longer capture orders in the field.** The stated Edition 1 salesman scope is assigned orders, delivery status, visits, GPS and photos — not order taking. | PO-2 "eliminate re-entry between field and office"; FR-ORD-008; the offline-first mandate C-4 exists primarily to serve field order capture | **Large and mostly positive.** Order origin moves to the retailer portal and the owner. This collapses the offline problem from six conflict classes to two (§5) and removes R-1, the highest-severity risk in the programme, from Edition 1 almost entirely. | **Accept.** This is the single largest cost reduction available and it is a sound product decision. See §5. |
| **DV-2** | **GPS capture at customer visit** added to Edition 1. | O7 excludes "route planning, GPS tracking and geo-optimisation" | Contradiction is only apparent. Capturing a latitude/longitude on a visit record is trivial; continuous tracking and route optimisation are not. | **Accept, narrowly scoped.** Edition 1 captures coordinates at visit check-in only. No background tracking, no breadcrumb trail, no optimisation. O7 remains excluded as written. |
| **DV-3** | **No payment or receivables capability in the stated Edition 1 list.** | PO-4 credit control is a top-five objective; Vision §3.3 names uncontrolled credit exposure as a core business problem; FR-REC-001…015 | **I disagree with this omission.** Without payment recording the system cannot answer "who owes me money" — and that is one of the five problems the product exists to solve. "View Bills" without a balance is a list of paper the retailer already has. | **Reject the omission. Add minimal payments to Edition 1.** One entity, one ledger, derived balance. Complexity Low, value High. See §6.1. |
| **DV-4** | **One Flutter binary serves Salesman, Delivery and Retailer.** | Vision §12.5 places `RETAILER` outside the internal trust boundary | Sound and cheap, **provided** authorisation stays server-side (BR-003). The binary is publicly downloadable, so it must contain no internal-only logic, endpoint, or secret that authorisation does not independently enforce. | **Accept, with the security condition stated in §9.3.** |
| **DV-5** | **Delivery is a role, not an application.** | Vision §7.1 lists S3 as a distinct surface | Correct call. The delivery workflow is four screens; a second application would triple its cost for no user benefit. | **Accept.** |
| **DV-6** | **No purchasing or supplier management in Edition 1.** | D5 confirmed in scope; FR-PUR-001…015 | Stock must still enter the system. Without purchase orders, inbound stock is recorded as a reason-coded receipt — which the Owner "Stock" feature already provides. | **Accept.** Stock-in in Edition 1; purchase orders and supplier ledger in Edition 2. |
| **DV-7** | **No schemes or slab discounts in Edition 1.** | PO-6; Vision §3.5 identifies manual scheme application as direct margin leakage; FR-PRC-010…021 | Partially costly. A full scheme engine is genuinely expensive; a single price list plus a bounded line discount is not. | **Accept the deferral of the scheme engine.** Edition 1 keeps one price list, optional customer-specific price, and a permission-bounded manual discount. |
| **DV-8** | **No structured returns in Edition 1.** | DR-9; FR-RET-001…010 | Returns happen daily at a distributor. But a reason-coded stock adjustment plus a manual credit note covers it adequately for one distributor at low volume. | **Accept.** Structured invoice-linked returns in Edition 2. |
| **DV-9** | **No approval workflow in Edition 1.** | DR-10; FR-ORD-020…027 | Acceptable only because the owner personally sees every order at this scale. | **Accept with one exception:** keep the credit-limit *check* (a warning and an owner override), since it is a conditional and an audit row, not a workflow. |
| **DV-10** | **Structural enablers under pressure from "avoid speculative engineering".** | C-14 mandates `Tenant`, `StockLocation`, `Lot` in the first migration | **This must not be cut.** See §9.1 — the distinction between a reversible-cost column and speculative engineering is the most important judgement in this document. | **Retain all three. Non-negotiable.** |

---

## 4. Task 1 — Module Decomposition

Eighteen modules. Each exists because a specific business activity would otherwise be unrepresented; none exists because a layer diagram suggested it.

| # | Module | Why it exists | Depends on |
| --- | --- | --- | --- |
| M-01 | **Identity & Access** | Every other module needs to know who is acting and what they may do. Four user groups with sharply different authority share one system; without this, authorisation is guesswork. | — |
| M-02 | **Customer Management** | The retailer is the commercial counterparty. Orders, prices, credit, deliveries and receivables all hang off customer identity. | M-01 |
| M-03 | **Product Catalogue** | Nothing can be priced, stocked, ordered or invoiced without an agreed definition of what is being sold, in what unit. | M-01 |
| M-04 | **Inventory & Stock** | The distributor's working capital is the stock. Vision §3.4 — stock that is trusted less than it is counted — is a founding problem. | M-03 |
| M-05 | **Pricing & Discounts** | Price must be applied by the system identically on every order, or margin leaks invisibly (Vision §3.5). | M-02, M-03 |
| M-06 | **Order Management** | The transaction that starts the revenue cycle. Its lifecycle is the spine the whole system hangs from. | M-02, M-04, M-05 |
| M-07 | **Fulfilment & Delivery** | The physical movement of goods, and the point at which stock actually leaves. Without it, stock figures drift from reality. | M-06 |
| M-08 | **Billing** | The legal and financial record of the sale. Immutable by construction. | M-07 |
| M-09 | **Payments & Receivables** | Distribution runs on credit. This module is what makes "who owes me what" answerable — the answer to Vision §3.3. | M-08 |
| M-10 | **Field Activity** | Evidence that the route was worked: visits, coordinates, photographs. Turns field effort from a claim into a record. | M-01, M-02 |
| M-11 | **Purchasing & Suppliers** | Stock has to come from somewhere, and the supplier has to be paid. Procurement informed by stock position instead of habit (Vision §3.6). | M-04 |
| M-12 | **Returns** | Goods come back. If returns are not modelled, stock and receivables both drift. | M-04, M-08 |
| M-13 | **Reporting** | The owner's visibility. Without it, the data is captured but the business is still run on recall (Vision §3.1). | All |
| M-14 | **Notifications** | Closes the loop between an event and the person who must act on it — a new order, a dispatched delivery, an overdue balance. | M-06 |
| M-15 | **Sync & Offline** | Field devices operate outside coverage. The cost of this module is set almost entirely by *what* is captured offline (§5). | M-06, M-07, M-10 |
| M-16 | **Zone & Route Management** | Determines which salesman serves which retailers — and therefore what data reaches which device, which is an access-control concern as much as an operational one. | M-02 |
| M-17 | **Salesman Performance** | Targets and achievement. Converts activity data already captured into management information. | M-06, M-10 |
| M-18 | **Audit** | Makes any figure defensible. Cheap when built in from the start; near-impossible to add retrospectively with integrity. | M-01 |

---

## 5. The Decision That Sets Edition 1's Cost

This section exists because one consequence of DV-1 dominates the entire cost model, and it would be easy to miss.

**In the frozen baseline, salesmen captured orders offline.** That single capability is what made offline synchronisation expensive. An offline order must be revalidated on arrival against stock, credit, price and master data that have all moved on — producing the six-class conflict taxonomy of Requirements §5.3, the `PRICE_VARIANCE` and `MASTER_STALE` exception states, the conflict resolution console, and R-1, the highest-severity risk in the programme.

**In Edition 1, salesmen no longer capture orders.** They read assigned orders and write delivery status, visits, coordinates and photographs.

Look at what those writes actually are:

| Offline write | Conflict potential |
| --- | --- |
| Delivery status update on a known order | State transition; last-write-wins is correct and safe |
| Customer visit record | Append-only; no shared resource |
| GPS coordinate | Append-only; immutable once captured |
| Photograph | Append-only blob |

**None of them contend for a shared resource.** No stock is allocated, no price is computed, no credit is consumed. The conflict taxonomy collapses from six classes to two — `SC-DUPLICATE` and `SC-SEQUENCE` — and both are deterministic and automatically resolvable (Requirements §5.3).

| | Baseline (offline order capture) | Edition 1 (offline status + activity) |
| --- | --- | --- |
| Conflict classes | 6 | 2 |
| Requiring human resolution | 4 | 0 |
| Conflict resolution console | Required | Not required |
| Exception order states | 3 | 0 |
| Sync mechanism | Bidirectional reconciliation protocol | Durable outbox with idempotent replay |
| Relative build effort | **Very High** | **Low** |
| R-1 exposure | Critical | Effectively removed |

> **This is where the majority of the savings in Edition 1 come from — not from cutting features, but from cutting the hardest problem out of the first release.** It is worth being explicit that this is a real trade, not a free lunch: PO-2 (eliminate re-entry) is only partially achieved in Edition 1. Orders placed by retailers on the portal are captured once, at source, and satisfy PO-2 fully. Orders phoned in are still keyed by the owner — but they were being keyed by the owner before, so nothing is worse than today, and one channel is now strictly better.
>
> **The upgrade path is intact.** Adding field order capture in Edition 2 means adding the four missing conflict classes and a resolution console *on top of* an outbox that already exists and is already proven in production. That is an extension, not a rewrite.

---

## 6. Task 2 — Edition Definitions

### 6.1 Edition 1 — Lean Commercial MVP

**Commercial promise:** the distributor runs their daily business — stock in, order, deliver, bill, collect — in one system, with retailers ordering for themselves and salesmen proving their routes.

**Positioning:** complete for one distributor, one warehouse, up to roughly 1,000 retailers.

| Module | Edition 1 content |
| --- | --- |
| M-01 Identity & Access | Login, four roles, server-side authorisation, device registration |
| M-02 Customer Management | Customer master, credit limit field, route assignment, deactivation |
| M-03 Product Catalogue | Product master, two units of measure with conversion, tax code, active flag |
| M-04 Inventory & Stock | Stock movements, derived on-hand, stock in, stock out, reason-coded adjustment |
| M-05 Pricing & Discounts | One price list, optional customer-specific price, bounded manual line discount |
| M-06 Order Management | Capture by Owner and Retailer, simple lifecycle, credit-limit warning with owner override |
| M-07 Fulfilment & Delivery | Assign to salesman, dispatch, delivery status, proof-of-delivery photograph |
| M-08 Billing | Invoice from dispatch, immutable, number series, configurable tax, PDF, manual credit note |
| M-09 Payments & Receivables | **Added per DV-3.** Record payment, allocate to invoice, derived outstanding balance, simple aging |
| M-10 Field Activity | Visit check-in with coordinates, photograph, notes |
| M-13 Reporting | Sales, stock, receivables aging, order status, customer statement. CSV export |
| M-14 Notifications | In-app only: new order to Owner, assignment to Salesman, status to Retailer |
| M-15 Sync & Offline | Durable outbox, idempotent replay, delivery status and field activity only |
| M-16 Zone & Route | Route as a customer attribute; salesman assigned to routes |
| M-18 Audit | Audit record on every state change |

**Not in Edition 1:** M-11 Purchasing, M-12 structured Returns, M-17 Performance, and the deferred depth within the modules above.

### 6.2 Edition 2 — Professional Upgrade

**Commercial promise:** the operational depth a growing distributor needs — field order capture, procurement, schemes, structured returns and performance management.

**Upgrade trigger:** roughly 1,000 retailers, a second salesman team, or supplier terms that make informal procurement costly.

| Addition | Why it belongs here |
| --- | --- |
| **Field order capture, offline, with full conflict resolution** | The flagship upgrade. Restores PO-2 in full. Requires the four deferred conflict classes and a resolution console — expensive, and only worth it once field volume justifies it |
| **M-11 Purchasing & Suppliers** | Purchase orders, goods receipt against order, supplier ledger, receipt variance |
| **Scheme engine** | Slabs, free goods, eligibility rules, best-for-customer resolution. The margin-protection upgrade |
| **M-12 Structured Returns** | Invoice-linked returns with automatic credit note and restockable/non-restockable disposition |
| **M-17 Salesman Performance** | Targets, achievement, commission basis |
| **Multi-level approvals** | Chained approval once the owner no longer sees every order personally |
| **Batch / lot / expiry tracking** | Activates the `Lot` dimension carried since Edition 1. Configuration and UI, not re-architecture |
| **Multi-warehouse operations** | Activates the `StockLocation` dimension. Transfers, per-location stock, location-aware picking |
| **Email / SMS / push notifications** | External channels once in-app is insufficient |
| **Payment gateway** | Digital collection from retailers |

### 6.3 Edition 3 — Complete Platform

**Commercial promise:** DistriCore as a product sold to many distributors, not a system operated by one.

| Addition | Why it belongs here |
| --- | --- |
| **Multi-tenant SaaS activation** | Activates the `Tenant` dimension carried since Edition 1: provisioning, isolation enforcement, subscription billing, self-service onboarding |
| **Vertical configuration packs** | Specialising the domain-agnostic core per industry without forking. The commercial payoff of C-12 |
| **Advanced analytics** | Dimensional reporting, trends, margin analysis |
| **Demand forecasting & replenishment** | Requires the operational history Editions 1 and 2 accumulate |
| **Route optimisation** | The capability O7 excludes. Only now is there route and coordinate history to optimise against |
| **AI features** | Credit-risk scoring, anomaly detection, natural-language reporting |
| **Public API & partner integrations** | Third-party access |
| **Accounting integration** | Across the O1 boundary. Integration, never a general ledger |
| **Separate role-specific applications** | Splitting the single Flutter binary, if scale justifies it |
| **iOS client** | On demand |

---

## 7. Task 3 — Feature Comparison Matrix

**Legend.** Value: **H** high · **M** medium · **L** low. Complexity: **VL** very low · **L** low · **M** medium · **H** high · **VH** very high. Mand: mandatory for Edition 1 to be a usable product. Upgrade: what the feature grows into later.

### 7.1 M-01 Identity & Access

| Feature | Value | Cplx | Ed | Mand | Upgrade | Reason |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| Username/password login | H | VL | 1 | Y | SSO (3) | Nothing works without it |
| Password hashing, rate limiting | H | VL | 1 | Y | — | Non-negotiable security floor; near-zero cost using a standard library |
| Four fixed roles | H | VL | 1 | Y | Custom roles (2) | Four roles cover every confirmed user. A role *builder* is speculative — role rows in a table are not |
| Server-side authorisation on every request | H | L | 1 | Y | — | BR-003. The one control that cannot be retrofitted safely, especially with a public app binary (DV-4) |
| Device registration & revocation | M | L | 1 | Y | MDM (3) | Field devices hold customer and price data (R-8). One table, one check |
| Password reset by Owner | M | VL | 1 | Y | Self-service email reset (2) | Owner resets are adequate for ~10 internal users; email infrastructure is not free |
| Self-service retailer registration | L | M | 2 | N | — | Owner onboards retailers personally at this scale. Self-registration needs verification and anti-abuse — real cost, no current value |
| Two-factor authentication | L | M | 3 | N | — | Not warranted for a single distributor's back office |

### 7.2 M-02 Customer Management

| Feature | Value | Cplx | Ed | Mand | Upgrade | Reason |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| Customer master (code, name, contacts, addresses) | H | VL | 1 | Y | — | Foundational |
| Credit limit field | H | VL | 1 | Y | Enforced workflow (2) | A number on a record. Made useful by M-09 |
| Route assignment | H | VL | 1 | Y | Multi-route (2) | Determines which salesman sees which customer — access control, not just convenience |
| Deactivation (never delete) | H | VL | 1 | Y | — | Deleting a customer with history corrupts every report. Cheaper to do right than to fix |
| Customer statement | H | L | 1 | Y | Scheduled email (2) | The owner's most-asked question. Trivial once M-09 exists |
| Customer categories for pricing | M | L | 2 | N | — | Needs the scheme engine to be useful; premature without it |
| Credit-risk scoring | L | H | 3 | N | — | Requires payment history that does not yet exist |

### 7.3 M-03 Product Catalogue

| Feature | Value | Cplx | Ed | Mand | Upgrade | Reason |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| Product master | H | VL | 1 | Y | — | Foundational |
| Two units of measure with conversion | H | L | 1 | Y | N-level UoM (2) | Distributors buy in cases and sell in pieces. Omitting this forces manual arithmetic on every order — an essential workflow, not a convenience |
| Tax code per product | H | VL | 1 | Y | — | Required by billing. One field |
| Active/inactive flag | H | VL | 1 | Y | — | Products are discontinued constantly |
| `trackingPolicy` field, `NONE` only | M | VL | 1 | **Y** | Activates batch/serial (2) | **One column and one validation.** See §9.1 — this is the cheapest insurance in the document |
| Product images | M | L | 1 | Y | CDN (3) | The retailer portal is unusable without them. One image per product, resized on upload |
| Category hierarchy | M | L | 2 | N | — | Flat categories suffice below ~500 SKUs |
| Batch/lot/expiry operation | H | H | 2 | N | — | High value *if* the industry needs it (CF-2, unconfirmed). Deferred, not foreclosed |

### 7.4 M-04 Inventory & Stock

| Feature | Value | Cplx | Ed | Mand | Upgrade | Reason |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| Stock movement ledger | H | L | 1 | Y | — | **See §9.2.** A movements table is the simplest correct design, not an enterprise pattern |
| Derived on-hand quantity | H | VL | 1 | Y | Cached balance (2) | A `SUM` query. At 10,000 SKUs it needs no optimisation |
| Stock in (receipt) | H | VL | 1 | Y | Purchase-order-linked (2) | Stock must be able to enter the system without building procurement |
| Stock out (issue on dispatch) | H | VL | 1 | Y | — | Automatic from fulfilment |
| Reason-coded adjustment | H | L | 1 | Y | — | PO-5. Also carries returns and damages in Edition 1 (DV-8) |
| `stockLocation` on every movement | M | VL | 1 | **Y** | Multi-warehouse (2) | One column, one seeded row. §9.1 |
| `lot` on every movement | M | VL | 1 | **Y** | Batch tracking (2) | One column, one default row. §9.1 |
| Physical stock count workflow | M | M | 2 | N | — | The owner counts on paper and posts adjustments in Edition 1. A guided count workflow is convenience |
| Stock allocation/reservation | M | M | 2 | N | — | Only matters with concurrent order sources at volume. At Edition 1 volume, dispatch-time deduction is sufficient and far simpler |
| Multi-warehouse transfers | M | H | 2 | N | — | Client has one warehouse (A-13) |

### 7.5 M-05 Pricing & Discounts

| Feature | Value | Cplx | Ed | Mand | Upgrade | Reason |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| Single price list | H | VL | 1 | Y | Multiple lists (2) | Every order needs a price |
| Customer-specific price override | H | L | 1 | Y | Category pricing (2) | Distributors negotiate per retailer. Without it the owner overrides manually on every order |
| Server-side price resolution | H | L | 1 | Y | — | BR-001/PO-6. Same price on web and app, by construction |
| Bounded manual line discount | H | L | 1 | Y | Approval workflow (2) | The pragmatic substitute for the scheme engine. Bounded by a maximum and audited |
| Price effective dating | M | L | 1 | Y | — | Trivial now; retrofitting it means reconstructing price history that was never recorded |
| Slab / quantity-break schemes | H | H | 2 | N | — | Real margin value, real cost. Manual discount covers it until volume justifies automation |
| Free-goods schemes | M | H | 2 | N | — | As above, plus stock-movement side effects |
| Best-for-customer scheme resolution | M | M | 2 | N | — | Meaningless without multiple schemes |

### 7.6 M-06 Order Management

| Feature | Value | Cplx | Ed | Mand | Upgrade | Reason |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| Order capture by Owner (web) | H | L | 1 | Y | — | Phone orders must be recordable |
| Order capture by Retailer (app) | H | M | 1 | Y | — | The channel that actually delivers PO-1/PO-2 in Edition 1 (§5) |
| Simple lifecycle: `PLACED → CONFIRMED → DISPATCHED → DELIVERED → INVOICED → CLOSED` | H | L | 1 | Y | Full state machine (2) | Six states the owner recognises. The baseline's eleven-state machine exists to serve approvals and sync exceptions, neither of which is in Edition 1 |
| Cancellation with reason | H | VL | 1 | Y | — | Orders get cancelled daily |
| Credit-limit warning + Owner override | H | L | 1 | Y | Enforced approval (2) | A conditional and an audit row — **not** a workflow engine. Preserves PO-4 at near-zero cost (DV-9) |
| Order editing before dispatch | M | L | 1 | Y | — | Retailers change their minds before the van leaves |
| Field order capture, offline | H | VH | 2 | N | — | **The single most expensive deferred feature.** Restores PO-2 fully. See §5 |
| Approval workflow, multi-level | M | H | 2 | N | — | The owner sees every order personally at this scale |
| Order templates / reorder-last | M | L | 2 | N | — | Genuine convenience, genuinely not essential |

### 7.7 M-07 Fulfilment & Delivery

| Feature | Value | Cplx | Ed | Mand | Upgrade | Reason |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| Assign order to salesman/delivery | H | VL | 1 | Y | Auto-assignment (3) | Someone must carry the goods |
| Dispatch → stock issue | H | L | 1 | Y | — | The point stock actually leaves |
| Delivery status update from app | H | L | 1 | Y | — | The salesman's primary Edition 1 job |
| Proof-of-delivery photograph | H | L | 1 | Y | Signature capture (2) | Settles delivery disputes. Camera plus upload |
| Partial delivery | M | M | 2 | N | — | Edition 1 records delivered or not delivered. Partial delivery needs per-line quantities and a reconciliation path |
| Picking list | M | L | 2 | N | — | One warehouse, one picker, order printout suffices |
| Delivery route sequencing | L | H | 3 | N | — | O7 |

### 7.8 M-08 Billing

| Feature | Value | Cplx | Ed | Mand | Upgrade | Reason |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| Invoice generated from dispatch | H | L | 1 | Y | — | The commercial and legal record |
| Immutable once issued | H | VL | 1 | Y | — | BR-006. Free if designed in; catastrophic to retrofit |
| Gapless number series | H | L | 1 | Y | Multiple series (2) | Statutory expectation in most jurisdictions |
| Configurable tax rules with effective dates | H | M | 1 | Y | Multi-jurisdiction (3) | DR-1. Rates change; the design cost is one table and a lookup |
| Persisted tax breakdown on the document | H | VL | 1 | Y | — | FR-BIL-008. Prevents a price update silently rewriting financial history |
| PDF invoice | H | L | 1 | Y | Branded templates (2) | The retailer needs a document |
| Manual credit note | H | L | 1 | Y | Invoice-linked returns (2) | Corrections must be possible without editing an invoice |
| Retailer views own invoices | H | VL | 1 | Y | — | Stated Edition 1 scope. A filtered query |
| E-invoicing / portal transmission | ? | H | 2 | N | — | **Blocked on CF-1.** If legally mandatory it is Edition 1 and the estimate in §8 rises |

### 7.9 M-09 Payments & Receivables — *added per DV-3*

| Feature | Value | Cplx | Ed | Mand | Upgrade | Reason |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| Record payment against customer | H | VL | 1 | **Y** | — | **Without this the system cannot say who owes money.** That is one of five founding problems (Vision §3.3) |
| Allocate payment to invoice | H | L | 1 | Y | Auto-allocation (2) | Makes an invoice closable |
| Derived outstanding balance | H | VL | 1 | Y | — | BR-005. A sum over ledger entries |
| Simple aging (4 buckets) | H | L | 1 | Y | Configurable buckets (2) | Turns a balance into a collection priority |
| Retailer views own balance | H | VL | 1 | Y | — | Reduces disputes before they start |
| Collection recorded in field | M | L | 2 | N | — | Depends on whether delivery staff handle cash — unconfirmed |
| Cash-in-hand reconciliation | M | M | 2 | N | — | Only matters once field collection exists |
| Payment gateway | M | H | 2 | N | — | O6. Records payments now, processes them later |

> **On the Edition 1 additions above.** Six rows, all VL or L complexity, delivering the answer to "who owes me money." I recommend this strongly enough to have marked it a rejection in DV-3 rather than a suggestion. Recording bills without recording payments produces a system that is *impressive on day one and useless by week three*, because the balances it shows are all wrong.

### 7.10 M-10 Field Activity

| Feature | Value | Cplx | Ed | Mand | Upgrade | Reason |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| Visit check-in against a customer | H | VL | 1 | Y | — | Stated Edition 1 scope. Proves the route was worked |
| GPS coordinates at check-in | H | L | 1 | Y | Geofence validation (2) | DV-2. One permission, one API call, two columns |
| Photograph upload | M | L | 1 | Y | Multiple photos (2) | Shelf and display evidence |
| Visit notes | M | VL | 1 | Y | Structured surveys (2) | A text field |
| Continuous GPS tracking | L | H | 3 | N | — | **Rejected for Edition 1.** Battery drain, storage cost, privacy exposure, and no confirmed use. O7 |
| Route optimisation | M | VH | 3 | N | — | O7. Requires the visit history Editions 1–2 produce |

### 7.11 M-11 Purchasing · M-12 Returns · M-16 Zone · M-17 Performance

| Feature | Value | Cplx | Ed | Mand | Upgrade | Reason |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| Stock-in with reason code *(substitutes for purchasing)* | H | VL | 1 | Y | PO-linked receipt (2) | Covers inbound stock without building procurement |
| Supplier master | M | VL | 2 | N | — | Nothing in Edition 1 consumes it |
| Purchase orders & goods receipt | M | M | 2 | N | — | Owner orders by phone at this scale |
| Supplier ledger & payables | M | M | 2 | N | — | Follows purchase orders |
| Returns as reason-coded adjustment + manual credit note | H | VL | 1 | Y | Structured returns (2) | Correct outcome, minimal machinery (DV-8) |
| Invoice-linked structured returns | M | M | 2 | N | — | Automates what Edition 1 does manually |
| Route as customer attribute | H | VL | 1 | Y | Zone hierarchy (2) | Needed to scope salesman data access |
| Zone hierarchy, territories | M | M | 2 | N | — | One route dimension is enough for one salesman team |
| Sales targets & achievement | M | M | 2 | N | — | Reads Edition 1 data. Zero structural dependency — the cleanest deferral in the product |
| Commission computation | M | M | 2 | N | — | Follows targets |

### 7.12 M-13 Reporting · M-14 Notifications · M-15 Sync · M-18 Audit

| Feature | Value | Cplx | Ed | Mand | Upgrade | Reason |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| Sales report by period/customer/product | H | L | 1 | Y | — | The owner's core question |
| Stock position report | H | VL | 1 | Y | — | Working capital visibility |
| Receivables aging report | H | L | 1 | Y | — | Depends on M-09 |
| Order status report | H | VL | 1 | Y | — | Daily operations |
| Customer statement | H | L | 1 | Y | — | Dispute resolution |
| CSV export | H | VL | 1 | Y | Excel/scheduled (2) | The owner's escape hatch into any tool they already use |
| Dashboard with charts | M | L | 1 | Y | Analytics (3) | Four numbers on a home screen. Disproportionate perceived value for the effort |
| Scheduled/emailed reports | L | M | 2 | N | — | Requires email infrastructure that costs money (A-19) |
| Analytics & trends | M | H | 3 | N | — | O11 |
| In-app notifications | M | L | 1 | Y | Push (2) | A table and a badge count. Closes the loop with no external dependency |
| Push notifications | M | M | 2 | N | — | Adds a third-party dependency and a cost line |
| SMS / email notifications | M | M | 2 | N | — | Per-message cost; excluded by A-19 |
| Durable outbox with idempotent replay | H | L | 1 | Y | Full sync protocol (2) | §5. Cheap *because* Edition 1 defers field order capture |
| Master-data pull to device | H | L | 1 | Y | Delta sync (2) | Scoped to the salesman's routes (FR-SYN-012) |
| Sync status visible to user | M | VL | 1 | Y | Admin console (2) | Nothing may fail silently. A timestamp and a pending count |
| Conflict resolution console | M | H | 2 | N | — | **Not needed in Edition 1** — both remaining conflict classes resolve deterministically (§5) |
| Audit record on every state change | H | L | 1 | **Y** | Audit reports (2) | §9.2. One table, written in one place. Retrofitting it means the history simply does not exist |

---

## 8. Task 4 — Relative Implementation Effort

No currency, per instruction. Effort is expressed relative to the complete platform, taken as 100 units.

### 8.1 By edition

| Edition | Modules | Relative effort | Classification | Cumulative |
| --- | --- | --: | :-: | --: |
| **Edition 1 — Lean Commercial MVP** | 15 modules at reduced depth | **28.5** | **Medium** | 28.5 |
| **Edition 2 — Professional Upgrade** | + 3 modules, + depth across all | **36.5** | **High** | 65.0 |
| **Edition 3 — Complete Platform** | + tenancy, analytics, AI, optimisation | **35.0** | **Very High** | 100.0 |

### 8.2 Edition 1 breakdown

| Module | Effort | Class | Note |
| --- | --: | :-: | --- |
| M-01 Identity & Access | 2.0 | Low | Standard patterns, no novelty |
| M-02 Customer Management | 1.5 | Very Low | CRUD |
| M-03 Product Catalogue | 2.0 | Low | UoM conversion is the only real logic |
| M-04 Inventory & Stock | 2.5 | Low | Movement ledger plus derived sums |
| M-05 Pricing & Discounts | 2.0 | Low | Resolution order plus bounded discount |
| M-06 Order Management | 3.5 | Medium | Two capture surfaces, lifecycle, credit check |
| M-07 Fulfilment & Delivery | 2.0 | Low | Status transitions plus photo upload |
| M-08 Billing | 3.5 | Medium | Tax engine, number series, immutability, PDF |
| M-09 Payments & Receivables | 2.0 | Low | Ledger plus allocation plus aging |
| M-10 Field Activity | 1.5 | Very Low | Append-only records |
| M-13 Reporting | 2.0 | Low | Six reports plus CSV |
| M-14 Notifications | 0.5 | Very Low | In-app only |
| M-15 Sync & Offline | 2.0 | Low | **Low only because of §5** |
| M-16 Zone & Route | 0.5 | Very Low | One attribute |
| M-18 Audit | 1.0 | Very Low | One table, one write path |
| **Subtotal** | **28.5** | | |
| *Shared infrastructure, deployment, hardening* | *included above* | | |

### 8.3 What the deferrals bought

| Deferred to Edition 2 | Effort avoided | As % of Edition 1 |
| --- | --: | --: |
| Field order capture with full conflict resolution | 9.0 | 32% |
| Scheme engine (slabs, free goods, resolution) | 5.0 | 18% |
| Purchasing & supplier ledger | 4.5 | 16% |
| Batch/lot/expiry operation | 3.5 | 12% |
| Multi-warehouse operations | 3.0 | 11% |
| Structured returns | 2.5 | 9% |
| Targets & commission | 2.5 | 9% |
| Multi-level approvals | 2.0 | 7% |
| **Total avoided** | **32.0** | **112%** |

> **Read that last row carefully. The deferrals are larger than Edition 1 itself.** Building the frozen baseline as one release would have been roughly 2.1× the work of Edition 1 — and the single largest line, field order capture, is also the one carrying R-1, the highest-severity risk in the programme. Edition 1 is not a reduced version of the product; it is the part of the product that is cheap and safe to build first.

---

## 9. Three Judgements Worth Defending

### 9.1 Structural enablers are not speculative engineering

"Avoid speculative engineering" and "carry `Tenant`, `StockLocation` and `Lot` from the first migration" appear to conflict. They do not, and the distinction matters more than any other decision here.

| | Speculative engineering | Reversible-cost dimension |
| --- | --- | --- |
| Example | A multi-warehouse UI, a transfer workflow, a tenancy-aware permission engine | A `location_id` column defaulting to one seeded row |
| Edition 1 cost | Weeks | Three columns and three seeded rows |
| Cost of omitting | — | Migrating a live stock ledger and financial history |
| Verdict | **Reject** | **Retain** |

The rule I have applied: *build no behaviour you do not need; carry any dimension whose later addition would require rewriting historical rows.*

There are exactly three such dimensions, and all three are already identified in C-14. I have added none, and I have not extended the principle to anything else — no generic entity-attribute model, no plugin registry, no abstract provider interfaces, no configuration framework. Those would be speculative engineering, and they are rejected.

### 9.2 A movement ledger is not event sourcing

"No event sourcing" could be misread as "store a mutable `quantity_on_hand` column and update it." That would destroy PO-5 and it would be the single most damaging simplification available in this document.

| | Event sourcing (rejected) | Movement ledger (retained) |
| --- | --- | --- |
| What is stored | Every state change as a domain event; state is a projection | Stock movements and ledger entries — the business documents themselves |
| Requires | Event store, projections, replay, versioning, eventual consistency | One table, one insert, one `SUM` |
| Analogy | An architectural pattern | A stock register — what every distributor already keeps on paper |
| Edition 1 verdict | **Rejected. Adds infrastructure for no current value** | **Retained. It is the simplest correct design** |

The same distinction applies to the audit table: writing a row recording who changed what is not event sourcing, it is a log. Both are cheap, both are standard, and both are effectively impossible to add later with any integrity — because the history they would have recorded was never captured.

### 9.3 One binary serving internal and external users is safe — conditionally

DV-4 puts `RETAILER` inside the same Flutter application as `SALESMAN` and `DELIVERY`. The binary is publicly downloadable and must be assumed fully decompilable. The condition on accepting this is absolute:

- Every authorisation decision is made server-side, per request (BR-003). Role-based UI is presentation only.
- The binary contains no API key, secret, internal endpoint or business rule whose confidentiality matters.
- The retailer's token grants access only to their own customer's records, enforced in the backend.

Under those conditions, one binary is meaningfully cheaper and no less secure than three. **Without them it is a data breach with a version number**, which is why it is recorded as a condition rather than a note.

---

## 10. Task 5 — Recommendation

**Build Edition 1, with the six M-09 payment features added per DV-3, and ship it before writing a line of Edition 2.**

The reasoning, in order of weight:

1. **It is a complete daily workflow, not a demo.** Stock in → order → dispatch → deliver → bill → collect → report. Nothing an owner does every day is missing. The test in the brief — *"the customer should never feel that an essential workflow is missing"* — is met, but only with M-09 included. Without payments, the owner hits the gap in week three.
2. **It costs under a third of the platform and avoids the hardest problem entirely.** 28.5 units against 100, and §8.3 shows the deferrals total more than Edition 1 itself. Deferring field order capture removes R-1 from the first release — the highest-severity risk in the programme — rather than merely mitigating it.
3. **The upgrade path is extension, not rewrite.** Every Edition 2 item adds behaviour to a model Edition 1 already carries: the `Lot` column activates batch tracking, `StockLocation` activates multi-warehouse, `Tenant` activates SaaS, the outbox extends into full sync, the discount field generalises into the scheme engine.
4. **It fits the client's own upgrade trigger.** They named ~1,000 retailers as the growth point. Edition 1 is sized for exactly that ceiling, which makes the commercial conversation natural rather than adversarial: they upgrade because they grew, not because they were sold something incomplete.
5. **It is commercially honest.** Every Edition 2 feature is a capability the client does not need today at their current scale. Selling depth before it is needed is how software gets built that nobody uses.

### 10.1 What I recommend against

| Proposal | Why not |
| --- | --- |
| Dropping M-09 payments to save effort | Saves 2 units of 28.5 and removes the answer to one of the five founding business problems. The worst value-per-unit trade available |
| Adding field order capture to Edition 1 | Adds 9 units — a third again on top — and reintroduces R-1. Retailer self-ordering delivers most of the same benefit at a fraction of the cost |
| Building the scheme engine early | 5 units. A bounded manual discount covers a single distributor's needs until scheme volume makes automation pay |
| Continuous GPS tracking | Battery drain, storage cost, privacy exposure, no confirmed use. Coordinate-at-check-in gives 80% of the management value at 5% of the cost |
| Cutting the three structural dimensions | Saves under half a unit. Costs a migration of live financial history later. §9.1 |
| Cutting audit to save effort | Saves 1 unit. The history it would have captured cannot be reconstructed afterwards at any price |

---

## 11. Extension Points Preserved

Documented, **not implemented**. Each is a place Edition 2 or 3 attaches without disturbing Edition 1's model.

| # | Extension point | How Edition 1 preserves it | Enables |
| --- | --- | --- | --- |
| EP-1 | `tenant_id` on every business row | One column, one seeded tenant | SaaS multi-tenancy (E3) |
| EP-2 | `location_id` on every stock movement | One column, one seeded location | Multi-warehouse (E2) |
| EP-3 | `lot_id` on every stock movement + `trackingPolicy` on product | One column each, default lot per product | Batch / serial / expiry (E2) |
| EP-4 | Order `source` field | Records web / portal / app origin | Field order capture (E2) |
| EP-5 | Durable outbox on device | Already carries status and activity records | Full sync protocol with conflict classes (E2) |
| EP-6 | Line-level `discountAmount` + `schemeId` (nullable) | Discount populated, scheme left null | Scheme engine (E2) |
| EP-7 | Tax rules as data with effective dates | Already configuration, not code | Multi-jurisdiction, e-invoicing (E2/E3) |
| EP-8 | Stock movement `sourceDocumentType` | Enumerated, extensible | Purchase orders, transfers, structured returns (E2) |
| EP-9 | Notification records as rows | In-app reads the table | Push / SMS / email dispatchers (E2) |
| EP-10 | Audit table from day one | Written on every state change | Compliance reporting, anomaly detection (E2/E3) |
| EP-11 | REST API separate from web UI | The Flutter app is already a first-class API client | Public API, partner integration, split applications (E3) |
| EP-12 | Visit records with coordinates | Accumulating from day one | Route optimisation, geofencing (E3) |

> **EP-12 is worth noting commercially.** Route optimisation in Edition 3 needs visit history to optimise against. By capturing coordinates from Edition 1, the client accumulates the dataset that makes a future upgrade valuable — at a cost of two columns. This is the same reasoning as §9.1, applied to data rather than schema.

---

## 12. Decisions Required Before Architecture

| # | Decision | Recommendation | Consequence if not decided |
| --- | --- | --- | --- |
| 1 | Approve or reject each deviation DV-1 … DV-10 | Accept all except **DV-3, which I recommend rejecting** — add payments to Edition 1 | Architecture would be built against an unapproved scope |
| 2 | Confirm CF-1: is statutory e-invoicing legally mandatory? | Proceed on A-15 (not mandatory) if unanswered | The only item that could add Edition 1 scope. Affects M-08 |
| 3 | Confirm A-19: what does ₹10,000–20,000 cover? | Proceed on annual-running-cost reading | Changes deployment topology, not edition boundaries |
| 4 | Confirm whether delivery staff collect cash | Defer field collection to Edition 2 | Affects M-09 depth only |
| 5 | Authorise amendment of the frozen baseline | Amend `01` and `02` to v0.3.0 recording edition membership | The frozen documents would contradict the roadmap (C-1) |

> **On decision 5.** The Vision and Requirements Specification are frozen and now describe a larger product than Edition 1. Rather than rewrite them, I recommend adding an *Edition* column to the requirements tables and a short §7.5 to the Vision cross-referencing this document. That preserves the baseline as the full product definition while making edition membership unambiguous — and it is a small edit, not a re-issue.

---

## 13. Edition 1 Re-validation — "Time to First Customer Success"

Added in v0.2.0. Sections 1–12 are unchanged and remain the product roadmap; this section supersedes §6.1 as the definition of Edition 1 scope.

### 13.1 The test applied

> **"If this feature is removed today, would the customer still be able to run the business successfully every day?"**
> **YES → Edition 2. NO → Edition 1.**

Applying this literally would strip the product past the point of being worth buying, so I have paired it with a second question that keeps it honest:

> **"Does this feature replace something the distributor already does manually, or does it add a new control they never had?"**
> **Replaces → keep. Adds → defer.**

Together these give a clean, defensible line. The distributor's manual workflow is: record stock in, take an order, send goods out, write a bill, note who owes money, know what sold. Software that replaces those six things is worth paying for on day one. Software that adds credit enforcement, approval workflows, scheme automation and territory management is worth paying for later — and it is worth *more* later, because by then they will have felt the need.

### 13.2 Re-validation results

**Demoted to Edition 2** — passes the removal test, and adds a control rather than replacing a manual step.

| Feature | Was | Why it moves | Saved |
| --- | --- | --- | --: |
| Credit-limit warning + owner override | E1 | The owner ran on judgement before and can continue to. Adds a control | 0.5 |
| Route / zone assignment | E1 | Orders are assigned to a salesman directly. Route is a *second* mechanism for the same outcome | 0.5 |
| Customer-specific price override | E1 | The manual discount field covers negotiated rates. More typing, same result | 0.5 |
| Price effective dating | E1 | Invoices persist their own price (BR-006), so no history is lost when a price changes | 0.3 |
| Effective-dated tax rate table | E1 | Same reasoning. A rate on the product, persisted onto the invoice at issue, is sufficient | 0.5 |
| Payment-to-invoice allocation | E1 | Distributors keep a running account, not an invoice-matched ledger. See §13.3 | 0.5 |
| Aging buckets report | E1 | A list of unpaid invoices with dates shows age without a bucketing engine | 0.3 |
| In-app notifications (M-14 entirely) | E1 | An "unactioned orders" filter on the order list achieves the same thing for nothing | 0.5 |
| Device registration & revocation | E1 | A security control, not a workflow. Sync records a device identifier regardless | 0.5 |
| Dashboard with charts | E1 | Explicitly excluded by direction 3. Four plain numbers, no charts | 0.3 |
| Product category hierarchy | E1 | Search covers a few hundred SKUs | 0.2 |
| `trackingPolicy` field on product | E1 | **Reclassified.** Adding a column to a master table later is an `ALTER TABLE` with a default — no historical rows are rewritten, so it fails my own §9.1 test | 0.1 |

**Simplified, not removed** — the workflow is preserved, the machinery is not.

| Feature | Was | Now |
| --- | --- | --- |
| Units of measure | UoM entity + conversion table | A single `pack_size` integer on the product. Order in pieces or packs. Same workflow, a fraction of the model |
| Price list | `PriceList` + `PriceListItem` entities | A `selling_price` on the product. One list does not need two tables |
| Tax | Tax code + effective-dated rate table | A `tax_rate_percent` on the product, computed and persisted onto the invoice at issue |
| Order lifecycle | 6 states + `INVOICED` | **5 states:** `PLACED → CONFIRMED → DISPATCHED → DELIVERED`, plus `CANCELLED`. Invoiced-ness is derived from whether an invoice exists, not tracked as a state |
| Audit | Every state change | Financial and stock events only: invoice issue, credit note, payment, stock adjustment, order cancellation, price change. The irreversible subset |
| Receivables | Invoice-allocated ledger + aging | Running-account ledger with derived balance and a list of unpaid invoices |
| Photographs | Object storage, multiple images | One image per delivery and per visit, resized to ≤200 KB, on local disk behind an authenticated endpoint |

**Retained in Edition 1** — fails the removal test. The business genuinely stops or degrades without it.

Products · Customers · Stock movements and derived on-hand · Stock in/out/adjustment with reason codes · Order capture by Owner · Order edit and cancel · Assign to salesman · Dispatch with stock issue · Delivery status from app · Proof-of-delivery photo · Invoice with persisted tax · Immutable documents · Gapless numbering · PDF · Credit note · Payment recording · Derived customer balance · Customer statement · Visit check-in with coordinates and photo · Six plain-table reports with CSV · Offline outbox and idempotent replay · Master-data pull · Sync status visibility · Login, roles and server-side authorisation.

### 13.3 One retained feature that fails the strict test

**Retailer order placement passes the removal test** — the owner can key phone orders exactly as they do today. By the literal rule it belongs in Edition 2.

I am keeping it, for one reason: **it is the only Edition 1 feature that reduces the owner's daily work rather than merely digitising it.** Everything else replaces paper with a screen. This replaces a phone call and a keystroke with nothing at all. It is also the only channel where an order is captured once, at source — the whole of PO-1 in Edition 1.

But "Time to First Customer Success" argues for getting the distributor operational sooner, so I recommend splitting the release rather than choosing:

| Sub-release | Contents | Effort | Outcome |
| --- | --- | --: | --- |
| **Edition 1a** | Everything internal: owner web admin, salesman/delivery app, stock, orders, billing, payments, reports, sync | 19.0 | **The distributor goes live.** Their manual workflow is replaced. This is first customer success |
| **Edition 1b** | Retailer role in the same Flutter app: login, browse, place order, view bills and order status | 3.0 | Retailers self-serve. Owner's data-entry load drops |

Edition 1b ships weeks after 1a, into a system already proven in production, and needs no architectural change — the retailer role and its API surface are designed in from the start.

### 13.4 Revised Edition 1 effort

| Module | v0.1.0 | v0.2.0 | Δ |
| --- | --: | --: | --: |
| M-01 Identity & Access | 2.0 | 1.5 | −0.5 |
| M-02 Customer Management | 1.5 | 1.0 | −0.5 |
| M-03 Product Catalogue | 2.0 | 1.5 | −0.5 |
| M-04 Inventory & Stock | 2.5 | 2.5 | — |
| M-05 Pricing & Discounts | 2.0 | 1.0 | −1.0 |
| M-06 Order Management | 3.5 | 2.5 | −1.0 |
| M-07 Fulfilment & Delivery | 2.0 | 2.0 | — |
| M-08 Billing | 3.5 | 3.0 | −0.5 |
| M-09 Payments & Receivables | 2.0 | 1.5 | −0.5 |
| M-10 Field Activity | 1.5 | 1.5 | — |
| M-13 Reporting | 2.0 | 1.5 | −0.5 |
| M-14 Notifications | 0.5 | 0.0 | −0.5 |
| M-15 Sync & Offline | 2.0 | 2.0 | — |
| M-16 Zone & Route | 0.5 | 0.0 | −0.5 |
| M-18 Audit | 1.0 | 0.5 | −0.5 |
| **Total** | **28.5** | **22.0** | **−6.5 (−23%)** |

Edition 1 is now **22 units of a 100-unit platform**, split 19.0 / 3.0 across 1a and 1b. The 6.5 units removed buy no lost workflow — every demotion in §13.2 either adds a control the distributor never had, or is a simplification that preserves the workflow exactly.

### 13.5 Amendment to the structural enablers

Direction 4 preserves the structural extension points, and §9.1 defended them. Re-applying that section's own test produces one change and one reversal.

**The test in §9.1:** *carry any dimension whose later addition would require rewriting historical rows; reject anything that is merely an `ALTER TABLE` with a default.*

| Dimension | v0.1.0 | v0.2.0 | Reasoning |
| --- | --- | --- | --- |
| `location_id` on stock movements | Carry | **Carry** | Adding it later re-keys the most sensitive table in the system and every balance query over it. One column, one seeded row |
| `lot_id` on stock movements | Carry | **Carry** | Same table, same reasoning |
| `trackingPolicy` on product | Carry | **Drop** | A master-table column. Adding it later is an `ALTER TABLE` with a default and touches no history. It fails the test I wrote, so it goes |
| `tenant_id` on ~30 tables | Carry | **Drop — replaced by a strategy** | See below |

**On tenancy — I am reversing my earlier recommendation.**

Row-level tenancy (`tenant_id` on every table plus a filter on every query) is one of two ways to reach SaaS, and for this product it is the worse one. Its cost is not the columns; it is that *every query for the rest of the product's life* must carry the filter, and a single omission is a cross-tenant data leak.

The alternative is **schema-per-tenant**: one PostgreSQL schema per distributor, selected by connection routing. It requires no `tenant_id` column anywhere, gives stronger isolation, makes per-tenant backup and restore trivial, and scales comfortably to the low hundreds of tenants — which is the realistic ceiling for a distributor SaaS in this market.

What Edition 1 must do to preserve it costs nothing:

- No hardcoded schema name anywhere; the schema is resolved from configuration.
- All DDL is scripted and repeatably applicable to a fresh schema (migrations already give this).
- No cross-schema joins or assumptions of a single global namespace.

That is three constraints on how migrations are written, versus thirty columns and a permanent query discipline. **This is a strictly better trade, and it means direction 4's "structural extension points" are preserved at lower cost than the version I originally proposed.**

### 13.6 Revised decisions requiring confirmation

Supersedes §12. Items 2, 3 and 4 there are unchanged.

| # | Decision | Recommendation |
| --- | --- | --- |
| 6 | Approve the §13.2 demotions | Accept. No workflow is lost |
| 7 | Approve the Edition 1a / 1b split | Accept. Fastest route to a working distributor |
| 8 | Approve dropping `tenant_id` in favour of schema-per-tenant | Accept. Cheaper now, safer later (§13.5) |
| 9 | Confirm the manual discount is acceptable in place of customer-specific pricing | Accept for Edition 1; **first candidate to pull forward** if the owner finds it slows daily order entry |

---

## Document Control

**Approval**

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Business Owner (Sponsor) | | ☐ Approved ☐ Changes requested | |
| Product Architect | | ☐ Approved ☐ Changes requested | |
| Lead Implementation Engineer | | ☐ Approved ☐ Changes requested | |

**Next documents** — to be produced after this document is approved, in this order:

1. `docs/03_System_Architecture.md` — modular monolith, module boundaries, deployment topology, authentication flow, sync strategy, technology stack, folder structure, decisions with rationale. Explicitly separating **Current MVP** from **Future Extension Points**.
2. `docs/04_Database_Design.md`
3. `docs/05_API_Contracts.md`

*No architecture, database design, API contract or implementation has been produced. Scope for all three following documents is Edition 1 as defined here.*

