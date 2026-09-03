# M8 — Mobile App: Design Review

| Field | Value |
| --- | --- |
| Document ID | `M8_Design_Review` |
| Version | **1.9.0** |
| Status | **Phase 1 FROZEN. Phase 2 — tasks 0–3 and TD-39 done and verified; task 4 M1–M5 verified and pushed. `make mobile-device-kill` PASSED 2026-09-01 (§5.6.1); `make mobile-device-storage` still unrun. Next: task 4 M6, frozen at §14.12, not yet implemented** |
| Date | 2026-08-16 |
| Milestone | M8 — Mobile app (3.0 units, `00` §19.1) |
| Scope | Flutter shell · auth · delivery · visits · GPS · photo · **local outbox** |
| Depends on | `00` v1.0.0 · `01` · `02` v0.2.0 · `02A` v0.2.0 · `03` · `04` · `05` · M0–M7 verified |
| ADR required | ~~Yes — two~~ **Both approved 2026-08-10.** §5.6 Drift + encrypted SQLite — *cipher amended by D-M9-8, 2026-08-25* · §7.5 Dio |

### Change log

| Version | Date | Change |
| --- | --- | --- |
| 1.0.0 | 2026-08-09 | Phase 1 issued for review |
| **1.1.0** | **2026-08-10** | **Signed.** §3.4 "no owner role" **replaced by Owner Companion Mode** (ruling); §3.4.1 and §3.4.2 record the two corpus conflicts it creates; **§1.3 Design Principles P-1…P-10 added and frozen**; §10 rewritten as the Phase 2 plan; §11.2, §12.5, §13 updated |
| **1.2.0** | **2026-08-10** | **Task 0 complete and verified** — `GET /reports/dashboard`, contracted at `05` §9.11.1. **§3.4.1a added: the seven report endpoints were already emitting money as JSON floats (TD-36)**, found while deciding this endpoint's encoding. §10 task 0 struck; §11.2 item 6 closed, item 8 opened; §12.8 added |
| **1.3.0** | **2026-08-10** | **Task 1 complete and verified** — Flutter shell, four-layer structure, DI/routing, pinned toolchain, and **16 blocking structural tests**. §10 task 1 struck; §12.9 records what the milestone's four infrastructure defects have in common; TD-37 and TD-38 opened |
| **1.4.0** | **2026-08-11** | **§14 added — Phase 2 frozen decisions**, after an independent review of the task 2 design: **D-A1/D-A2** (delivery idempotency keyed on `client_uuid`; **TD-39** opened as a separate Django commit before task 3), **D-B1** (single-flight refresh), **D-B2** (structurally isolated refresh client), **D-B3** (retry preserves operation identity). Dashboard DTO **rejected** from task 2. §7.2 and §10 task 2 point at §14. **No code changed** |
| **1.5.0** | **2026-08-11** | **Task 2 complete and verified** — API layer, four interceptors, single-flight refresh, problem+json, the `Money` codec. §10 task 2 struck; §14.3–§14.5 marked **built**; §14.8 added (what implementing the decisions taught). `make verify` 8/8 · 743/743 · 94.88%; `make mobile-verify` 38/38 · 0 errors |
| **1.6.0** | **2026-08-11** | **§14.9 Task 3 decisions frozen** — D-C1 (`AUTOINCREMENT` PK as the local sequence), D-C2 (`client_created_at` demoted to metadata; the `operations` array is the order — corrected in `04` T-26 and `05` §11.2 PU-1…PU-4), D-C3 (storage-full `Failure` variant at the outbox write boundary), D-C4 (`device_id` batch-level, no outbox column). **§14.10 records the Task 3 gate.** Documentation only — no code changed |
| **1.6.1** | **2026-08-11** | **TD-39 verified — §14.10 gate 1 CLOSED.** `make verify` 8/8 · **758/758** · **94.71%** · `mypy` clean over 115 files · 3 contracts kept (144 files, 271 dependencies) · `makemigrations --check` **No changes detected**. Patch version, not minor: **no architectural decision changed** — only a gate status and its evidence |
| **1.7.0** | **2026-08-16** | **§14.12 — Task 4 / M6 offline authentication window frozen**, after an evidence audit returned *BLOCKED — MISSING CONTRACT*. **D-D1** (the refresh token's `iat` is the trusted anchor — P-4 forbids the device clock and the `server_time` §5.5 relies on does not exist on the auth response), **D-D2** (`DISTRICORE_OFFLINE_WINDOW_DAYS`, compile-time, default 7, **not** in `BusinessProfile`), **D-D3** (anchor on the most recent successful authenticated server *contact*, not last login — `03` §5.2 would force an OTP weekly on a fully connected device), **D-D4/D-D5** (a successful `/auth/refresh` is the post-expiry round trip), **D-D6** (no biometric, PIN or passcode in V1; local auth = cached identity + retained refresh token + unexpired window). **§14.12.1 records three corpus statements this supersedes**, including a §5.5 sentence that is not true of the shipped contract. Documentation only — **no code changed** |
| **1.6.2** | **2026-08-11** | **§14.11 — Task 3 gate contradiction resolved.** §10's task-3 Gate cell claimed *"Kill · restart · storage exhaustion, at every write boundary"*, which §9 and `00` §19.1 assign to `integration_test/` at the **M8→M9** boundary. Task 3's gate corrected to the hermetic subset. **No architectural decision changed; no code changed** |
| **1.8.0** | **2026-08-25** | **§5.6 amended in place — the cipher is SQLite3MultipleCiphers, not SQLCipher.** Authority: **D-M9-8** (`M9_Design_Review` v1.3.0). **The original §5.6 paragraph is preserved verbatim**; the amendment is appended beneath it. Drift, the ADR's conclusion and all of its reasoning are unchanged, as are the schema, the migrations and the key source (Android keystore via `PlatformDatabaseKey`). **`02` is not amended** — FR-SYN-016 and NFR-SEC-008 name no cipher. `chacha20` and SQLite `3.53.4` are recorded as **observations, not requirements**. Encryption proven on a **Pixel 8a API 34 emulator, `android-x64` only**; **`00` §19.2's durability gate remains open**. The header ADR row, §11.2 item 1 and §13 item 7 updated mechanically. **Minor, not patch: an architectural decision changed** (1.6.1's rule, applied in the opposite direction). Documentation only — the code it records was built and verified beforehand |
| **1.9.0** | **2026-09-01** | **§5.6.1 added — the kill gate's first recorded run, and it PASSED.** `make mobile-device-kill` on `emulator-5554` (Pixel 8a, API 34, x86_64), host Windows Flutter 3.44.7 reached from WSL through `scripts/win-flutter.sh`. Phase 1 reached `GATE-P1: KILL-NOW` and died; phase 2 found the database mid-WAL (4096 B / 119512 B / `-shm` present) and **all tests passed** — five committed appends present, three rows still `IN_FLIGHT`, the claim positionally on 1–3, the sequence unbroken (**D-C1**). This discharges `02` NFR-OFF-005 by its own stated method. §5.6's gate-status paragraph corrected from *"NOT closed"* to **partly closed**: `make mobile-device-storage` has still never run, so §19.2's *storage exhaustion* clause remains open, and `M9_Design_Review` TD-42's *"no shell where both `make` and `flutter` work"* is retired while its CI half stands. **Minor, not patch: new evidence closes half a gate.** Documentation only |

---

## 1. The governing principle

Every milestone has been organised around refusing to store or derive something in the
wrong place. M8 is the first to run **outside** the trust boundary, on hardware the business
does not control, against a network that is not there for hours at a time.

> **The device captures facts. It never decides them.**

A fact is something the field already knows and the server cannot: *this delivery was
handed over at 14:32, here, to this person, and here is the photograph.* A decision is
everything else — whether the customer has credit, what the price is, whether the stock
exists, whether this user may do this at all.

`02` BR-001 states the rule and `02A` §9.3 states the consequence: **the binary is publicly
downloadable and must be assumed fully decompiled.** Role-based UI is presentation. Every
authorisation decision is server-side, per request.

### 1.1 Why this milestone is affordable at all

`02A` §5 is the reason M8 is 3.0 units rather than the largest thing in the programme.

**In the frozen baseline, salesmen captured orders offline.** That one capability produced
six conflict classes, four needing human resolution, a resolution console, and R-1 — the
highest-severity risk in the programme.

**In Edition 1 they do not.** They read assigned orders and write delivery status, visits,
coordinates and photographs. None of those contend for a shared resource:

| Offline write | Why it cannot conflict |
| --- | --- |
| Delivery status on a known order | A state transition; last-write-wins is correct |
| Visit record | Append-only; no shared resource |
| GPS coordinate | Append-only; immutable once captured |
| Photograph | Append-only blob |

Six conflict classes collapse to two — `SC-DUPLICATE` and `SC-SEQUENCE` — and both resolve
deterministically. **The app is cheap because the hard problem was cut out of the release,
not because the app is small.**

### 1.2 The boundary with M9, stated before anything else

`00` §19.1 splits them deliberately, and the split is easy to blur:

| | M8 | M9 |
| --- | --- | --- |
| Owns | Flutter shell, auth, delivery, visits, GPS, photo, **the outbox** | **Push/pull**, idempotency, ordering, sync status |
| Gate | *"Outbox survives kill, restart and storage exhaustion"* | *"Zero loss, zero duplicates"* |

**M8 writes the outbox. M9 drains it.** M8 must therefore be built so that a device with no
network and no sync engine is still a correct, useful tool for a full working day — because
for the whole of M8 that is exactly what it is.

That is not a limitation to work around. It is the acceptance test: **if M8 needs M9 to be
useful, M8 is wrong.**

---

### 1.3 Design principles — the invariants Phase 2 is held to

**Frozen with this document.** Ten statements, each derived from the governing principle or
from a frozen clause. They exist so that a Phase 2 implementation decision can be checked in
one line instead of re-argued, and so a reviewer can cite a number.

**A principle is violated the moment code makes it false — not when it looks untidy.**

| # | Principle | Source | What violating it looks like |
| --: | --- | --- | --- |
| **P-1** | **The device captures facts. It never decides them.** | §1 | A total, a price, a tax or a status computed in Dart |
| **P-2** | **A user action writes to the outbox, never to the network.** The network is a background consequence | §5.1, NFR-OFF-001 | A screen that awaits an HTTP call, or shows a spinner during a save |
| **P-3** | **Money and quantity are `Decimal` end to end.** No `double` on any path that reaches a figure | `05` C-1, AD-02 | `as double`, `jsonDecode` into a numeric field, `double.parse` |
| **P-4** | **The device clock is never on a correctness path.** It labels; it does not order or expire | §5.5, `05` C-8 | Sorting the outbox by local time; expiring a session against `DateTime.now()` |
| **P-5** | **Nothing leaves the outbox unacknowledged, and a `REJECTED` row is never deleted by code.** | §5.3, `05` **C-3**, C-11 | A cleanup that deletes by age; a retry that drops after N attempts |
| **P-6** | **`client_uuid` is generated before the first attempt and never regenerated.** | `05` **C-2**, AD-09 | A new UUID on retry — the one bug that defeats server idempotency |
| **P-7** | **Roles are an array. The UI composes; it never switches on a single role.** | `05` C-12, §4 | `if (role == 'DELIVERY')`; a screen unreachable by a dual-role user |
| **P-8** | **A cached figure is always displayed with its `as_of`.** Stale is acceptable; silently stale is not | §2.3, §5.2 | A KPI or balance rendered with no timestamp |
| **P-9** | **The binary holds no secret and no rule that the server does not independently enforce.** | `02A` §9.3, DV-4, N-06 | An API key in source; a limit checked only on the device; a hidden button as a control |
| **P-10** | **`domain/` imports nothing.** Dependencies point inward only: `features → data → domain` | §2.1 | A Drift or Dio type appearing in `domain/` |

> **Citation correction, 2026-08-11 (v1.4.0).** P-5 cited `05` C-4/C-9 and P-6 cited C-3.
> Checked against `05` §12: **C-2** is the `client_uuid` obligation and **C-3** is the
> never-delete-`REJECTED` obligation — the two were transposed. The principle *statements*
> are unchanged and remain frozen; only the references were wrong. Recorded rather than
> silently corrected because **§14.5 (D-B3) rests on P-6**, and a reader following the old
> citation would have landed on the outbox-retention rule and concluded P-6 had no basis.

**P-3, P-6 and P-9 are the three that cannot be fixed later.** P-3 corrupts figures already
sent; P-6 defeats a server guarantee M9 depends on; P-9 is a security property of a binary
that has already been downloaded. **These get tests, not review comments.**

**P-10 is the one with an existing enforcement precedent.** The backend has `import-linter`
and three contracts; the Dart analogue was added in task 1, not the last task — `reporting`'s
four AST tests were written before `reporting` had a second file, and that is why the
contract still holds.

> **Enforced since task 1** by `backend/tests/adversarial/test_mobile_boundary.py`, in
> Python and inside stage 7 — not by `analysis_options.yaml`, which `make verify` never
> runs and which would therefore have been advisory (TD-37).

---

## 2. Mobile architecture

### 2.1 Four layers, one direction

```
  ┌──────────────────────────────────────────────────┐
  │  presentation   screens, widgets, routing        │
  ├──────────────────────────────────────────────────┤
  │  application    controllers — orchestration only │
  ├──────────────────────────────────────────────────┤
  │  domain         entities, value objects, results │
  ├──────────────────────────────────────────────────┤
  │  data           repositories · outbox · API · db │
  └──────────────────────────────────────────────────┘
```

Dependencies point **downward only**, mirroring the backend's `03` §2.1 layering and
enforced the same way: a structural test, not a convention (§10, task 1).

**`domain` depends on nothing** — no Flutter, no Dio, no Drift. It is the layer that can be
tested without a device, an emulator or a network, and it is where the two things worth
protecting live: `Decimal` money and the outbox state machine.

### 2.2 The repository is the only thing the UI can see

No screen touches `Dio`, the database, or the outbox directly. A repository answers one
question and hides where the answer came from:

```
DeliveryRepository.assignedToday()      -> local cache, always
DeliveryRepository.complete(...)        -> writes the outbox, returns immediately
```

**Writes never await the network.** They append to the outbox and return. That is what makes
the app work identically on 4G and in a basement, and it is why M8 can ship before M9: the
outbox simply grows until a drain exists.

### 2.3 What the app is not allowed to compute

`05` C-6 forbids displaying a locally derived price or tax as authoritative. §1's principle
generalises it: **no price, tax, credit decision, stock availability or authorisation is
computed on the device.** Cached values are displayed with the `as_of` label C-8 requires.

The temptation this forbids is real: *"we already have the products, we could total the
order locally."* That total would eventually disagree with the invoice in front of the
retailer, and the retailer would believe the phone.

---

## 3. Screen inventory by role

`02A` DV-4 puts all three roles in **one binary**. `05` C-12 says `roles` is an **array** —
one person is routinely both `SALESMAN` and `DELIVERY`, and the M0 conftest models exactly
that. **The app must never assume a single role.**

### 3.1 Shared

| Screen | Notes |
| --- | --- |
| Splash / bootstrap | Restore session, decide route |
| Login — OTP | Phone → code. The field path |
| Login — password | Internal fallback |
| Sync status | Last sync, pending count, failed count (FR-SYN-008). **Present at M8 showing outbox depth**; gains server figures at M9 |
| Settings / about | Version, device id, sign out |

### 3.2 `DELIVERY` — the milestone's core

| Screen | Writes | Requirement |
| --- | --- | --- |
| Today's deliveries | — | FR-FUL-* |
| Delivery detail | — | Order lines, customer, address, phone |
| **Complete delivery** | Outbox | Recipient name, time, GPS, photo |
| **Fail delivery** | Outbox | Mandatory reason (`ck_delivery_failed_reason`) |
| Capture photo | Media queue | Separate queue — C-9 |

### 3.3 `SALESMAN`

| Screen | Writes | Notes |
| --- | --- | --- |
| My customers | — | Scoped by zone, server-side (P-3) |
| Customer detail | — | Balance and ageing **labelled `as_of`** (C-8) |
| **Record visit** | Outbox | GPS, outcome, note (FR-SYN payload shape, `05` §11.2) |
| Customer statement | — | Read-only, cached |
| Collections | **Deferred** | FR-REC-010 is **v1.1** — §3.5 |

### 3.4 `OWNER` — **Companion Mode** *(RULED 2026-08-09, replacing "no owner role")*

> **Lightweight read-only operational visibility. All administration and reporting stay on
> the web.**

v1.0.0 recommended no owner surface, on the reasoning that the owner sits at a desk. §12.5
already flagged that as an inference about the client rather than an observation of them.
**The ruling is that a distributor's owner is not at a desk — they are in the market, on a
scooter, at a supplier.** Companion Mode is the right shape: it answers *"is anything wrong
right now?"* without becoming a second admin UI.

| Screen | Content | Backing |
| --- | --- | --- |
| **Today** | The four D-4 numbers: sales today · collected today · total outstanding · orders awaiting dispatch | §3.4.1 — **one endpoint is missing** |
| **Pending deliveries** | Assigned and not yet completed, with the salesman's name | `/deliveries?status=PENDING` ✔ exists |
| **Receivables summary** | Total outstanding, oldest bucket, worst ten customers | `/reports/receivables` ✔ exists |
| **Needs attention** | Confirmed orders not dispatched · failed deliveries · overdue balances | §3.4.2 — **replaces "notifications"** |

**The boundary that keeps this from becoming the admin UI:**

| Companion Mode does | Companion Mode does not |
| --- | --- |
| Read | Write **anything** |
| Show today's operational state | Run reports over arbitrary periods |
| Drill from a number to the list behind it | Export CSV |
| Link out to the web admin for action | Approve, cancel, adjust, price, invoice |

**Read-only is enforced server-side, not by hiding buttons.** An owner token carries owner
scope; the app simply has no write path for it. This is `02A` §9.3 again: the binary is
public, so the absence of a button is not a control.

#### 3.4.1 The four numbers need a backend endpoint that M7 deliberately did not build

`M7_Design_Review` §8.2 states, in terms:

> *"**The owner dashboard is not an endpoint.** It is four scalars rendered by webadmin,
> two of which describe today and are therefore not reproducible. It offers no CSV."*

Checked against what exists:

| D-4 number | Available today? |
| --- | --- |
| Total outstanding | ✔ `/reports/receivables` total |
| Orders awaiting dispatch | ✔ `/reports/order-status`, `CONFIRMED` count |
| Sales today | ✔ `/reports/sales?date_from=today&date_to=today` |
| **Collected today** | ✘ **No total endpoint.** Only `/payments`, a paginated list |

Three of four are reachable; the fourth is not. Composing it on the device would mean paging
payments and summing them — **deriving a figure on the device**, which §1 and `05` C-6
forbid, over 2G.

**Recommendation: add `GET /reports/dashboard`**, returning the four D-4 scalars and **no
CSV**.

Small, and it does not overturn M7's reasoning. Re-read §8.2: the objection is that a
non-reproducible figure *"must not acquire the authority of a document"* — an argument about
**export**, not about accessibility. An endpoint that returns live scalars and offers no
export honours it exactly. `reporting.selectors.dashboard()` already exists, is tested, and
returns precisely these four.

**This puts a backend task inside M8** (§10, task 0). Stated plainly because it is the only
one, and because a mobile milestone quietly growing server work is how scope moves.

> **BUILT 2026-08-10.** `GET /reports/dashboard` ships in `api.v1.report_views.DashboardView`,
> contracted at `05` §9.11.1, verified 8/8 at **726/726, 94.88%**. No CSV; no period
> parameter; the same `_internal` scoping as the seven reports.

#### 3.4.1a What building it found — money was already leaving as a float

Checking how to encode the response surfaced a defect in the **existing** seven report
endpoints, and it is the exact one P-3 exists to prevent, on the server side:

| | |
| --- | --- |
| `05` AD-02 | *"Every monetary and quantity value crosses the wire as a string."* Its rationale names Dart |
| Settings | `COERCE_DECIMAL_TO_STRING: True` — **but that only reaches `serializers.DecimalField`** |
| `report_views._as_json` | Hand-builds its response dict, bypassing serialisation entirely |
| Measured | `json.dumps({"x": Decimal("1180.00")}, cls=rest_framework...JSONEncoder)` → `{"x": 1180.0}` |

**The seven reports emit money as JSON floats.** `jsonDecode` in Dart yields a `double` for
that, and a figure exact through the column, the service and the selector becomes inexact at
the last hop — where no database constraint can see it.

The existing test reads `Decimal(str(body["total"]["sales"]))`. **The `str()` wrapper makes it
pass whichever type arrives**, which is why seven endpoints carried this through four reviews.

**Task 0 fixed only its own endpoint.** Changing the seven is a breaking change to a published
response type and belongs in its own change with its own verification — recorded as **TD-36**,
and it **blocks task 8**, which reads `/reports/receivables`.

> **This is the recurring shape again, in a new place:** a rule enforced on one side of a
> boundary and not the other. AD-02 was enforced in the serializer layer and not in the
> hand-built layer beside it. §12.7 called P-1…P-10 *"asserted, not yet enforced"* the day
> before this was found.

#### 3.4.2 "Notifications" conflicts with a recorded decision — and `02A` supplies the answer

`02A` §7.12's feature matrix lists in-app notifications as Edition 1. **`02A` §13's
Edition-1 re-validation cut them:**

> *"In-app notifications (**M-14 entirely**) | E1 | An 'unactioned orders' filter on the
> order list achieves the same thing for nothing | **0.5**"*

Verified against the code: **no notification model, table, endpoint or milestone exists.**
Building M-14 for Companion Mode would reopen a decision taken to save 0.5 units, and add a
table, an endpoint, a read-state machine and a badge-count sync.

**This is the same shape as M7's C-1…C-6** — `02A` §7.x's matrix predates §13's
re-validation, and §13 governs.

**Recommendation: adopt `02A`'s own substitute.** A **"Needs attention"** screen — one
filtered read across state the server already exposes — satisfies the intent (*the owner
learns what needs them*) at zero backend cost, and is the answer `02A` chose when it made
the cut.

**What is genuinely lost:** *push*. A filtered list must be opened; a notification arrives.
`02A` §7.12 puts push in Edition 2 behind a third-party dependency and a cost line, and A-19
excludes per-message costs. **Companion Mode is a thing the owner checks, not a thing that
interrupts them** — and that should be said out loud rather than discovered.

### 3.5 Deliberately absent, with authority

| Absent | Why |
| --- | --- |
| **Field order capture** | `02A` §5 — the decision the whole edition rests on |
| **Payment collection** | FR-REC-010 is **v1.1**, not v1.0 |
| Retailer screens | M12, Edition 1b |
| Conflict resolution | `02A` §5 — zero classes need human resolution |
| Any report | `S1` only |

> Field order capture is the one a stakeholder will ask for by name. The answer is not
> "later" — it is `02A` §5, and re-opening it re-opens R-1.

---

## 4. Navigation architecture

**Declarative routing, role-derived, with the redirect as the only guard.**

```
/splash  → decide
/login   → /login/otp · /login/password
/home    → role-derived tab shell
           ├ today        (OWNER)      ← Companion Mode, §3.4
           ├ deliveries   (DELIVERY)
           ├ customers    (SALESMAN)
           └ status       (always)
/delivery/:id · /delivery/:id/complete · /delivery/:id/fail
/customer/:id · /customer/:id/visit
/owner/receivables · /owner/attention · /owner/pending-deliveries   (read-only)
/settings
```

Three rules:

1. **Tabs are composed from `roles`, never switched on a "primary role".** A user holding
   both sees both. C-12 exists because getting this wrong hides delivery screens from a
   salesman who delivers — and that person is the client's normal case.
2. **One redirect guard**: unauthenticated → `/login`; authenticated at `/login` → `/home`.
   Route-level role checks are presentation only.
3. **Deep links are not supported in M8.** Nothing external links into the app, and a route
   reachable without the guard is a route reachable without a session.

---

## 5. Offline-first strategy

### 5.1 The requirement is absolute

`02` NFR-OFF-001: *"fully functional for a complete working day with no connectivity"*,
verified by an **8-hour soak test**. NFR-OFF-004: three days of transactions without sync.
NFR-OFF-005: crash, force-close and battery exhaustion must not lose a committed write.

**These are not "offline support". They are the operating condition.** The app is built as
if the network is absent and treats connectivity as an optimisation.

### 5.2 Two stores, different guarantees

| Store | Holds | Guarantee |
| --- | --- | --- |
| **Cache** | Products, customers, orders, deliveries, config | Disposable. Rebuilt by a pull; may be wiped |
| **Outbox** | Every local write, in creation order | **Durable. Nothing is ever deleted before acknowledgement, and a rejected operation is never deleted at all** (C-3) |

Conflating them is the defect to avoid: a cache is a convenience, an outbox is a promise.

### 5.3 The outbox state machine

```
PENDING ──sent──> IN_FLIGHT ──ack──> ACKNOWLEDGED ──> (purged after N days)
   ▲                  │
   └───── retry ──────┘
                      └──rejected──> REJECTED   (never auto-deleted — C-3, FR-SYN-006)
```

| Property | How |
| --- | --- |
| Durable | Committed to disk in the same transaction as the UI's confirmation. **The user is never told "saved" before it is** (NFR-OFF-005) |
| Ordered | Monotonic per-device sequence, not a timestamp (BR-013, FR-SYN-002). **The device clock is never on the correctness path.** Mechanism frozen at **§14.9 D-C1**; the server-side half at **D-C2** |
| Idempotent | `client_uuid` generated **before the first attempt** and reused on every retry (C-2, AD-09) |
| Never lost | No delete path from `REJECTED`. A malformed payload is quarantined, not dropped (FR-SYN-006) |
| Encrypted | At rest (FR-SYN-016, NFR-SEC-008) |

**At M8 the machine stops at `PENDING`.** No transition out of it exists until M9. Building
the full state set now is not speculative: the M8 gate is *"outbox survives kill, restart and
storage exhaustion"*, and a schema that has to grow states at M9 is a migration on a device
already carrying a farmer's week of unsent work.

### 5.4 Media is a separate queue — not a nicety

`05` C-9 and §10.7: **a 200 KB photo on 2G must never block a delivery confirmation.** Two
queues, drained independently. If the photo fails, the delivery still submits with
`photo_media_id: null`.

### 5.5 The clock is not trusted, anywhere

`05` P-2: the client stores `server_time` and sends it as the next `since`. A device five
minutes fast would send a future `since` and **silently skip every record in that window.**

M8 does not pull yet, but it stores `server_time` from the login response from day one. If
M8 persists a device timestamp as the sync cursor, M9 inherits a silent data-loss bug.

*(M7 §12.2 has just paid for this lesson on the server: four tests read the wall clock while
asserting against a constant, and one failed the morning the date rolled.)*

### 5.6 **ADR required — the local database**

Drift (SQLite, typed, transactional, migration-aware) versus Hive/Isar versus files.

The outbox needs **atomic multi-row commits**, **ordered reads** and **schema migration on a
device that cannot be wiped**. Recommendation is **Drift with SQLCipher**, but the choice is
irreversible in the sense that matters: changing it after M9 means migrating outboxes on
devices in the field.

> #### Amendment — 2026-08-25 (D-M9-8). The database is Drift; the cipher is no longer SQLCipher.
>
> **The paragraph above stands unaltered and none of its reasoning is affected.** Drift was
> chosen for atomic multi-row commits, ordered reads and migration on a device that cannot be
> wiped; not one of those concerns a cipher. **The ADR's conclusion is unchanged.** What
> changes is the implementation behind `PRAGMA key`.
>
> **The requirement did not change and is not amended.** FR-SYN-016 and NFR-SEC-008 require
> *"encrypted at rest"* and name no cipher, library or algorithm. `02` receives no amendment.
>
> **V1 as built and proven:**
>
> | | |
> | --- | --- |
> | Mechanism | the `package:sqlite3` build hook — `hooks: user_defines: sqlite3: source: sqlite3mc` |
> | Native asset | SQLite3MultipleCiphers — **one library for both the verification host and Android** |
> | Observed cipher | `chacha20` — **recorded, not required** (D-M9-8 §2) |
> | Observed SQLite | `3.53.4` — **recorded, not required** |
> | Key source | **unchanged** — the Android keystore via `PlatformDatabaseKey` |
> | Runtime guard | `connection.dart` refuses to open the database if `PRAGMA cipher` is empty — a hard throw in **every build mode**, not an `assert` |
> | Gate | `make mobile-device-encryption` |
> | Proven on | **Pixel 8a API 34 emulator, `android-x64`. Not arm64, not physical hardware** (TD-45) |
>
> **Why SQLCipher was not carried forward** — full reasoning at D-M9-8 §3; in short:
>
> 1. **It was never actually in use.** `sqlcipher_flutter_libs` feeds `open.overrideFor`, an API
>    `package:sqlite3` 3.x removed, so no call site was possible. The 2026-08-24 APK carried
>    upstream `libsqlite3.so` beside 13.8 MiB of `libsqlcipher.so` that nothing could open.
>    Against upstream SQLite `PRAGMA key` is an unrecognised pragma — ignored, not failed — so
>    the outbox shipped in cleartext for a milestone with no test able to see it.
> 2. **`source: sqlcipher` was tried first and does not run in the pinned environment.** Its
>    Linux prebuilt requires `GLIBC_2.38`; `docker/flutter.Dockerfile` is `debian:bookworm-slim`
>    (2.36). 151 of 317 tests died in `dlopen`.
> 3. **`source:` is one global value** — per-OS selection is unimplemented upstream
>    (`simolus3/sqlite3.dart#346`, open) — so one library must serve host and device.
>
> **Why this was free now and will not be later.** The paragraph above warns the choice is
> irreversible *"after M9 … devices in the field"*. **There are no devices in the field**, and
> the one emulator database was plaintext and had to be cleared regardless. That condition never
> triggered, which is exactly why this was settled before M11 rather than after.
>
> **Gate status, stated precisely** *(updated 2026-09-01)*. The **encryption** gate is closed.
> **`00` §19.2's durability gate — *"Outbox survives kill, restart and storage exhaustion"* —
> is PARTLY closed.** `make mobile-device-kill` **passed on 2026-09-01**, Pixel 8a API 34
> emulator, evidence in §5.6.1. `make mobile-device-storage` **still has no recorded run**, so
> the *storage exhaustion* clause of §19.2 remains open. Nothing in this amendment may be cited
> as evidence for either; §5.6.1 is the only record of the kill result.


### 5.6.1 Kill-gate evidence — `make mobile-device-kill`, 2026-09-01

**VERIFIED.** First recorded run. Discharges `02` NFR-OFF-005 — *"Application termination —
crash, force-close, battery exhaustion — MUST NOT lose a **committed** local transaction"* —
by its own stated method, *"kill-test at each write boundary"*. It does **not** discharge the
*storage exhaustion* half of `00` §19.2; that gate has still never been run.

| Field | Value |
| --- | --- |
| Command | `make mobile-device-kill`, run from WSL |
| Device | `emulator-5554` — Pixel 8a, API 34, Google APIs, x86_64 |
| Toolchain | host Windows Flutter 3.44.7 via `scripts/win-flutter.sh`; Gradle 9.1.0; JDK 18 |
| Result | **passed** |

Phase 1 — commit, then die:

```
GATE-P1: database deleted
GATE-P1: 5 appends committed
GATE-P1: 3 claimed IN_FLIGHT
GATE-P1: KILL-NOW
DriverError: ext.flutter.driver: (112) Service has disappeared
phase 1 terminated abnormally, as designed
```

`KILL-NOW` is the last line the process can print, so reaching it is what proves the signal
was sent **after** both commit boundaries were crossed rather than during either. The
`DriverError` is the host driver observing the VM service vanish; the Makefile's check on this
phase is **inverted**, and a clean exit would have failed the gate instead.

Phase 2 — reopen and account for everything:

```
GATE-P2: database=4096B wal=119512B shm=present
00:01 +2: All tests passed!
```

The file sizes are themselves evidence: a 4 KiB main database beside a ~117 KiB `-wal` and a
live `-shm` is a database killed **mid-WAL**, with no checkpoint — the condition NFR-OFF-005
describes. Every assertion held: all five committed appends present, the three `claimBatch`
rows still `IN_FLIGHT`, the claim landed positionally on rows 1–3, and the `AUTOINCREMENT`
sequence continued without reuse (**D-C1**).

**Not claimed by this run:** storage exhaustion (`make mobile-device-storage`, never run),
`arm64`, physical hardware, and any device other than the one named above. **TD-45** stands.

---

## 6. State management

### 6.1 Recommendation: **Riverpod**

Justification against the two alternatives a reviewer will raise:

| Option | Assessment |
| --- | --- |
| **Riverpod** | **Recommended.** Compile-time safe dependency injection, testable without widgets, and — decisively — **`AsyncValue` models loading/data/error as one type**, which is the shape every screen in this app actually has |
| BLoC | Well-proven and explicit, but every screen needs event and state classes for what is mostly "show cached data, queue one write". Ceremony without a matching benefit here |
| `setState` + `InheritedWidget` | Sufficient for the shell, insufficient the moment two screens observe outbox depth |

### 6.2 The argument that actually decides it

**This app's hard state is not UI state — it is the outbox.** Its truth lives in SQLite, and
the state layer's job is to *observe* it, not to own it.

Riverpod's stream providers over Drift watch-queries give exactly that: the outbox-depth
badge, the delivery list and the sync screen all observe the same database and cannot drift
apart. **A pattern that encourages the queue to live in memory is a pattern that loses
transactions when the OS kills the app.**

The recommendation is therefore weaker than it looks: *any* solution that keeps durable state
in the database and treats the state layer as a view over it would be acceptable. Riverpod is
the smallest one that does so naturally.

---

## 7. Networking and API layer

### 7.1 Non-negotiables from `05` §12

Four of the twelve client obligations *each individually* break a guarantee:

| # | Obligation | If broken |
| --- | --- | --- |
| **C-1** | Money and quantity parsed as **`Decimal`, never `double`** (AD-02) | Silent rounding on invoices |
| **C-2** | `client_uuid` generated before the first attempt, reused on retry | Duplicate orders and payments |
| **C-3** | A `REJECTED` operation is **never deleted** | A lost transaction |
| **C-5** | `server_time` as the next `since`, never the device clock | Permanently skipped records |

**C-1 deserves emphasis: Dart has no `Decimal`.** `jsonDecode` will produce `double` for any
unquoted number. `05` AD-02 sends money as a **string** precisely so the client can parse
exactly — and a single careless `as double` reintroduces the defect the whole `core.fields`
discipline exists to prevent. This must be enforced by a **codec, not a convention** (§10,
task 3).

### 7.2 Shape

```
ApiClient (Dio)
 ├─ AuthInterceptor      attaches the access token
 ├─ RefreshInterceptor   refreshes ONCE on 401 TOKEN_EXPIRED, then re-auths (C-7)
 │                      **single-flight, isolated client, identity-preserving retry —
 │                      see §14.3, §14.4, §14.5. The server rotates AND blacklists
 │                      refresh tokens, so parallel refresh logs the user out.**
 ├─ DeviceInterceptor    device_id on every write (C-10)
 └─ ProblemInterceptor   RFC 9457 problem+json -> typed failures
```

`05` returns RFC 9457 for every error with a stable machine-readable `code`. **The client
branches on `code`, never on `detail`** — `05` says `title` and `detail` may be reworded
without breaking a client.

### 7.3 Failures are values, not exceptions

Every repository returns a result type. A field app has no "unexpected" network failure — no
signal is the normal state, and an app that throws on it will throw all day.

### 7.4 What M8 calls, and what it does not

**Calls:** `/auth/*`, `/deliveries*`, `/customers*`, `/media`.
**Does not call:** `/sync/pull`, `/sync/push`, `/sync/status` — M9.

M8 reads through the ordinary REST endpoints and caches the responses. **The cache schema is
designed to be what `/sync/pull` will fill**, so M9 replaces the filling mechanism without
touching the readers.

### 7.5 **ADR required — HTTP client and offline auth window**

Dio versus `http` + hand-rolled interceptors; and the FR-IAM-016 offline authentication
period. `02` OI-5 records the default as **7 days, configurable**, due at M8. That number is
a security decision: it is how long a lost, unreported device keeps working (R-8).

---

## 8. Authentication and session

### 8.1 Two paths, one session

| Path | Use |
| --- | --- |
| **OTP** (`/auth/otp/request` → `/auth/otp/verify`) | The field default. FR-IAM-001 |
| **Password** (`/auth/login`) | Internal fallback |

Both return access and refresh tokens plus the user payload with **`roles` as an array**.

### 8.2 Storage

| Item | Where |
| --- | --- |
| Refresh token | **Platform keystore** (`flutter_secure_storage` → Android Keystore) |
| Access token | Memory. Re-derived from refresh on cold start |
| Cached user, roles | Encrypted local DB |
| Local auth material | FR-IAM-016 — §8.3 |

**No token in shared preferences, no token in the outbox, no token in a log.** FR-IAM-015:
credentials must not reach logs, audit records, error messages or crash reports — which
makes the crash reporter a place this rule can be broken accidentally.

### 8.3 Offline authentication is a security decision

FR-IAM-016: offline surfaces authenticate **locally against cached credential material** for
a configurable maximum period, after which sync is required. OI-5's default is 7 days.

Beyond the window the app **stops accepting a local unlock and requires a server round-trip**
— but it must still surrender nothing: the outbox is not readable, and it is **not erased**.
A device that locks out with three days of unsent deliveries must still be able to hand them
over once it reaches signal.

> **Frozen at §14.12 (v1.7.0).** This section states the *requirement* and left three things
> undefined that an implementation cannot proceed without: what time is trusted, where the
> period is configured, and what *"cached credential material"* is. D-D1…D-D6 answer them.
> The `| Local auth material | FR-IAM-016 — §8.3 |` row in §8.2 pointed here and found nothing;
> **D-D6 is what it now points to.**

### 8.4 Device identity

`device_id` is generated once, stored in the keystore, and sent on **every write** (C-10,
FR-IAM-009). It is the attribution in the audit trail and the unit FR-IAM-010 revokes.

### 8.5 The condition M8 must not violate

From `02A` §9.3, restated because it is the one thing that makes DV-4 acceptable:

> **The binary contains no API key, secret, internal endpoint or business rule whose
> confidentiality matters.** Role-based UI is presentation only.

A structural test asserts no secret-shaped constant ships in the binary (§10, task 1).

---

## 9. Folder structure

```
mobile/
├── lib/
│   ├── main.dart
│   ├── app/                    bootstrap, router, theme, DI
│   ├── core/                   Result, Decimal codec, failures, clock, logging
│   ├── domain/                 entities · value objects · repository INTERFACES
│   │   ├── identity/  delivery/  customer/  outbox/
│   ├── data/
│   │   ├── api/                Dio client, interceptors, DTOs
│   │   ├── db/                 Drift schema, DAOs, migrations
│   │   ├── outbox/             queue, sequencer, state machine
│   │   └── repositories/       implementations of the domain interfaces
│   └── features/               one folder per feature, presentation + controllers
│       ├── auth/  deliveries/  customers/  visits/  sync_status/  settings/
├── test/                       unit — domain and outbox, no Flutter binding
├── integration_test/           on-device: kill, restart, storage exhaustion
└── pubspec.yaml
```

Two properties this shape exists for:

- **`domain/` imports nothing from `data/` or `features/`.** Repository *interfaces* live in
  `domain`, implementations in `data` — so the domain compiles without Flutter and the
  outbox is testable on a laptop.
- **`features/` is presentation.** Business logic in a feature folder is the mobile form of
  the N-01 violation the backend has spent seven milestones refusing.

---

## 10. Phase 2 plan — implementation task decomposition

**Ordered by dependency, not by visibility.** Each task is one logically complete unit that
compiles, runs and is verified before the next opens. The principle it is held to is named,
so a review has something to check against.

| # | Task | Principles | Gate |
| --: | --- | --- | --- |
| ~~**0**~~ | ~~**Backend: `GET /reports/dashboard`**~~ | — | ✔ **DONE 2026-08-10** — 8/8, **726/726**, 94.88%, `mypy` clean, 3 contracts kept |
| **1** | Toolchain, shell, DI, router; **`analysis_options.yaml` layering rule and the no-secrets structural test** | P-9, P-10 | The contract tests exist **before** the first feature |
| ~~**2**~~ | ~~Decimal codec and the API layer~~ | — | ✔ **DONE 2026-08-11** — 8/8, **743/743**, 94.88%; `mobile-verify` **38/38**, 0 analyzer errors |
| **3** | **← NEXT. Drift schema, outbox, sequencer.** ~~Blocked on TD-39~~ — **unblocked 2026-08-11**; decisions frozen at §14.9 | **P-2, P-5, P-6** | Schema · sequence · PENDING-only append · **restart** durability · `StorageFull` classification. **Process-kill and real storage exhaustion are task 10's** (§14.11) |
| 4 | Auth: OTP, password, keystore, refresh-once, device id, offline window | P-4, P-9 | C-7, FR-IAM-015, FR-IAM-016 |
| 5 | Delivery: list, detail, complete, fail | P-1, P-2, P-7 | No screen touches the network to save |
| 6 | GPS and the **separate media queue** | P-2, P-5 | C-9. Media never blocks a transactional row |
| 7 | Customers, visits | P-1, P-8 | — |
| 8 | **Owner Companion Mode** — Today · pending deliveries · receivables · needs attention | **P-1, P-8, P-9** | Read-only; every cached figure carries `as_of`; no write path exists |
| 9 | Sync-status screen (outbox depth) | P-8 | FR-SYN-008, necessarily partial until M9 |
| 10 | **The 8-hour offline soak** (NFR-OFF-001) and the M8→M9 gate | P-2, P-5 | **Measured on a real device, not assumed** |

### 10.1 What the ordering is actually protecting

**Task 3 is the milestone.** Everything else is screens over a REST API that already exists
and is already verified. If task 3 is wrong, M9 inherits a corrupt queue and both
non-negotiable sync metrics become unreachable.

**Tasks 1 and 2 come before any feature deliberately.** M7's four AST tests were written
when `reporting` had one file, and that is the reason the contract still holds at seven. The
Dart equivalents are worth nothing written last — by then the violation is the code.

**Task 0 is first because it is a different toolchain.** It goes through `make verify`, gets
committed, and is finished before Flutter enters the repository. Mixing a Django change into
a Dart milestone is how a green gate stops meaning anything.

**Task 8 is late on purpose.** Companion Mode is read-only over endpoints that already exist;
it carries no risk that task 3 does not already carry, and no other task depends on it. If
M8 runs long, **task 8 is the first thing that can move to M8.1 without breaking the
milestone gate** — task 10 cannot.

### 10.2 Entry conditions for Phase 2

| # | Condition | State |
| --: | --- | :-: |
| 1 | §13 signed, both ADRs approved | ✔ 2026-08-10 |
| 2 | §1.3 principles frozen | ✔ |
| 3 | **TD-32 closed** — retire the superseded `==` dev pins (`NEXT_TASK.md`) | ☐ **Do before the Dart toolchain lands** |
| 4 | **K-1 keystore procedure agreed** — generated once, two off-machine backups, never in Git | ☐ |
| 5 | **TD-11 — DLT registration started** | ☐ **External, unbounded lead time** |
| 6 | Flutter SDK version pinned, as `uv.lock` pins Python (TD-21's reasoning applies unchanged) | ☐ Decide in task 1 |

> **Conditions 3 and 6 are the same lesson.** TD-21 was closed *before* a second toolchain
> arrived, precisely so that reproducibility was settled with one language in the repository.
> Phase 2 adds the second. **Pin Dart the way Python is pinned, on the first day.**

---

## 11. Risks, trade-offs and open items

| # | Risk | Severity | Position |
| --: | --- | :-: | --- |
| **AR-1** | **`double` reaches money.** Dart has no `Decimal`; `jsonDecode` yields `double` | **Severe** | Codec + a test that fails on any `double` in a money path (§7.1) |
| **AR-2** | **The outbox loses a write on kill.** NFR-OFF-005, and the M8→M9 gate | **Severe** | Commit before confirming; kill-test at **every** write boundary |
| **AR-3** | An outbox schema change at M9 migrates devices holding unsent work | **High** | Full state machine at M8 (§5.3) |
| **AR-4** | Role assumed singular; delivery screens vanish for a salesman who delivers | **High** | C-12; compose tabs from the array; test the both-roles user |
| **AR-5** | **The keystore is lost.** `00` §2.3 K-1: *"the application can never be updated again"* | **Severe** | Not an M8 code risk — an M8 **procedure** risk. K-1 at generation, verified at M11 |
| **AR-6** | Device clock persisted as a sync cursor | High | §5.5. M9 inherits silent loss if M8 gets this wrong |
| **AR-7** | Stale cache read as a guarantee | Medium | C-8 `as_of` labels on every cached balance and stock figure |
| **AR-8** | Scope pressure to add field order capture | Medium | `02A` §5. Re-opening it re-opens R-1 |

### 11.1 Trade-offs accepted

**One binary for three roles** (DV-4) — cheaper, and safe *only* under §8.5. **Android only,
API 26+** (DR-3). **No iOS** (O10). **PO-2 only partially achieved** in Edition 1: phoned-in
orders are still keyed by the owner — but they were before, so nothing is worse and the
portal channel is strictly better.

### 11.2 Open items for the Product Architect

| # | Item | State |
| --: | --- | :-: |
| 1 | **ADR — local database** (§5.6): Drift + encrypted SQLite | ✔ **Approved 2026-08-10.** Cipher amended by **D-M9-8** (2026-08-25) — SQLite3MultipleCiphers via the `sqlite3` build hook. Drift unchanged |
| 2 | **ADR — HTTP client and the FR-IAM-016 offline window** (§7.5): Dio | ✔ **Approved 2026-08-10** |
| 3 | ~~Does the owner get mobile screens?~~ | ✔ **Ruled: Owner Companion Mode** (§3.4) |
| 4 | **No payment collection** in M8 — FR-REC-010 is v1.1 (§3.5) | ✔ Confirmed |
| 5 | **TD-11 — SMS/DLT registration** is on M8's critical path: OTP login is the field default and DLT approval has unbounded lead time. `00` §2.4's contingency is owner-provisioned passwords, recorded as a deviation | ☐ **Open** |
| ~~**6**~~ | ~~`GET /reports/dashboard`~~ | ✔ **Built and verified 2026-08-10** (§3.4.1) |
| **8** | **TD-36 — the seven report endpoints emit money as JSON floats** (§3.4.1a). AD-02 violated by `_as_json` bypassing serialisation. **Breaking change to a published response type**, so it is its own change with its own verify | ☐ **New — blocks task 8** |
| **7** | **"Notifications" was cut from Edition 1** by `02A` §13 (M-14 entirely, 0.5 units). Recommendation: adopt `02A`'s own substitute — a **"Needs attention"** filtered read — rather than reopening the cut (§3.4.2) | ☐ **New — decide before task 8** |

> **Item 5 is the one that can stop this milestone from outside it.** Everything else here
> is engineering.
>
> **Items 6 and 7 arrived with Companion Mode and were not visible when it was requested.**
> Neither changes the architecture; both change what task 8 is allowed to build. Item 7 in
> particular is a request that a frozen document has already answered — recorded here so the
> answer is a decision rather than a surprise during implementation.

---

## 12. Self-critique

**1. §6's recommendation is softer than it appears.** I argue Riverpod and then concede any
solution keeping durable state in the database would do. That is honest, and it means the
choice is worth less scrutiny than §5.6's database ADR — which is the one that is genuinely
hard to reverse.

**2. I have specified an outbox state machine M8 cannot exercise.** Only `PENDING` is
reachable until M9. The justification — avoiding a device-side migration — is real, but the
cost is that `ACKNOWLEDGED` and `REJECTED` ship untested through a milestone. If the M9
design finds the shape wrong, M8 will have shipped dead code that looks load-bearing.

**3. The 8-hour soak is specified and not designed.** NFR-OFF-001 names the method; task 9
names the task. How it is actually run — a real device, a day of representative volume, who
watches it — is not settled here, and a soak test nobody schedules is a requirement nobody
meets. FR-RPT-015 sat unmeasured for exactly this reason until three days ago.

**4. Effort.** 3.0 units, the largest single milestone in Edition 1, and the first in a
language and toolchain this project has never built in. Every M5–M7 estimate held; **none of
them involved a new platform.** I have no basis for predicting cycles and will not offer one.

**5. Owner screens — this critique was upheld within a day.** v1.0.0 recommended none, on
the reasoning that the owner sits at a desk, while admitting that was an inference rather
than an observation. **It was overturned by one sentence from the business, which is exactly
what this paragraph predicted.** Kept verbatim rather than deleted: the reasoning was sound
and the premise was invented, and that is the failure mode worth being able to recognise
again. The §3.4 ruling is right; v1.0.0's §3.4 was not wrong about duplication, it was wrong
about the user.

**6. Companion Mode's dependencies were checked after it was approved, not before.** §3.4.1
and §3.4.2 exist because I verified the four KPIs and the notification feature against the
code and `02A` *after* the ruling — and found one missing endpoint and one feature cut by a
frozen document. Had the ruling been implemented directly, task 8 would have discovered both
mid-milestone. **The check cost minutes; it belonged in the same minutes as the request.**

**7. §1.3's principles are asserted, not yet enforced.** P-1…P-10 currently have the status
that TD-2's type gate had for six milestones: *advisory*. Only P-3, P-9 and P-10 have a named
mechanism in §10, and P-1, P-4 and P-8 have none — they are review comments, and this project
has already recorded what review comments are worth against a path the tests do not take.

**9. Task 1's cost was entirely infrastructure, and three of its four defects lied about
where they were.** A dead image registry, a pub cache that did not survive the container
boundary, an analyzer whose defaults differ from `dart analyze`, and a directory never
bind-mounted. None was in the Dart. What they share is that **the error message named the
wrong layer**: 51 `uri_does_not_exist` errors that read as broken source were a missing
cache; *"the Flutter pin is not stated exactly once"* was a missing mount.

**The design review predicted the wrong risk.** §11.2 lists AR-1…AR-8 — `double`, the
outbox, the keystore — all real, none of them what this task actually cost. **§10.1's claim
that "everything else is screens over a REST API that already exists" is true and was
irrelevant**, because the milestone was not spent on screens. A second toolchain is not a
line item; it is a second set of assumptions about how things fail.

**8. Task 0 found a server-side defect four milestones of review did not** (§3.4.1a). AD-02
has been frozen since `05` was written; the seven report endpoints have violated it since M7;
four reviews and a newly blocking type gate all passed over it. It surfaced only because
someone had to decide, concretely, how to encode **one number** — and that decision required
reading what the encoder does rather than what the setting says.

**The transferable part is not "check the encoder".** It is that §12.6 repeated inside the
same milestone: I wrote §3.4.1 asserting three of four numbers were *"reachable"* without once
asking in what **type** they were reachable. A claim about behaviour is worth whatever the
check behind it cost, and here the check was one line of Python that I ran a day late.

---

## 13. Sign-off

**Signed 2026-08-10.**

| # | Item | Party | Status |
| --: | --- | --- | :-: |
| 1 | §1 governing principle and the §1.2 M8/M9 boundary | All | ✔ |
| 2 | §2 layering; §9 folder structure | All | ✔ |
| 3 | §3 screen inventory — **§3.4 Owner Companion Mode** *(replaces "no owner role")* | Product Architect | ✔ |
| 4 | §5 offline strategy and the §5.3 outbox state machine | All | ✔ |
| 5 | §6 Riverpod | All | ✔ |
| 6 | §7–§8 networking, auth, and the §8.5 condition | All | ✔ |
| 7 | **ADR — local database:** Drift + encrypted SQLite (§5.6; cipher amended by D-M9-8) | All | ✔ |
| 8 | **ADR — HTTP client and offline window:** Dio (§7.5) | All | ✔ |
| 9 | §11.2 items 4 and 5 | Product Architect | ✔ / ☐ open |
| 10 | **§1.3 Design Principles P-1…P-10** | All | ✔ **Frozen** |
| 11 | §10 Phase 2 plan | All | ✔ |
| 12 | This document accepted | All | ✔ |

### 13.1 What is frozen, and what freezing means here

**Frozen:** §1 (principle and boundary), **§1.3 (P-1…P-10)**, §2, §3, §4, §5, §6, §7, §8, §9.

A frozen clause is not reopened by an implementation preference. It is reopened by a
**verified contradiction** — the same standard M5, M6 and M7 were held to, and the reason
`02A` §5 can still answer the field-order-capture question without re-arguing it.

### 13.2 The two things that were **not** settled by this signature

| # | Item | Blocks |
| --: | --- | --- |
| ~~**6**~~ | ~~`GET /reports/dashboard`~~ | ✔ **Closed by task 0** |
| **7** | "Notifications" vs `02A` §13's cut (§3.4.2) — recommendation: the "Needs attention" substitute | **Task 8 only** |
| **8** | **TD-36** — money as floats on the seven report endpoints (§3.4.1a) | **Task 8 only** |

**None blocks Phase 2 from proceeding.** All sit inside task 8, which §10.1 places last for
this reason. **Tasks 1–7 are unblocked.**

> **TD-11 still blocks nothing in engineering and everything in go-live.**

---

## 14. Phase 2 frozen decisions

Decisions taken **during** Phase 2, after an independent review of the task 2 design. They
bind implementation the way §1.3's principles do. Recorded here rather than in §7 because
they were settled against evidence from the running system, not from the design.

**Every claim below was checked against the repository.** Where the review that prompted
them was wrong, the correction is recorded with it — a review's errors are as reusable as
its findings.

### 14.1 D-A1 — Delivery idempotency is keyed on `client_uuid`

**Frozen.** `POST /deliveries/{id}/complete` and `POST /deliveries/{id}/fail` are
contractually idempotent: `05` §9.4 marks both **`Idem ✓`**, §6's *"Applies to"* names
`/complete`, and `M5_Design_Review` F-5/F-6 state *"Idempotent on `client_uuid`"*.

**They do not honour that keying.** Verified in `fulfilment/services.py`: both take a row
lock (`_lock_dispatched`) and then

```python
if locked.status != Delivery.Status.PENDING:
    return locked        # F-5 / F-6
```

so replay is keyed on **`delivery.id` + status**, not on `client_uuid`.

**What is already correct, and must not be broken by the fix:**

| Guarantee | Evidence |
| --- | --- |
| No duplicate stock movement | `test_failing_twice_does_not_return_the_stock_twice` |
| Completing twice is a no-op | `test_completing_twice_is_a_no_op` |
| Replay returns the original resource, `200`, not an error | `Response(DeliverySerializer(delivery).data)` — satisfies I-4 |
| Concurrent double-submit serialises | `SELECT … FOR UPDATE`, which is what I-6 exists to require |

**Severity: a contract-conformance gap, not a data-integrity one.** The independent review
rated it *Severe* on the ground that it could produce *"double stock movements"*. **It cannot** —
the guard and its tests prevent exactly that. Recorded because a severity attached to an
impossible consequence is how effort is spent in the wrong place.

**Recorded as TD-39.**

### 14.2 D-A2 — TD-39's scope and position

**A separate Django milestone and commit, landing before task 3.**

| | |
| --- | --- |
| **Does** | Accept `client_uuid` on `/complete` and `/fail`; on a seen key return **200 with the original resource** (I-4); leave behaviour unchanged when the field is absent |
| **Does not** | Invent an M8-side operation store; migrate or pre-empt `sync_operation`, which is **M9's** (`04` T-26); change the `delivery` model's own `client_uuid`, which belongs to the *assignment* |
| **Also** | Correct `05` §6's *"Applies to"* line, which lists `/complete` and **omits `/fail`** while §9.4 marks both ✓. The text is how someone later concludes `/fail` was never in scope |

**Why separate from task 2.** It is a Django change inside a Dart milestone. Task 0 was kept
separate for that reason and it held; **mixing toolchains in one commit is how a green gate
stops meaning anything.**

**Why before task 3.** The outbox schema stores a `client_uuid` per queued operation. If the
endpoints do not accept one, task 3 either omits the column — and **AR-3** says an outbox
schema change at M9 migrates devices holding unsent work — or persists a field the server
ignores, which is worse than either.

### 14.3 D-B1 — Refresh is single-flight  ·  **BUILT, task 2**

**Frozen semantics:**

> **Concurrent `401 TOKEN_EXPIRED` responses share exactly one refresh operation. Waiting
> requests await the same result. On success each original request is retried exactly once.
> A second `401` after that retry is terminal — sign out, never recurse.**

**This is not a style preference.** `config/settings/base.py` sets

```python
"ROTATE_REFRESH_TOKENS": True,      # 05 §7.1
"BLACKLIST_AFTER_ROTATION": True,   # reuse detection
```

Rotation **with blacklisting** is precisely the configuration under which parallel refresh is
destructive: the first call rotates and blacklists the token, the second presents a
blacklisted token, and **reuse detection treats it as an attack.** Three requests failing
together can therefore log the user out of a working session. C-7's *"refresh once, then
re-authenticate, never loop"* is the client half; this is what it means under concurrency.

### 14.4 D-B2 — The refresh call is structurally isolated  ·  **BUILT, task 2**

**Frozen.** `/auth/refresh` executes through a **separate `Dio` instance carrying neither
`AuthInterceptor` nor `RefreshInterceptor`.**

Isolation by construction, **not by a re-entrancy flag.** The same reasoning as
`DashboardView` declaring only `JSONRenderer`: an absent interceptor cannot be defeated by a
later edit, whereas a flag is a rule someone deletes while adding a feature. A refresh call
that could itself trigger the refresh interceptor is an infinite loop reachable from one
expired token.

### 14.5 D-B3 — A retry preserves operation identity  ·  **BUILT, task 2**

**Frozen.** Retrying a request replays the original request unchanged — body, request-scoped
headers, and **especially any `client_uuid`**. **The retry must never generate a new operation
identity.**

This is **P-6** at the transport layer. `05` C-2 requires the key to be minted before the
first attempt and reused on every retry; a refresh-and-retry path that rebuilds the request
is the most plausible place in the whole client for a second UUID to appear, because the code
that retries is not the code that created the operation.

### 14.6 Rejected — a dashboard DTO in task 2

The same review recommended a *"`TypedDict`-equivalent"* dashboard DTO with `Decimal` fields,
to contain TD-36 on the client. **Rejected on scope and on principle.**

- The dashboard is **task 8**, contracted at `05` §9.11.1. Task 2 has no caller for it.
- `DeliverySerializer` was checked: **`/deliveries` carries no money at all**, only lat/long.
  The DTO would have no caller in tasks 2–7 either.
- **TD-36 is a server-side defect with a server-side fix.** Building a client-side workaround
  now hard-codes a bug we intend to remove, and makes removing it a two-sided change.
- *(`TypedDict` has no Dart meaning; Dart has classes and records. The recommendation carried
  Python vocabulary into a Dart review.)*

### 14.7 One thing the review got structurally wrong

It cited **`M9_NEXT_TASK.md`** — a file that does not exist in this repository — and quoted it
verbatim as the evidence for D-A1. The sentence is a restatement of an engineering note from
the preceding session, re-presented as a citation.

**The finding survived; the evidence for it did not.** Recorded because the finding was
accepted on re-verification against the code, and would have been accepted for the wrong
reason had nobody checked the source.

### 14.8 What building §14.3–§14.5 taught

**The decisions held. The thing that nearly defeated them was the test harness.**

It stored live `RequestOptions`. D-B3 replays the *same* object — that is the mechanism, it
is how the body and `client_uuid` survive — and `AuthInterceptor` then rewrites that object's
header in place. So every recorded attempt showed the final token, and the assertion meant to
prove P-6:

```dart
expect((writes.first.data as Map)['client_uuid'], (writes.last.data as Map)['client_uuid']);
```

was **comparing an object with itself.** A test that could not fail, guarding one of the three
principles §1.3 calls unrepairable. Fixed by snapshotting each request at the adapter.

**Two contract details the frozen text did not carry, both found by implementing it:**

- **`device_id` goes in the body.** §7.2's diagram says *"device_id on every write"* and no
  more. `05` §9's examples and the DRF serializers both read it from `request.data`; a
  header would be accepted by the transport and ignored by the server — the silent
  attribution loss C-10 exists to name.
- **Offline during refresh must not sign the user out.** D-B1 specifies the 401 path and is
  silent on a refresh that never arrives. Clearing the keystore there would end FR-IAM-016's
  offline window at the first tunnel, so only a 401 clears.

**And one framework default that would have made the whole decision inert:**
`validateStatus: (_) => true` reads as tidy — every response becomes a value — but Dio then
never enters its error path, and `RefreshInterceptor.onError` becomes code no 401 can reach.
**D-B1 would have been implemented, documented, tested against a fake, and dead.**

### 14.9 Task 3 decisions — frozen 2026-08-11

Four decisions, taken before task 3 opens, after tracing the M8 → M9 → server path against
`02`, `04` and `05`. **Task 3 remains the outbox only; the media queue is task 6** (§10),
and **M8 still writes `PENDING` only** (§5.3).

#### D-C1 — The local sequence is an `AUTOINCREMENT` integer primary key

One column, serving as both row identity and queue order.

**Accepted on the purge argument, not on ubiquity.** §5.3 requires `ACKNOWLEDGED` rows to be
*"purged after N days"*. A plain `INTEGER PRIMARY KEY` assigns `max(rowid) + 1`, so deleting
the highest row **lowers the next value and re-issues one already used** — monotonicity
gone. `AUTOINCREMENT` is the only SQLite construct that forbids reuse.

**`NumberSeries` is deliberately not the model here.** Its docstring rejects engine sequences
*"because they are explicitly not gapless"* — correct for a statutory invoice number, where a
gap is a question from an auditor. **The outbox needs monotonicity, not gaplessness**; gaps
are harmless, so the locked-counter cost buys nothing. The house pattern was chosen for a
property this table does not need.

> **Invariant, and it is testable: an outbox row is never renumbered and never re-inserted.**
> Conflating identity with order is only safe while that holds.

#### D-C2 — `client_created_at` is metadata; the array is the order

**Corrected in `04` T-26 and `05` §11.2 (PU-1…PU-3), not here.** `04` made a device clock the
ordering key, which P-4 forbids and which cannot deliver BR-013: a timezone change or NTP
correction makes the timestamp non-monotonic **within one device**.

FR-SYN-002 already obliges the client to transmit in creation order, and `operations` is an
ordered array. Applying it serially satisfies BR-013 through a channel no clock can corrupt.

**No wire field is added.** Ordering correctness for *dependencies* was never the timestamp's
job in the first place — `02` §5.3 `SC-SEQUENCE` and `05` §11.3 L-3 hold an operation whose
dependency is not yet accepted and retry it, keyed on `client_uuid`.

#### D-C3 — Storage-full is a distinct `Failure` variant at the outbox write boundary

`core/failure.dart` is a **sealed** hierarchy whose members are all transport failures —
`Offline`, `Refused`, `Unauthenticated`, `ProblemFailure`, `MalformedResponse`. Task 3 adds
one member for storage exhaustion. Sealed means every `fold` fans out at compile time, which
is the point.

**It must not be folded into `Offline`.** The two demand opposite behaviour: `Offline` means
*retry later and it will work*; storage-full means *retrying changes nothing until space is
freed*.

**Where it propagates:** the durable outbox write returns `Err`, and **the action fails**.
§5.3 — *"The user is never told 'saved' before it is"* — and NFR-OFF-005 make that binding.
No UI text is specified here.

Established by: `00` §19.1 gate *"outbox survives kill, restart and storage exhaustion"*,
`02` §18's adversarial note, NFR-OFF-004/005.

#### D-C4 — `device_id` is batch-level, from the keystore

**No column in the outbox. No `device_id` inside any operation payload.**

`05` §11.2 carries it **once per batch**, alongside `operations`; its own `DELIVERY_COMPLETE`
example payload contains `delivery_id`, `recipient_name`, `photo_media_id` — and no
`device_id`. §8.4 keeps the value in the keystore, which survives restart independently of
the database, so batch construction reads it then.

> **A correction to the reasoning that produced this section.** An earlier analysis concluded
> `device_id` was "already inside every operation payload", generalising from `05` §10.3/§10.4
> — the **direct REST** bodies — to §11.2, a different transport. §11.2's example disproves it.
> The sync payload is the REST body **minus the fields hoisted to batch and operation level**,
> and `device_id` is one of them. Recorded because the conclusion was right and the evidence
> for it was not.

**Backup/restore attribution is an M9 concern, recorded not fixed.** An Android Keystore is
hardware-bound, so a backup restored to a new handset yields a new `device_id` while carrying
the old outbox, and operations produced on one device would be attributed to another under
FR-IAM-009's *"every transaction it produces"*. **`02A` §13 demotes device registration and
revocation to Edition 2**, so no Edition 1 control depends on it. It belongs to batch
construction, not to the outbox schema — and a nullable column added later, while the outbox
is small, is the cheaper direction than the migration AR-3 warns about.

### 14.10 Task 3 implementation gate

| # | Gate | State |
| --: | --- | :-: |
| 1 | **TD-39 verified** | ✔ **CLOSED 2026-08-11** — `make verify` 8/8, **758/758**, **94.71%** |
| 2 | `04` T-26 and `05` §11.2 corrected (D-C2) | ✔ |
| 3 | Storage-full variant recorded (D-C3) | ✔ |
| 4 | Sequence invariant recorded, with its contract test named (D-C1) | ✔ |

**All four gates are closed. Task 3 may open.**

#### The TD-39 run

| | |
| --- | --- |
| Stages | 8/8 · **VERIFIED** (N-12) |
| Tests | **758 passed** (743 → 758; the 15 new cases in `test_delivery_outcome_idempotency.py`) |
| Coverage | **94.71%** |
| `mypy` | clean, **115 source files** |
| `ruff` | All checks passed |
| Contracts | **3 kept, 0 broken** — 144 files, 271 dependencies |
| Migrations | `makemigrations --check` → **No changes detected** |

> **The hand-written migration was the risk, and stage 3 retired it.** `fulfilment/0002` was
> written by hand because `makemigrations` could not run in the authoring environment
> (Python 3.10, no Postgres). *"No changes detected"* is Django confirming the file matches
> what it would have generated — the cheap check that made the deviation acceptable.

> **Coverage fell 0.17 points, 94.88% → 94.71%, and that is recorded rather than rounded
> away.** Attribution from the run's per-file table: `fulfilment/services.py` **93%**
> (11 statements uncovered, at 144 · 305–311 · 388–394) and `fulfilment/models.py` **94%**.
> Those line ranges are the two `IntegrityError` recovery branches — the arms that fire only
> when the unique constraint actually loses a race, which a single-threaded suite cannot
> reach. **The uncovered lines are the concurrency guarantee itself**, which is the honest
> shape of this milestone: the mechanism that matters most is the one a serial test cannot
> execute.

### 14.11 Task 3's gate — the hermetic subset (ruling, 2026-08-11)

**§10's task-3 Gate cell contradicted §9 and `00` §19.1, and the cell was wrong.** Recorded
rather than quietly rewritten, because the contradiction was found by auditing a milestone
that had already passed both gates — and a reader who finds only the corrected text learns
nothing about how it got there.

**The wording that was there:**

> *Kill · restart · storage exhaustion, at **every** write boundary*

**The evidence against it:**

| Source | Text | Says |
| --- | --- | --- |
| `00` §19.1 | `\| M8 → M9 \| Outbox survives kill, restart and storage exhaustion \|` | A **milestone-boundary** gate, not a task gate |
| §9 | `├── integration_test/    on-device: kill, restart, storage exhaustion` | The frozen folder structure puts all three **on a device** |
| §10 task 10 | *"The 8-hour offline soak (NFR-OFF-001) and **the M8→M9 gate** … Measured on a real device, not assumed"* | Task 10 already owns that gate |
| `02` NFR-OFF-005 | Verification method: *"Kill-test at each write boundary"* | Names the method; assigns it to no task |

Three frozen sources place kill and storage exhaustion on-device at the milestone boundary.
One table cell claimed them for task 3. **The cell loses.**

**The ruling.** Task 3's gate is what can be proven hermetically, in `flutter test`, with no
device:

| In task 3's gate | Owned by task 10 |
| --- | --- |
| Drift schema | **Process-kill** (`kill -9` mid-write) |
| Sequence correctness, including across purge | **Real storage exhaustion** (a genuinely full filesystem) |
| `PENDING`-only append | The 8-hour soak (NFR-OFF-001) |
| **Restart** durability — close, reopen, sequence continues | |
| `StorageFull` **classification** from SQLite result codes | |

**The distinction that matters:** task 3 proves the outbox *classifies* a full disk
correctly; task 10 proves it *survives* one. The first is a mapping and needs no device; the
second is a system property and cannot be faked without one.

> **`mobile/integration_test/` does not exist**, and `make verify` cannot reach it (TD-37).
> That is task 10's problem, and this ruling is what makes it task 10's problem rather than
> an unstated debt inside task 3.

**No architectural decision changed.** D-C1…D-C4 and §5.3 are untouched; only the table cell
that misstated ownership.

---

### 14.12 Task 4 / M6 — the offline authentication window, frozen 2026-08-16

Six decisions, taken after an evidence audit found **FR-IAM-016 unimplementable as
specified**. The audit's verdict was *BLOCKED — MISSING CONTRACT*, and this section is what
unblocks it.

> **Labelled `D-D1…D-D6` under this document's letter convention** — task 2 took `D-A*`/`D-B*`,
> task 3 took `D-C*`, task 4 takes `D-D*`. The freeze instruction numbered them `D-1…D-6`;
> they are the same six decisions. A bare `D-3` already means `customer.state_code` in M5 and
> a bare `D-1` already means a M7 ruling, so the letter is not decoration.

#### 14.12.0 What was established, and what is being decided

The distinction is kept because the two carry different authority: a fact can be re-read from
the corpus, a decision can only be re-opened by another ruling.

| | Statement | Source |
| --- | --- | :-- |
| **FACT** | FR-IAM-016 bounds a *"configurable maximum **offline** period, after which sync is required to continue"* | `02` FR-IAM-016 |
| **FACT** | OI-5 = **7 days, configurable** | `02` OI table |
| **FACT** | *"bounded by refresh-token validity… Offline authentication grants local access only; it never authorises a server write"* | `05` §7.2 |
| **FACT** | Refresh token = 30 days; access = 30 minutes | `05` §7.1, `settings/base.py` |
| **FACT** | Beyond the window the app stops accepting a local unlock; the outbox is **not readable and not erased** | §8.3 |
| **FACT** | Cached user and roles live in the **encrypted local DB**; the refresh token and `device_id` live in the **keystore** | §8.2, §8.4 |
| **FACT** | **P-4 names *"expiring a session against `DateTime.now()`"* as its own counter-example** | §1.3 |
| **FACT** | The auth response carries `{access_token, refresh_token, expires_in, user}` — **no `server_time`** | `05` §10.1, `auth_views._issue_tokens` |
| **FACT** | No `BusinessProfile` field, no `AppConfig` field and no `--dart-define` exists for the window | `core/models.py`, `app/config.dart` |
| **FACT** | Nothing in the corpus mentions a biometric, passcode or device PIN | corpus-wide search |
| **DECISION** | Everything in D-D1…D-D6 below |

#### D-D1 — The trusted time anchor is the refresh token's `iat` claim

**ENGINEERING DECISION.** No frozen document specifies a time source that exists.

P-4 forbids the device clock **by name**, so `Clock.nowUtc()` cannot decide expiry. §5.5
asserts that M8 *"stores `server_time` from the login response from day one"* — and it does
not, because there is no such field on either side (see §14.12.1). A monotonic elapsed source
that survives a reboot does not exist in Dart without a new native dependency.

The refresh token already carries server-issued `iat` and `exp` (`05` §7.1). **Both bounds
therefore come from the same artefact**: `iat` is the anchor and `exp` is the
refresh-validity ceiling `05` §7.2 requires. No wire field, no dependency, no clock.

> **The cost, stated plainly:** the client begins decoding a JWT payload it has so far
> treated as opaque bytes. This is safe — a JWT payload is base64, not a secret, and P-9
> concerns what the *binary* discloses, not what it reads — but it is a new competence in the
> client and it is recorded as a decision rather than slipped in as an implementation detail.

`Clock` is **not** deleted and **not** extended. It keeps labelling; it does not expire.

#### D-D2 — `DISTRICORE_OFFLINE_WINDOW_DAYS`, compile-time, default `7`

**ENGINEERING DECISION**, over an EVIDENCE-SUPPORTED default.

| | |
| --- | --- |
| Name | `DISTRICORE_OFFLINE_WINDOW_DAYS` |
| Mechanism | `--dart-define`, read in `AppConfig` |
| Default | **`7`** — unlike `DISTRICORE_API_BASE_URL`, this one **has** a default, because 7 days is a frozen product requirement (OI-5) rather than a deployment unknown |
| Rejected | zero, negative, non-numeric — refused at start-up, before `runApp`, exactly as an unusable base URL is |
| **Not** in `BusinessProfile` | `05` §7.2 already decouples the window from the only related profile field, and a server-supplied window is unreadable by a device that is offline — which is the only state in which it matters |

#### D-D3 — The window anchors on the most recent successful **authenticated server contact**

**ENGINEERING DECISION**, resolving a conflict inside the corpus.

Qualifying events, each of which **resets** the window:

1. OTP verification (`POST /auth/otp/verify`)
2. Password login (`POST /auth/login`)
3. **Successful token refresh** (`POST /auth/refresh`)

`03` §5.2 anchors on *"last successful **login**"*. FR-IAM-016 bounds a *"maximum **offline**
period"*. These are different quantities, and the difference is not academic: under `03`'s
reading, **a device with perfect connectivity is forced through an OTP every seven days**,
which is a lockout the requirement never asked for and which would be discovered by a
salesman in a market. FR-IAM-016 is the requirement; `03` is derived from it. **The
requirement wins** (see §14.12.1).

Because refresh rotates the token on every use (`05` §7.1), the new token's `iat` *is* the
new anchor. D-D1 and D-D3 compose: **re-anchoring requires storing nothing extra.**

#### D-D4 / D-D5 — A successful `/auth/refresh` is the post-expiry round trip

**ENGINEERING DECISION.** §8.3 requires *"a server round-trip"*; `03` §5.2 and `05` §7.2 say
*"re-authentication is forced"*. The narrower reading would force a full OTP after every
lockout even though the device still holds a credential the server would honour.

A refresh that **succeeds** re-anchors and restores local access. A refresh that is
**rejected** falls through to behaviour that already ships:

| Outcome | Behaviour | Already built |
| --- | --- | :-: |
| `401 TOKEN_INVALID` / `REFRESH_EXPIRED` | `Unauthenticated`, keystore cleared, `device_id` kept | `problem.dart`, `SessionRestorer`, `SecureTokenStore.clear()` |
| `Offline` | **Credentials are not cleared** — §17 is explicit that clearing on a failed-to-arrive refresh *"would end FR-IAM-016's offline window at the first tunnel"* | `SessionRestorer` |
| Window expired | `Unauthenticated`. **The refresh token is retained**: expiry ends local unlock, it does not revoke a credential | — |

#### D-D6 — No new user-presented local factor in V1

**ENGINEERING DECISION**, closing the gap §8.2 opened and §8.3 never filled.

§8.2's storage table reads `| Local auth material | FR-IAM-016 — §8.3 |`, and §8.3 defines no
such material. `03` §5.2's *"a hash of the last successful login"* is the only other
statement, and it does not say a hash **of what** — nor could it describe the field path,
since OTP is the field default and an OTP user has no password to hash.

**"Authenticate locally" for V1 means exactly three conditions, all of which must hold:**

1. cached encrypted user/session identity is present and readable,
2. the refresh token is still in the keystore,
3. the offline window is unexpired.

No biometric, no PIN, no passcode, no locally minted credential. **The device stores no
secret the server did not issue.**

#### 14.12.1 Three corpus statements this freeze supersedes

Recorded rather than silently overwritten, in the pattern §3.4.1 established — a reader who
finds only the corrected text learns nothing about how it got there.

| Where | Text | Status |
| --- | --- | --- |
| §5.5 | *"M8 does not pull yet, but it stores `server_time` from the login response from day one"* | **Not true of the shipped contract.** `05` §10.1 does not specify `server_time` on any auth response, `_issue_tokens` does not emit it, and `AuthBundle` does not parse it. **Superseded by D-D1.** M9's sync path still uses `server_time` as `05` P-2 requires; this correction is confined to the *auth* response |
| `03` §5.2 | *"stores the user profile and a hash of the last successful login"* | **Superseded by D-D6.** Amend `03` when M6 lands |
| `03` §5.2, `05` §7.2 | *"re-authentication is forced"* after the window | **Refined by D-D4/D-D5:** a successful refresh satisfies it. Amend `05` §7.2 when M6 lands |

#### 14.12.2 Window semantics

Let `A` = `iat` of the currently held refresh token, `W` = `DISTRICORE_OFFLINE_WINDOW_DAYS`,
`X` = `exp` of that token.

| Condition | Behaviour |
| --- | --- |
| Elapsed `< min(W, X − A)` | Local unlock permitted. Reads served from cache. Writes go to the outbox (P-2). **No server write is authorised** (`05` §7.2) |
| Elapsed `== W` exactly | **DENIED.** The predicate is `<`, not `<=` — a boundary that admits equality is a boundary chosen by accident |
| Elapsed `> W` | Denied. No session published. The existing router redirect sends every route to `/login` |
| No network | Irrelevant to the predicate. The window is elapsed time, not reachability |
| Network after expiry | A successful refresh re-anchors (D-D4/D-D5) |
| Token present after expiry | Retained, not cleared |

At defaults 7 < 30, so the window binds and the token ceiling does not. **If
`DISTRICORE_REFRESH_TOKEN_DAYS` is ever lowered below the window, the token ceiling binds
first** — which is why the ceiling is in the predicate rather than assumed away.

#### 14.12.3 What M6 must not touch

| Untouched | Why it is named here |
| --- | --- |
| `outbox_operation` table and its schema | §8.3: the outbox is neither readable nor erased at lockout. **M6 adds no `DELETE` against it**, and that absence is the enforcement |
| `TokenStore` interface | Frozen since M1 |
| `RefreshInterceptor` | D-B1/D-B2/D-B3 built and verified |
| `AuthService` | Implements `Authenticator`; the port is M5's |
| `Session` | The anchor is repository-owned persistence state, not identity. Putting a timestamp on the entity every screen holds is how P-4 erodes |
| `Clock` | Keeps labelling. Never expires |

---

*Phase 1 is closed. Phase 2 is at task 4: M1–M5 are verified and pushed (`af9a1ca`,
152/152, 0 analyzer errors); M6 — the offline authentication window — is frozen at §14.12 and
not yet implemented.*
