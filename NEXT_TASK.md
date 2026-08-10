# Next Task

> **M8 Phase 1 is frozen.** Design authority `docs/M8_Design_Review.md` **v1.3.0**, signed
> 2026-08-10. Both ADRs approved: **Drift + SQLCipher** (§5.6), **Dio** (§7.5). Design
> principles **P-1…P-10** frozen at §1.3.
>
> **Phase 2 tasks 0 and 1 are verified.** Task 0: `GET /reports/dashboard`, contracted at
> `05` §9.11.1. Task 1: the Flutter shell, the four-layer structure, DI/routing, the pinned
> toolchain and **16 blocking structural contracts** — 8/8, **742/742**, **94.88%**, `mypy`
> clean, **3 contracts kept** (143 files, 271 dependencies).

**Milestone:** M8 — Mobile app (3.0 units, `00` §19.1)
**Phase:** **2 — Implementation. Tasks 0 and 1 of 10 done. Next: task 2.**
**`mobile/` holds 18 Dart files and no feature behaviour.** No outbox, no delivery, no GPS,
no photo, no Owner Companion Mode — all placeholders behind contracts that already bite.

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
| **2** | **← NEXT. Decimal codec and the API layer** (Dio, interceptors, typed failures) | Build fails on any `double` in a money path |
| **3** | **Drift schema, outbox, sequencer** | Kill · restart · storage exhaustion, at **every** write boundary |
| 4 | Auth: OTP, password, keystore, refresh-once, device id, offline window | C-7, FR-IAM-015/016 |
| 5 | Delivery: list, detail, complete, fail | No screen touches the network to save |
| 6 | GPS and the **separate media queue** | C-9 |
| 7 | Customers, visits | — |
| 8 | **Owner Companion Mode** | Read-only; every figure carries `as_of`; **blocked on OI-7 and TD-36** |
| 9 | Sync-status screen | FR-SYN-008, partial until M9 |
| 10 | **8-hour offline soak** (NFR-OFF-001) and the M8→M9 gate | **Measured on a real device** |

**Task 3 is the milestone.** Everything else is screens over an API that already exists and
is already verified. If task 3 is wrong, M9 inherits a corrupt queue and both non-negotiable
sync metrics become unreachable.

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
| **Uncommitted** | Task 1's code and this documentation pass await the milestone commit. **`LICENSE` also shows as modified — line endings only (LF→CRLF), no content change.** `git checkout -- LICENSE` before committing so it does not ride along |
| **Re-run `ops/report_performance.py`** after any change to a report or the §5A walk | Not in `make verify` and never will be — an 858-second dataset build has no place in an 8-stage gate, so **nothing else catches a regression of that class** |
| **TD-29** | Nothing asserts a new report is wired into `REPORT_MENU`, the API router **and** the CSV path. **Task 0 adds an eighth report endpoint — this is the first time TD-29 can actually bite** |
| **TD-31** | Clock-dependent tests. Four fixed; the class is not structurally prevented |
| **TD-37** | **New. `mobile-verify` is not in `make verify`** — the 16 structural contracts are blocking, but *"does the Dart compile"* is not. Promote to stage 9 once the toolchain image has held for a milestone |
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
