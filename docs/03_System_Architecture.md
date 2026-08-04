# DistriCore — System Architecture

| Field | Value |
| --- | --- |
| Document ID | `03_System_Architecture` |
| Product | DistriCore (working title) |
| Version | 0.1.0 |
| Status | **Draft — pending sign-off. No implementation authorised** |
| Date | 2026-08-04 |
| Owner | Solution Architecture |
| Scope | **Edition 1 (1a + 1b)** as defined in `02A_Product_Editions.md` §13 |
| Depends on | `01_Project_Vision.md` v0.2.0 · `02_Requirements_Specification.md` v0.1.0 · `02A_Product_Editions.md` v0.2.0 |

> **Reading rule.** Every section is split into **▸ MVP** — what is built now — and **▸ Extension Point** — what is deliberately left possible and deliberately not built. If a capability appears only under Extension Point, **no code for it exists in Edition 1.** Writing that code early is the failure mode this document is structured to prevent.
>
> **Optimisation target.** Fast development, low maintenance, low operating cost, easy upgrades, clean production architecture. Explicitly *not* enterprise complexity. Where those goals conflict, the resolution and its reasoning are recorded as an ADR in §12.

---

## 1. Architectural Overview

### 1.1 Shape

```
┌──────────────────────────┐   ┌──────────────────────────┐
│  Owner / Staff           │   │  Flutter application     │
│  Responsive Web Admin    │   │  (single binary)         │
│  server-rendered HTML    │   │  Salesman · Delivery ·   │
│                          │   │  Retailer (1b)           │
└────────────┬─────────────┘   └────────────┬─────────────┘
             │ session cookie                │ JWT
             │ HTML over HTTPS               │ REST/JSON over HTTPS
             └───────────────┬───────────────┘
                             ▼
                 ┌───────────────────────┐
                 │   Reverse proxy       │  TLS termination,
                 │   (Caddy)             │  static + media serving
                 └───────────┬───────────┘
                             ▼
        ┌────────────────────────────────────────┐
        │        DistriCore Backend              │
        │        (modular monolith)              │
        │                                        │
        │  ┌──────────────┐  ┌────────────────┐  │
        │  │ Web Admin UI │  │   REST API     │  │  delivery layer
        │  │ (templates)  │  │  (serializers) │  │
        │  └───────┬──────┘  └────────┬───────┘  │
        │          └────────┬─────────┘          │
        │            ┌──────▼──────┐             │
        │            │  Services   │             │  business logic —
        │            │  (per module)│            │  the only place
        │            └──────┬──────┘             │  rules live
        │            ┌──────▼──────┐             │
        │            │   Models    │             │  persistence
        │            └──────┬──────┘             │
        └───────────────────┼────────────────────┘
                            ▼
                 ┌────────────────────┐
                 │    PostgreSQL      │
                 └────────────────────┘

                 ┌────────────────────┐
                 │  Local filesystem  │  photographs, PDFs
                 └────────────────────┘
```

**One deployable process. One database. One VPS.**

### 1.2 The five rules that make this a modular monolith rather than a large application

| # | Rule | Enforcement |
| --- | --- | --- |
| 1 | Each module owns its own models. No module reads or writes another module's tables directly. | Code review; import-linter in CI |
| 2 | Cross-module interaction goes through the owning module's `services.py`. Never through its models, views or serialisers. | Import-linter forbids `from other_module.models import …` |
| 3 | The module dependency graph is acyclic. | Import-linter contract |
| 4 | Business rules live in `services.py`. Views, serialisers and templates contain no business logic. | Code review |
| 5 | The web admin and the REST API are two delivery adapters over the same services. Neither may contain a rule the other lacks. | BR-001 |

> **Why these five and not a hexagonal-architecture layer stack.** These rules cost nothing to follow and are mechanically checkable. Repository interfaces, domain/persistence model separation and dependency-injection containers would each add real code for benefits that only appear at a team size and complexity this project will not reach in Edition 1. Rule 2 alone delivers the extractability that matters: a module whose only inbound coupling is a service function can be lifted out later. **Rejected: ports-and-adapters, DI container, separate domain models. Reason: cost with no Edition 1 benefit.** (ADR-006)

---

## 2. Module Boundaries

### 2.1 Modules and dependencies

Fourteen modules, matching `02A` §4 minus those deferred in §13.

```
                    ┌──────────┐
                    │ platform │   base model, audit, config, auth primitives
                    └────┬─────┘
                         │  (every module depends on platform)
     ┌───────────┬───────┴───────┬────────────┬──────────────┐
     ▼           ▼               ▼            ▼              ▼
┌─────────┐ ┌──────────┐  ┌───────────┐ ┌──────────┐  ┌──────────┐
│ identity│ │ catalogue│  │ customers │ │ pricing  │  │  field   │
└────┬────┘ └────┬─────┘  └─────┬─────┘ └────┬─────┘  └────┬─────┘
     │           │              │            │             │
     │           ▼              │            │             │
     │      ┌─────────┐         │            │             │
     │      │inventory│◄────────┼────────────┘             │
     │      └────┬────┘         │                          │
     │           │              │                          │
     │           ▼              ▼                          │
     │      ┌──────────────────────┐                       │
     │      │      orders          │                       │
     │      └──────────┬───────────┘                       │
     │                 ▼                                   │
     │      ┌──────────────────────┐                       │
     │      │     fulfilment       │───────────────────────┘
     │      └──────────┬───────────┘
     │                 ▼
     │      ┌──────────────────────┐
     │      │      billing         │
     │      └──────────┬───────────┘
     │                 ▼
     │      ┌──────────────────────┐
     │      │     receivables      │
     │      └──────────────────────┘
     │
     ▼
┌─────────┐   ┌──────────┐   ┌──────────┐
│  sync   │   │ reporting│   │ webadmin │   read-only across modules
└─────────┘   └──────────┘   └──────────┘
```

| Module | Owns | May call | Edition |
| --- | --- | --- | :-: |
| `platform` | `TimeStampedModel`, `AuditLog`, settings, permissions, storage | — | 1a |
| `identity` | `User`, `Role` | `platform` | 1a |
| `catalogue` | `Product` | `platform` | 1a |
| `customers` | `Customer` | `platform` | 1a |
| `pricing` | price resolution, discount rules | `catalogue`, `customers` | 1a |
| `inventory` | `StockMovement`, `ReasonCode` | `catalogue` | 1a |
| `orders` | `Order`, `OrderLine` | `customers`, `catalogue`, `pricing`, `inventory` | 1a |
| `fulfilment` | `Delivery`, `DeliveryPhoto` | `orders`, `inventory`, `identity` | 1a |
| `billing` | `Invoice`, `InvoiceLine`, `CreditNote`, `NumberSeries` | `orders`, `fulfilment`, `customers` | 1a |
| `receivables` | `Payment`, `CustomerLedgerEntry` | `billing`, `customers` | 1a |
| `field` | `Visit`, `VisitPhoto` | `customers`, `identity` | 1a |
| `sync` | `SyncBatch` | `orders`, `fulfilment`, `field`, `catalogue`, `customers` | 1a |
| `reporting` | nothing — read-only queries | all (read) | 1a |
| `webadmin` | templates, views | all (via services) | 1a |
| `api` | serialisers, viewsets | all (via services) | 1a / 1b |

> `reporting`, `webadmin` and `api` own no models. They are delivery and query surfaces. This is why rule 1 is not violated by their broad reach: they read through services, and they write nothing.

### 2.2 Anti-corruption on the hot boundary

`orders → inventory` is the only cross-module write path in Edition 1 that must be transactional. It is expressed as exactly one service call:

```
inventory.services.issue_stock(product_id, qty, source_type, source_id, actor)
inventory.services.receive_stock(...)
inventory.services.adjust_stock(..., reason_code)
```

Nothing outside `inventory` writes a `StockMovement`. That single constraint is what makes BR-004 and BR-007 enforceable rather than aspirational.

**▸ Extension Point EP-A.** When multi-warehouse arrives (Edition 2), `location_id` becomes a parameter on these three functions rather than a defaulted column. Call sites change; the model does not.

---

## 3. Technology Stack

### 3.1 Selection

| Layer | Choice | Why this, for this client |
| --- | --- | --- |
| Language / framework | **Python 3.12 + Django 5 + Django REST Framework** | Auth, migrations, admin scaffolding, ORM, permissions and CSRF come built in. For a lean MVP these are weeks of work not written. One developer can hold the whole stack |
| Web admin UI | **Django templates + HTMX + Tailwind (CDN build)** | The admin is lists, forms and tables (direction 3). Server-rendered HTML delivers that with **no second build pipeline, no CORS, no duplicated auth, no separate deployment**. See ADR-003 |
| Mobile | **Flutter (Dart)**, one binary, role-based routing | Confirmed direction. One codebase, Android first |
| Mobile local store | **SQLite via Drift** | Typed queries, migrations, transactions. The outbox needs durability, not a sync framework |
| Database | **PostgreSQL 16** | Correct decimal arithmetic, real transactions, JSONB when needed. Runs in ~200 MB |
| API | **REST/JSON over HTTPS**, DRF | Confirmed direction |
| Auth | Django sessions (web) · **JWT access + refresh** (mobile) | §5 |
| PDF | **WeasyPrint** | HTML template → PDF. Reuses the invoice template already written for the web view |
| Images | **Pillow**, resized on upload | One dependency; no external service |
| Reverse proxy | **Caddy** | Automatic TLS certificates with no configuration. Removes an entire class of ops work |
| Process manager | **Gunicorn** + systemd or Docker restart policy | Boring and proven |
| Containers | **Docker Compose** | Confirmed direction. Identical locally and in production |
| CI | **GitHub Actions** | Free at this scale |

### 3.2 Deliberately absent

| Not used | Why |
| --- | --- |
| Redis | Nothing in Edition 1 needs a cache or a broker. Postgres handles sessions and locks |
| Celery / RQ / any broker | Directed against, and unnecessary: image resize (~200 ms) and PDF render (~300 ms) are fast enough to run inline |
| React / Vue / Next.js SPA | ADR-003. A second build pipeline and a second auth implementation for lists and forms |
| GraphQL | REST is confirmed and sufficient |
| Kubernetes, service mesh, message bus | One process on one VPS |
| Elasticsearch | Postgres full-text search is more than adequate at 10,000 SKUs |
| S3 / object storage | Local disk plus offsite backup. Under A-19, an object store is a recurring cost for a feature a 40 GB VPS volume already provides |
| ORM-independent repository layer | ADR-006 |

### 3.3 The one input that would change §3.1

**If the team's existing proficiency is in Node/TypeScript or Java, use it instead.** Team familiarity beats framework merit by a wide margin on a one-developer project, and the architecture in this document is framework-shaped, not framework-dependent: the module boundaries (§2), sync protocol (§6), auth flow (§5) and data model all transfer unchanged.

| If you choose | Substitute | What changes |
| --- | --- | --- |
| Node / TypeScript | NestJS + Prisma; Nunjucks or EJS templates + HTMX | Modules become Nest modules; migrations become Prisma migrations. **You lose Django's built-in admin and auth — roughly 2 units of extra work** |
| Java | Spring Boot + JPA + Thymeleaf + HTMX | As above; heavier memory footprint, needs a 4 GB VPS rather than 2 GB |

I recommend Django unless the team is materially stronger elsewhere. **This is the single decision in this document most worth overriding on local knowledge, and it is worth deciding before §14.**

---

## 4. Deployment Topology

### 4.1 Production — single VPS

```
┌─────────────────────────────────────────────────────┐
│  VPS — 2 vCPU / 4 GB RAM / 80 GB SSD                │
│  Ubuntu 24.04 LTS · Docker Compose                  │
│                                                     │
│   ┌──────────┐   :443                               │
│   │  caddy   │◄──────── internet                    │
│   └────┬─────┘   auto-TLS, static + media           │
│        │                                            │
│   ┌────▼─────────────┐    ┌────────────────┐        │
│   │  districore-web  │───►│   postgres:16  │        │
│   │  gunicorn+django │    │   named volume │        │
│   │  ~400 MB         │    │   ~400 MB      │        │
│   └────┬─────────────┘    └───────┬────────┘        │
│        │ media volume             │                 │
│   ┌────▼─────────────┐    ┌───────▼────────┐        │
│   │  /srv/media      │    │  backup (cron) │        │
│   │  photos, PDFs    │    │  pg_dump + WAL │        │
│   └──────────────────┘    └───────┬────────┘        │
└───────────────────────────────────┼─────────────────┘
                                    ▼  nightly encrypted
                          offsite storage (rclone)
```

**Headroom at the DR-8 envelope:** 4 GB RAM against ~1 GB used. At 10,000 retailers and 10,000 order lines/day this box is not close to its limit, and vertical scaling to 8 GB is a reboot.

### 4.2 Cost

| Item | Monthly | Annual |
| --- | --: | --: |
| VPS (2 vCPU / 4 GB, Indian or EU region) | ₹500–700 | ₹6,000–8,400 |
| Domain | ₹80 | ₹1,000 |
| Offsite backup (~20 GB) | ₹50 | ₹600 |
| TLS (Caddy / Let's Encrypt) | ₹0 | ₹0 |
| **Total** | **₹630–830** | **₹7,600–10,000** |

Inside the A-19 envelope with room to spare. **No managed database, no object store, no paid third-party tier** — each of those alone would consume most of the annual budget while providing nothing this workload needs.

### 4.3 Local development

`docker compose up` gives web, postgres and caddy identical to production, seeded with demo data. No cloud account, no credentials, no network dependency. **A developer must be able to run the entire system offline on day one** — this is a requirement, not a convenience, because it is what keeps the Docker Compose file honest.

### 4.4 Backup and recovery

| Aspect | MVP position |
| --- | --- |
| Nightly | Full `pg_dump`, encrypted, pushed offsite |
| Continuous | WAL archiving to a separate local volume |
| Media | Nightly `rclone` sync of `/srv/media` |
| Restore | Documented and **rehearsed quarterly** (ACT-F). An untested backup is not a backup |
| **RPO** | **≈1 hour** local, 24 hours offsite |
| **RTO** | ≈2 hours — provision VPS, `docker compose up`, restore dump |

> **Deviation from DR-5, declared.** DR-5 set RPO ≤ 15 minutes. Achieving that needs streaming replication to a second host — roughly doubling infrastructure cost for a business whose worst case is re-keying part of one day's orders from paper delivery notes. **RPO is relaxed to ≈1 hour for Edition 1.** This requires sign-off (§14). Streaming replication is EP-K.

---

## 5. Authentication & Authorisation

### 5.1 Two mechanisms, one authority

| Surface | Mechanism | Why |
| --- | --- | --- |
| Web admin | Django session cookie, `HttpOnly` `Secure` `SameSite=Lax`, CSRF token | Server-rendered HTML. Sessions are free, revocable, and immune to token-in-storage problems |
| Flutter app | JWT: 30-minute access token + 30-day refresh token | Mobile clients need a bearer credential that survives app restarts and works offline between syncs |

Both resolve to the **same `User` and the same permission check in `services.py`**. Two front doors, one lock (BR-001, BR-003).

### 5.2 Mobile flow

```
  App                          Backend
   │  POST /api/v1/auth/login   │
   │  {username, password}      │
   ├───────────────────────────►│  verify (argon2)
   │                            │  issue access(30m) + refresh(30d)
   │◄───────────────────────────┤  + user profile + role
   │  store in secure storage   │
   │                            │
   │  GET /api/v1/... (Bearer)  │
   ├───────────────────────────►│  authorise per request (BR-003)
   │◄───────────────────────────┤
   │                            │
   │  401 → POST /auth/refresh  │
   ├───────────────────────────►│  rotate refresh, issue new access
   │◄───────────────────────────┤
```

**Offline authentication (FR-IAM-016).** The app stores the user profile and a hash of the last successful login. While offline it permits use for a configurable maximum (default 7 days, OI-5) using the cached refresh token's validity as the ceiling. On the first successful sync after that window, re-authentication is forced.

### 5.3 Authorisation model — MVP

Four roles as **data rows**, not classes. A single DRF permission class plus a per-service ownership check:

```
owner     → everything
salesman  → own deliveries, own visits, read customers & products
delivery  → same as salesman (a role flag, not a separate code path)
retailer  → own customer's orders, invoices, ledger — read + place order
```

`retailer` scoping is enforced by a service-level filter on `request.user.customer_id`. **Never by the client, and never by URL structure.**

> **The DV-4 condition, restated as an architectural constraint.** The Flutter binary is public and must be assumed decompiled. It therefore contains no API key, no secret, no internal-only endpoint, and no business rule whose confidentiality matters. Every one of its requests is authorised server-side as though it came from an attacker. **This is what makes one binary for internal and external users safe.**

**▸ Extension Point EP-B.** Custom roles: the four roles are already rows in a `Role` table with a permission set. Edition 2 adds a management screen. No model change.

---

## 6. Offline Synchronisation Strategy

This is where `02A` §5 pays off. **Because Edition 1 salesmen do not capture orders, sync is an outbox — not a reconciliation protocol.**

### 6.1 What synchronises

| Direction | Data | Conflict potential |
| --- | --- | --- |
| **Pull** | Products, customers, assigned deliveries, own visit history | None — server is authoritative, client replaces |
| **Push** | Delivery status updates, visit records, coordinates, photographs | **None contend for a shared resource** |

No stock is allocated offline. No price is computed offline. No credit is consumed offline. The four conflict classes that required human resolution in the frozen baseline (`SC-STOCK`, `SC-CREDIT`, `SC-PRICE`, `SC-MASTER`) **cannot arise in Edition 1**, because nothing the device writes touches the state those classes protect.

### 6.2 Push protocol

```
Device                                  Backend
  │                                       │
  │  local write → SQLite outbox          │
  │  { client_uuid, op_type, payload,     │
  │    created_at, device_id }            │
  │                                       │
  │  POST /api/v1/sync/push               │
  │  { operations: [ ... ] }              │
  ├──────────────────────────────────────►│
  │                                       │  per operation, in creation order:
  │                                       │   1. seen client_uuid? → ACCEPTED (no-op)
  │                                       │   2. dependency unmet? → DEFERRED
  │                                       │   3. apply via module service
  │                                       │   4. record client_uuid
  │◄──────────────────────────────────────┤
  │  { results: [{client_uuid, status}] } │
  │                                       │
  │  ACCEPTED / DUPLICATE → delete from outbox
  │  DEFERRED             → retain, retry next sync
  │  REJECTED             → retain, flag to user, never delete
```

**Idempotency (BR-012).** The client generates a UUIDv4 per operation at creation. The server keeps a `sync_operation` table keyed on it. Replaying a batch is a no-op — which makes retry-on-timeout safe, and retry-on-timeout is what makes the protocol robust on a 2G connection.

**Ordering (BR-013).** Operations apply in device creation order. A delivery status update cannot overtake the visit that preceded it.

**No transaction is discarded (BR-014).** A malformed or rejected operation is stored server-side with its error and surfaced to the owner. It is never dropped, and it is never silently deleted from the device.

### 6.3 Pull protocol

`GET /api/v1/sync/pull?since=<iso8601>` returns rows changed since the timestamp, using an indexed `updated_at`. First sync sends `since=null` and gets everything the user is authorised to hold (FR-SYN-012). Payload at the DR-8 envelope: roughly 200–400 KB — small enough that delta sync is an optimisation, not a requirement.

### 6.4 Photographs

Uploaded on a **separate queue** from transactional operations, so a 200 KB photo on a weak connection never blocks a delivery confirmation (FR-FUL-014). Resized client-side before queueing.

### 6.5 What this costs, and what the upgrade costs

| | Edition 1 outbox | Edition 2 full sync |
| --- | --- | --- |
| Conflict classes | 2, both automatic | 6, four needing human resolution |
| Resolution console | Not built | Built |
| Effort | 2.0 units | +9.0 units |

**▸ Extension Point EP-C.** Edition 2 adds order-creation operations to the same outbox and the same push endpoint. The four additional conflict classes are new branches in the per-operation handler, plus a resolution screen. **The protocol, the idempotency table, the ordering guarantee and the device outbox are unchanged.** This is the extension-not-rewrite claim made concrete.

---

## 7. Component Communication

| Path | Mechanism | Notes |
| --- | --- | --- |
| Browser → Backend | HTTPS, HTML, session cookie | HTMX partial updates; full page loads where simpler |
| Flutter → Backend | HTTPS, REST/JSON, Bearer JWT | Versioned at `/api/v1/` |
| Module → Module | **In-process Python function call** into `services.py` | No HTTP, no queue, no event bus. §2.1 rule 2 |
| Backend → Postgres | psycopg over the Docker network | Never exposed to the internet |
| Backend → filesystem | Django storage API | The storage backend is the seam for object storage later |

> **Why in-process calls and not domain events.** An event bus would decouple modules that currently have twelve well-understood dependencies. It would also make every flow asynchronous, every failure partial, and every bug non-reproducible. Directed against, and correctly so. **Rejected: event bus, domain events, outbox pattern between modules.** (ADR-005)

**▸ Extension Point EP-D.** A module extracted into its own service later needs its `services.py` boundary turned into an HTTP client. Because rule 2 already forbids reaching past it, the call sites do not change.

---

## 8. Data Architecture Principles

Full schema is `04_Database_Design.md`. The principles that constrain it:

| # | Principle | Consequence |
| --- | --- | --- |
| 1 | **Stock is derived from movements** (BR-004) | `SELECT SUM(quantity) … GROUP BY product_id`. No `quantity_on_hand` column exists to drift |
| 2 | **Customer balance is derived from ledger entries** (BR-005) | Same shape. No stored balance |
| 3 | **Issued documents are immutable** (BR-006) | Invoices and credit notes have no update path in any service |
| 4 | **Money is `NUMERIC(14,2)`; quantity is `NUMERIC(14,3)`** | Never floating point (NFR-INT-005) |
| 5 | **Every stock movement carries source document or reason code** (BR-007) | Enforced by a database `CHECK`, not only in application code |
| 6 | **Soft delete via `is_active`; hard delete forbidden where history exists** | FR-CUS-009, FR-PRD-009 |
| 7 | **`location_id` and `lot_id` present on `stock_movement`** | Defaulted to seeded rows. §13.5 of `02A` |
| 8 | **No `tenant_id`** | Tenancy is schema-per-tenant. §13.5 of `02A` |

> **On principle 1 at scale.** A `SUM` over movements is fine to roughly 5 million rows on this hardware. At the DR-8 envelope Edition 1 generates ~1.5 million movements over three years. **No cache is needed and none is built.**
>
> **▸ Extension Point EP-E.** If it is ever needed, a `stock_balance` cache table maintained in `inventory.services` and reconcilable from movements (FR-STK-007). One module changes.

---

## 9. Project Folder Structure

```
districore/
├── docker-compose.yml              # dev: web, db, caddy
├── docker-compose.prod.yml
├── Dockerfile
├── Caddyfile
├── pyproject.toml
├── .env.example                    # never .env — NFR-SEC-007
│
├── docs/                           # 01 … 05, the source of truth (C-1)
│
├── backend/
│   ├── manage.py
│   ├── config/
│   │   ├── settings/{base,dev,prod}.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   │
│   ├── platform/                   # base model, audit, permissions, storage
│   ├── identity/
│   ├── catalogue/
│   ├── customers/
│   ├── pricing/
│   ├── inventory/
│   ├── orders/
│   ├── fulfilment/
│   ├── billing/
│   ├── receivables/
│   ├── field/
│   ├── sync/
│   ├── reporting/
│   │
│   ├── api/                        # DRF: serialisers, viewsets, routers
│   │   └── v1/
│   ├── webadmin/                   # templates, views, static
│   │   └── templates/
│   └── tests/
│       ├── unit/                   # services, no database where possible
│       ├── integration/
│       └── adversarial/            # §11.2 — sync, immutability, authorisation
│
├── mobile/                         # Flutter, single binary
│   └── lib/
│       ├── core/                   # api client, auth, secure storage
│       ├── data/
│       │   ├── local/              # Drift: outbox, cached master data
│       │   └── remote/
│       ├── features/
│       │   ├── auth/
│       │   ├── delivery/           # salesman + delivery role
│       │   ├── visit/
│       │   └── retailer/           # Edition 1b
│       └── shared/
│
└── scripts/
    ├── backup.sh
    ├── restore.sh
    └── seed_demo.py
```

**Every module folder has the same five files:**

```
<module>/
├── models.py          # owned tables only
├── services.py        # THE public interface. All business rules
├── selectors.py       # read queries
├── admin.py
└── tests/
```

> Uniformity is the point. A developer opening any module knows where the rules are without exploring, and rule 2 is visible in the file layout rather than only in a document.

---

## 10. Current MVP vs. Future Extension Points

The consolidated answer to "what is built now, and what is merely left possible."

| ID | Extension point | MVP carries | MVP does **not** build | Edition |
| --- | --- | --- | --- | :-: |
| EP-A | Multi-warehouse | `location_id` on `stock_movement`, one seeded location | Location UI, transfers, per-location stock | 2 |
| EP-B | Custom roles | Roles as data rows | Role management screen | 2 |
| EP-C | Field order capture | Outbox, idempotency, ordering | 4 conflict classes, resolution console | 2 |
| EP-D | Service extraction | `services.py` boundary, acyclic graph | Any network boundary | 3 |
| EP-E | Stock balance cache | Derivation from movements | The cache table | 2 |
| EP-F | Batch / lot tracking | `lot_id` on `stock_movement`, default lot | `trackingPolicy`, expiry, batch UI | 2 |
| EP-G | Scheme engine | `discount_amount` + nullable `scheme_id` on order line | Scheme model, slabs, free goods, resolution | 2 |
| EP-H | Purchasing | `source_type` enum on movements, extensible | Purchase orders, supplier ledger | 2 |
| EP-I | Push / SMS / email | Nothing — notifications cut entirely | Any notification infrastructure | 2 |
| EP-J | Object storage | Django storage API abstraction (built in) | S3 configuration | 2 |
| EP-K | Streaming replication | Documented restore procedure | A second host | 2 |
| EP-L | SaaS multi-tenancy | Schema-agnostic migrations, no hardcoded schema | Tenant routing, provisioning, billing | 3 |
| EP-M | Public API | Versioned `/api/v1/`, DRF | Keys, rate limits, docs portal | 3 |
| EP-N | Route optimisation | Visit records with coordinates accumulating | Any optimisation | 3 |
| EP-O | Separate apps per role | Role-based routing at the app shell | Any second binary | 3 |

> **The rule this table enforces:** an extension point is a *shape decision*, never unused code. Fifteen entries; total Edition 1 cost is two columns, one nullable field, one enum, and a discipline about how migrations are written. **No abstract base classes, no plugin registry, no strategy interfaces, no configuration framework are built for any of them** — those would be the speculative engineering the brief rules out.

---

## 11. Cross-Cutting Concerns

### 11.1 Security — MVP

| Concern | Position |
| --- | --- |
| Passwords | Argon2 (Django default) |
| Transport | TLS via Caddy; HTTP redirects to HTTPS |
| SQL injection | ORM only; no raw SQL without parameters (NFR-SEC-002) |
| XSS | Django template auto-escaping; no `mark_safe` on user content |
| CSRF | Django middleware on the session-authenticated admin |
| Authorisation | Service-level, every request (BR-003) |
| Uploads | Type and size validated, re-encoded by Pillow, served through an authorised view — never directly from the filesystem |
| Secrets | Environment variables; `.env` git-ignored; CI secret scanning blocks merge |
| Rate limiting | `django-axes` on login |
| Dependencies | `pip-audit` in CI; critical findings block release |

**Absent by decision:** WAF, IDS, secret-management service, 2FA. Each is real cost against a threat model that is one distributor's back office. Reconsider at Edition 3 when the tenant is not the owner.

### 11.2 Testing

| Layer | Target |
| --- | --- |
| Unit — services | 100% of pricing, tax, stock and ledger logic including failure paths |
| Integration — API | Every endpoint, every role, authorised and unauthorised |
| **Adversarial** | Sync replay and interruption · invoice mutation attempts through every path · full role × capability matrix issued directly to the API, bypassing all clients |
| Overall | ≥ 80% on business-rule code (NFR-TST-001) |

> Requirements §25.2 lists six requirements that ordinary testing cannot verify. Four of them survive into Edition 1 and live in `tests/adversarial/`. **A green happy-path suite is not evidence for any of them.**

### 11.3 Observability

Structured JSON logs to stdout, captured by Docker. `/healthz` endpoint. Sync status per device visible in the admin (FR-SYN-009). **No APM, no metrics stack, no log aggregation service** — at one process on one host, `docker logs` and a health check answer every question worth asking, at zero cost.

---

## 12. Architectural Decision Records

| # | Decision | Alternatives rejected | Rationale |
| --- | --- | --- | --- |
| **ADR-001** | Modular monolith, single process | Microservices; modular-with-separate-API-service | One developer, one VPS, one database. Microservices would add network failure modes, deployment complexity and distributed-transaction problems in exchange for independent scaling nobody needs |
| **ADR-002** | Django + DRF + PostgreSQL | NestJS+Prisma; Spring Boot; Laravel; FastAPI | Auth, ORM, migrations, admin, CSRF built in — weeks of MVP work not written. **Override on team proficiency (§3.3)** |
| **ADR-003** | Server-rendered admin (templates + HTMX), not an SPA | React/Vue SPA; Next.js | The admin is lists, forms and tables (direction 3). An SPA adds a second build pipeline, a second auth implementation, CORS, a second deployment and client-side state — **for the one UI shape server rendering is best at.** Saves ~3 units |
| **ADR-004** | One database, no cache layer | Redis for sessions and cache | Postgres handles sessions and locks at this scale. Redis is a second stateful service to run, monitor and back up, for a performance problem that does not exist |
| **ADR-005** | In-process module calls | Event bus; domain events; internal HTTP | Twelve well-understood dependencies. An event bus converts synchronous, debuggable flows into asynchronous partial failures |
| **ADR-006** | Services layer only; no repository/DI layers | Hexagonal architecture; DI container; separate domain models | Rule 2 alone gives the extractability that matters. The remaining ceremony costs code and comprehension for benefits at a team size this project will not reach |
| **ADR-007** | Schema-per-tenant deferred; **no `tenant_id`** | `tenant_id` on ~30 tables | Reverses the earlier recommendation. Row-level tenancy costs a query filter forever, and one omission is a cross-tenant leak. Schema-per-tenant costs three migration disciplines and gives stronger isolation (`02A` §13.5) |
| **ADR-008** | Stock derived from movements, no cache | Stored `quantity_on_hand` | A stored quantity drifts and cannot be reconciled. **"No event sourcing" does not mean "mutable balance"** (`02A` §9.2) |
| **ADR-009** | Local disk for media | S3 / object storage | Under A-19 an object store is recurring cost for what an 80 GB volume already provides. Django's storage API is the free seam (EP-J) |
| **ADR-010** | No background job queue | Celery + Redis; RQ | Image resize ~200 ms, PDF ~300 ms — both acceptable inline. A broker is directed against and would be the third stateful service |
| **ADR-011** | Two auth mechanisms, one authority | JWT everywhere; sessions everywhere | Sessions are strictly better for server-rendered HTML; JWT is necessary for a mobile client that must survive restarts. Both resolve to one permission check |
| **ADR-012** | RPO relaxed to ≈1 hour | Streaming replication for 15-minute RPO | Doubles infrastructure cost. Worst case is re-keying part of one day from paper delivery notes. **Requires sign-off (§14)** |
| **ADR-013** | Outbox sync, not reconciliation | Full bidirectional protocol in Edition 1 | Edition 1 devices write nothing that contends for a shared resource. Saves 9 units and removes R-1 from the first release (§6.5) |

---

## 13. What This Architecture Deliberately Costs

Honest accounting of the trade-offs, so they are chosen rather than discovered.

| Limitation | When it bites | Response |
| --- | --- | --- |
| Single point of failure | VPS outage stops the web admin | Field app keeps working offline. RTO ≈2 hours. Accept until revenue justifies a standby (EP-K) |
| Vertical scaling only | Beyond ~10× the DR-8 envelope | A bigger VPS is a reboot. Horizontal scaling is an Edition 3 problem |
| Server-rendered admin | If the admin ever needs rich client-side interactivity | HTMX covers most of it. A targeted React island is possible without rewriting |
| No background queue | If a future feature is genuinely slow | Add one *then*, for that feature. Not before |
| Deployment is a compose pull and restart | ~30 seconds of downtime | Acceptable for a single-distributor back office. Blue-green is Edition 3 |
| RPO ≈1 hour | Data loss window on catastrophic failure | ADR-012. Explicit, signed-off |

---

## 14. Decisions Required Before `04_Database_Design.md`

| # | Decision | Recommendation | Blocks |
| --- | --- | --- | --- |
| 1 | Confirm backend stack (ADR-002) | Django + DRF unless team is materially stronger in Node or Java | All of `04` and `05` |
| 2 | Approve server-rendered admin (ADR-003) | Accept — saves ~3 units and matches direction 3 | Folder structure, `05` |
| 3 | Approve dropping `tenant_id` (ADR-007) | Accept | `04` schema |
| 4 | Approve RPO relaxation to ≈1 hour (ADR-012) | Accept | Deployment scope |
| 5 | Confirm CF-1 — statutory e-invoicing | Proceed on A-15 (not mandatory) | `billing` module scope |
| 6 | Confirm A-19 — what ₹10,000–20,000 covers | Proceed on annual-running-cost reading | §4.2 sizing only |

> **Only decision 1 blocks `04_Database_Design.md`.** The schema is framework-independent; decisions 2 and 4 affect deployment and delivery layers, not the data model. If decision 1 is Django, `04` can proceed immediately.

---

## Document Control

**Approval**

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Business Owner (Sponsor) | | ☐ Approved ☐ Changes requested | |
| Product Architect | | ☐ Approved ☐ Changes requested | |
| Lead Implementation Engineer | | ☐ Approved ☐ Changes requested | |

**Next documents**

1. `docs/04_Database_Design.md` — tables, columns, types, constraints, indexes, migrations. Scope: Edition 1.
2. `docs/05_API_Contracts.md` — REST endpoints, payloads, status codes, error format, auth, sync contract.

*No implementation has been produced or authorised.*
