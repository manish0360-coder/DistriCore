# Next Task

## The immediate next action

**`00` §19.2's durability gate is CLOSED. The next action is a decision, not a run.**

> **Updated 2026-09-04.** Both halves have now been run and both PASSED:
> `make mobile-device-kill` on 2026-09-01 (`M8_Design_Review` §5.6.1) and
> `make mobile-device-storage` on 2026-09-04 (§5.6.2). Kill, restart and storage exhaustion are
> all discharged. The storage gate found a real defect in shipping code on the way — a full
> disk crashed the outbox instead of returning `StorageFull` — which is recorded in §5.6.2 and
> fixed.
>
> **What this does not do:** it closes no milestone, and it does not shorten the open-decision
> list below. Coverage is `x86_64` emulator only (**TD-45**), and the device gates still cannot
> run in CI (**TD-42**). The paragraphs that follow described the state before these runs and
> are otherwise unchanged.

**It needs no ruling from anyone.** Both targets exist, both are written, and
`M8_Design_Review` §10.1 says this is the one task that **cannot** slip. What was missing was
never a decision — it was a run. The encryption work of 2026-08-25 settled that question in
practice: `make mobile-device-encryption` executed on the Pixel 8a API 34 emulator and closed
NFR-SEC-008, so the harness, the AVD and the by-hand invocation path are all known to work
(TD-42 records that they cannot yet run in CI).

**This changes what is next, not what is blocked.** Until 2026-08-25 this file said *"the next
action is a decision, not an implementation."* That was true when every open item needed a
Product Architect. It is no longer true of **all** of them: D-M9-4, D-M9-6, D-M9-7 and D-M9-8
have since been ruled, and the encryption defect was found by *running the thing*, not by
deciding anything. Item 4 below is now in the same category.

**No milestone number is proposed here, and none should be invented.**
`docs/00_Engineering_Foundation.md` §19.1 defines **M9 = Sync** and **M10 = Hardening** and
defines no sub-milestones; `M9.1`–`M9.4` are working labels for four commits, not roadmap
entries. There is no M9.5.

**The next milestone still cannot be selected.** **Eight items are open and five of them remain
questions no engineer may answer alone** — two are direct contradictions between frozen
documents. They are listed in `PROJECT_STATE.md` under *Open at M9*, unresolved and
deliberately so. **Running the durability gate does not shorten that list**; it discharges the
one item that was waiting on nobody.

**What still needs a decision, before any code:**

| # | Question | Who |
| --: | --- | --- |
| 1 | **FR-SYN-005/013/014 vs `05` §11.4.** `02` requires a `SyncConflict` in `PENDING_RESOLUTION`; `05` says *"no conflict resolution console is built, because none is needed"*. `SyncConflict` exists in no schema and no contract | Product Architect |
| 2 | **FR-SYN-009.** `05` §11.5 claims coverage that **D-M9.3-1** makes unreachable — the endpoint reads `device_id` from the JWT and can only ever describe the caller's own device | Product Architect |
| 3 | **FR-RPT-009 sync health report.** Placed *at M9* by ruling **A-5** and `M7_Design_Review` §C-4. Unbuilt, and unspecified in `05` | Product Architect |
| 4 | **M8 → M9 gate** (M8 task 10) — **no recorded evidence of this gate was found in the repository**, and `M8_Design_Review` §10.1 says this one **cannot** slip. **This is the immediate next action above: it needs a run, not a ruling.** *A different device gate — `make mobile-device-encryption` — did run on 2026-08-25 and closed NFR-SEC-008 (D-M9-8). It is not this gate and is not evidence for it.* M8 tasks 6 and 8 also have no commit | Engineering *(the gate)* + Product *(tasks 6 and 8)* |
| 5 | **M9 → M10 gate** — no adversarial sync suite exists | Engineering |
| 6 | **FR-SYN-007 remainder / stock snapshot** — D-M9.4-1's recorded CONTRACT GAP | Product Architect |
| 7 | **Orphaned `RECEIVED` recovery** — deferred by `05` §11.5 *"to M9.4/M10"*; M9.4 has passed, so it landed on M10 by default | Engineering |
| 8 | **TD-41 / FR-SYN-010** — launch-only trigger, no connectivity mechanism | Engineering |

> **Why this is a task and not a preamble.** Until 2026-08-21 this file said *"Next: task 3"*
> and `PROJECT_STATE.md` said *"M9 — Not started"*, while fourteen commits had landed past
> both. The corpus is the single source of truth; a corpus six milestones behind the tree
> cannot answer *"what is next"*, and picking a milestone anyway means picking it from memory.

---

> **M8 Phase 1 is frozen.** Design authority `docs/M8_Design_Review.md` **v1.8.0**, signed
> 2026-08-10. Both ADRs approved: **Drift** (§5.6 — the cipher clause amended by **D-M9-8** on
> 2026-08-25 to SQLite3MultipleCiphers via the `sqlite3` build hook; the ADR's conclusion,
> Drift, is unchanged) and **Dio** (§7.5). Design principles **P-1…P-10** frozen at §1.3.
>
> **M8 Phase 2 tasks 0–5, 7 and 9 are committed**, plus TD-39; **tasks 6, 8 and 10 are not.**
> **M9 has four committed increments** (M9.1–M9.4) and is **not closed**. Commit-by-commit
> history and the open items are in `PROJECT_STATE.md`.
>
> The working tree passes the full mobile verification suite (**317 tests**); it was **305** at
> commit `bf94b8e`. **Encryption at rest is closed** (FR-SYN-016, NFR-SEC-008; D-M9-8) —
> `sqlite3mc` via the build hook, keyed from the Android keystore, with `chacha20` and SQLite
> `3.53.4` **observed and recorded, not required**. Proven on a **Pixel 8a API 34 emulator,
> `android-x64` only — not arm64 and not physical hardware** (TD-45). **It closes a
> requirement, not a milestone**: the M8 → M9 durability gate and the M9 → M10 adversarial sync
> gate are both still open. Backend
> `make verify` figures for the M9 increments were not captured in the state documents and
> are **not restated here from memory**.

**Milestone:** M9 — Sync (2.0 units, `00` §19.1). M8 remains open on tasks 6, 8 and 10.
**Next:** see *The immediate next action* above.

---

## What task 0 found, and why it matters more than the endpoint

Deciding how to encode one number surfaced a defect in the **seven existing** report
endpoints — the exact one P-3 exists to prevent, on the server side:

| | |
| --- | --- |
| `05` AD-02 | *"Every monetary and quantity value crosses the wire as a string."* Its rationale names Dart by name |
| Settings | `COERCE_DECIMAL_TO_STRING: True` — **but it only reaches `serializers.DecimalField`** |
| `_as_json` | Hand-builds its response dict, bypassing serialisation entirely |
| Measured | `Decimal("1180.00")` → `1180.0` under DRF's own encoder |

**The existing assertion reads `Decimal(str(body["total"]["sales"]))`.** That `str()` makes it
pass whichever type arrives. Seven endpoints carried this through four reviews and a newly
blocking type gate because the test could not fail.

**Recorded as TD-36. Not fixed in task 0** — changing the seven is a breaking change to a
published response type, so it gets its own change and its own verify run. `money_string()`
was added in task 0 to be the mechanism that fix reuses.

> **The recurring shape, in a new place:** a rule enforced on one side of a boundary and not
> the other. Canonical on read but not on write; a grant path for the second owner and none
> for the first; and now AD-02 enforced in the serializer layer and not in the hand-built
> layer beside it.

---

## The ruling that changed the design

**§3.4 "no owner mobile role" is replaced by Owner Companion Mode.** Lightweight read-only
operational visibility on the phone; all administration and reporting stay on the web.

v1.0.0's §12.5 predicted this recommendation would be *"overturned by one sentence from the
business"* because its premise — that the owner sits at a desk — was an inference, not an
observation. **It was, within a day.** The paragraph is kept verbatim in v1.1.0 rather than
deleted.

**Two dependencies were found only after the ruling, by checking it against the code:**

| # | Finding | Effect |
| --: | --- | --- |
| ~~**OI-6**~~ | ~~`GET /reports/dashboard` does not exist.~~ Three of the four D-4 numbers were reachable; **"collected today" was not** — only a paginated `/payments` list, which the device would have had to page and sum, **deriving a figure on the device** over 2G | ✔ **Built and verified as task 0.** `05` §9.11.1 |
| **OI-7** | **"Notifications" were cut from Edition 1** — `02A` §13: *"In-app notifications (**M-14 entirely**)… 0.5"*. No model, table, endpoint or milestone exists | Blocks task 8. Recommendation: adopt `02A`'s own substitute — a **"Needs attention"** filtered read |

> **Same shape as M7's C-1…C-6.** `02A` §7.x's feature matrix predates §13's Edition-1
> re-validation, and **§13 governs.** OI-7 is a request a frozen document has already
> answered.

**Neither blocks Phase 2 from starting.** Both sit inside task 8, which §10.1 places last
precisely because nothing depends on it.

---

## Design principles — frozen, and the reason they exist

`docs/M8_Design_Review.md` §1.3 records **P-1…P-10** so a Phase 2 decision is checked in one
line instead of re-argued. The three that cannot be repaired after the fact:

| # | Principle | Why it is unrecoverable |
| --: | --- | --- |
| **P-3** | Money and quantity are `Decimal` end to end — **no `double`** | Corrupts figures that have already been sent |
| **P-6** | `client_uuid` generated before the first attempt, **never regenerated** | Defeats the server idempotency M9 depends on |
| **P-9** | The binary holds **no secret and no rule** the server does not independently enforce | A security property of a binary already downloaded |

> **These get tests, not review comments.** §12.7 admits the rest are currently advisory —
> the exact status TD-2's type gate held for six milestones before it caught 24 errors.

---

## Phase 2 task order

| # | Task | Gate |
| --: | --- | --- |
| ~~**0**~~ | ~~Backend: `GET /reports/dashboard`~~ | ✔ **DONE** — 8/8, 726/726, 94.88% |
| ~~**1**~~ | ~~Toolchain, shell, DI, router; layering + no-secrets tests~~ | ✔ **DONE** — 8/8, **742/742**, 94.88%. 16 contracts, each proved able to fail |
| ~~**2**~~ | ~~Decimal codec and the API layer~~ | ✔ **DONE** — 8/8, **743/743**, 94.88%; `mobile-verify` **38/38**, 0 errors |
| ~~**TD-39**~~ | ~~`client_uuid` on `/deliveries/{id}/complete` and `/fail`~~ | ✔ **DONE** — 8/8, **758/758**, 94.71%; `makemigrations --check` clean |
| ~~**3**~~ | ~~Drift schema, outbox, sequencer~~ | ✔ **COMMITTED** — `3009e3b`. **The kill and real-storage-exhaustion halves were deferred to task 10 by §14.11, and no recorded evidence of them was found in the repository** |
| ~~4~~ | ~~Auth: OTP, password, keystore, refresh-once, device id, offline window~~ | ✔ **COMMITTED** — `1014c88`, `cea3e84`, `5b0f035`, `1ebbe43`, `af9a1ca`, `b9d4eb4` |
| ~~5~~ | ~~Delivery: list, detail, complete, fail~~ | ✔ **COMMITTED** — `b3f738c` |
| **6** | **GPS and the separate media queue** | C-9. **No commit.** No GPS, media or photo code exists under `mobile/lib/` |
| ~~7~~ | ~~Customers, visits~~ | ✔ **COMMITTED** — `11bb370` |
| **8** | **Owner Companion Mode** | Read-only; every figure carries `as_of`. **No commit.** Still **blocked on OI-7 and TD-36** |
| ~~9~~ | ~~Sync-status screen~~ | ✔ **COMMITTED** — `feeb85d`, extended by M9.3 (`e26aa87`) |
| **10** | **8-hour offline soak** (NFR-OFF-001) and the **M8→M9 gate** | **Measured on a real device. No commit, and no recorded evidence of this gate was found in the repository** |

**Tasks 6, 8 and 10 remain.** §10.1 is explicit that of the three, only task 8 could ever
move: *"task 8 is the first thing that can move to M8.1 without breaking the milestone gate —
**task 10 cannot**."* Task 10 carries the M8→M9 gate condition from `00` §19.2 — *"outbox
survives kill, restart and storage exhaustion"* — and §14.11 assigned it the two halves of
task 3's durability proof that task 3 itself did not make. **No recorded evidence of this gate
was found in the repository** — which is an absence of an artefact, not proof that nothing was
run. A soak measured on a device leaves no trace here unless someone writes it down. This
document records the absence; it does not rule on it.

**Tasks 1 and 2 precede every feature deliberately.** `reporting`'s four AST tests were
written when it had one file; that is why the contract still holds at seven. Written last,
they are worth nothing — by then the violation *is* the code.

**Task 0 was first because it is a different toolchain**, and that held: it verified and
committed on its own, before any Dart entered the repository.

**Task 1's contracts were written before the first widget, and that held too.** They are in
**Python, inside stage 7** — not in `analysis_options.yaml`, which `make verify` never runs
and which would therefore have been advisory from birth. Each of the 16 was proved able to
fail by mutating the tree, because a green test that cannot go red is not evidence.

> **Task 1 cost four infrastructure defects and zero application defects**: a dead image
> registry, a pub cache that did not survive the container boundary, an analyzer whose
> defaults differ from `dart analyze`, and a directory that was never bind-mounted. **Three
> of the four reported the wrong layer** — a missing mount surfaced as *"the Flutter pin is
> not stated exactly once"*. Expect task 2's surprises to be of the same kind, not in the
> Dart.

---

## Task 2 — the frozen boundary, as built (`M8_Design_Review` §14)

**Built, and nothing else:** Dio `ApiClient` · `AuthInterceptor` · **single-flight**
`RefreshInterceptor` · `DeviceInterceptor` · problem+json → typed `Failure` · the `Money`
codec · a `TokenStore` **interface only** · 29 Dart tests.

**Held out, and still out:** the outbox (task 3) · auth screens, the keystore and the offline
credential store (task 4) · **any dashboard DTO or dashboard-specific client code** (task 8,
§14.6) · **TD-39** · any backend change.

| # | Frozen | One line |
| --- | --- | --- |
| **D-B1** | Single-flight refresh | Concurrent `401`s share **one** refresh; each original request retries **exactly once**; a second `401` is terminal |
| **D-B2** | Structural isolation | `/auth/refresh` runs on a **separate `Dio`** carrying neither auth nor refresh interceptor — not a re-entrancy flag |
| **D-B3** | Identity-preserving retry | The retry replays the original request, **especially its `client_uuid`**. Never a new operation identity (P-6) |

> **D-B1 is not a style preference.** The server sets `ROTATE_REFRESH_TOKENS: True` **and**
> `BLACKLIST_AFTER_ROTATION: True`. Parallel refresh means the second call presents a
> blacklisted token and **reuse detection treats it as an attack** — three requests failing
> together can log a working session out.

### What task 2 found

| Finding | Where it landed |
| --- | --- |
| **`device_id` is a body field, not a header.** §7.2 only says *"on every write"*; `05` §9's examples and the DRF serializers both put it in `request.data`. A header would be accepted by the transport and **ignored by the server** — the exact attribution loss C-10 names | `DeviceInterceptor` injects into the body; a test asserts the header is absent |
| **Offline during refresh must not sign the user out.** D-B1 covers the 401 and says nothing about a refresh that never reaches the server. Clearing the keystore there would end FR-IAM-016's window at the first tunnel | Only a 401 clears. Tested |
| **`package:decimal` normalises `'11800.00'` to `'11800'`** — correct arithmetic, wrong transport, and a silent change to a field's declared scale | `Money` carries the scale it arrived with |

> **The costliest defect was in the test harness, not the code.** It stored live
> `RequestOptions`; D-B3 replays the *same* object and `AuthInterceptor` rewrites its header
> in place, so every recorded attempt showed the last token — **and the `client_uuid`
> assertion was comparing an object with itself.** A test that could not fail, guarding the
> principle that cannot be repaired later. Fixed by snapshotting each request.

---

## Entry conditions

| # | Condition | State |
| --: | --- | :-: |
| 1 | §13 signed; both ADRs approved | ✔ |
| 2 | §1.3 principles frozen | ✔ |
| 3 | **TD-32 — retire the superseded `==` dev pins** | ☐ **Missed its window.** It was to land before the Dart toolchain; the toolchain arrived first. Still owed, now without that argument |
| 4 | **K-1 — keystore procedure agreed** | ☐ |
| 5 | **TD-11 — DLT registration started** | ☐ **External, unbounded** |
| ~~6~~ | ~~Flutter/Dart SDK pinned, as `uv.lock` pins Python~~ | ✔ **Done in task 1** — `mobile/.flutter-version` + `mobile/pubspec.lock` (32 packages). **By version, not by bytes: TD-38** |
| ~~7~~ | ~~OI-6 — the dashboard endpoint~~ | ✔ **Built and verified** |
| 8 | **OI-7** ("Needs attention" vs reopening M-14) and **TD-36** ruled | ☐ Task 8 only |

> **Conditions 3 and 6 are one lesson.** TD-21 was closed *before* a second toolchain
> arrived, so reproducibility was settled with one language in the repository. Phase 2 adds
> the second. **Pin Dart the way Python is pinned, on the first day** — not after the first
> "works on my machine".

### K-1 — the one irreversible thing in M8

> **If the Android release keystore is lost, the application on Google Play can never be
> updated again.** Not by you, not by Google (`00` §2.3).

Generated once, stored in the password manager, backed up to **two locations that are not
the development machine**, never in Git (S-06, N-11). Done at M8, verified at M11.

### The condition DV-4 is accepted on, and it is absolute

> **The binary is publicly downloadable and must be assumed fully decompiled** (`02A` §9.3).
> It may contain no internal-only logic, endpoint or secret that server-side authorisation
> does not independently enforce.

**Companion Mode raises the stakes on this, it does not change it.** An owner token now
reaches the app, so read-only must be enforced by the absence of a server-side write path —
**not by the absence of a button.**

---

## Workflow, unchanged

1. Review the frozen corpus and `M8_Design_Review.md` v1.1.0 §1.3 before deciding anything.
2. Identify specification conflicts **before** proposing an implementation.
3. Implement one logically complete task.
4. `make verify` 8/8 — the only authority (N-12).
5. Verification note, then documentation, then commit.

**No weakened tests. No lowered coverage. No bypassed contracts.**

---

## Carried forward

| Item | Note |
| --- | --- |
| **Uncommitted** | Task 2's code and this documentation pass await the milestone commit. **`LICENSE` also shows as modified — line endings only (LF→CRLF), no content change.** `git checkout -- LICENSE` before committing so it does not ride along |
| **Re-run `ops/report_performance.py`** after any change to a report or the §5A walk | Not in `make verify` and never will be — an 858-second dataset build has no place in an 8-stage gate, so **nothing else catches a regression of that class** |
| **TD-29** | Nothing asserts a new report is wired into `REPORT_MENU`, the API router **and** the CSV path. **Task 0 adds an eighth report endpoint — this is the first time TD-29 can actually bite** |
| **TD-31** | Clock-dependent tests. Four fixed; the class is not structurally prevented |
| **TD-37** | **Open, and costlier after task 2.** `mobile-verify` is still not in `make verify`. The 21 structural contracts are blocking, but *"does the Dart compile"* is not — and **the 317 Dart cases are invisible to the only authority.** The 829 figure does not include them. Promote to stage 9 once the toolchain image has held for a milestone |
| **TD-38** | **New. The Flutter SDK is pinned by version, not by bytes.** `make mobile-image` prints the checksum; paste it into `FLUTTER_SHA256` and the gap closes |
| **TD-36** | **On M8's path.** Money leaves the seven report endpoints as a JSON float. Fix by routing `_as_json`'s numeric cells through `money_string()` — added in task 0 for this reuse — in its own change, with its own verify run |
| Deferred debt | TD-32, TD-33 (DRF stubs), TD-34 (`ops/` outside mypy), TD-35 (`pip-audit \|\| true`), TD-23, TD-26, TD-28, TD-14, TD-15 |
| **The lesson still standing** | **A design review cannot find a defect on a path the tests do not take.** Four reviews found none of M7's four defects; running the real thing found all of them. M8 runs on hardware no test rig replicates — §10 task 10 is the only place that gets checked |

## Blocking, not owned by engineering

| Item | Owner |
| --- | --- |
| **CF-1 — is statutory e-invoicing mandatory?** (`02` OI-1). More expensive with every invoice issued | Business owner |
| **TD-11 — SMS/DLT registration.** Inside M8's critical path | Business owner |
| **OI-7 — "Needs attention" substitute vs reopening M-14** | Product Architect |
| **TD-15 — `offer` has no milestone** | Product Architect |
