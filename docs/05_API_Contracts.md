# DistriCore — API Contracts

| Field | Value |
| --- | --- |
| Document ID | `05_API_Contracts` |
| Version | 0.1.0 |
| Status | **Draft — pending sign-off** |
| Date | 2026-08-04 |
| Owner | Chief Systems Engineer |
| Scope | **Edition 1 (1a + 1b)** — the only API surface for Version 1 |
| Transport | REST over HTTPS, JSON |
| Depends on | `00` v1.0.0 · `01` v0.2.0 · `02` v0.1.0 · `02A` v0.2.0 · `03` v0.1.0 · `04` v0.1.0 (approved) |

> **Standing.** This document is the contract between the backend and every client. Once a Flutter build is in a salesman's hand, this contract is **in the field** and cannot be changed unilaterally (C-7, E-07). It is therefore designed with the same care as the database.
>
> **No implementation code, serialisers, viewsets or routers are produced here.** Contract only.

---

## 1. Scope and Position in the Architecture

### 1.1 What this API serves

| Consumer | Auth | Surface |
| --- | --- | --- |
| **Flutter application** — salesman, delivery, retailer | JWT bearer | The entire API |
| **Web admin** — owner | Django session | Server-rendered HTML; **uses services directly, not this API** |
| Future: public / partner API | — | Edition 3 (EP-M) |

> **The web admin is not an API client.** Per ADR-003 it is server-rendered and calls `services.py` in-process. This matters: the API exists for the Flutter app, so its shape is optimised for a mobile client on a weak connection — not as a general-purpose interface the admin happens to reuse. Both surfaces call the same services (N-01, BR-001), so a rule cannot differ between them.

### 1.2 What the API must be good at

Ranked, because these rank differently from a typical web API:

1. **Surviving bad connectivity.** Retry-safe, resumable, small payloads. The client is a ₹8,000 Android phone on 2G in a village.
2. **Never double-writing money.** Idempotency is not an optimisation here (§6).
3. **Being answerable offline.** Everything the app needs for a day must arrive in one pull.
4. **Refusing unauthorised access server-side.** The binary is public and must be assumed decompiled (DV-4, N-06).
5. Being pleasant to consume. Last, deliberately — the first four are correctness.

---

## 2. Design Decisions

Same five-field format as the constitution (§P.6 of `00`).

### AD-01 — URI path versioning, `/api/v1/`

**Decision.** Every endpoint lives under `/api/v1/`. Additive changes only within a version; a breaking change requires `/api/v2/` with v1 maintained until field devices have upgraded.

**Why.** Field devices run whatever build the salesman last installed, and a distributor cannot compel 40 people to update on a Tuesday. The version must be visible in the path so both sides can reason about it, and so a proxy can route two versions concurrently.

**Alternatives.** (a) Header versioning (`Accept: application/vnd.districore.v1+json`) — cleaner in theory, invisible in logs and browser testing, and easy to omit by accident. (b) Query-parameter versioning — pollutes caching and is trivially dropped. (c) No versioning — the option that seems free and costs a forced-upgrade campaign.

**Trade-offs.** Path versioning is sometimes criticised as un-RESTful. That criticism is aesthetic; the operational benefit is real.

**Long-term impact.** Under Edition 3's public API (EP-M), partners depend on a stable, visible version.

**Migration cost if changed later.** *Medium* now, **High** once devices are deployed. Which is why it exists from the first endpoint.

---

### AD-02 — Money is a **decimal string**, never a JSON number

**Decision.** Every monetary and quantity value crosses the wire as a string: `"total_amount": "12450.00"`, `"quantity": "24.000"`.

**Why.** JSON numbers are IEEE-754 doubles in essentially every parser, including Dart's. `0.1 + 0.2` is not `0.3`, and an invoice total that is off by one paisa is a defect the client will find and will not forgive. Encoding as a string forces both sides to parse into an exact decimal type — `Decimal` in Python, `Decimal` from the `decimal` package in Dart — and makes the precision requirement impossible to ignore. This is N-07 extended to the transport layer, where it would otherwise be silently lost.

**Alternatives.** (a) JSON number — the default, and wrong for money. (b) Integer paise (`1245000`) — exact and compact, but every client must remember the scale, and one forgotten division is a 100× error on an invoice. (c) `{"amount": "124.50", "currency": "INR"}` — needed for multi-currency, which this product does not have.

**Trade-offs.** Slightly noisier JSON. Clients must not naively `double.parse()`. **This is stated as a client obligation in §12 and must be enforced in review.**

**Long-term impact.** Correct arithmetic is a precondition for the Edition 3 accounting integration.

**Migration cost if changed later.** **High** — changing the encoding after devices are deployed breaks every build in the field, and the failure is silent rounding rather than a visible error.

#### AD-02.1 — Clarification: a **rate** is a decimal string too; a **count** is not

*Added 2026-09-06 with TD-36. **AD-02 above is unchanged** — this states the boundary it always implied for a value AD-02's wording does not name.*

AD-02 says *"monetary and quantity"*. `GET /reports/sync-health` (§9.11.2) introduced a third `Decimal`: `conflict_rate`, a percentage at two places. It is neither money nor quantity, so AD-02 did not literally reach it — and as a JSON number it would become an IEEE-754 double for exactly the reason AD-02 gives.

> **The rule the report API applies, in full: a `Decimal` never crosses the wire as a JSON number. A count always does.**

| Kind | Wire form | Scale | Example |
| --- | --- | --- | --- |
| `MONEY` | **string** | `04` §1.6 `NUMERIC(14,2)` | `"12450.00"` |
| `QUANTITY` | **string** | `04` §1.6 `NUMERIC(14,3)` | `"24.000"` |
| `RATE` | **string** | two places (`core.fields.to_percent`) | `"1.25"` |
| `COUNT` | **JSON integer**, or `null` when the cell holds no count | — | `3` · `null` |
| `TEXT` | string | — | `"CONFIRMED"` |

**A blank cell is `null`, never `""` and never `0`.** A total row has no rank and no *oldest days*; `/reports/receivables` and `/reports/top-customers` both carry one. `0` would be a measurement — rank zero, aged zero days — and `""` is a string in a column the client parses as an integer. This is the same rule §9.11.2 already applies to an unmeasured `conflict_rate`. A `TEXT` cell keeps its empty string: `"code": ""` is a value, not an absence.

`COUNT` is stated because the opposite error is real: `rank`, `oldest_days`, `documents`, `orders` and the six per-status sync counters are numbers that are **not** money, and `"3"` orders would be over-applying the rule until it lied about the type — the reasoning §9.11.1 item 3 already applied to `awaiting_dispatch`.

**No semantic definition changes.** `conflict_rate` is still `REJECTED ÷ settled` exactly as §9.11.2 defines it; only its encoding is fixed.

**Every report response carries its column kinds.** `columns[].kind` is added alongside the existing `columns[].numeric`, which is retained unchanged: a client holding `"25.00"` cannot otherwise tell a rate from an amount, and `numeric` told it neither. Additive, so no existing consumer breaks.

---

### AD-03 — RFC 9457 `application/problem+json` for every error

**Decision.** All 4xx and 5xx responses use Problem Details, extended with a machine-readable `code` and, for validation failures, a field-level `errors` array.

```json
{
  "type": "https://districore.app/errors/credit-limit-exceeded",
  "title": "Credit limit exceeded",
  "status": 409,
  "detail": "Order total 12450.00 exceeds available credit 3200.00 for customer C-0142.",
  "instance": "/api/v1/orders",
  "code": "CREDIT_LIMIT_EXCEEDED",
  "request_id": "01J8ZQ4K7M",
  "errors": []
}
```

**Why.** A published standard means no invention, no argument, and predictable client handling. The `code` field is what the Flutter client actually branches on — `title` and `detail` are for humans and may be reworded without breaking a client. `request_id` correlates the error to the server log and audit row (§12 and §19 of `00`), which is what turns "the app showed an error" into a two-minute diagnosis.

**Alternatives.** (a) A bespoke `{"error": {...}}` envelope — one more thing to specify and document. (b) DRF's default error shapes — inconsistent between validation errors (a dict) and permission errors (a `detail` string), which pushes the inconsistency onto the client. (c) Always 200 with an error body — makes every HTTP intermediary useless and is a well-known anti-pattern.

**Trade-offs.** DRF needs a custom exception handler. Written once.

**Long-term impact.** Stable, documented error semantics are what make an Edition 3 public API supportable.

**Migration cost if changed later.** *Medium* — every client error path changes.

---

### AD-04 — `snake_case` JSON keys

**Decision.** Request and response keys are `snake_case`, matching the database and the Python layer.

**Why.** The translation has to happen somewhere. Doing it on the server means every serialiser carries a mapping that can be got wrong silently — a mistyped `camelCase` key produces a missing field, not an error. Dart's `json_serializable` maps `snake_case` to `camelCase` fields declaratively, in generated code, checked by the compiler. **Put the translation where the compiler can see it.**

**Alternatives.** (a) `camelCase` — conventional for mobile JSON; moves an unchecked mapping onto the server. (b) Mixed — the worst option, and the one that happens by accident when this is not decided.

**Trade-offs.** Dart developers see `snake_case` in raw payloads. Cosmetic.

**Migration cost if changed later.** *Medium* — every client model regenerates.

---

### AD-05 — Bare resource for single objects; a paginated envelope for collections

**Decision.** `GET /orders/{id}` returns the order object at the top level. `GET /orders` returns:

```json
{ "count": 248, "next": "...?page=3", "previous": "...?page=1", "results": [ … ] }
```

**Why.** Collections need metadata that has nowhere else to live; single resources do not. Wrapping a single resource in `{"data": …}` adds a level of nesting to every access for no information. This is also DRF's default shape, so it is zero custom code — and code not written cannot be got wrong.

**Alternatives.** (a) Envelope everything — consistent, more nesting, more code. (b) JSON:API — comprehensive and far heavier than this product needs (E-11). (c) Bare arrays for lists — no room for pagination metadata, and a known JSON hijacking footgun.

**Trade-offs.** Two shapes to document. Mitigated because the distinction is mechanical: list or not.

**Migration cost if changed later.** *Medium.*

---

### AD-06 — Timestamps ISO-8601 UTC with `Z`; dates plain

**Decision.** `"created_at": "2026-08-04T09:14:22Z"`. Business dates are `"invoice_date": "2026-08-04"` with no time or zone.

**Why.** N-08 requires UTC storage. Sending an offset-bearing local time invites a client to compare it against a naive local value, which is how off-by-5½-hours bugs appear in Indian systems. A business date is a calendar fact — an invoice dated 4 August is dated 4 August in every timezone — and giving it a time implies a precision it does not have.

**Alternatives.** (a) Unix epoch integers — compact, unreadable in logs, and ambiguous about seconds versus milliseconds. (b) Local time with offset — pushes conversion onto every client. (c) Naive strings — the classic source of silent timezone corruption.

**Trade-offs.** Clients must convert to IST for display. That is one utility function and it belongs on the client.

**Migration cost if changed later.** **High** — historical data would need to be reinterpreted, and the information needed to do so was never recorded.

---

### AD-07 — No `DELETE` verb anywhere in Version 1

**Decision.** The API exposes no `DELETE` on any business resource. Deactivation is `PATCH {"is_active": false}`. Cancellation is an explicit action endpoint.

**Why.** `04` §D-03 forbids hard deletes where history exists, and N-04 makes financial documents immutable. If the verb does not exist, it cannot be called by mistake, by a misconfigured client, or by a curious developer with a REST tool. **Removing a capability is stronger than documenting that it must not be used.**

**Alternatives.** (a) `DELETE` mapped to soft delete — dishonest; the verb says one thing and does another, and the next developer will believe the verb. (b) `DELETE` for genuinely disposable resources — there are none in V1.

**Trade-offs.** Slightly unconventional REST. Correct for a financial system.

**Migration cost if changed later.** *Trivial* to add; the point is that it is not added casually.

---

### AD-08 — Actions that are not CRUD get explicit sub-resource endpoints

**Decision.** State transitions are `POST /orders/{id}/confirm`, `/cancel`, `/assign`; `POST /deliveries/{id}/complete`. They are **not** expressed as `PATCH {"status": "CONFIRMED"}`.

**Why.** A status change is not a field edit. Confirming an order allocates nothing in V1 but validates credit, sets assignment and becomes auditable; completing a delivery writes stock movements and moves the order — **one transaction, several tables** (`04` T-16). `PATCH {"status": …}` implies the client may set any status, which invites an invalid transition and pushes the state machine into the client. An action endpoint states the intent, accepts only the arguments that action needs, and lets the server own the machine.

**Alternatives.** (a) `PATCH` with status — smaller surface, leaks the state machine, permits illegal transitions to be attempted. (b) A generic `POST /orders/{id}/transitions` — one endpoint, untyped payload, worse errors.

**Trade-offs.** More endpoints. Each is unambiguous.

**Migration cost if changed later.** *Low.*

---

### AD-09 — Idempotency by `client_uuid` in the request body

**Decision.** Every resource that a device can create carries `client_uuid` in the request body. Re-posting an accepted `client_uuid` returns **`200` with the original resource**, not a duplicate and not an error.

**Why.** `04` puts `client_uuid UNIQUE` on `sales_order`, `delivery`, `payment`, `visit` and `sync_operation`. The API must expose that guarantee, or the database constraint becomes a `500` on retry instead of a correct response. A body field rather than an `Idempotency-Key` header is chosen because the value **is part of the resource** — it is stored, queried and reported on, not merely a transport concern.

**Alternatives.** (a) `Idempotency-Key` header (Stripe's model) — excellent for a payments API where the key is transport-only; here the value is persisted, so a header would mean carrying the same thing twice. (b) Server-side dedupe on a content hash — fragile: a retry with a corrected typo is a different hash and would create a duplicate.

**Trade-offs.** Clients must generate and persist a UUID **before** the first attempt, not on retry. Stated as a client obligation in §12.

**Long-term impact.** Edition 2 field order capture reuses this unchanged (EP-C).

**Migration cost if changed later.** **High** — a window with no duplicate protection on financial rows.

---

### AD-10 — Page-number pagination for lists; a `since` cursor for sync

**Decision.** Lists use `?page=&page_size=` with a default of 25 and a maximum of 100. Sync pull uses `?since=<ISO-8601>` and returns a `server_time` to use as the next `since`.

**Why.** They solve different problems. Admin and app lists are browsed by a human who wants "page 3" and a total count; offset pagination is correct and cheap at V1 volumes. Sync must be **resumable and complete under concurrent writes**, where offset pagination silently skips rows when the underlying set changes mid-pagination — precisely the failure that loses a transaction (BR-014).

**Alternatives.** (a) Offset everywhere — breaks sync correctness. (b) Cursor everywhere — no total count, worse browsing, more client code for no gain on list screens. (c) No pagination — a 10,000-row response on 2G.

**Trade-offs.** Two mechanisms. Justified because they have different correctness requirements.

**Migration cost if changed later.** *Low.*

---

### AD-11 — Retailer scoping is derived from the token, never accepted from the client

**Decision.** Endpoints serving `RETAILER` **do not accept a `customer_id`**. The server resolves it from `app_user.customer_id` on the authenticated token and filters unconditionally.

**Why.** The Flutter binary is public and must be assumed decompiled and modified (DV-4). Any parameter a client can send is a parameter an attacker can change. If the server accepts `customer_id`, then the entire isolation between one retailer and another rests on a check that must be written correctly at every call site. Deriving it from the token means **there is no parameter to tamper with.** This is N-06 and BR-003 made structural rather than procedural.

**Alternatives.** (a) Accept `customer_id` and validate it against the token — works until the one endpoint where the check is forgotten. (b) Separate `/retailer/*` endpoints — duplicates every serialiser and every rule.

**Trade-offs.** The same path returns different data by role. Documented explicitly per endpoint in §9.

**Long-term impact.** Under Edition 3 tenancy the same principle extends to schema resolution.

**Migration cost if changed later.** *Medium*, plus whatever the breach cost.

---

## 3. Conventions

| Aspect | Convention | Example |
| --- | --- | --- |
| Base path | `/api/v1` | |
| Resource naming | Plural, kebab-case for multi-word | `/credit-notes`, `/reason-codes` |
| Identifiers in paths | Integer `id` | `/orders/4471` |
| JSON keys | `snake_case` (AD-04) | `total_amount` |
| Money & quantity | **Decimal string** (AD-02) | `"12450.00"` |
| Percentage | Decimal string | `"18.00"` |
| Timestamp | ISO-8601 UTC, `Z` (AD-06) | `"2026-08-04T09:14:22Z"` |
| Date | `YYYY-MM-DD` | `"2026-08-04"` |
| Booleans | JSON `true` / `false` | |
| Null | Explicit `null`; **never omitted**, never `""` | |
| Enumerations | `SCREAMING_SNAKE_CASE` strings, matching the DB `CHECK` | `"DISPATCHED"` |
| Coordinates | Decimal string | `"25.594095"` |
| Empty list | `[]`, never `null` | |
| Content type | `application/json; charset=utf-8`; `multipart/form-data` for media only |
| Compression | `gzip` on responses over 1 KB | |
| Correlation | `X-Request-Id` echoed on every response | |

**Nulls are always present.** A field that is absent and a field that is null are indistinguishable to a careless client, and Dart's null-safety makes the difference matter. Every documented field appears in every response.

---

## 4. Status Codes

| Code | Used for | Body |
| --- | --- | --- |
| `200 OK` | Successful `GET`, `PATCH`, action; **idempotent replay** (AD-09) | Resource |
| `201 Created` | New resource created | Resource + `Location` |
| `202 Accepted` | Sync batch received, partially processed | Per-operation results |
| `204 No Content` | Logout | Empty |
| `400 Bad Request` | Malformed JSON, wrong type, unparseable | Problem |
| `401 Unauthorized` | Missing, invalid or expired token | Problem, `code: TOKEN_EXPIRED` |
| `403 Forbidden` | Authenticated but not permitted | Problem |
| `404 Not Found` | Absent, **or present but outside the caller's scope** | Problem |
| `409 Conflict` | Business rule violated — credit limit, invalid transition, insufficient stock | Problem with a specific `code` |
| `410 Gone` | API version retired | Problem |
| `413 Payload Too Large` | Upload over limit | Problem |
| `422 Unprocessable Entity` | Well-formed, failed **field** validation | Problem + `errors[]` |
| `429 Too Many Requests` | Rate limited | Problem + `Retry-After` |
| `500 Internal Server Error` | Unhandled | Problem, **no stack trace** (NFR-SEC-010) |
| `503 Service Unavailable` | Database unreachable, maintenance | Problem + `Retry-After` |

### 4.1 Two distinctions that matter

**`400` vs `422`.** `400` means the server could not understand the request — broken JSON, a string where a number was required. `422` means it understood perfectly and the values are invalid — a negative quantity, a missing customer. The client reacts differently: `400` is a bug to report, `422` is a form to correct.

**`403` vs `404` for out-of-scope resources.** A retailer requesting another retailer's invoice receives **`404`, not `403`.** `403` confirms the resource exists, which is an information disclosure — an attacker enumerating IDs learns which are real. `404` reveals nothing. **Scope violations are indistinguishable from non-existence, deliberately.**

---

## 5. Error Catalogue

Every `code` the API can return. The Flutter client branches on `code`; `title` and `detail` may be reworded without breaking it.

### 5.1 Authentication

| Code | Status | Meaning | Client action |
| --- | :-: | --- | --- |
| `INVALID_CREDENTIALS` | 401 | Wrong phone or password | Show a generic failure. **Never reveal which** |
| `TOKEN_EXPIRED` | 401 | Access token expired | Refresh, retry once |
| `TOKEN_INVALID` | 401 | Malformed or revoked | Log out, re-authenticate |
| `REFRESH_EXPIRED` | 401 | Refresh token expired | Full re-login |
| `ACCOUNT_INACTIVE` | 403 | User deactivated | Log out, show a message |
| `OTP_INVALID` | 422 | Wrong code | Allow retry, show attempts left |
| `OTP_EXPIRED` | 422 | Past `expires_at` | Offer resend |
| `OTP_ATTEMPTS_EXCEEDED` | 429 | Too many wrong codes | Lock the flow, honour `Retry-After` |
| `OTP_RATE_LIMITED` | 429 | Too many requests | Honour `Retry-After` |

### 5.2 Authorisation and validation

| Code | Status | Meaning |
| --- | :-: | --- |
| `PERMISSION_DENIED` | 403 | Role lacks the capability |
| `VALIDATION_FAILED` | 422 | One or more fields invalid; see `errors[]` |
| `RESOURCE_NOT_FOUND` | 404 | Absent or out of scope (§4.1) |

### 5.3 Business rules — the ones the client must handle by name

| Code | Status | Meaning | Client action |
| --- | :-: | --- | --- |
| `CREDIT_LIMIT_EXCEEDED` | 409 | Order exceeds available credit | If `WARN` mode, offer owner override; if `BLOCK`, refuse |
| `CUSTOMER_INACTIVE` | 409 | Customer deactivated | Refuse; refresh master data |
| `PRODUCT_INACTIVE` | 409 | Product deactivated | Remove the line; refresh master data |
| `PRICE_UNRESOLVED` | 409 | No price for the product | Refuse the line (FR-PRC-004) |
| `INVALID_STATE_TRANSITION` | 409 | e.g. cancel after dispatch | Refresh the order; show the real state |
| `ORDER_ALREADY_INVOICED` | 409 | Invoice exists | Refresh |
| `INSUFFICIENT_STOCK` | 409 | Dispatch exceeds on-hand | Show shortfall; owner decides |
| `INVOICE_IMMUTABLE` | 409 | Attempt to modify an issued invoice | **Never send this request.** A client bug |
| `CREDIT_EXCEEDS_INVOICE` | 409 | Credit note over invoice value | Cap and retry |
| `DUPLICATE_CLIENT_UUID` | 200 | **Not an error** — replay (AD-09) | Treat as success |
| `SYNC_DEPENDENCY_UNMET` | 202 | Operation deferred, awaiting a prior one | Keep in outbox, retry next sync |
| `MEDIA_TOO_LARGE` | 413 | Over the size limit | Re-compress and retry |
| `MEDIA_TYPE_UNSUPPORTED` | 422 | Not an accepted image type | Refuse locally |

### 5.4 Validation error shape

```json
{
  "type": "https://districore.app/errors/validation-failed",
  "title": "Validation failed",
  "status": 422,
  "detail": "One or more fields are invalid.",
  "instance": "/api/v1/orders",
  "code": "VALIDATION_FAILED",
  "request_id": "01J8ZQ4K7M",
  "errors": [
    { "field": "lines[0].quantity", "code": "MIN_VALUE",  "message": "Quantity must be greater than zero." },
    { "field": "customer_id",       "code": "NOT_FOUND",  "message": "Customer does not exist." }
  ]
}
```

`field` uses dotted and indexed paths so the client can attach a message to the exact input. `code` is stable and translatable; `message` is English and may change.

---

## 6. Idempotency Contract

**The single most important behavioural guarantee in this API.** `01` §10.3 sets zero duplicate transactions as non-negotiable.

| Rule | Detail |
| --- | --- |
| I-1 | The **client** generates a UUIDv4 at the moment the user acts, and persists it in the outbox **before** the first network attempt |
| I-2 | The same `client_uuid` is sent on every retry, unchanged |
| I-3 | First acceptance → `201 Created` |
| I-4 | Any subsequent request with the same `client_uuid` → **`200 OK` with the original resource**. Never `409`, never a duplicate |
| I-5 | Idempotency is scoped per resource type; the same UUID on a different endpoint is a client bug and is rejected `422` |
| I-6 | The guarantee is enforced by a database unique constraint (`04` T-26 and per-table), not by an application check — a concurrent double-submit would defeat an application check |

**Applies to** `POST /orders` · `POST /payments` · `POST /visits` · `POST /customers` · `POST /deliveries/{id}/complete` · every operation in `POST /sync/push`.

> **Why replay returns `200` and not `409`.** A retry after a timeout is the *correct* client behaviour on a bad connection — the request may well have succeeded before the connection dropped. Answering `409` would train clients to treat a successful write as a failure, which is exactly how a salesman ends up recording a payment twice.

---

## 7. Authentication and Session

### 7.1 Mobile — OTP then JWT

```
  App                                        API
   │  POST /auth/otp/request  {phone}         │
   ├─────────────────────────────────────────►│  create otp_request (hashed)
   │                                          │  send SMS
   │◄─────────────────────────────────────────┤  202 {expires_in_seconds, attempts_allowed}
   │                                          │
   │  POST /auth/otp/verify  {phone, code,    │
   │                          device_id}      │
   ├─────────────────────────────────────────►│  verify hash, consume, load roles
   │◄─────────────────────────────────────────┤  200 {access, refresh, user}
   │  store in secure storage                 │
   │                                          │
   │  Authorization: Bearer <access>          │
   ├─────────────────────────────────────────►│  authorise every request (N-06)
   │                                          │
   │  401 TOKEN_EXPIRED → POST /auth/refresh  │
   ├─────────────────────────────────────────►│  rotate refresh, issue access
   │◄─────────────────────────────────────────┤  200 {access, refresh}
```

| Token | Lifetime | Storage | Notes |
| --- | --- | --- | --- |
| Access | 30 minutes | Memory + secure storage | Sent as `Authorization: Bearer` |
| Refresh | 30 days | Secure storage only | **Rotated on every use**; the old value is invalidated |

**Refresh rotation with reuse detection.** Each refresh issues a new refresh token and invalidates the previous one. Presenting an already-used refresh token means it was captured — the server invalidates the whole family and forces re-authentication. This costs one column and closes the main practical attack on long-lived mobile refresh tokens.

**Claims.** `sub` (user id) · `roles` (array of codes) · `customer_id` (retailers only) · `device_id` · `exp` · `iat` · `jti`.

> **Claims are a cache, not an authority.** The server re-reads roles from the database on any request that changes money or stock. A role revoked five minutes ago must not remain effective for the 30-minute life of a token.

### 7.2 Offline authentication

Per FR-IAM-016 and `03` §5.2: the app remains usable offline for `business_profile.otp_expiry_minutes`-independent window — default **7 days** (OI-5) — bounded by refresh-token validity. On the first sync after that window, re-authentication is forced. **Offline authentication grants local access only; it never authorises a server write.**

### 7.3 Web admin

Django session cookie, `HttpOnly` `Secure` `SameSite=Lax`, CSRF token on every state-changing form. The admin does not use JWT and does not call this API (§1.1).

---

## 8. Authorisation Matrix

Enforced in `services.py` on every request (N-01, N-06). ● full · ◐ own records only · ○ read-only · — none

| Capability | OWNER | SALESMAN | DELIVERY | RETAILER |
| --- | :-: | :-: | :-: | :-: |
| Products — read | ● | ○ | ○ | ○ |
| Products — write | ● | — | — | — |
| Customers — read | ● | ○ own zones | ○ own zones | ◐ self |
| Customers — create | ● | ● | — | — |
| Customers — credit limit | ● | — | — | — |
| Zones / reason codes | ● | ○ | ○ | — |
| Offers — read | ● | ○ | ○ | ○ |
| Offers — write | ● | — | — | — |
| Orders — read | ● | ◐ assigned | ◐ assigned | ◐ own |
| Orders — create | ● | — ¹ | — | ◐ own |
| Orders — confirm / assign | ● | — | — | — |
| Orders — cancel | ● | — | — | ◐ own, before dispatch |
| Deliveries — read | ● | ◐ assigned | ◐ assigned | ○ own order |
| Deliveries — complete | ● | ◐ assigned | ◐ assigned | — |
| Stock — read | ● | ○ | ○ | — |
| Stock — adjust | ● | — | — | — |
| Invoices — read | ● | ○ own customers | ○ own deliveries | ◐ own |
| Invoices — issue | ● | — | — | — |
| Credit notes | ● | — | — | — |
| Payments — read | ● | ◐ collected | ◐ collected | ◐ own |
| Payments — create | ● | ● | ● | — |
| Ledger / balance | ● | ○ own zones | ○ own zones | ◐ own |
| Visits — create | ● | ● | ● | — |
| Visits — read | ● | ◐ own | ◐ own | — |
| Sync push / pull | — | ● | ● | ● |
| Reports | ● | ◐ own | — | — |
| Media upload | ● | ● | ● | ◐ |

¹ Salesmen do not create orders in Version 1 (DV-1). The capability arrives in Edition 2 (EP-C) — the endpoint exists, the permission does not.

> **Every ◐ is a server-side filter, never a client-side one.** Verified by the adversarial authorisation test (`00` §6.4) which issues the full role × capability grid directly against the API with all clients bypassed.

---

## 9. Endpoint Catalogue

**60 endpoints.** Idem = carries `client_uuid` (AD-09). Roles: O = OWNER, S = SALESMAN, D = DELIVERY, R = RETAILER.

### 9.1 Authentication — `/auth`

| Method | Path | Roles | Purpose | Idem |
| --- | --- | --- | --- | :-: |
| POST | `/auth/otp/request` | public | Send an OTP to a phone number | — |
| POST | `/auth/otp/verify` | public | Exchange an OTP for tokens | — |
| POST | `/auth/login` | public | Password login (staff) | — |
| POST | `/auth/refresh` | public | Rotate refresh, issue access | — |
| POST | `/auth/logout` | any | Invalidate the refresh family | — |
| GET | `/auth/me` | any | Current user, roles, permissions | — |

### 9.2 Master data — read-mostly

| Method | Path | Roles | Purpose | Idem |
| --- | --- | --- | --- | :-: |
| GET | `/products` | all | List; `?search=&is_active=&updated_since=` | — |
| GET | `/products/{id}` | all | Single product | — |
| POST | `/products` | OWNER | Create | — |
| PATCH | `/products/{id}` | OWNER | Update; deactivate via `is_active` | — |
| GET | `/customers` | O,S,D | List; `?zone_id=&search=&is_active=` | — |
| GET | `/customers/{id}` | O,S,D,R | Single; **R sees only their own** (AD-11) | — |
| POST | `/customers` | OWNER, SALESMAN | Create — field capture | ✓ |
| PATCH | `/customers/{id}` | OWNER, SALESMAN | Update; credit limit **OWNER only** | — |
| GET | `/zones` | O,S,D | List | — |
| GET | `/reason-codes` | O,S,D | List; `?direction=` | — |
| GET | `/offers` | all | Active, in-date offers | — |
| POST | `/offers` | OWNER | Create | — |
| PATCH | `/offers/{id}` | OWNER | Update | — |

### 9.3 Orders

| Method | Path | Roles | Purpose | Idem |
| --- | --- | --- | --- | :-: |
| GET | `/orders` | O,S,D,R | `?status=&assigned_to=me&customer_id=&date_from=&date_to=` | — |
| GET | `/orders/{id}` | O,S,D,R | With lines, delivery, invoice reference | — |
| POST | `/orders` | OWNER, RETAILER | Place an order | ✓ |
| PATCH | `/orders/{id}` | OWNER, RETAILER | Edit lines — **before `DISPATCHED` only** | — |
| POST | `/orders/{id}/confirm` | OWNER | `PLACED → CONFIRMED` | — |
| POST | `/orders/{id}/assign` | OWNER | Assign a salesman; creates the delivery | — |
| POST | `/orders/{id}/cancel` | OWNER, RETAILER | Requires a reason | — |

### 9.4 Delivery

| Method | Path | Roles | Purpose | Idem |
| --- | --- | --- | --- | :-: |
| GET | `/deliveries` | O,S,D | `?status=&assigned_to=me&date=` — the app's home screen | — |
| GET | `/deliveries/{id}` | O,S,D | Single | — |
| POST | `/deliveries/{id}/complete` | O,S,D | Deliver: POD, GPS, **writes stock issue** | ✓ |
| POST | `/deliveries/{id}/fail` | O,S,D | Failed attempt with reason | ✓ |

### 9.5 Billing

| Method | Path | Roles | Purpose | Idem |
| --- | --- | --- | --- | :-: |
| GET | `/invoices` | O,S,D,R | `?customer_id=&date_from=&unpaid_only=` | — |
| GET | `/invoices/{id}` | O,S,D,R | Full invoice with lines | — |
| GET | `/invoices/{id}/pdf` | O,S,D,R | PDF stream | — |
| POST | `/invoices` | OWNER | Issue from a dispatched order | ✓ |
| POST | `/invoices/{id}/cancel` | OWNER | Before sharing only | — |
| GET | `/credit-notes` | OWNER | List | — |
| GET | `/credit-notes/{id}` | OWNER | Single | — |
| POST | `/credit-notes` | OWNER | Issue against an invoice | ✓ |

### 9.6 Payments and ledger

| Method | Path | Roles | Purpose | Idem |
| --- | --- | --- | --- | :-: |
| GET | `/payments` | O,S,D,R | `?customer_id=&method=&date_from=` | — |
| POST | `/payments` | O,S,D | Record a collection | ✓ |
| POST | `/payments/{id}/reverse` | OWNER | Compensating entry, requires a reason | — |
| GET | `/customers/{id}/ledger` | O,S,D,R | Paginated ledger entries | — |
| GET | `/customers/{id}/balance` | O,S,D,R | Balance, credit limit, available credit | — |
| GET | `/customers/{id}/statement` | O,S,D,R | `?date_from=&date_to=` — opening, entries, closing | — |

### 9.7 Stock

| Method | Path | Roles | Purpose | Idem |
| --- | --- | --- | --- | :-: |
| GET | `/stock` | O,S,D | Derived on-hand per product | — |
| GET | `/stock/movements` | OWNER | `?product_id=&date_from=&reason_code_id=` | — |
| POST | `/stock/movements` | OWNER | Stock-in or reason-coded adjustment | ✓ |

### 9.8 Field activity

| Method | Path | Roles | Purpose | Idem |
| --- | --- | --- | --- | :-: |
| POST | `/visits` | O,S,D | Check in with GPS, photo, notes | ✓ |
| GET | `/visits` | O,S,D | `?user_id=&customer_id=&date_from=` | — |

### 9.9 Media

| Method | Path | Roles | Purpose | Idem |
| --- | --- | --- | --- | :-: |
| POST | `/media` | all | `multipart/form-data`; returns `media_id` | ✓ |
| GET | `/media/{id}` | scoped | Authorised stream — **never a public path** | — |

### 9.10 Sync

| Method | Path | Roles | Purpose | Idem |
| --- | --- | --- | --- | :-: |
| GET | `/sync/pull` | S,D,R | Changed master data and assignments since a timestamp | — |
| POST | `/sync/push` | S,D,R | Batch of queued device operations | ✓ per op |
| GET | `/sync/status` | S,D,R | Server view of this device's pending and rejected operations | — |

### 9.11 Reports — owner

> **Amended 2026-08-08** by `M7_Design_Review.md` v1.2.0 §2 (C-6, C-7) and §4.2 (D-2). Two
> endpoints added, marked below. **Purely additive** — no existing path, parameter,
> response field or role changed, so every client written against the previous table
> continues to work.
>
> `/reports/stock` previously read *"On-hand valuation"*. **Corrected to quantity (C-7):
> Edition 1 has no cost basis** — `Product.selling_price` is the only money field on a
> product, and a cost price arrives with M-11 Purchasing in Edition 2. This corrects a
> description the schema never supported; no field is removed, because none was ever built.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/reports/sales` | `?date_from=&date_to=&group_by=day\|product\|customer` |
| GET | `/reports/stock` | On-hand **quantity** by product. On hand only — allocation is Edition 2; **no valuation** — no cost basis (C-7) |
| GET | `/reports/stock-variance` | **Added.** `?date_from=&date_to=&reason_code=` — reason-coded movements **in units**, the **physical** trace of a return |
| GET | `/reports/returns` | **Added.** `?date_from=&date_to=&group_by=reason\|customer` — credit notes by reason, the **financial** trace |
| GET | `/reports/receivables` | Balance, ageing bucket and oldest unpaid per customer |
| GET | `/reports/top-customers` | `?limit=10&date_from=` — the Top 10 ranking |
| GET | `/reports/order-status` | Pipeline counts by status |
| GET | `/reports/sync-health` | **Added.** `?date_from=&date_to=` — one row per device: settled operations, the `REJECTED` count, and the FR-SYN-015 conflict proportion. §9.11.2 |

All **reports** accept `?format=csv` (FR-RPT-012). The dashboard below does not, and is not a report.

#### 9.11.1 Dashboard — the four D-4 numbers

> **Added 2026-08-10** by `M8_Design_Review.md` v1.1.0 §3.4.1 (M8 Phase 2, task 0). **Purely
> additive.** No existing path, parameter, response field or role changed.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/reports/dashboard` | The four D-4 scalars: sales today · collected today · total outstanding · orders awaiting dispatch |

```json
{
  "as_of": "2026-08-10",
  "metrics": [
    {"key": "sales_today",       "label": "Sales today",              "value": "11800.00", "caption": "Taxable value, net of credit notes",     "is_live": true,  "is_money": true},
    {"key": "collected_today",   "label": "Collected today",          "value": "500.00",   "caption": "Payments recorded today, excluding reversals", "is_live": true,  "is_money": true},
    {"key": "total_outstanding", "label": "Total outstanding",        "value": "11300.00", "caption": "Derived from the ledger, oldest first",  "is_live": false, "is_money": true},
    {"key": "awaiting_dispatch", "label": "Orders awaiting dispatch", "value": 3,          "caption": "Confirmed, not yet gone",               "is_live": false, "is_money": false}
  ]
}
```

**Three deliberate departures from the report contract**, each the reason this sits in its own
subsection rather than in the table above:

| # | Departure | Why |
| --: | --- | --- |
| 1 | **No `?format=csv`.** Returns `404`, from renderer negotiation rather than from a branch | M7 §8.2 — two of the four numbers describe *today* and are not reproducible. A figure that cannot be reproduced must not acquire the authority of a document |
| 2 | **No period parameter.** It resolves "today" server-side — the one endpoint under `/reports/` that does | A period would make the live numbers reproducible for arbitrary past dates, which is exactly the authority (1) withholds. `/reports/sales` answers that question over any period, with a CSV |
| 3 | **`awaiting_dispatch` is a JSON number, not a string** | AD-02 governs money and quantity. A count is neither; `"3.00"` orders would be over-applying the rule until it lies about the type. `is_money` says which encoding applies, per metric |

`is_live` marks the two figures that are not reproducible, so a client can label them rather
than cache them as a record (C-8's reasoning, applied to a figure rather than to a snapshot).

**Roles:** the same `_internal` predicate as the seven reports — `OWNER`, `SALESMAN`,
`DELIVERY`, each scoped. A `RETAILER` receives `403`, not an empty dashboard.

**`stock-variance` and `returns` are separate endpoints, not one endpoint with a filter.** A
credit note writes no stock movement (ADR-0009), so the two report different facts with
different row shapes and their totals legitimately differ. Merging them would imply a join
the domain does not have.

Every report requires an explicit period or `as_of`; none resolves "now" server-side, so a
report over a closed period returns the same answer on any later day. **§9.11.1's dashboard is
the sole exception, and is not a report** — it resolves today deliberately, offers no export,
and says so per metric with `is_live`.

> ~~**The owner dashboard is not an endpoint.** It is four scalars rendered by webadmin (`M7`
> §4.4), two of which describe *today* and are therefore not reproducible. It offers no CSV.~~
>
> **Superseded 2026-08-10 by §9.11.1.** The first sentence no longer holds; the last one
> still does. M8 Owner Companion Mode needs the four numbers on a phone, and this paragraph's
> own reasoning — that a non-reproducible figure must not acquire the authority of a
> **document** — is an argument about *export*, not about *access*. The export stays refused.
> Kept struck rather than deleted: the reasoning was sound and only its scope was wrong.

#### 9.11.2 Sync health — FR-RPT-009 / FR-SYN-015

> **Added 2026-09-06** by `M9_Design_Review.md` §D-M9-10 (FR-RPT-009, delivered at M9 per `02`
> ruling **A-5**). **Purely additive.** No existing path, parameter, response field or role
> changes, and **no new storage**: every column is derived from `sync_operation` (`04` T-26),
> which M9.1 already writes.

**Audience and authorisation.** `S1`, through the same `_internal` rule the other seven reports
use — **`OWNER`, `SALESMAN`, `DELIVERY`; `RETAILER` is refused.** That admits field roles to a
fleet-wide operational view, which is the **existing** reporting authorisation model rather than
a decision taken here; narrowing it is a corpus question for all eight reports, not for this one.
**`SALESMGR` is not an implemented role** — `04` T-02 seeds four, and the code appears nowhere in
`04` or `05` — so this endpoint does not serve FR-SYN-009, which D-M9-7 moved to `Rel = v2.0`.

**Parameters.** `?date_from=` and `?date_to=` (inclusive dates, the shape every period report
uses). Both optional; omitted means all history. `?format=csv` per FR-RPT-012.

**Scope of a row.** One row per `device_id` seen in the period, ordered by device.

| Column | Meaning |
| --- | --- |
| `device_id` | `sync_operation.device_id` — the device as attributed by PU-4, never from a request |
| `last_sync_at` | `MAX(received_at)` in the period |
| `accepted` | `status = 'ACCEPTED'` |
| `duplicate` | `status = 'DUPLICATE'` — a replay, which BR-012 and `05` C-4 define as **success** |
| `deferred` | `status = 'DEFERRED'` — held and auto-retried |
| `rejected` | `status = 'REJECTED'` — the only Edition-1 outcome needing a human |
| `in_flight` | `status = 'RECEIVED'` — recorded before the business operation completed. **Excluded from the denominator**; a persistent value here is an orphan |
| `settled` | `accepted + duplicate + deferred + rejected` — the denominator |
| `conflict_rate` | `rejected / settled`, as a percentage. **Empty when `settled = 0`** |

**The conflict proportion.** `01` §10.3's metric is *"sync conflicts requiring manual
intervention ≤ 1% of synchronised transactions"*. Edition 1's `02` §5.3 taxonomy reduces to
`SC-DUPLICATE` and `SC-SEQUENCE`, **both marked automatic**, so neither is in the numerator;
`05` §11.4 confirms *"only the two automatic classes exist in Version 1"*. `REJECTED` is what
remains: never auto-retried, carrying a mandatory `error_code` (`04` T-26), and which §11.2
obliges the client to flag to a user. This is S-5's reasoning applied to FR-SYN-015 and is
**proposed as `02` amendment S-7**; until S-7 is ratified the report states its definition in
its own `definition` field, which the CSV carries (M7-1).

**Empty denominator.** `conflict_rate` is **blank, never `0%`**. A fleet that has synchronised
nothing has not demonstrated integrity, and printing zero would assert a measurement never made.

**Empty fleet.** No `sync_operation` rows in the period yields a report with **zero rows** and no
total line — a valid, empty report, not an error.

### 9.12 System

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/healthz` | none | Unversioned. Database, disk, last backup (§13 of `00`) |

---

## 10. Key Payload Contracts

The endpoints where getting the shape wrong is expensive. Everything else follows the same conventions.

### 10.1 `POST /auth/otp/verify`

```json
// request
{ "phone": "+919876543210", "code": "482913", "device_id": "a3f9…" }

// 200
{
  "access_token": "eyJ…",
  "refresh_token": "eyJ…",
  "expires_in": 1800,
  "user": {
    "id": 12,
    "full_name": "Ramesh Kumar",
    "phone": "+919876543210",
    "language": "hi",
    "roles": ["SALESMAN", "DELIVERY"],
    "customer_id": null
  }
}
```

`roles` is an **array** — one person may be both salesman and delivery (`04` T-03). The client must not assume a single role.

### 10.2 `POST /orders`

```json
// request
{
  "client_uuid": "9f1c…",
  "customer_id": 142,                    // omitted by RETAILER — derived from token (AD-11)
  "expected_delivery_date": "2026-08-05",
  "notes": "Deliver before noon",
  "lines": [
    { "product_id": 88, "quantity": "24.000", "pack_quantity": "2.000", "discount_amount": "0.00" },
    { "product_id": 91, "quantity": "6.000",  "pack_quantity": null,    "discount_amount": "15.00" }
  ]
}
```

```json
// 201
{
  "id": 4471,
  "order_number": "SO-00004471",
  "client_uuid": "9f1c…",
  "customer": { "id": 142, "code": "C-0142", "shop_name": "Sharma Kirana" },
  "status": "PLACED",
  "source": "PORTAL",
  "order_date": "2026-08-04",
  "expected_delivery_date": "2026-08-05",
  "assigned_user": null,
  "subtotal_amount": "1200.00",
  "discount_amount": "15.00",
  "tax_amount": "213.30",
  "total_amount": "1398.30",
  "credit_warning": {
    "shown": true,
    "credit_limit_amount": "10000.00",
    "outstanding_amount": "9200.00",
    "available_amount": "800.00",
    "mode": "WARN"
  },
  "lines": [ /* … */ ],
  "created_at": "2026-08-04T09:14:22Z"
}
```

**The client never computes price or tax.** It sends product and quantity; the server resolves price, discount bound and tax and returns the authoritative figures (BR-001, BR-011). A client that displays a locally computed total will eventually disagree with the invoice.

**`credit_warning` is returned on a successful `201` when the limit is breached in `WARN` mode.** The order is accepted and the app shows the warning. In `BLOCK` mode the same condition returns `409 CREDIT_LIMIT_EXCEEDED` and no order is created (DV-9).

### 10.3 `POST /deliveries/{id}/complete`

```json
// request
{
  "client_uuid": "b72e…",
  "delivered_at": "2026-08-05T06:41:10Z",     // DEVICE time — may be hours before receipt
  "recipient_name": "Sharma ji",
  "photo_media_id": 9912,
  "latitude": "25.594095",
  "longitude": "85.137566",
  "accuracy_metres": "8.50",
  "device_id": "a3f9…"
}
```

```json
// 200
{
  "id": 3312,
  "sales_order_id": 4471,
  "status": "DELIVERED",
  "delivered_at": "2026-08-05T06:41:10Z",
  "synced_at": "2026-08-05T11:20:03Z",
  "order_status": "DELIVERED",
  "stock_movements_created": 2
}
```

**One transaction:** delivery status, order status and stock issue movements commit together or not at all (NFR-INT-001, `04` T-16). `stock_movements_created` is returned so the client can surface a meaningful confirmation rather than a bare success.

### 10.4 `POST /payments`

```json
// request
{
  "client_uuid": "4d8a…",
  "customer_id": 142,
  "amount": "5000.00",
  "method": "UPI",
  "reference_number": "UPI/2026/8899",
  "payment_date": "2026-08-05",
  "device_id": "a3f9…"
}
```

```json
// 201
{
  "id": 812,
  "payment_number": "PAY-00000812",
  "client_uuid": "4d8a…",
  "customer": { "id": 142, "shop_name": "Sharma Kirana" },
  "amount": "5000.00",
  "method": "UPI",
  "payment_date": "2026-08-05",
  "balance_after_amount": "4200.00",
  "created_at": "2026-08-05T11:20:05Z"
}
```

`balance_after_amount` is returned because the salesman is standing in front of the retailer and the next question is always *"toh ab kitna baaki?"* — one field that removes a follow-up round trip on a connection that may not survive one.

### 10.5 `GET /customers/{id}/balance`

```json
{
  "customer_id": 142,
  "credit_limit_amount": "10000.00",
  "outstanding_amount": "4200.00",
  "available_amount": "5800.00",
  "oldest_unpaid_invoice_date": "2026-06-18",
  "unpaid_invoice_count": 3,
  "as_of": "2026-08-05T11:20:05Z"
}
```

Every figure is derived from `customer_ledger_entry` at request time (N-03). `as_of` exists because an offline client will cache this and must be able to show how stale it is (BR-010 applied to money).

### 10.6 `POST /invoices`

```json
// request
{ "client_uuid": "7c3f…", "sales_order_id": 4471, "invoice_date": "2026-08-05" }
```

The request carries almost nothing. **Everything on the invoice is derived server-side and snapshotted** — seller identity from `business_profile`, buyer from `customer`, lines from the order, tax from each product's rate, number from `number_series` under a row lock (`04` T-06, T-17). A client that could supply amounts could supply wrong ones.

### 10.7 `POST /media`

`multipart/form-data`: `file`, `purpose`, `client_uuid`.

| Rule | Value |
| --- | --- |
| Max size | 5 MB request; images re-encoded to ≤ 200 KB server-side |
| Accepted | `image/jpeg`, `image/png`, `image/webp` |
| Validation | Content sniffed, **not** trusted from `Content-Type` (NFR-SEC-006) |
| Response | `201 { "id": 9912, "purpose": "DELIVERY_PHOTO", "size_bytes": 184320, "url": "/api/v1/media/9912" }` |
| Retrieval | Authorised view only. **Never a directly reachable filesystem path** |

**Media uploads use a separate queue from transactional operations** (FR-FUL-014). A 200 KB photo on 2G must never block a delivery confirmation. The client uploads media first, obtains `media_id`, then submits the transaction referencing it — and if the upload fails, the transaction still goes through with `photo_media_id: null`.

---

## 11. The Synchronisation Contract

This is the part of the API that carries the two non-negotiable metrics of `01` §10.3: **zero transactions lost, zero duplicates.** Per ADR-013, Version 1 sync is an outbox, not a reconciliation protocol — devices write nothing that contends for a shared resource, so only two conflict classes exist and both resolve deterministically.

### 11.1 Pull

```
GET /api/v1/sync/pull?since=2026-08-05T04:00:00Z
```

```json
{
  "server_time": "2026-08-05T11:20:05Z",
  "since": "2026-08-05T04:00:00Z",
  "has_more": false,
  "config": {
    "max_manual_discount_percent": "10.00",
    "credit_limit_mode": "WARN",
    "business_profile": { "legal_name": "…", "gstin": "…" }
  },
  "products":   { "updated": [ … ], "deactivated_ids": [77, 81] },
  "customers":  { "updated": [ … ], "deactivated_ids": [] },
  "zones":      { "updated": [ … ], "deactivated_ids": [] },
  "reason_codes": { "updated": [ … ], "deactivated_ids": [] },
  "offers":     { "updated": [ … ], "deactivated_ids": [] },
  "orders":     { "updated": [ … ] },
  "deliveries": { "updated": [ … ] }
}
```

| Rule | Detail |
| --- | --- |
| P-1 | `since=null` or absent → full bootstrap of everything the user may hold |
| P-2 | The client stores `server_time` and sends it as the next `since`. **It never uses its own clock** — device clocks drift, and a fast clock silently skips records |
| P-3 | Scoped by role and assignment: a salesman receives customers in their zones and orders assigned to them (FR-SYN-012, NFR-SEC minimisation) |
| P-4 | `deactivated_ids` is sent separately because a deactivated row may no longer appear in `updated` under scoping, and the client must remove it rather than keep a stale copy |
| P-5 | `has_more: true` means the payload was capped; the client pulls again with the **same** `since` **and the returned `next_page_token`** until it is false, then advances the cursor (amended — D-M9.4-8) |
| P-7 | `page_token` is an **opaque** continuation position *within one pull*. It is **never** persisted as the device's sync cursor; `server_time` is (D-M9.4-8) |
| P-6 | Pull is read-only, safe to repeat, and never mutates server state |

**Why `server_time` rather than the client's clock.** A device whose clock is five minutes fast would send a `since` in the future and permanently skip every record written in that window. Those records are not resent, and the loss is silent. Returning the server's own time removes the client's clock from the correctness path entirely.

> **Implementation rulings, 2026-08-16 (D-M9.4-1 … D-M9.4-3).** **No field is added, removed
> or renamed, and the envelope above is unchanged.** These record which parts of it M9.4
> builds and which remain unbuilt, so that a reader does not mistake an unimplemented
> collection for an absent contract.
>
> **D-M9.4-1 — the stock snapshot is a CONTRACT GAP, and M9.4 does not close it.**
> FR-SYN-007 requires sync to deliver *"customers on assigned routes, products, prices,
> schemes and **stock snapshot**"*. **This envelope has no stock collection**, `04` has no
> stock table, and the architecture is emphatic that none may exist: `04` N-03/E-01 —
> *"**no `quantity_on_hand` … exists anywhere**"*; ADR-008 — *"stock derived from movements,
> no cache"*; M2-3, signed — *"there never will be"*. `M8_Design_Review` §2 adds that **no
> stock decision is computed on the device**.
>
> Nothing here is therefore merely missing: three frozen documents and one requirement do not
> share a reading, and a `stock_levels` field invented to bridge them would be a new contract
> written by an implementer. **Deferred to a formal amendment.** M9.4 ships no stock.
>
> **D-M9.4-2 — M9.4 implements `customers` and `deliveries` only.** These are the two
> collections with verified shipped consumers: T6's customer round and T5's delivery
> workflow. `products`, `offers`, `zones`, `reason_codes` and `orders` are **not implemented
> in M9.4 and are not thereby declared out of V1** — FR-SYN-007 names several of them and
> their consumer mapping is a later ruling. A response from an M9.4 server simply omits them.
>
> **`schemes` resolves to `offer`**, confirmed against `04` T-24: *"`02A` §13 splits this:
> **V1 shows an owner-posted offer; automatic scheme calculation is Edition 2.** This table
> is the V1 half."* Recorded because the mapping was not obvious; it does not put `offer`
> into M9.4.
>
> **D-M9.4-3 — `deactivated_ids` is the only removal mechanism, and absence is not deletion.**
> A cached record **must not** be deleted because it did not appear in a pull. Under P-5 a
> delta pull returns only what changed since `since`, so "absent" describes almost every
> record the device holds; deleting on absence would erase the cache on the first incremental
> pull. It is coherent only for a full bootstrap, and only if every page of an unbounded
> `has_more` sequence is held before deciding — on a phone.
>
> **The consequence is recorded rather than solved.** A customer *reassigned out of a user's
> zone* is not deactivated and will simply stop appearing in `updated`; the device keeps it.
> P-4 explains deactivation and is silent on rescoping. That is a **CONTRACT GAP with an
> FR-SYN-012 dimension** — a device retaining records it may no longer be authorised to hold
> — and it is deferred to a later amendment rather than closed by inference. Bounded
> over-retention is recoverable; mass deletion on a device carrying unsent work is not.
>
> **D-M9.4-4 — the cursor comparison is `updated_at >= since`.**
>
> `>` and `>=` are not symmetric in cost. `>` can permanently miss a row stamped in the same
> microsecond as the `server_time` that became the next `since`; `>=` can resend one. **A
> lost row is silent and unrecoverable; a resent row is visible and harmless** — provided the
> client upserts by the server's immutable `id`, which D-M9.4-4 therefore also requires of
> the device. Inserting blindly would turn the safe failure into duplicate rows.
>
> This is the position §6 already takes on replay — *"a retry after a timeout is the **correct**
> client behaviour"*, and I-4 makes a duplicate a success rather than an error.
>
> **Both collections can share one cursor.** `Customer` and `Delivery` both inherit
> `updated_at` from `TimeStampedModel` (`auto_now`, `timestamptz`, UTC per N-08), and every
> write path in `customers/services.py` and `fulfilment/services.py` — including
> **deactivation** and **`complete_delivery`** — carries `updated_at` in its `update_fields`.
> That was checked rather than assumed: Django fires `auto_now` only for fields actually being
> written, so one `save(update_fields=[…])` omitting it would leave a completed delivery
> invisible to every subsequent pull, and nothing would report the loss.
>
> **Ordering must be `(updated_at, id)`.** `timestamptz` is microsecond-resolution but not
> unique — one transaction can stamp two rows identically — and a tie split across a page
> boundary drops or repeats a row.
>
> **D-M9.4-5 — the pull page size is deliberately NOT a wire-contract number.**
>
> §4 separates the two mechanisms explicitly: *"Lists use `?page=&page_size=` with a default
> of 25 and a maximum of 100. **Sync pull uses `?since=…`**"* — so pull never inherited the
> list numbers, and §13's `sync/push` cap of 200 counts *operations a device sends*, not rows
> a server returns across heterogeneous collections. P-5 asserts a cap exists and states no
> value. **It is left unstated on purpose.**
>
> A server MAY bound a page however it needs to; `has_more` is the contract, the number is
> not. A client MUST NOT depend on any particular page size, and MUST follow `has_more`
> rather than counting rows.
>
> **The paging protocol, stated once so an implementer does not re-derive it:**
>
> | Rule | Detail |
> | --- | --- |
> | `server_time` is sampled **once, at request start** | Sampling it after the query would drop every row written in between — the same silent skip §11.1 describes for client clocks |
> | Every page of one pull uses the **same `since`** | P-5 |
> | The client advances its persisted cursor **only after the final page is durably applied** | `has_more: false` **and** committed |
> | The cursor is **never** advanced page by page | A crash mid-sequence would otherwise skip every page not yet fetched, permanently (FR-SYN-004, FR-SYN-017) |
>
> **Correction to D-M9.4-5, 2026-08-16.** The clause above previously read *"the pull page
> size is deliberately not a wire-contract number"* and cited its absence from the corpus.
> **That was wrong.** **O-5 defines it: 500 records per collection.** It was missed because
> the audit grepped for *"page size"* and O-5 says *"page cap"*. What survives is the client
> obligation, which O-5 does not weaken: **a client MUST follow `has_more` and
> `next_page_token` and MUST NOT depend on the numeric page size.** A server may cap below
> 500; the contract is the flag, and 500 is the ceiling.
>
> ---
>
> **D-M9.4-8 — opaque continuation token (amendment, 2026-08-16).**
>
> **P-5 as originally written was unimplementable.** With no page-position field, a repeat
> request carrying the same `since` is byte-identical to the first: the server returns the
> same page, `has_more` never becomes false, and a client following the rule literally loops
> forever without ever writing its cursor. **Found while building the client against a
> backend that had already passed 17 focused tests** — none of which asserted that a *second*
> page could be reached. The suite verified the pieces and never the traversal.
>
> **Two frozen statements also could not both hold.** AD-10 chose *"a `since` cursor for
> sync"* and rejected offset explicitly — *"offset pagination silently skips rows when the
> underlying set changes mid-pagination, precisely the failure that loses a transaction
> (BR-014)"* — while P-5 required `since` to stay fixed. A cursor that never moves is not a
> cursor.
>
> **And one scalar could not serve two collections.** §11.1 returns `customers` and
> `deliveries` in one envelope. If both are capped at different `updated_at` positions, a
> single `since` cannot express both, so no rewording of P-5 could have fixed it. That is a
> shape problem, and it is what forced a token rather than a redefinition.
>
> | Rule | Detail |
> | --- | --- |
> | Request | `?since=<ISO-8601>&page_token=<opaque>` — both optional |
> | Response | `next_page_token` **MUST** be present when `has_more: true`, and **MUST** be absent when it is false |
> | Meaning | Position **within the current pull**, across **both** collections, so each can advance independently |
> | Encoding | **Deliberately unspecified.** A client that parsed it would couple itself to a server internal; opacity is the guarantee |
> | Lifetime | **Transient.** Held for the duration of one pull and discarded. The device persists `server_time` and nothing else |
> | `since` | **Unchanged across every page of one pull.** `updated_at >= since` is untouched (D-M9.4-4) |
>
> **The persisted-cursor model does not change.** `server_time` still advances once, after the
> final page is durably applied. The token exists precisely so that rule can survive: without
> it there was no final page.
>
> ---
>
> **D-M9.4-6 and D-M9.4-7 — client obligations, recorded 2026-08-21.**
>
> **Recorded late, and that is the finding.** Both were frozen during M9.4 mobile
> implementation and cited by identifier in shipped source —
> `mobile/lib/domain/sync/cached_round.dart` cites D-M9.4-6, `mobile/lib/app/bootstrap.dart`
> cites D-M9.4-7 — while existing in no document. The pre-commit audit found the dangling
> references. **Neither changes the wire contract**; both govern how a client consumes §11.1,
> which is why they belong beside it rather than in a mobile-only note.
>
> **D-M9.4-6 — `as_of` is a property of the pull, not of the record.**
>
> A cached read returns `CachedRound<T>`: the rows, and **one** `asOf` for the round. The
> value is the **server-provided `server_time`** of the last completed pull, persisted
> verbatim — the same string P-2 sends back as the next `since`, never a re-rendered or
> re-parsed copy of it, and never the device's clock (P-4).
>
> **One timestamp per round rather than one per entity**, because that is what actually
> happened: a pull is a snapshot, every row in it was true at the same server instant, and a
> per-entity copy would be the same value repeated N times with N chances to diverge. It also
> answers the question P-8 asks — *"how old is what I am looking at?"* — which is a question
> about the round, not about a row.
>
> `asOf == null` means **no pull has ever completed**, which a screen must render differently
> from an empty round pulled this morning. An empty list with a timestamp is a salesman with
> no calls today; an empty list without one is a device that has never synced.
>
> **D-M9.4-7 — start-up background synchronization is ordered, and stops on no session.**
>
> ```
> session restore → push → pull
> ```
>
> | Step | Outcome | Then |
> | --- | --- | --- |
> | restore | `Err` — restoration failed | **stop.** No push, no pull |
> | restore | `Ok(null)` — succeeded, no authenticated session | **stop.** No push, no pull |
> | restore | `Ok(session)` | push |
> | push | `Unauthenticated` | **stop.** No pull |
> | push | any other failure (`Offline`, storage, server) | **pull proceeds** |
> | push | success | pull |
>
> **Ordered, not concurrent.** Local durable writes must reach the server before a pull
> overwrites the cache describing them. Run together, a pull that wins the race lands the
> server's stale view over work the device has already recorded; the outbox overlay would
> still mask it on screen, but the ordering must be a decision rather than whatever the event
> loop chose.
>
> **`Ok(null)` and `Err` stop for the same reason and are not the same event.** `Ok(null)` is
> restoration *succeeding* and finding no credential — a fresh install, or a signed-out
> device — and §8.2 makes it the state that lets the shell render a login screen without
> waiting on a timeout. `Err` is restoration *failing*. Neither produces an authenticated
> session, and neither can produce a useful request: a push would meet a guaranteed 401 and a
> pull would return an empty scope. Both would look like work and be neither.
>
> **A non-auth push failure must not block the pull.** The rows stay `PENDING`, nothing is
> lost (P-5 of §11.2), and the connection may have recovered between the two calls. Treating
> every push failure as terminal would leave a device whose depot Wi-Fi hiccuped on
> yesterday's round for the rest of the day.
>
> **This is not FR-SYN-010 and is not claimed to be (TD-41).** The requirement is *"within 2
> minutes of reconnection"*; the frozen mobile stack has no connectivity-state mechanism to
> detect one, so the trigger is launch. A launch is when a device reconnects in practice, not
> by guarantee. When the real trigger is built it calls this same chain — the ordering above
> is the contract, the trigger is not.

### 11.2 Push

```
POST /api/v1/sync/push
```

```json
{
  "device_id": "a3f9…",
  "operations": [
    {
      "client_uuid": "c1a4…",
      "operation_type": "CUSTOMER_CREATE",
      "client_created_at": "2026-08-05T06:12:00Z",
      "payload": { "shop_name": "Nayi Dukan", "phone": "+9198…", "zone_id": 7 }
    },
    {
      "client_uuid": "d2b5…",
      "operation_type": "VISIT_CREATE",
      "client_created_at": "2026-08-05T06:14:30Z",
      "payload": {
        "customer_client_uuid": "c1a4…",
        "visited_at": "2026-08-05T06:14:30Z",
        "latitude": "25.594095", "longitude": "85.137566",
        "accuracy_metres": "8.50", "outcome": "NO_ORDER"
      }
    },
    {
      "client_uuid": "e3c6…",
      "operation_type": "DELIVERY_COMPLETE",
      "client_created_at": "2026-08-05T06:41:10Z",
      "payload": { "delivery_id": 3312, "recipient_name": "Sharma ji", "photo_media_id": 9912 }
    }
  ]
}
```

```json
// 202 Accepted
{
  "server_time": "2026-08-05T11:20:05Z",
  "results": [
    { "client_uuid": "c1a4…", "status": "ACCEPTED",  "entity_type": "customer", "entity_id": 501 },
    { "client_uuid": "d2b5…", "status": "ACCEPTED",  "entity_type": "visit",    "entity_id": 2210 },
    { "client_uuid": "e3c6…", "status": "DUPLICATE", "entity_type": "delivery", "entity_id": 3312 }
  ]
}
```

| Status | Meaning | Client action |
| --- | --- | --- |
| `ACCEPTED` | Applied | Delete from the outbox |
| `DUPLICATE` | Already applied — a replay (BR-012) | **Delete from the outbox. This is success**, not an error |
| `DEFERRED` | A dependency is not yet accepted | Keep; retry next sync |
| `REJECTED` | Failed validation | **Keep. Never delete.** Flag to the user; the server has stored it for the owner (BR-014) |

**`202`, not `200`.** The batch was received and processed **per operation**; some may not have succeeded. A `200` would imply the whole batch succeeded, which is exactly the ambiguity that loses transactions.

| Rule | Detail |
| --- | --- |
| **PU-1** | **The `operations` array is ordered, and the server applies it serially in array order.** It does **not** sort by `client_created_at`, and does **not** apply operations concurrently |
| **PU-2** | The client fills the array in creation order per device (FR-SYN-002). Array position is therefore creation order, and **BR-013 is satisfied by the array, not by a timestamp** |
| **PU-3** | `client_created_at` is **metadata** — audit, display and diagnosis. It is never an ordering key |
| **PU-4** | `device_id` is sent **once per batch**. It is not repeated on an operation and does not appear inside `payload` |

> **Added 2026-08-11.** PU-1…PU-3 close a contradiction between this document, `04` T-26 and
> `M8_Design_Review` P-4. §11.2 was previously silent on whether array order was significant,
> so a conforming server was free to sort by `client_created_at` — putting a **device clock**
> on the correctness path, which P-4 forbids and which cannot deliver BR-013 anyway, because
> a clock adjustment makes that timestamp non-monotonic **within one device**.
>
> **No field is added or removed.** This fixes what the existing array *means*, not what the
> payload contains. PU-4 states what §11.2's example already shows, because it was read the
> other way once.

### 11.3 Local reference resolution — the subtlest part of the contract

A salesman offline creates a new shop, then records a visit and takes a payment against it — all before any sync. **The visit and the payment reference a customer that has no server ID.**

**Resolution.** Payloads may reference a not-yet-synced entity by its `client_uuid` instead of its server id, using a `*_client_uuid` field:

| Server-id field | Offline alternative |
| --- | --- |
| `customer_id` | `customer_client_uuid` |
| `sales_order_id` | `sales_order_client_uuid` |

| Rule | Detail |
| --- | --- |
| L-1 | Exactly one of the pair must be present. Both, or neither, is `422` |
| L-2 | The server resolves `client_uuid → id` from `sync_operation.result_entity_id` |
| L-3 | If the referenced operation is not yet accepted, the operation is `DEFERRED`, not rejected |
| L-4 | Because operations apply in `client_created_at` order per device (BR-013), a dependency created earlier on the same device is always processed first — so `DEFERRED` should be rare and self-healing |
| L-5 | An operation deferred more than 3 consecutive syncs is escalated to `REJECTED` with `SYNC_DEPENDENCY_UNMET` and surfaced to the owner, so it cannot loop silently forever |

> **This is the one place where a plausible-looking design fails quietly.** The obvious approach — have the client wait for the customer to sync before allowing a visit against it — means a salesman cannot record a visit to a shop he just added, which is precisely the situation that occurs on every new route. The obvious alternative — let the client invent a negative or temporary id — produces two different ids for one shop and a merge problem later. Resolving by `client_uuid`, with ordering already guaranteed, is the only option that is both correct and invisible to the salesman.

### 11.4 Conflict classes in Version 1

| Class | Trigger | Automatic? | Version |
| --- | --- | :-: | --- |
| `SC-DUPLICATE` | `client_uuid` already accepted | **Yes** | V1 |
| `SC-SEQUENCE` | Dependency not yet applied | **Yes** | V1 |
| `SC-STOCK` | Ordered quantity exceeds stock at sync | No | Edition 2 |
| `SC-CREDIT` | Credit breached at sync | No | Edition 2 |
| `SC-PRICE` | Quoted price differs from recomputed | No | Edition 2 |
| `SC-MASTER` | Customer or product deactivated since last sync | No | Edition 2 |

**Only the two automatic classes exist in Version 1.** No conflict resolution console is built, because none is needed — a direct consequence of DV-1 removing field order capture (`02A` §5). Edition 2 adds `ORDER_CREATE` to `operation_type` and the four remaining classes as new `status` values. **The endpoint, the idempotency key, the ordering guarantee and the outbox are unchanged** (EP-C).

### 11.5 `GET /sync/status`

```json
{
  "device_id": "a3f9…",
  "last_sync_at": "2026-08-05T11:20:05Z",
  "pending_count": 0,
  "deferred_count": 1,
  "rejected_count": 0,
  "rejected": []
}
```

Nothing fails silently (FR-SYN-008/009). The device shows its own outbox depth; this endpoint shows the **server's** view, so a disagreement between the two is visible rather than assumed away.

| Field | Meaning |
| --- | --- |
| `device_id` | Taken from the authenticated JWT claim, **never from the request** (D-M9.3-1) |
| `last_sync_at` | `MAX(sync_operation.received_at)` for that device. `null` if it has never pushed |
| `pending_count` | `sync_operation.status = 'RECEIVED'` — recorded by the server, business processing not completed |
| `deferred_count` | `status = 'DEFERRED'` |
| `rejected_count` | `status = 'REJECTED'` |
| `rejected[]` | `client_uuid`, `operation_type`, `error_code`, `client_created_at` — **and nothing else** (D-M9.3-2) |

> **Clarification, 2026-08-16 (D-M9.3-1, D-M9.3-2).** The field table above is added; **no
> field is added, removed or renamed**, and the JSON example is unchanged.
>
> **`pending_count` was undefined in prose**, and the four lines that mention it corpus-wide
> — this example and FR-SYN-008/009 — do not say whose "pending" it is. That matters because
> the two sides use different vocabularies: the device's `PENDING` means *not yet
> transmitted*, which a server cannot observe, while `04` T-26's `RECEIVED` means *recorded
> before the business operation was attempted*. **The example itself settles the rest**:
> `pending_count: 0` alongside `deferred_count: 1` proves the two are disjoint, which rules
> out any reading where `pending_count` is a superset of unresolved work.
>
> **A non-zero `pending_count` is therefore an alarm, not a queue depth.** The receiver
> records an operation and completes it in the same request, so `RECEIVED` survives only if
> processing was interrupted after receipt — a killed worker, a lost connection mid-handler.
> That is precisely the "nothing fails silently" this section exists for.
>
> **Orphaned `RECEIVED` rows are recovered by replaying the original operation** (amended
> 2026-08-21; the clause below is what this replaces).
>
> A device that receives no verdict keeps the operation and resends it under the same
> `client_uuid` (P-6, BR-012). When that resend finds a row already at **`RECEIVED`**, the
> server **re-enters the handler for the original row** rather than answering `DUPLICATE`:
> the same `client_uuid`, the same `sync_operation`, no second record. Success settles it as
> **`ACCEPTED`**; a refusal settles it as **`REJECTED`**. **No status, field or endpoint is
> added, and no other status is affected** — `ACCEPTED` and `DUPLICATE` are finished,
> `REJECTED` is terminal evidence (BR-014) and is never re-run, and `DEFERRED` returns to
> `PENDING` on the device and arrives as a fresh push.
>
> **`RECEIVED` is not a verdict, which is why answering `DUPLICATE` to one was a defect.**
> Receipt commits before the business operation is attempted (`04` T-26), so an interruption
> in that window leaves the row `RECEIVED` with nothing applied — and `DUPLICATE` tells the
> device *"delete from the outbox, this is success"* (§11.2) for work that never happened.
> **Found by reading the receiver, reproduced by
> `backend/tests/adversarial/test_sync_integrity.py`, and repaired in the same change as this
> paragraph.** It was a silent loss against `01` §10.3's non-negotiable zero, and it is the
> reason the M9→M10 gate exists.
>
> **Re-entry is safe because the handlers are idempotent on `client_uuid` against a database
> constraint, not because they are called retries.** `record_visit` resolves through
> `visit.client_uuid`; `complete_delivery` through `delivery.outcome_client_uuid`
> (I-6, TD-39). Each wraps its write in a savepoint, so a lost race returns the original row
> instead of aborting the caller's transaction. Whether the first attempt left the business
> effect **absent** or **present-but-unrecorded**, re-entering converges on one row.
> Concurrent recoveries serialise on `SELECT … FOR UPDATE` over the `sync_operation` row.
>
> **Superseded clause, kept so the change is legible:** *"Recovery of orphaned `RECEIVED`
> rows is not specified and is not built. Nothing retries, escalates or purges them, so the
> count only grows once it is non-zero. Deferred to M9.4/M10 by ruling."* The deferral ended
> when the window was shown to lose transactions rather than merely to strand them.
>
> **Still true, and unchanged:** a non-zero `pending_count` remains an alarm rather than a
> queue depth. Recovery happens when the device resends; **nothing sweeps `RECEIVED` rows on
> the server's own initiative**, so a device that never returns still leaves one visible.
>
> `rejected[]` carries four fields and omits `payload` and `error_detail` deliberately:
> `payload` is business data the device already holds, and `error_detail` is prose §5 permits
> rewording, so no client may branch on it.

---

## 12. Client Obligations

The contract binds both sides. A client that violates these will produce defects the server cannot prevent.

| # | Obligation | Consequence of breaking it |
| --- | --- | --- |
| C-1 | **Parse money and quantity as `Decimal`, never `double`** (AD-02) | Silent rounding errors on invoices |
| C-2 | **Generate `client_uuid` before the first attempt** and reuse it on every retry (AD-09) | Duplicate orders and duplicate payments |
| C-3 | **Never delete a `REJECTED` operation from the outbox** | A lost transaction — violates the non-negotiable metric |
| C-4 | Treat `DUPLICATE` as success | Retry storms, and a user told their payment failed when it did not |
| C-5 | **Use `server_time` for the next `since`, never the device clock** (P-2) | Permanently skipped records |
| C-6 | Never compute or display a locally derived price or tax as authoritative | The app and the invoice disagree in front of the retailer |
| C-7 | Refresh once on `401 TOKEN_EXPIRED`, then re-authenticate. Never loop | Infinite refresh loop, battery drain, lockout |
| C-8 | Label cached stock and balance with their `as_of` time (BR-010) | The salesman treats a stale snapshot as a guarantee |
| C-9 | Upload media on a separate queue from transactions (§10.7) | A photo blocks a delivery confirmation on 2G |
| C-10 | Send `device_id` on every write | Loss of attribution in the audit trail |
| C-11 | Persist the outbox durably — survive app kill, reboot, battery death | Lost transactions (NFR-OFF-005) |
| C-12 | Never assume a single role; `roles` is an array | Delivery screens hidden from a salesman who also delivers |

> **C-1, C-2, C-3 and C-5 are each sufficient on their own to break a non-negotiable guarantee.** They belong in the Flutter code review checklist, not only in this document.

---

## 13. Rate Limiting and Payload Limits

| Endpoint | Limit | Rationale |
| --- | --- | --- |
| `POST /auth/otp/request` | 3 per phone / 15 min; 20 per IP / hour | **SMS costs real money.** An unthrottled OTP endpoint is both a security hole and a bill |
| `POST /auth/otp/verify` | 5 attempts per `otp_request` | FR-IAM-004 |
| `POST /auth/login` | 10 per phone / 15 min, progressive backoff | FR-IAM-004 |
| `POST /sync/push` | 60 per device / hour | Prevents a retry loop from becoming a denial of service |
| `POST /media` | 100 per user / hour | Disk protection |
| All authenticated | 1,000 per user / hour | Backstop |

Exceeding a limit returns `429` with `Retry-After` in seconds. Limits are counted server-side per user, per device and per IP.

| Limit | Value |
| --- | --- |
| Request body (JSON) | 1 MB |
| Request body (multipart) | 5 MB |
| `sync/push` operations per batch | 200 |
| Page size | 100 max, 25 default |
| Response timeout | 30 s |

---

## 14. Versioning and Compatibility Policy

### 14.1 Permitted within `v1` — additive only

Adding an optional request field · adding a response field · adding an endpoint · adding an enum value **the client may ignore** · relaxing a validation rule · adding an error `code` for a genuinely new condition.

### 14.2 Requires `v2`

Removing or renaming any field · changing a type or its encoding · making an optional field required · **changing the meaning of an existing value** · removing an endpoint · tightening validation on existing traffic · changing an existing error `code`.

### 14.3 The trap

> **Adding an enum value is only safe if clients ignore unknown values.** A new `sales_order.status` would be received by an app built before it existed. Clients must therefore treat an unrecognised enum as "unknown" and degrade gracefully — never crash, never assume exhaustive matching. **This is a client obligation and a Dart code-review item**, because Dart's exhaustive `switch` on a sealed type makes the failure a compile-time habit and a runtime crash. Stated here so the trap is designed around rather than discovered.

### 14.4 Deprecation

A `v2` release keeps `v1` alive for **at least 6 months**, or until telemetry shows no field device on the old build — whichever is longer. `v1` responses then carry `Deprecation` and `Sunset` headers. After sunset, `410 Gone` with an upgrade message. A distributor cannot compel 40 salesmen to update on demand, and the API must not assume otherwise.

---

## 15. Traceability

### 15.1 Endpoints → database tables

| Group | Endpoints | Tables (`04`) |
| --- | :-: | --- |
| Auth | 6 | `app_user`, `role`, `user_role`, `otp_request` |
| Master data | 13 | `product`, `customer`, `zone`, `reason_code`, `offer`, `media_file` |
| Orders | 7 | `sales_order`, `sales_order_line`, `customer`, `product` |
| Delivery | 4 | `delivery`, `sales_order`, `stock_movement`, `media_file` |
| Billing | 8 | `invoice`, `invoice_line`, `credit_note`, `credit_note_line`, `number_series`, `customer_ledger_entry` |
| Payments & ledger | 6 | `payment`, `customer_ledger_entry`, `customer` |
| Stock | 3 | `stock_movement`, `stock_location`, `stock_lot`, `reason_code` |
| Field | 2 | `visit`, `media_file` |
| Media | 2 | `media_file` |
| Sync | 3 | `sync_operation` + all device-writable tables |
| Reports | 5 | Derived — no dedicated tables |
| System | 1 | — |
| **Total** | **60** | All 27 tables reachable |

Every endpoint maps to approved tables. **No schema change is required to implement this contract** — confirming the §16 verification in `04`.

### 15.2 Client requirements → endpoints

| Client requirement | Endpoint |
| --- | --- |
| Registration, OTP, alternate number, language | `/auth/otp/*`, `/auth/me` |
| Add product, image + rate | `POST /products`, `POST /media` |
| Customer profile — bills | `GET /invoices?customer_id=` |
| Customer profile — udhaari | `GET /customers/{id}/ledger`, `/balance` |
| Customer profile — scheme | `GET /offers` |
| Customer profile — call | `customer.phone` in the customer payload |
| Zone — road, PIN, panchayat, ward, city | `GET /zones` |
| Salesman — pending orders | `GET /deliveries?assigned_to=me&status=PENDING` |
| Salesman — customer add | `POST /customers` |
| Salesman — live location + photo | `POST /visits`, `POST /media` |
| Salesman — bill | `GET /invoices`, `GET /invoices/{id}/pdf` |
| Owner — daily sales | `GET /reports/sales` |
| Owner — stock | `GET /stock` |
| Owner — total amount | `GET /reports/sales`, `/receivables` |
| Top 10 customers | `GET /reports/top-customers` |
| 120-day customer history | `GET /customers/{id}/statement?date_from=` |
| Shopkeeper places own order | `POST /orders` as `RETAILER` |
| Order direct to processing | No approval endpoint exists — by design |
| Credit limit set by owner | `PATCH /customers/{id}` |
| GST bill | `POST /invoices`, `GET /invoices/{id}/pdf` |
| Cash / UPI | `POST /payments` with `method` |
| GPS only during visit | `POST /visits` — no tracking endpoint exists |
| Offline bill, syncs on network | `/sync/push`, `/sync/pull`, `client_uuid` |
| Same price for everyone | No customer-price parameter exists anywhere |

**Every Version 1 client requirement is served. Two are Edition 2 by agreement** — salesman targets and the salesman-wise Cash/UPI report — and have no endpoint here, correctly.

### 15.3 Non-negotiable guarantees → mechanism

| Guarantee | Mechanism |
| --- | --- |
| Zero duplicate transactions | AD-09, §6, `uq_*_client_uuid` |
| Zero lost transactions | `REJECTED` retained (§11.2), C-3, `sync_operation.payload` |
| Authorisation server-side | AD-11, §8, adversarial test |
| Money exact | AD-02, C-1 |
| Rules only in `CORE` | §10.2 — the client sends intent, the server returns authority |
| Nothing fails silently | `GET /sync/status`, `202` per-operation results |

---

## 16. Open Items

| # | Item | Impact | Default |
| --- | --- | --- | --- |
| O-1 | OpenAPI schema generation (`drf-spectacular`) | Developer experience; generated Dart models | **Recommended at M4**, when the API stabilises (`00` §3.4) |
| O-2 | Should `GET /media/{id}` support signed time-limited URLs? | Offloads media serving | Not in V1. Authorised view is sufficient at this volume |
| O-3 | Push notification registration endpoint | Edition 2 (EP-I) | Not in V1 — notifications were cut entirely |
| O-4 | e-invoicing fields on `POST /invoices` response | Blocked on CF-1 | Additive when confirmed |
| O-5 | Sync pull page cap before `has_more` | Payload tuning | 500 records per collection |

**None is structural. None blocks implementation.**

---

## 17. Architectural Uncertainty Review

Per the workflow: Gemini is engaged only where a **high-impact architectural uncertainty** appears. Three candidates were assessed while designing this contract.

| Candidate | Assessment | Escalated? |
| --- | --- | :-: |
| Local reference resolution for offline-created entities (§11.3) | Genuinely subtle, and the naive designs fail quietly. But the resolution — reference by `client_uuid`, ordering already guaranteed by BR-013 — is well-established and follows directly from decisions already frozen | **No** |
| Integer ids vs public UUIDs in API paths | Assessed in `04` DBD-01. Enumeration is neutralised by AD-11 token-derived scoping and `404`-for-out-of-scope (§4.1). Reversible via an exposed alternate key if ever needed | **No** |
| Refresh token rotation with reuse detection (§7.1) | Standard practice, one column, closes the main mobile attack. No architectural fork | **No** |

**No high-impact uncertainty requiring escalation was found.** All three resolve deterministically from the frozen architecture. Recorded here so the absence of escalation is a documented judgement rather than an omission.

---

## 18. Sign-Off

### 18.1 Verification performed

| # | Check | Result |
| --- | --- | --- |
| 1 | Consistent with the frozen architecture (`03`) | ✓ REST, `/api/v1`, JWT mobile + session web, services-only rules |
| 2 | Consistent with the approved database (`04`) | ✓ 60 endpoints, 0 schema changes required |
| 3 | Every endpoint has defined roles | ✓ §8, §9 |
| 4 | Every error has a stable machine code | ✓ §5 |
| 5 | Idempotency defined for every device-created resource | ✓ §6 |
| 6 | Sync contract complete, including dependency resolution | ✓ §11 |
| 7 | Client obligations explicit | ✓ §12 |
| 8 | Versioning and deprecation policy stated | ✓ §14 |
| 9 | Every V1 client requirement served | ✓ §15.2 |
| 10 | Non-negotiable guarantees traced to mechanisms | ✓ §15.3 |
| 11 | Architectural uncertainty reviewed | ✓ §17 — no escalation |
| 12 | No implementation code produced | ✓ |

### 18.2 Approval

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Business Owner (Sponsor) | | ☐ Approved ☐ Changes requested | |
| Product Architect (ChatGPT) | | ☐ Approved ☐ Changes requested | |
| Chief Systems Engineer (Claude) | | ☐ Approved ☐ Changes requested | |

### 18.3 What happens next

The design corpus is complete: `00` through `05`. Implementation may begin once these preconditions are met.

| # | Precondition | Reference |
| --- | --- | --- |
| 1 | `00_Engineering_Foundation.md` ratified | `00` §P.4, P0-10 |
| 2 | Irreversible decisions I-01 … I-12 signed | `04` §17 |
| 3 | This document approved | §18.2 |
| 4 | **`AUTH_USER_MODEL` set before the first `makemigrations`** | `04` I-01 |
| 5 | Phase 0 tasks P0-1 … P0-9 complete | `00` §2.6 |
| 6 | SMS / DLT registration submitted | `00` P0-8 |

**Then M0 — Foundation.**

*No implementation code, serialisers, viewsets, routers or Dart models have been produced or authorised.*
