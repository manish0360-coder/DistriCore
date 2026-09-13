# Project State

| | |
| --- | --- |
| Phase | **Phase 1 — Implementation** |
| Current milestone | **M10 — Hardening.** The `00` §19.2 **M10 → M11 gate is met on both halves** — security review complete (11/11 NFR-SEC, `docs/M10_Security_Review.md`; NFR-SEC-009 met at M10.5) and restore rehearsed and recorded (B-3, 2026-09-07, PASS in 8s). **HEAD is `eb02ae9`** *(was `95214e2`; and `bf94b8e` before that — this row was seven commits stale until 2026-09-04)*. **A met gate is not a closed milestone:** M10 also delivers performance work — **measured at the DR-8 envelope on 2026-09-08 and now evidenced** (`docs/M10.6_Performance_Report.md`: NFR-PER-003 PASS, NFR-SCA-001 PASS, NFR-PER-005 MET; NFR-PER-001 and NFR-SCA-003 PARTIAL, bounded by a surface that is Edition 1b and by the instrument, not by a defect) — and carries TD-24, TD-28, TD-42…TD-48, none of which the gate touches. Four M9 increments are committed (M9.1–M9.4, below). The working tree passes the full mobile verification suite (**352 tests**; 346 at `1daac33`, 324 at `e2fbc07`, 317 when this row was written). **TD-41's retry cadence shipped in `8a3cee2`, and its FR-SYN-010 acceptance (B1) passed on a device on 2026-09-06.** **One requirement closed on 2026-08-25 — encryption at rest** (FR-SYN-016, NFR-SEC-008; D-M9-8), proven on a device and uncommitted at the time of writing. **That closes a requirement, not a milestone and not a gate.** **M9 is not closed:** several FR-SYN requirements are unbuilt and two corpus contradictions are open — see *Open at M9*. **All three documented gates now have recorded evidence** (`docs/M8_Verification_Report.md`, `docs/M9_Verification_Report.md`, and for M10 → M11 `docs/M10_Security_Review.md` + `docs/runbooks/restore-from-backup.md`), which closes three rows of that register and no requirement. **FR-RPT-009 closed 2026-09-06 (D-M9-10)** — `GET /reports/sync-health`, no model and no migration. **The remaining M9 items are decisions, not implementations** (`NEXT_TASK.md`) |
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
| M8 | Mobile app | **In progress.** Phase 1 signed — `docs/M8_Design_Review.md` **v1.8.0**, both ADRs approved: **Drift over an encrypted SQLite** (§5.6 — the cipher clause amended to SQLite3MultipleCiphers by **D-M9-8**, 2026-08-25; the ADR's conclusion, Drift, is unchanged) and **Dio** (§7.5). Principles P-1…P-10 frozen. **Phase 2 tasks 0–5, 7 and 9 committed** plus TD-39 (see the commit history below). **Task 8 — Owner Companion Mode — built 2026-09-06** (§3.4; OI-7 ruled with it). **Tasks 6 and 10 have no commit** — GPS and the separate media queue (**FR-FUL-008/011/014 are `Rel = v1.1`, so not V1** — `02` §111), and the 8-hour offline soak. `mobile/lib/features/` contains `auth`, `companion`, `customers`, `deliveries`, `settings` and `sync_status` |
| M9 | Sync | **In progress.** Four increments committed — M9.1 push receiver, M9.2 mobile drain, M9.3 server status, M9.4 pull and cache. **Not closed:** see *Open at M9* |
| M10 | Hardening | **In progress.** Security review **complete** — 11/11 NFR-SEC evidenced (`docs/M10_Security_Review.md`). **M10.5 addresses NFR-SEC-009**: 15 of 16 findings remediated by upgrade (Django 5.1.15→5.2.17, DRF 3.15.2→3.17.2, WeasyPrint 66.0→68.1, **sqlparse 0.5.5→0.6.0 via `[tool.uv] constraint-dependencies`**), one unfixed WeasyPrint issue exempted with a dated record and two guarding tests. **VERIFIED 2026-09-07** — `make verify` 1203/1203, 94.51%; `make audit` *No known vulnerabilities found, 1 ignored*. **NFR-SEC-009 MET.** **B-3 closed 2026-09-07** — rehearsed, PASS in 8s, recorded in `docs/runbooks/restore-from-backup.md`; re-verified at 1211/1211, 94.51%. **The `00` §19.2 M10 → M11 gate is met on both halves.** **M10.6 closed the performance half 2026-09-08** — first measurement ever taken at the DR-8 envelope (10,000 retailers, 10,000 SKUs, 5 years); M10.6a found two breaches, M10.6b fixed their shared cause (`receivables_position` materialising 373,000 ledger models), re-measured at **0 breaches**: receivables ageing 17.139→**2.922 s**, dashboard 16.874→**2.625 s**. **VERIFIED 1241/1241, 94.57%.** `docs/M10.6_Performance_Report.md`. **The milestone still carries TD-24, TD-28, TD-42…TD-48** |
| M11 | Go-live | **Started — ACT-E, M11.1 deployment readiness, K-1 procedure and M11.2 recovery (all 2026-09-12); M11.3 A-05 provisioning (2026-09-13); M11.4 visual system (2026-09-14).** **M11.4 found there was no design system to redesign:** 71 lines of CSS in four private `<style>` blocks, **zero static files, zero JavaScript, zero media queries, zero focus rules**, `order_detail.html` using `.note`/`.tot` with no rule behind them, and a documented front end (Tailwind, HTMX) that had never been built. Now **one** stylesheet — `webadmin/static/webadmin/districore.css`, 10,405 bytes of rules, 4,453 gzipped, no build step — on a two-plane model: a dark **command surface** for navigation and identity, a light high-contrast **work surface** one elevation step above it. **Colour means state** (settled/pending/breach) and nothing else; per-page themes were rejected because a hue per screen destroys the hue that means *overdue*. Navigation went from **18 flat peer links to four groups** (Sell/Buy/Hold/Configure) collapsing through `<details>`/`<summary>` with no script; `max-width:960px` became `min(96vw,1440px)`; **18 contrast pairs measured, all WCAG AA, worst 5.73**; a focus ring on every control; `tabular-nums` on every figure; all motion ≤200 ms and switched off under `prefers-reduced-motion`. **A landmine was caught before it fired:** `test.py` sets `DEBUG=False` against whitenoise's *manifest* storage with no `collectstatic` in the test container, so the first `{% static %}` call would have killed all 57 web-admin-rendering tests with `Missing staticfiles manifest entry` — fixed in test settings rather than by dropping the tag and forfeiting production cache-busting. 17 contracts, 30 mutations proved, **three of which found defects in this work** — including a contract satisfied by `base.html`'s own comment about `<details>`, the third occurrence of that class after `backup.sh` and `test_release_signing`. `00` FD-05, T-03, the HTMX dependency row and `03` §171/§391 corrected to describe the front end that exists; **ADR-003's title still names HTMX and renaming a ratified ADR is left to the Architect**. No view, URL, model, serializer, permission or business rule changed, and the invoice PDF stylesheet stays independent. **M11.3: A-05 is locked — Backblaze B2, EU Central (Amsterdam) `eu-central-003` — and the disposable smoke test is CLOSED/PASS** (authentication, bucket-scoped access, 16 MiB streaming upload, byte-exact round trip, `delete --min-age`, `deletefile`, 1,200-object pagination; the 24-hour billing observation is deferred to production week 1, where the traffic is real). **Following `deploy.md` end to end produced a broken deploy:** no step provisioned A-05 or configured `rclone`, so steps 1–3 all assumed a remote that nothing created; `.env.example` shipped `DISTRICORE_BACKUP_REMOTE=` with no format, and omitting the bucket segment makes rclone read the prefix as a bucket name and attempt `b2_create_bucket` — the `401 unauthorized` the smoke test hit; **none of the three units sets `User=`, so all run as root** and `rclone` reads `/root/.config/rclone/rclone.conf`, which nothing said; and *Before* step 4 told the operator to run `./ops/backup.sh` by hand as the deploy user while the timers run it as root — two credentials, one job, now standardised on `sudo systemctl start districore-backup.service`. **The env-var contract was scanning one level too narrowly** — `backend/config/settings/*.py` only — and passed while `DISTRICORE_PITR_IMAGE` and `DISTRICORE_PITR_WAIT_SECONDS`, read by the script that discharges NFR-AVA-001, were undocumented; it now scans `ops/*.sh` too. **Documentation plus one widened contract; no mechanism changed, no B2 retest, no retention or Object Lock redesign, no rclone pin (TD-51), no S-09** — `00` §2.5 still has no register entry for the B2 key that can delete every backup, and that stays an Architect decision. **Residency recorded, not resolved:** B2 EU is correct for a proprietorship or partnership; if the business is a company under the Companies Act 2013, Rule 3(5) requires a daily India-resident backup, satisfied by *adding* a destination for the nightly dump rather than changing provider. **NFR-AVA-001 remains NOT MEASURED.** **M11.2 built FD-16's continuous layer, which had never existed.** The Product Architect kept NFR-AVA-001 at RPO ≤ 15 min / RTO ≤ 4 h (single VPS, WAL/PITR, continuous encrypted offsite archival, no standby), so `03` §4.4's unsigned ≈1-hour deviation is moot and no requirement wording changed. **The delivered RPO had been ≈24 hours, not ≈1 hour:** FD-16 decided *"WAL archiving · continuous · separate local volume"* and derived its figure from it, but `wal_level`, `archive_mode`, `archive_command`, `pg_basebackup` and `restore_command` returned **zero hits repository-wide**, and neither NFR-AVA-001 nor NFR-AVA-002 appeared in `backend/` or any verification report. Now: `archive_mode=on` with `archive_timeout=300` to a **separate** `wal_archive` volume (a local `cp` only — `archive_command` runs in the server's shell, and a network upload there stalls WAL recycling until writes stop); `ops/ship-wal.sh` every 5 minutes encrypts, ships and **reads the remote back**; `ops/basebackup.sh` weekly is the PITR anchor and owns WAL retention, because only the base-backup schedule knows where the oldest retained chain starts. **15 minutes is arithmetic** — 300 s + 300 s + 60 s = 11 min against 900 — and a contract recomputes it from all three files, since raising `archive_timeout` in one line would silently unmeet the requirement. **C-5 and two more of its shape:** a missing passphrase warned then stamped success (B-2 green for a dump in clear); a missing remote silently skipped offsite then stamped success (B-7); and **the stamps, the dump and the media sync all used host paths while `/healthz` reads the `backup_data` volume** — so `backup.ok` could never be true on a correctly backed-up host, and `rclone sync /srv/media` named a nonexistent host directory that under `set -e` **failed the nightly run every night**. All three fail closed now, verify from the remote before stamping, and write stamps through the app container. `/healthz` gained `wal_archive` (from `pg_stat_archiver`), `wal_offsite` (**the RPO observable** — lag in seconds against `rpo_target_seconds`), `basebackup`, and one `recovery_ready` boolean — no fifth alert channel, which `00` §13.1 forbids. **`make pitr-rehearsal` is the evidence path**: it recovers from the *offsite* copy, waits for `pg_is_in_recovery()` to go false rather than `pg_isready`, and reports `max(audit_log.occurred_at)` as the achieved recovery point. **NFR-AVA-001 is NOT MEASURED** (`docs/M11.2_Recovery_Report.md`) — `02` §21.6 verifies it by rehearsal, which needs A-03 and A-05; the PITR log is empty and a contract refuses a PASS on any line naming it. 19 contracts, 44 mutations proved, two of which found defects in the new code. **A-05's requirement changed:** ~288 small objects/day plus a weekly base backup, so request-count pricing now matters and a nightly-file-only target no longer suffices. TD-49 (nightly media full tar, revisit above 2 GB) and TD-50 (`cp`+`mv` without `fsync`) recorded. **EP-K / streaming replication remains unbuilt and out of scope.** **VERIFIED 2026-09-12 (N-12)** — clean no-cache build, `make verify` **1319/1319**, 94.51%, ruff/mypy/migrations clean, 3 import contracts kept, `wal_archive` mounted, and **the running PostgreSQL reporting `archive_mode=on`, `archived_count=2`, `failed_count=0`** — read back out of the cluster by a unit test, which is what proves the entrypoint wrapper passed its flags through and gave `archive_command` a writable directory. **`recovery_ready: false` in that clean run is the correct answer and is asserted by a test:** there is no A-05 in a development container, so nothing has been verified offsite and no base backup exists. The default posture is *"not ready"*, not *"presumed fine"*. **M11.1 closed three repository-side gaps that would each have surfaced only in production:** **M11.1 closed three repository-side gaps that would each have surfaced only in production:** `compose.prod.yml` never passed `DISTRICORE_DOMAIN`, so Caddy fell back to `localhost` and would have served an untrusted certificate for a purchased domain — silently; **nothing scheduled the nightly backup** FD-16 requires, so a fresh host would have had none and `/healthz` would have reported `backup.ok: false` for ever; and `ops/backup.sh` loaded a production overlay it does not need, which would have let a missing certificate name stop the backups. Eight contracts in `test_deployment_readiness.py`, each mutation-proved. **The rest of M11.1 is operator provisioning** — A-03/A-04/A-05, S-04/S-05/S-07, A-08 and K-1 — none of which exists. **ACT-E:** `02` §ACT-E *"Opening-balance load and reconciliation"* is the first clause of the `00` §19.2 M11 → live gate, and its two services had **no caller outside the test suite**. `manage.py load_opening_balances` is now that caller: dry-run by default, fail-closed on refusals, idempotent by natural key, with an A/B/C reconciliation the owner signs. Rehearsed against the disposable `districore_perf` — 3 loaded, 7 refused, A = B = C = 105,750.49, re-run a no-op, development database untouched (`docs/runbooks/go-live-data.md`). **ACT-E is ready to execute, not executed** — the real load is an owner action against real figures. **The other two gate clauses — owner sign-off and training — are untouched**, and both need a deployed system: A-03 host, A-04 domain, A-05 offsite, S-04/S-05/S-07 and K-1 do not exist. **K-1's *procedure* was written 2026-09-12** — `docs/runbooks/android-keystore.md`, closing an M8 entry condition that had been open since M8 because, as `rotate-secrets.md` said outright, *"there is no procedure."* Writing it exposed **one real gap** — no ignore rule anywhere matched the `*.p12` that `keytool` actually produces (PKCS12 has been its default since JDK 9), in the root `.gitignore` or in Flutter's generated `mobile/android/.gitignore`; `.pepk` likewise — and **one misplaced rule**: `key.properties`, which holds the store password, key password, alias and path in clear, was ignored *only* by that generated Android file, which `make mobile-android-scaffold` rewrites and which guards one directory, so it was hoisted to the root where N-11 belongs. `git check-ignore -v` is what distinguished the two, correcting a stronger claim first drafted. Nine contracts in `test_release_signing.py`, fifteen mutations proved, asserted on the root `.gitignore` because the backend image has no git. **VERIFIED 2026-09-12 — `make verify` 1285/1285, 94.66%.** **The keystore itself has not been generated and the runbook's log is empty**, so this closes an M8 entry condition and moves the M11 → live gate not at all |
| M12 | Retailer role (Edition 1b) | Not started |

### The canonical roadmap

`docs/00_Engineering_Foundation.md` §19.1 defines **M9 = Sync** and **M10 = Hardening**, and
**defines no sub-milestones**. `M9.1`–`M9.4` below are *working labels for four commits*, not
roadmap entries. There is no M9.5 and none is proposed here.

Gates, from `00` §19.2, verbatim:

| Gate | Condition | State |
| --- | --- | --- |
| M8 → M9 | *"Outbox survives kill, restart and storage exhaustion"* | **PASSED** 2026-09-01 / 2026-09-04 — `docs/M8_Verification_Report.md` |
| M9 → M10 | *"Adversarial sync suite passes: zero loss, zero duplicates"* | **PASSED** 2026-09-04 — `docs/M9_Verification_Report.md` |
| M10 → M11 | *"Restore rehearsed and recorded (B-3); security review complete"* | **PASSED** 2026-09-07 — security review 11/11 (`docs/M10_Security_Review.md`, NFR-SEC-009 met at M10.5); B-3 rehearsed 2026-09-07, PASS in 8s, recorded in `docs/runbooks/restore-from-backup.md` |
| M11 → live | *"Opening balances loaded and reconciled; owner signed off; training done"* | **OPEN — 1 of 3 clauses mechanised.** Opening balances: the ACT-E load exists and was **rehearsed 2026-09-12** (`docs/runbooks/go-live-data.md`); the load itself is an owner action against real figures and has **not** been performed. Owner sign-off and training: **not started**, and both require a deployed system that does not yet exist (A-03/A-04/A-05, S-04/S-05/S-07, K-1 — K-1's procedure is written, `docs/runbooks/android-keystore.md`, but the keystore is not generated) |

> **A passed gate is not a closed milestone.** All three conditions above now hold. M8 still has
> two uncommitted tasks, M9 still has five open items — four of them questions no engineer may
> answer alone — and M10's own debt register is untouched by its gate. Its performance half
> was closed separately at M10.6 (2026-09-08), which the gate does not mention either. The
> gates and the milestones are tracked separately on purpose.

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
| 1 | **FR-RPT-009 — sync health report** (FR-SYN-015) | **CLOSED 2026-09-06 — D-M9-10.** `GET /reports/sync-health` (`05` §9.11.2), per-device counts with the FR-SYN-015 conflict proportion. **No model, no field, no migration**: `sync_operation` already recorded every column. FR-SYN-015's Edition-1 quantity is `REJECTED ÷ settled`, proposed as `02` amendment **S-7** and **not yet written**. Proven by `make verify` against seeded rows — **no field-fleet evidence is claimed** |
| 2 | **FR-SYN-009 — `SALESMGR`/`ADMIN` per-device view.** `05` §11.5 is captioned *"(FR-SYN-008/009)"*, but **D-M9.3-1** freezes `device_id` as taken from the JWT *"never from the request"*, so the endpoint can only ever show the caller's own device. No other surface exists | **Open — apparent contradiction inside `05` §11.5** |
| 3 | **Orphaned `RECEIVED` recovery.** `05` §11.5: *"not specified and is not built … Deferred to M9.4/M10 by ruling."* M9.4 shipped without it, so it has arrived at M10 by default rather than by decision | **Open** |
| 4 | **FR-SYN-007 remainder / stock.** `02` requires *"customers on assigned routes, products, prices, schemes and stock snapshot"*. **D-M9.4-2** implements customers and deliveries only; **D-M9.4-1** records the stock snapshot as an unclosed **CONTRACT GAP** against `04` N-03/E-01 and ADR-008 | **Open — recorded gap** |
| 5 | **FR-SYN-005 / 013 / 014 — conflict console.** `02` FR-SYN-005: *"MUST … persist it as a `SyncConflict` in `PENDING_RESOLUTION`"* (also BR-014). `05` §11.4: *"**No conflict resolution console is built, because none is needed**"*. `SyncConflict` occurs **only in `02`** — no table in `04`, no endpoint in `05`, no model in `backend/sync` | **Open — direct contradiction between `02` and `05`** |
| 6 | **M9 → M10 gate.** *Superseded 2026-09-04: this row read* **"13 suites and none is a sync suite"** *and was true at `bf94b8e`. `4d4854e` (2026-08-22) added* `test_sync_integrity.py`*; the tree now holds **18** suites.* | **CLOSED** — `test_sync_integrity.py` **11/11**, all five fault classes of `02` §25.2 injected; `docs/M9_Verification_Report.md` §3 |
| 7 | **M8 → M9 gate.** Assigned to M8 task 10 (`M8_Design_Review` §10), which §14.11 also carries process-kill and real storage exhaustion for | **CLOSED** — `make mobile-device-kill` passed 2026-09-01 (§5.6.1), `make mobile-device-storage` passed 2026-09-04 (§5.6.2); `docs/M8_Verification_Report.md`. **The storage gate found a real defect in shipping code**: a full disk crashed the outbox instead of returning `StorageFull`. Coverage is `x86_64` emulator only (**TD-45**) |
| 8 | **FR-SYN-010 / NFR-PER-004 / FR-SYN-017 — TD-41** | **CLOSED 2026-09-06 — B1 PASSED: 67 046 ms of a 120 000 ms budget**, 200 operations in one push batch, one pull page, Pixel 8a API 34 **`x86_64` emulator** over host loopback (`M9_Design_Review` §5.1). *Previously:* **Mechanism built 2026-09-05, requirement NOT discharged.** `SyncRound` + `SyncScheduler`: a 60 s fixed cadence, no new dependency, 22 tests, 5 structural contracts. **FR-SYN-017's retry half is closed by the same mechanism.** FR-SYN-010 no longer waits on B1. **TD-45 is unchanged — `arm64` and physical hardware remain unproven — and the transport was emulator↔host loopback, not a field radio link.** Background scope is **TD-47**, still open |

> **All three device gates have now run.** `make mobile-device-encryption` closed NFR-SEC-008 on
> 2026-08-25 — see the note below — and it was never evidence for item 7, which is why this
> paragraph used to say so. **`00` §19.2's durability gate is CLOSED**: `make mobile-device-kill`
> PASSED 2026-09-01 (`M8_Design_Review` §5.6.1) and `make mobile-device-storage` PASSED
> 2026-09-04 (§5.6.2), recorded in `docs/M8_Verification_Report.md`. Kill, restart and storage
> exhaustion are all discharged, on an `x86_64` emulator and nothing else (**TD-45**). `00`
> §19.2's durability gate needs
> `make mobile-device-kill` and `make mobile-device-storage`, which exist in the Makefile and
> still have **no recorded run**. **Neither gate may be cited as evidence for the other**, and
> the encryption result does not shrink this list: all eight items above stand.

> **Encryption at rest — CLOSED 2026-08-25 (D-M9-8). Read narrowly.**
>
> FR-SYN-016 and NFR-SEC-008 are met and proven on a device. **Implementation:** the
> `package:sqlite3` build hook selects SQLite3MultipleCiphers (`source: sqlite3mc`); the key is
> the Android keystore value from `PlatformDatabaseKey`, unchanged. **Observed, and recorded as
> observations rather than requirements:** `PRAGMA cipher` → `chacha20`, SQLite `3.53.4`.
> Neither `02` nor this document requires a particular cipher, and neither is amended.
>
> **Evidence:** a keyed round trip recovered the row and payload; a deliberately wrong key was
> refused with `SqliteException` `resultCode = 26` (`SQLITE_NOTADB`), non-destructively; the
> raw database and its WAL carried no SQLite header and no plaintext marker, with the same
> scanner shown able to find those markers in an unencrypted control. Gate:
> `make mobile-device-encryption`.
>
> **Coverage boundary, stated because it is easy to overstate.** Proven on a **Pixel 8a API 34
> emulator, `android-x64`**. **Not arm64. Not physical hardware** (TD-45).
>
> **What this does not close.** No milestone. The **M8 → M9 durability gate** (item 7) and the
> **M9 → M10 adversarial sync gate** (item 6) both remain open.

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
| Python · Django | 3.12.13 · **5.2.17** *(was 5.1.15; raised at M10.5 — seven CVEs, no fix inside `>=5.1,<5.2`)* |
| pytest · **pytest-django** · pytest-cov | 9.1.1 · **4.12.0** · 7.1.0 |

## Structural gates

| Gate | State |
| --- | --- |
| `ops/check_structural_columns.py` | Satisfied since M2 — `location_id` and `lot_id` on every movement (ADR-0004, E-06) |
| `lint-imports` — 3 contracts | Kept. **144 files, 271 dependencies**, 14 root packages *(captured from the TD-39 verify run; 143 / 271 was task 1's)*. Has caught 4 violations across 7 milestones, all by the rule's author |
| **The mobile layers hold, from the first Dart file** | **21** tests in `backend/tests/adversarial/test_mobile_boundary.py`, running **inside stage 7** because `make verify` is the only authority and it does not run `flutter analyze`. They assert layering, `features` never importing an implementation, **P-9** (no secret, internal surface or high-entropy literal in a decompilable binary), **P-3**, **P-6**, and that the parser refuses constructs it cannot read. Each was **proved able to fail** by mutation. **Two were added on 2026-08-25 (D-M9-8):** one asserts the `sqlite3` build hook selects an encrypting source, one asserts the runtime cipher guard is unconditional and paired with it. Both were proved able to fail across eight mutations, including a control confirming a coherent switch to another cipher still passes — the contract holds the property FR-SYN-016 states, not the product chosen to satisfy it |
| **The Flutter pin is stated once** | `mobile/.flutter-version`. The Makefile reads it; `docker/flutter.Dockerfile` takes it as an `ARG` with no default. A test fails if either restates it — the first draft kept two copies and policed them with a test, which is the worse answer |
| **The Flutter toolchain is built, not borrowed** | `ghcr.io/cirruslabs/flutter` stopped publishing 2026-05-01, before Flutter 3.44 existed. A test fails if `FLUTTER_IMAGE` points at that registry or its Docker Hub predecessor |
| **The refresh client carries no interceptors** | **D-B2.** `api_client.dart` gives interceptors to `_dio` only; a test fails if `_refreshDio` receives any, or if any name other than `_dio` appears before `.interceptors.add`. A refresh call able to trigger the refresh interceptor is an infinite loop reachable from one expired token — and an interceptor never added cannot be re-entered, which a flag can |
| **Money cannot be built from a number** | **P-3 / AD-02 / C-1.** `Money.fromJson` throws on `num`; by the time a `double` exists the precision is gone and no later check recovers it. It also carries the scale it arrived with, because `package:decimal` normalises `'11800.00'` to `'11800'` — correct arithmetic, wrong transport |
| **No mobile check can be silenced** | A test forbids `\|\| true` and make's leading `-` in any mobile recipe. `mypy` carried `\|\| true` for six milestones with 24 real errors behind it (TD-2); **`pip-audit` carried it from P0 until M10 (TD-35, closed 2026-09-07) — and the first blocking run found 16 vulnerabilities** |
| **A test factory cannot collide with a hand-written code** | **New.** `factory.Sequence`'s counter is global to the pytest process, so `CustomerFactory`'s `C-{n:04d}` walked the namespace `credit_customer` (**C-0142**, the M7 worked scenario) and `other_zone_customer` (**C-9999**) hard-code. The 143rd anonymous customer in a session was always going to collide on `customer_code_key`; TD-36's twenty-six new cases reached it. Generated codes now take a reserved `C-T` prefix. `tests/adversarial/test_fixture_isolation.py` parses `factories.py` with AST, generates 20 000 codes per sequence and intersects them with every `code="…"` literal under `tests/` — and is **proved able to fail** against the sequence that shipped. **A latent failure that depends on test *count* is invisible until it is expensive** |
| **A `Decimal` cannot leave a report as a JSON number** | **TD-36, closed.** `Column` carries a semantic `ColumnKind`; `MONEY`/`QUANTITY`/`RATE` cross the wire as canonical strings through `core.fields`, `COUNT` stays a JSON integer (`05` AD-02, AD-02.1). `tests/adversarial/test_report_wire_format.py` runs a pure rule against **every registered report**, read from `REPORT_MENU` so it cannot drift from TD-29's registry, and **fourteen mutations were each proved to make it fail** — money, quantity and rate as floats, an undeclared `Decimal`, four wrong scales, a stringified count, the total row separately, plus a conformant control. The rule that replaced it caught what the old assertion could not: `Decimal(str(...))` passed whichever type arrived |
| **Repository contracts are bind-mounted, not assumed** | `docker/compose.dev.yml` mounts `Makefile`, `mobile/`, `docker/`, `scripts/` and — since M10 — `.github/`, `docs/` and `.gitignore`, read-only, so stage 7 can assert them. **Both suites that read outside `backend/` first failed on the missing mount rather than on their subject**, so each opens with a `REQUIRED_PATHS` precondition test that names the compose block in its message. A diagnosis pointing at the wrong layer costs more than the failure it describes |
| **The dependency audit cannot be silenced** | **NFR-SEC-009, M10 + M10.5.** Three contracts read `.github/workflows/ci.yml`, which *is* the mechanism: no `\|\| true`, `--strict` present, no `continue-on-error`; **every `--ignore-vuln` identifier must appear in `M10_Security_Review.md`** and any exemption must carry a review date; and `presentational_hints` must appear nowhere in backend code, because the one exemption's validity rests on that. **M10's blanket ban on `--ignore-vuln` became a traceability requirement, which is stronger** — an undocumented ignore still fails. Four mutations proved: `\|\| true` restored, an undocumented ID added, the review date removed, hints enabled |
| **The dashboard cannot acquire an export** | `DashboardView` declares only `JSONRenderer`, so `?format=csv` fails DRF's negotiation with `Http404` before the view runs — a mechanism, not a branch. Two tests hold it: one asserts the 404, one asserts the dashboard is **absent** from the seven-report CSV parametrisation, so it cannot be handed an export by a test (M7 §8.2, `05` §9.11.1) |
| **`reporting` owns nothing** | No `models.py`, no `services.py`, no migration, absent from `INSTALLED_APPS`. Four AST tests assert it, including that it imports no `*.services` and no first-party `*.models` (M7-4, M7-5) |
| **One canonical phone number** | `identity/phone.py` defines it once; `UserManager._create` writes it and every lookup reads it. Migration `identity/0004` normalised existing rows and **refuses to merge collisions** (`04` T-01) |
| **The first authorised user is reachable** | `bootstrap_owner` (FR-IAM-014). Refuses while an **active** owner exists, refuses a deactivated target, audits every use as `OWNER_BOOTSTRAP` with `actor_user` NULL. **A test asserts the deadlock it exists to break**, so it cannot be deleted as redundant |
| **The factory builds users like production** | `UserFactory._create` routes through `UserManager.create_user`. A test gives it a non-canonical phone and asserts it comes back canonical — the smallest statement that the production path is taken, and it fails the moment anyone reverts it |
| **FR-RPT-015 measured, not assumed** | `make perf` builds the five-year DR-8 dataset **at `01` NFR-4's stated ceilings** — 10,000 retailers, 10,000 SKUs, 73k invoices, 292k lines, 373k ledger entries — into the disposable `districore_perf`, and times all **thirteen** reports individually plus eleven S1 operations and six linearity curves. **0 breach(es)** at 2026-09-08. Re-run after any change to a report or to the §5A walk; the verdicts are `ops/perf_verdicts.py`, and a measured breach can no longer be reported as NOT MEASURED |
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

### Open inside M8 — ~~blocking task 8~~ **both closed 2026-09-06**

| # | Item | Owner |
| --- | --- | --- |
| ~~OI-7~~ | ~~"Notifications" were cut from Edition 1 by `02A` §13~~ — **RULED 2026-09-06.** M-14 stays cut; "Needs attention" is two filtered reads (confirmed-not-dispatched orders, failed deliveries). **"Overdue balances" excluded from V1** — no overdue rule exists, `Customer.credit_days` is read by nothing, and defining one is a `receivables` decision (D-3) | ~~Product Architect~~ |
| ~~TD-36~~ | ~~The report endpoints emit money as JSON floats~~ — **CLOSED 2026-09-06** (below). **OI-7 is now the only thing blocking task 8** | ~~Engineering~~ |

## Technical debt

Full list in `docs/M7_Verification_Report.md` §7. **M7 opened three items and closed none
it can prove.**

| # | Item | Due |
| --- | --- | --- |
| ~~**TD-39**~~ | ~~`/deliveries/{id}/complete` and `/fail` do not accept `client_uuid`~~ | **CLOSED 2026-08-11.** `outcome_client_uuid` added as a *separate* key — `Delivery.client_uuid` still identifies the assignment. Savepoint + `IntegrityError`, the `record_payment` pattern; in `fail_delivery` the identity is claimed **before** the RETURN movements, so a lost race cannot leave a duplicate restock. 15 tests. Verified 8/8, **758/758**, 94.71% |
| **TD-41** | **Mechanism built 2026-09-05; the requirement is not discharged.** *This row read: "Sync is triggered at launch only… the frozen mobile stack carries **no connectivity-state mechanism**, so no reconnection can be detected."* Two claims in it were wrong. **(a)** Reconnection needs no connectivity package: a connectivity event reports *link* state, not reachability — a phone behind a captive portal reports connected and cannot reach the server — so the authoritative test of "reconnected" is a request that succeeds, and the mechanism that bounds FR-SYN-010 is a **fixed-cadence attempt**. **(b)** *"its single-flight guard already makes a burst safe"* held for `SyncEngine` only: `PullService` had **no guard at all**, and the push→pull ordering lived in a private function in `bootstrap.dart` that also restores a session. What shipped is `SyncRound` (the ordering + a guard over the **pair**) and `SyncScheduler` (a **60 s fixed cadence**, no new dependency). **`FR-SYN-017` is folded in here** — *"retained **and retried**"* — its retry half never existed either, and this is the same mechanism. **B1 measured 2026-09-06 and PASSED** — 67 046 ms against the 120 000 ms budget, of which ≈60 000 ms is the cadence itself (the conservative `t0` charges the whole wait) and ≈7 046 ms is the actual push-and-pull. FR-SYN-010 is satisfied **at the measured configuration**: `x86_64` emulator (**TD-45 unchanged**), emulator↔host loopback rather than a field link, one device, one run. See **TD-47** for the background case. Pinned by five contracts in `test_mobile_boundary.py` | **CLOSED — B1 passed** |
| **TD-48** | **New. The B1 harness prints a `t0` that is not the basis of its own `elapsed_ms`.** `sync_reconnect_test.dart` emits `t0=` at the offline probe, then computes `elapsed` from `ticker.previousTickAt` — the last failed *tick*. In the passing run those differ by 60 061 ms, so `t1 − t0` reads 127 107 ms against a 120 000 ms budget: **a reader subtracting the printed pair concludes the run failed when it passed.** The measurement is correct; only the label is wrong. Emit `t0_effective` alongside the probe before the next B1 run | M10 |
| **TD-47** | **New. FR-SYN-010's scope in the background is unspecified, and no in-process mechanism can satisfy it there.** `02` FR-SYN-010 says *"within 2 minutes of reconnection"* and names no application state. Android Doze and App Standby suspend in-process timers, and on many OEM builds connectivity callbacks too — so **neither the shipped cadence nor a `connectivity_plus` listener can guarantee the bound while the app is backgrounded**. That needs `WorkManager`/`JobScheduler` with a network constraint, which is a platform-service milestone rather than a parameter change. TD-41 deliberately does **not** cancel the cadence on `paused`/`inactive`: whether a Dart timer survives backgrounding is the OS's decision, and stopping it in our own code would add a *second, self-inflicted* reason to miss the bound. **Whether FR-SYN-010 binds in the background is a Product Architect ruling, not an engineering choice**, and the lenient reading has not been assumed | **Open — needs a ruling** |
| **TD-37** | **Open, and costlier after task 2.** `mobile-verify` is not part of `make verify`, so *"does the Dart compile"* is ungated — and the **346 Dart cases are invisible to the only authority** (317 when this row was written, 324 at `e2fbc07`). The 829 figure does not include them. The M8 contracts that *must* be blocking are enforced from stage 7 in Python because they are structural and need a parser, not a compiler; a Dart compile error still reaches `main`. Promote `mobile-verify` to stage 9 once the toolchain image has held for a milestone — adding an untested stage to the only authority is worse than none. **TD-42 is the stronger statement of the same gap and does not close this one** | M9 |
| **TD-42** | **New. No Android SDK or JDK in the pinned toolchain image.** `grep -inE "android\|jdk\|sdkmanager\|adb" docker/flutter.Dockerfile` returns nothing, so **every Android artefact is produced by an unpinned host toolchain that `make verify` cannot see**, and no device gate can run in CI. **Amended 2026-09-01:** *"no shell in which both `make` and `flutter` work"* is no longer true — `make` in WSL reaches the Windows launcher through `scripts/win-flutter.sh`, and `make mobile-device-kill` passed that way. The device gates are still run by hand and still cannot run in CI. Strictly stronger than TD-37, which stays open | M10 |
| **TD-43** | **New. `PRAGMA key = '$key'` is unescaped string interpolation** in `mobile/lib/data/db/connection.dart`. Safe today only because `PlatformDatabaseKey._mint()` emits 64 hexadecimal characters — **safe by accident, not by construction**. Nothing enforces the key's shape at the boundary that consumes it | M10 |
| **TD-44** | **New. `libsqlite3-0` in `docker/flutter.Dockerfile` is very likely unnecessary** since `package:sqlite3` 3.x bundles its own library through a build hook. Its justifying comment has been corrected in place; **the package is retained until disproved**, because disproving it costs an image rebuild and a full gate run, and removing it on the strength of a comment is the reasoning that left `sqlcipher_flutter_libs` in the tree for a milestone | M10 |
| **TD-45** | **New. `arm64` and physical hardware are unproven.** The encryption gate (D-M9-8) covers **`android-x64` on a Pixel 8a API 34 emulator only**. The same is true of any device gate run on that AVD | M10 |
| **TD-46** | **New. `storage_failure.dart` imports `package:drift/remote.dart`, which drift marks experimental.** `flutter analyze` reports `experimental_member_use`; the gate passes it only because `--no-fatal-warnings` is set. Deliberate: `DriftRemoteException` is the wrapper `NativeDatabase.createInBackground` puts around every error from the background isolate, and without it a full disk is not classified at all — the app crashes instead of returning `StorageFull` (`M8_Design_Review` §5.6.2) | M10 |
| **TD-38** | **New. The Flutter SDK is pinned by version, not by bytes.** `FLUTTER_SHA256` is an optional build-arg and the build prints the checksum it downloaded; `uv.lock` gives the Python side the stronger guarantee. Closing it is one paste from a `make mobile-image` run | M8, before task 3 |
| ~~**TD-36**~~ | **CLOSED 2026-09-06** — `M8_Design_Review` §3.4.1b, `05` **AD-02.1**. *This row read: "New, and the most consequential. The seven report endpoints emit money as JSON floats… Fix by routing `_as_json`'s numeric cells through `money_string`."* **Eight, not seven** — FR-RPT-009 landed in between and carried the same defect. **And the prescribed fix was wrong**: routing every *numeric* cell through `money_string` would have stringified `rank`, `oldest_days`, `documents`, `orders` and the six sync counters, shipping the opposite defect. `numeric: bool` could not distinguish them, which is why the fix is a semantic **`ColumnKind`** — `TEXT`/`COUNT`/`MONEY`/`QUANTITY`/`RATE` — with `numeric` **derived** (`kind is not TEXT`) so the CSV formula guard and the screen alignment are unchanged. `reporting` owns what a number *is*; `_as_json` owns how it travels. A `Decimal` backstop covers row keys no column declares (`_sales_by_customer` emits one). **CSV proven byte-identical** by rendering the same table through both versions. `RATE` is new and is a **clarification, not an amendment**: `05` AD-02.1 states the boundary AD-02 always implied; `02` is untouched and §9.11.2's metric definition is unchanged. **The client needed no change** — `money.dart` already refused a number, so every float was a hard failure waiting on a device. **The first authoritative `make verify` run found three more things and the new contract found two of them**: a blank `COUNT` was leaving as `""` (now `null`, and `0` was rejected because rank-zero is a measurement); the customer statement's JSON path is a serializer, not a `ReportTable`, so TD-36 never reached it; and a latent `CustomerFactory` collision on **C-0142** was exposed. All three fixed forward — `M8_Design_Review` §3.4.1b | **CLOSED** |
| **TD-32** | **New. Retire the `==` dev pins**, now superseded by `uv.lock`. Their own change, their own verify run — and keep the pytest-django incident narrative when the comment block goes | M8 |
| TD-11 | **SMS / DLT registration not started — blocks go-live.** Unbounded external lead time | Now |
| **TD-33** | **New. Adopt `djangorestframework-stubs`.** Deferred deliberately: it would surface a fresh error wave across `api/v1` in the same change that closed the gate. The original objection — tight `mypy`/`django-stubs` pins — is now **weaker**, because `uv.lock` manages them (TD-21). Adopt once the gate has held through one milestone | M8+ |
| **TD-34** | **New. `ops/` is outside `mypy backend/`.** `ops/report_performance.py` imports eight model modules and every report selector, and the blocking gate cannot see it — so a selector signature can change under it silently | M8 |
| ~~**TD-35**~~ | ~~`pip-audit --strict \|\| true` in CI is still advisory~~ — **CLOSED 2026-09-07 (M10), and the blocker it opened was closed by M10.5 the same day.** The `\|\| true` is gone and `test_the_dependency_audit_cannot_be_silenced` keeps it gone. **Its first blocking run failed**: 16 known vulnerabilities across `django`, `djangorestframework`, `sqlparse` and `weasyprint`, and **no fix existed inside the constraints declared at the time** — every one needed a version outside `pyproject.toml`'s then-current ranges. Escalated as a release blocker rather than silenced. **M10.5 raised three declared floors and resolved 15 of the 16**; the sixteenth has no published fix in any version and is exempted on a source-level unreachability proof, with a review date and two tests holding it. `docs/M10_Security_Review.md` §3 | **CLOSED** |
| TD-23 | `billing/selectors.py` scoping branches. FR-RPT-014's tests exercise exactly that surface, so it is **very likely closed — but per-file coverage was not captured**, and this table does not record what was not observed | M8 |
| TD-26 | `_walk`'s three robustness guards are exercised only by the randomised property test | M8 |
| ~~TD-14~~ | ~~`Product._has_history()` still inert~~ — **CLOSED, and this row was stale.** `catalogue/services.py:71` calls it: `if _has_history(product)`. Found by the M10 V1 gap audit, not by anyone closing it — **a debt register that records a fix nobody logged is as wrong as one that misses a defect** | **CLOSED** |
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
