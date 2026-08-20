# Project State

| | |
| --- | --- |
| Phase | **Phase 1 — Implementation** |
| Current milestone | **M9 — Sync.** Four increments committed (M9.1–M9.4, below); HEAD is `bf94b8e`. The pre-commit working tree passed the full mobile verification suite (**305 tests**) immediately before commit `bf94b8e`. **M9 is not closed:** several FR-SYN requirements are unbuilt, no recorded evidence was found for two documented gates, and two corpus contradictions are open — see *Open at M9*. **The next action is a decision, not an implementation** (`NEXT_TASK.md`) |
| Last closed | **M7 — Reporting**, verified 8/8, plus the identity fix, the owner bootstrap, TD-30, TD-27, TD-21 and TD-2/TD-18 |
| Edition | 1a — **back end feature-complete, and installable for the first time** |
| Design corpus | `docs/00`–`05`, frozen · `02` at v0.2.0 · amended by ADR-0007, ADR-0008, ADR-0009 |

> **Edition 1a's server side is done, and every requirement in it now has evidence.**
> FR-RPT-015 was the last one without any: measured at the DR-8 envelope, it caught a
> quadratic in the §5A walk (11.7 s), which was fixed to **0 breach(es)**. TD-27 closed —
> `docs/M7_Verification_Report.md` §13.
>
> **`00` §20.3 criterion 2 became true on 2026-08-08.** *"A user can log in ... by password
> on web"* was never satisfiable on a clean machine through the supported path; it passed at
> M0 and every milestone since only because the suite reached that state through
> `UserFactory`, which bypasses the production creation path (TD-30).

## Milestones

| # | Milestone | State |
| --- | --- | --- |
| P0 | Engineering Foundation | Complete |
| M0 | Foundation — identity, roles, OTP, audit, health, logging | **Verified & tagged** — `docs/M0_Verification_Report.md` |
| M1 | Master data — zones, customers, products, reason codes, media | **Verified & tagged** — `docs/M1_Verification_Report.md` |
| M2 | Inventory — stock ledger | **Verified & tagged** — `docs/M2_Verification_Report.md` |
| M3 | Commercial Operations — business profile, pricing, orders, credit | **Verified & tagged** — `docs/M3_Verification_Report.md` |
| ~~M4~~ | ~~Orders~~ | **Absorbed into M3** by ADR-0007. The number is retired, not reused |
| M5 | Fulfilment & Billing — delivery, dispatch, GST invoice, credit note, ledger | **Verified & tagged** — `docs/M5_Verification_Report.md` |
| M6 | Receivables — payments, reversal, write-off, derived outstanding, statement | **Verified & tagged** — `docs/M6_Verification_Report.md` |
| M7 | Reporting — seven reports, CSV, scoping, owner dashboard | **Verified** — `docs/M7_Verification_Report.md` |
| M8 | Mobile app | **In progress.** Phase 1 signed — `docs/M8_Design_Review.md` **v1.6.1**, both ADRs approved (Drift + SQLCipher, Dio), principles P-1…P-10 frozen. **Phase 2 tasks 0–5, 7 and 9 committed** plus TD-39 (see the commit history below). **Tasks 6, 8 and 10 have no commit** — GPS and the separate media queue, Owner Companion Mode, and the 8-hour offline soak. `mobile/lib/features/` contains `auth`, `customers`, `deliveries`, `settings`, `sync_status` and nothing else |
| M9 | Sync | **In progress.** Four increments committed — M9.1 push receiver, M9.2 mobile drain, M9.3 server status, M9.4 pull and cache. **Not closed:** see *Open at M9* |
| M10 | Hardening | Not started |
| M11 | Go-live | Not started |
| M12 | Retailer role (Edition 1b) | Not started |

### The canonical roadmap

`docs/00_Engineering_Foundation.md` §19.1 defines **M9 = Sync** and **M10 = Hardening**, and
**defines no sub-milestones**. `M9.1`–`M9.4` below are *working labels for four commits*, not
roadmap entries. There is no M9.5 and none is proposed here.

Gates, from `00` §19.2, verbatim:

| Gate | Condition |
| --- | --- |
| M8 → M9 | *"Outbox survives kill, restart and storage exhaustion"* |
| M9 → M10 | *"Adversarial sync suite passes: zero loss, zero duplicates"* |

## Committed implementation history — M8 Phase 2 and M9

Read from `.git/logs/HEAD`. **Subjects are verbatim.** The *Task* column maps each commit to
`M8_Design_Review` §10 and is an **inference from the commit subject**, not a statement any
document makes.

| Commit | Subject (verbatim) | Task *(inferred)* |
| --- | --- | --- |
| `3009e3b` | `feat(mobile): implement durable outbox` | M8 task 3 |
| `1014c88` | `feat(mobile): add secure token store` | M8 task 4 |
| `cea3e84` | `feat(mobile): restore session from secure token store` | M8 task 4 |
| `5b0f035` | `feat(mobile): add authentication engine` | M8 task 4 |
| `1ebbe43` | `feat(mobile): wire production bootstrap` | M8 task 4 |
| `af9a1ca` | `feat(mobile): add V1 login experience` | M8 task 4 |
| `b9d4eb4` | `feat(mobile): add offline authentication window` | M8 task 4 |
| `b3f738c` | `feat(mobile): add delivery workflow` | M8 task 5 |
| `11bb370` | `feat(mobile): add customer visit workflow` | M8 task 7 |
| `feeb85d` | `feat(mobile): add sync status visibility` | M8 task 9 |
| **`1a26781`** | `feat(sync): add backend sync receiver` | **M9.1** |
| **`ffd2702`** | `feat(mobile): add sync engine` | **M9.2** |
| **`e26aa87`** | `feat(sync): add server sync status` | **M9.3** |
| **`bf94b8e`** | `feat(sync): add offline pull and cache` | **M9.4 — HEAD** |

| Increment | Delivered | Contract |
| --- | --- | --- |
| **M9.1** | `POST /sync/push` receiver; `sync_operation` (`04` T-26); `field` app; five-value server status vocabulary | `05` §11.2, PU-1…PU-4 |
| **M9.2** | Mobile `SyncEngine` — single-flight drain, batch claim/settle, launch-time trigger | `05` §11.2, §11.4 |
| **M9.3** | `GET /sync/status`; server view rendered beside the local queue | `05` §11.5, D-M9.3-1/2 |
| **M9.4** | `GET /sync/pull` with opaque `page_token`; Drift v2→v3 cache; `PullService`; cache-first delivery and customer rounds; ordered start-up chain | `05` §11.1, D-M9.4-1…8 |

> **Not recorded in the verification-history table below.** That table records `make verify`
> stage/test/coverage figures for backend milestones. These four increments were verified by a
> mixture of `make verify` and `make mobile-verify` runs whose figures are not captured here;
> recording numbers that were not observed at the time would be worse than recording none.

## Open at M9 — carried, not decided

**Nothing in this section is resolved by this document.** Each item is either unbuilt, or a
place where two frozen documents disagree. They are listed so that the next milestone is
chosen with them in view, not so that they are quietly closed.

> **Three different statements, kept apart on purpose.** *"The suite does not exist"* is an
> observed absence in the tree. *"No recorded evidence was found"* is an absence of a
> verification artefact, and says nothing about what was or was not executed. **Neither is
> proof that something was never run**, and this document makes no such claim anywhere — a
> measurement taken on a device leaves no trace in a repository unless someone records it.

| # | Item | State |
| --: | --- | --- |
| 1 | **FR-RPT-009 — sync health report** (FR-SYN-015). `02:737` ruling **A-5** and `M7_Design_Review` §C-4 both place it *at M9*. No implementation in `backend/reporting`; **no endpoint in `05`** | **Open** |
| 2 | **FR-SYN-009 — `SALESMGR`/`ADMIN` per-device view.** `05` §11.5 is captioned *"(FR-SYN-008/009)"*, but **D-M9.3-1** freezes `device_id` as taken from the JWT *"never from the request"*, so the endpoint can only ever show the caller's own device. No other surface exists | **Open — apparent contradiction inside `05` §11.5** |
| 3 | **Orphaned `RECEIVED` recovery.** `05` §11.5: *"not specified and is not built … Deferred to M9.4/M10 by ruling."* M9.4 shipped without it, so it has arrived at M10 by default rather than by decision | **Open** |
| 4 | **FR-SYN-007 remainder / stock.** `02` requires *"customers on assigned routes, products, prices, schemes and stock snapshot"*. **D-M9.4-2** implements customers and deliveries only; **D-M9.4-1** records the stock snapshot as an unclosed **CONTRACT GAP** against `04` N-03/E-01 and ADR-008 | **Open — recorded gap** |
| 5 | **FR-SYN-005 / 013 / 014 — conflict console.** `02` FR-SYN-005: *"MUST … persist it as a `SyncConflict` in `PENDING_RESOLUTION`"* (also BR-014). `05` §11.4: *"**No conflict resolution console is built, because none is needed**"*. `SyncConflict` occurs **only in `02`** — no table in `04`, no endpoint in `05`, no model in `backend/sync` | **Open — direct contradiction between `02` and `05`** |
| 6 | **M9 → M10 gate.** `backend/tests/adversarial/` holds 13 suites and **none is a sync suite** | **The suite does not exist** — observed absence of the artefact the gate names |
| 7 | **M8 → M9 gate.** Assigned to M8 task 10 (`M8_Design_Review` §10), which §14.11 also carries process-kill and real storage exhaustion for. §10.1: *"task 8 is the first thing that can move to M8.1 without breaking the milestone gate — **task 10 cannot**."* No commit | **No recorded evidence of this gate was found in the repository** — no commit, and no `M8_Verification_Report.md` where M0–M7 each have one |
| 8 | **FR-SYN-010 / NFR-PER-004 — TD-41** | **Open** (below) |

## Verification history

| Milestone | Stages | Tests | Coverage | Contracts | Verify cycles |
| --- | :-: | --: | --: | :-: | :-: |
| M0 | 8/8 | 100 | 87.30% | 3 kept | 4 |
| M1 | 8/8 | 192 | 93.01% | 3 kept | 4 |
| M2 | 8/8 | 245 | 93.56% | 3 kept | 1 |
| M3 | 8/8 | 312 | 93.38% | 3 kept | 2 |
| M5 | 8/8 | 449 | 94.33% | 3 kept | 4 |
| M6 | 8/8 | 525 | 93.92% | 3 kept | 5 |
| M7 | 8/8 | 665 | 94.47% | 3 kept | **2** |
| M7 + identity fix | 8/8 | 685 | 94.78% | 3 kept | **1** |
| M7 + owner bootstrap | 8/8 | 703 | 94.83% | 3 kept | **1** |
| M7 + TD-30 | 8/8 | 712 | 94.85% | 3 kept | **2** |
| M7 + TD-21 | 8/8 | 712 | 94.85% | 3 kept | **1** |
| M7 + TD-2/TD-18 | 8/8 | **712** | **94.83%** | 3 kept | **1** |
| **M8 task 0 — dashboard endpoint** | 8/8 | **726** | **94.88%** | 3 kept | **1** |
| **M8 task 1 — Flutter shell + contracts** | 8/8 | **742** | **94.88%** | 3 kept | **1** |
| **M8 task 2 — API layer** | 8/8 | **743** | **94.88%** | 3 kept | **1** |
| **TD-39 — delivery outcome idempotency** | 8/8 | **758** | **94.71%** | 3 kept | **1** |

> Coverage fell 0.18 points in M3, 0.41 in M6, **0.02 closing TD-2** and **0.17 closing
> TD-39**. All recorded rather than rounded away. The gate is 80% and has never been moved.
>
> **TD-39's dip is the guarantee itself.** Per-file: `fulfilment/services.py` **93%** (lines
> 144, 305–311, 388–394) and `fulfilment/models.py` **94%**. Those ranges are the two
> `IntegrityError` recovery branches — the arms that execute only when the unique constraint
> actually loses a race, which a single-threaded suite cannot reach. **The uncovered lines
> are the concurrency mechanism**, and no amount of serial testing will colour them in.
>
> **The TD-2 dip is structural and will not come back.** The `WithAnnotations` block in
> `inventory/selectors.py` sits under `if TYPE_CHECKING:` — statements that **can never
> execute**, and so can never be covered. That is the price of describing an annotated
> queryset without asserting that every `Product` carries `on_hand`, and it is a deliberate
> trade. *(Attribution is inference: per-file coverage was not captured for this run.)*
>
> **Only two of M6's five cycles were domain work.** One went to lint, one to migrations
> that by definition cannot be generated, one to test defects. Cycle count measures
> difficulty only when everything else holds still.
>
> **M7's two cycles are the design, not the engineering.** A milestone that writes no
> migration, takes no lock and enforces no business rule has less that can fail. Both of
> its defects were framework-integration failures — `csv.writer` quoting, DRF content
> negotiation — which **no design review can find and only stage 7 can**.

## Pinned verification environment

Introduced at M5 after a toolchain change broke the gate under unchanged source.
**The pins held through M6** — and are now **superseded by `uv.lock`** (TD-21 closed). They
stay in place until retired in their own change: removing them alongside the lock's
introduction would move two variables at once.

| Component | Version |
| --- | --- |
| Python · Django | 3.12.13 · 5.1.15 |
| pytest · **pytest-django** · pytest-cov | 9.1.1 · **4.12.0** · 7.1.0 |

## Structural gates

| Gate | State |
| --- | --- |
| `ops/check_structural_columns.py` | Satisfied since M2 — `location_id` and `lot_id` on every movement (ADR-0004, E-06) |
| `lint-imports` — 3 contracts | Kept. **144 files, 271 dependencies**, 14 root packages *(captured from the TD-39 verify run; 143 / 271 was task 1's)*. Has caught 4 violations across 7 milestones, all by the rule's author |
| **The mobile layers hold, from the first Dart file** | **17** tests in `backend/tests/adversarial/test_mobile_boundary.py`, running **inside stage 7** because `make verify` is the only authority and it does not run `flutter analyze`. They assert layering, `features` never importing an implementation, **P-9** (no secret, internal surface or high-entropy literal in a decompilable binary), **P-3**, **P-6**, and that the parser refuses constructs it cannot read. Each was **proved able to fail** by mutation |
| **The Flutter pin is stated once** | `mobile/.flutter-version`. The Makefile reads it; `docker/flutter.Dockerfile` takes it as an `ARG` with no default. A test fails if either restates it — the first draft kept two copies and policed them with a test, which is the worse answer |
| **The Flutter toolchain is built, not borrowed** | `ghcr.io/cirruslabs/flutter` stopped publishing 2026-05-01, before Flutter 3.44 existed. A test fails if `FLUTTER_IMAGE` points at that registry or its Docker Hub predecessor |
| **The refresh client carries no interceptors** | **D-B2.** `api_client.dart` gives interceptors to `_dio` only; a test fails if `_refreshDio` receives any, or if any name other than `_dio` appears before `.interceptors.add`. A refresh call able to trigger the refresh interceptor is an infinite loop reachable from one expired token — and an interceptor never added cannot be re-entered, which a flag can |
| **Money cannot be built from a number** | **P-3 / AD-02 / C-1.** `Money.fromJson` throws on `num`; by the time a `double` exists the precision is gone and no later check recovers it. It also carries the scale it arrived with, because `package:decimal` normalises `'11800.00'` to `'11800'` — correct arithmetic, wrong transport |
| **No mobile check can be silenced** | A test forbids `\|\| true` and make's leading `-` in any mobile recipe. `mypy` carried `\|\| true` for six milestones with 24 real errors behind it (TD-2); `pip-audit` still does (TD-35) |
| **The dashboard cannot acquire an export** | `DashboardView` declares only `JSONRenderer`, so `?format=csv` fails DRF's negotiation with `Http404` before the view runs — a mechanism, not a branch. Two tests hold it: one asserts the 404, one asserts the dashboard is **absent** from the seven-report CSV parametrisation, so it cannot be handed an export by a test (M7 §8.2, `05` §9.11.1) |
| **`reporting` owns nothing** | No `models.py`, no `services.py`, no migration, absent from `INSTALLED_APPS`. Four AST tests assert it, including that it imports no `*.services` and no first-party `*.models` (M7-4, M7-5) |
| **One canonical phone number** | `identity/phone.py` defines it once; `UserManager._create` writes it and every lookup reads it. Migration `identity/0004` normalised existing rows and **refuses to merge collisions** (`04` T-01) |
| **The first authorised user is reachable** | `bootstrap_owner` (FR-IAM-014). Refuses while an **active** owner exists, refuses a deactivated target, audits every use as `OWNER_BOOTSTRAP` with `actor_user` NULL. **A test asserts the deadlock it exists to break**, so it cannot be deleted as redundant |
| **The factory builds users like production** | `UserFactory._create` routes through `UserManager.create_user`. A test gives it a non-canonical phone and asserts it comes back canonical — the smallest statement that the production path is taken, and it fails the moment anyone reverts it |
| **FR-RPT-015 measured, not assumed** | `ops/report_performance.py` builds a five-year DR-8 dataset (73k invoices, 292k lines, 103k ledger entries) and times all eleven report calls **individually**. Currently **0 breach(es)**. Re-run after any change to a report or to the §5A walk |
| **`mypy` is blocking** | **Zero errors across 115 source files.** Stage 6 of `make verify` and the CI type-check step both fail on a type error — verified by injecting one and confirming exit code 1. No error was silenced with `Any`; three were **false signatures** the check caught (TD-2/TD-18) |
| **The build is reproducible** | `uv.lock` pins **91 packages** including every transitive one. All three install sites — Dockerfile builder, builder-dev, CI — use `uv sync --frozen`, which **refuses to re-resolve**. `COPY ... uv.lock` carries no glob, so a missing lock fails stage 1 rather than falling back silently (TD-21) |
| Order/inventory/ledger boundary | Orders write no stock movement and no ledger entry, and cannot import the ledger's writer (M3-6) |
| Financial immutability | Raw SQL refused on `invoice`, `invoice_line`, `credit_note`, `credit_note_line`, `customer_ledger_entry` and now `payment` |
| Double-restock (Scenario F) | Impossible by construction — a credit note writes no stock (ADR-0009) |
| **§5A.7 ledger invariant** | `Σ outstanding - credit_on_account ≡ settled_balance`, asserted over five randomised seeds spanning all six entry roles |
| **One opening balance per customer** | Partial unique index. The go-live import is idempotent (M6-11) |
| `make verify` | 8 blocking stages. The only authority (N-12) |

## Blocking before M8

| # | Item | Owner |
| --- | --- | --- |
| 1 | M7, **the identity phone fix and the owner bootstrap** committed, tagged `m7-reporting`, pushed. **The tag goes here** — this is the first commit in the repository's history at which `git clone && make up && make owner` yields a usable system | Engineering |
| ~~2~~ | ~~TD-27 — run `ops/report_performance.py`~~ | **Done.** Measured before M8, which was the point: a second toolchain would have conflated two variables |
| ~~3~~ | ~~TD-21 — make the build reproducible~~ | **Done.** `uv.lock` committed and consumed; the build fails closed without it |
| ~~4~~ | ~~TD-2/TD-18 — make `mypy` blocking~~ | **Done.** Zero errors, stage 6 and CI both blocking |
| 5 | **CF-1 — is statutory e-invoicing mandatory?** More expensive with every invoice issued | Business owner |
| ~~6~~ | ~~M8 design review written and signed~~ | **Done.** `docs/M8_Design_Review.md` v1.2.0, signed 2026-08-10, both ADRs approved |
| 7 | TD-15 — assign a milestone to `offer` | Product Architect |

### Open inside M8, blocking task 8 only

| # | Item | Owner |
| --- | --- | --- |
| OI-7 | **"Notifications" were cut from Edition 1** by `02A` §13 (*"In-app notifications, M-14 entirely"*, 0.5 units). Recommendation: adopt `02A`'s own substitute — a **"Needs attention"** filtered read — rather than reopening the cut | Product Architect |
| TD-36 | **The seven report endpoints emit money as JSON floats** (below) | Engineering |

## Technical debt

Full list in `docs/M7_Verification_Report.md` §7. **M7 opened three items and closed none
it can prove.**

| # | Item | Due |
| --- | --- | --- |
| ~~**TD-39**~~ | ~~`/deliveries/{id}/complete` and `/fail` do not accept `client_uuid`~~ | **CLOSED 2026-08-11.** `outcome_client_uuid` added as a *separate* key — `Delivery.client_uuid` still identifies the assignment. Savepoint + `IntegrityError`, the `record_payment` pattern; in `fail_delivery` the identity is claimed **before** the RETURN movements, so a lost race cannot leave a duplicate restock. 15 tests. Verified 8/8, **758/758**, 94.71% |
| **TD-41** | **New. Sync is triggered at launch only, which does not satisfy FR-SYN-010.** The requirement is *"within 2 minutes of reconnection at the DR-8 envelope"* (NFR-PER-004); the frozen mobile stack carries **no connectivity-state mechanism**, so no reconnection can be detected. A launch is when a device reconnects in practice, not by guarantee. Cited in three places in the repository — `mobile/lib/app/bootstrap.dart`, `mobile/test/startup_refresh_race_test.dart` and `docs/05_API_Contracts.md` §11.1 (D-M9.4-7) — each stating that the launch trigger **is not claimed** to be FR-SYN-010. `SyncEngine.sync()` and the D-M9.4-7 chain do not change when the trigger is built; its single-flight guard already makes a burst of connectivity events safe | **Open — M9** |
| **TD-37** | **Open, and costlier after task 2.** `mobile-verify` is not part of `make verify`, so *"does the Dart compile"* is ungated — and the **29 Dart cases that prove D-B1/D-B2/D-B3 are invisible to the only authority**. The 743 figure does not include them. The M8 contracts that *must* be blocking are enforced from stage 7 in Python because they are structural and need a parser, not a compiler; a Dart compile error still reaches `main`. Promote `mobile-verify` to stage 9 once the toolchain image has held for a milestone — adding an untested stage to the only authority is worse than none | M9 |
| **TD-38** | **New. The Flutter SDK is pinned by version, not by bytes.** `FLUTTER_SHA256` is an optional build-arg and the build prints the checksum it downloaded; `uv.lock` gives the Python side the stronger guarantee. Closing it is one paste from a `make mobile-image` run | M8, before task 3 |
| **TD-36** | **New, and the most consequential.** The seven report endpoints **emit money as JSON floats**, against AD-02 — whose rationale names Dart and whose client obligation is C-1. `COERCE_DECIMAL_TO_STRING` is set but reaches only `serializers.DecimalField`; `api.v1.report_views._as_json` hand-builds its dict, so DRF's encoder renders `Decimal("1180.00")` as `1180.0`. **Measured, not inferred.** The existing assertion reads `Decimal(str(...))`, and that `str()` makes it pass whichever type arrives — which is how this survived four reviews and a blocking type gate. **Breaking change to a published response type: its own change, its own verify run.** Fix by routing `_as_json`'s numeric cells through `money_string`, added in task 0 for exactly this reuse | **M8, before task 8** |
| **TD-32** | **New. Retire the `==` dev pins**, now superseded by `uv.lock`. Their own change, their own verify run — and keep the pytest-django incident narrative when the comment block goes | M8 |
| TD-11 | **SMS / DLT registration not started — blocks go-live.** Unbounded external lead time | Now |
| **TD-33** | **New. Adopt `djangorestframework-stubs`.** Deferred deliberately: it would surface a fresh error wave across `api/v1` in the same change that closed the gate. The original objection — tight `mypy`/`django-stubs` pins — is now **weaker**, because `uv.lock` manages them (TD-21). Adopt once the gate has held through one milestone | M8+ |
| **TD-34** | **New. `ops/` is outside `mypy backend/`.** `ops/report_performance.py` imports eight model modules and every report selector, and the blocking gate cannot see it — so a selector signature can change under it silently | M8 |
| **TD-35** | **New. `pip-audit --strict \|\| true` in CI** is still advisory. Found while closing the type gate; the *same* pattern, a different scan | M8 |
| TD-23 | `billing/selectors.py` scoping branches. FR-RPT-014's tests exercise exactly that surface, so it is **very likely closed — but per-file coverage was not captured**, and this table does not record what was not observed | M8 |
| TD-26 | `_walk`'s three robustness guards are exercised only by the randomised property test | M8 |
| TD-14 | `Product._has_history()` still inert. **Overdue** since M3 | M8 |
| ~~TD-22 / TD-25~~ | ~~Advisory `mypy` diagnostics~~ | **CLOSED with TD-2/TD-18** — all 24 fixed, none silenced with `Any` |
| **TD-29** | **New.** Nothing asserts a *newly added* report is wired into `REPORT_MENU`, the API router and the CSV path. The eighth report will be added by someone who forgets one of the three. **Task 0 added an eighth endpoint under `/reports/` and TD-29 did not bite — because the dashboard is deliberately in none of the three.** A test now asserts that absence; the gap for a genuine eighth *report* is unchanged | M8 |
| **TD-31** | **New. A test that reads the wall clock while asserting against a constant fails on a date rather than on a change.** Four instances found and fixed; two other `stocked` fixtures were left alone because they bound no period. The class is recorded because the next instance will be written by someone who has not read this row | M8 |
| **TD-28** | **New.** `?format=csv` on an unauthorised report stringifies the problem+json body through `CsvRenderer`. Cosmetic, untested error path | M10 |
| TD-24 | Move `_ImmutableDocument` to `core` (D-7, deferred by ruling) | M10 |
| TD-15 | `offer` has no milestone | Open |

**Closed:** TD-5 (M1) · TD-12, TD-13 (M2) · TD-17 (M3) · TD-16, TD-19 (M5) · **none (M6)** ·
**none confirmed (M7)** · **TD-30, TD-27, TD-21, TD-2/TD-18, TD-22/TD-25 (post-M7)**.

> **M8 task 1 opened two debts and cost four infrastructure defects, none of them in the
> application code.** A dead image registry, a pub cache that did not survive the container
> boundary, an analyzer whose defaults differ from its sibling's, and a directory that was
> never bind-mounted. **Every one was found by running the thing**, and three of the four
> produced a failure message that pointed at the wrong layer — the missing mount reported
> *"the Flutter pin is not stated exactly once"*. That is the cost worth remembering: a
> misdiagnosis is more expensive than the fault, and the fix for it is a precondition check
> that fails as plumbing.

> **TD-2/TD-18 closed at the fourth attempt.** Missed at M5, M6 and M7 — each time for a
> sound reason, and the fourth time there was none left. Of the 24 errors it cleared,
> **three were signatures that lied** about what a function returned; one of those alone
> produced five errors, four of them in a module it did not live in.

> **TD-27 closed with evidence, not with a tick.** The harness measured 11.7 s for
> receivables ageing — a **quadratic in the §5A walk**, where `_annulled_entry_ids` was
> re-evaluated once per entry inside a comprehension condition. Hoisting the pure call
> fixed it without changing a single answer or a single test. **0 breach(es)**
> (`docs/M7_Verification_Report.md` §13).

> **TD-30's creation half is closed structurally; its role half is closed by coverage
> elsewhere** (`docs/TD-30_Factory_Creation_Path_Note.md` §3). The second is a discipline
> rather than a mechanism. If the fixture layer is ever reworked, routing `roles=` through
> the services is the right thing to do then.
