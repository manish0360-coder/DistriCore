# M9 — Sync: Gate Verification Report

| Field | Value |
| --- | --- |
| Document ID | `M9_Verification_Report` |
| Version | **1.0.0** |
| Status | **GATE VERIFIED — `00` §19.2's M9 → M10 gate passes.** `make verify` 8/8 · `test_sync_integrity.py` 11/11. **M9 itself is NOT closed** — five open items still need a Product Architect ruling; see §5 |
| Date | 2026-09-04 |
| Milestone | M9 — Sync (`00` §19.1) |
| Design authority | `docs/M9_Design_Review.md` v1.3.0 |
| Tree verified | `e2fbc07` |

> Every figure here comes from the single passing `make verify` run of 2026-09-04 and from one
> `pytest -v` of the sync suite. Nothing is restated from memory, and nothing from a failing run
> is reported as if it had passed.

---

## 1. What this report does and does not do

**It closes one gate.** `00` §19.2 conditions M9 → M10 on *"adversarial sync suite passes: zero
loss, zero duplicates"*. That suite exists, runs inside `make verify`, and passes. §2 and §3 are
the evidence.

**It closes no milestone.** M9 has five open items that no engineer may settle alone — two of
them are direct contradictions between frozen documents. They are listed in §5 unchanged.
`PROJECT_STATE.md`'s *Open at M9* is the register; this report removes two rows from it and
leaves the rest exactly as they were.

**The distinction is the point.** A passing gate says a stated condition holds. It says nothing
about whether every requirement of the milestone is built. `M8_Design_Review` §10.1 draws the
same line, and `PROJECT_STATE.md` warns in its own words that *"no recorded evidence was found"*
and *"the suite does not exist"* are different claims from *"it was never run"*.

## 2. Verification results — `make verify`, 2026-09-04

`make verify` is the only authority (**N-12**, `00` §5.2). Eight stages, all green:

| # | Stage | Result |
| --: | --- | --- |
| 1 | clean build, `--no-cache` | completed — proves dependencies are declared |
| 2 | start, wait for healthchecks | completed |
| 3 | no missing migration | `No changes detected` |
| 4 | lint — `ruff check .` | `All checks passed!` |
| 5 | import contracts — `lint-imports` | `Analyzed 178 files, 329 dependencies` · **`Contracts: 3 kept, 0 broken`** |
| 6 | type check — `mypy backend/` | `Success: no issues found in 134 source files` |
| 7 | tests + coverage | **`1108 passed, 25 warnings in 149.13s`** · `Total coverage: 94.42%` |
| 8 | health endpoint | `{"status": "ok", ...}` |

```
TOTAL                                                      5952    332    94%
Required test coverage of 80% reached. Total coverage: 94.42%
================ 1108 passed, 25 warnings in 149.13s (0:02:29) =================

  VERIFIED. This is the only result that counts (N-12).
```

The three import contracts kept are N-01/N-02's two — delivery layers must not touch models, and
domain modules must not import a delivery layer — and `03` §2.1's *"module graph is layered and
acyclic"*.

### 2.1 Coverage of the module under test

| Module | Statements | Missed | Coverage |
| --- | --: | --: | --: |
| `backend/sync/__init__.py` | 0 | 0 | 100% |
| `backend/sync/apps.py` | 5 | 0 | 100% |
| `backend/sync/models.py` | 32 | 1 | 97% |
| `backend/sync/selectors.py` | 77 | 6 | 92% |
| `backend/sync/services.py` | 84 | 11 | 87% |

`services.py` is where `_process_one` and `_settle_existing` live — the recovery path §3 exercises.

## 3. The gate — `test_sync_integrity.py`, 11/11

`00` §19.2 names the condition; `02` §25.2 names the **method**: *"Fault injection: severed
connections, replayed batches, killed processes, clock skew, exhausted storage."* All five
classes are injected. Run individually with `-v` so each verdict is attributable:

| Fault class (`02` §25.2) | Test | Verdict |
| --- | --- | --- |
| **Killed processes** | `test_an_interrupted_operation_leaves_a_received_row_and_no_visit` | PASSED |
| | `test_replaying_an_interrupted_operation_must_not_lose_the_visit` | PASSED |
| | `test_recovering_work_that_already_committed_does_not_duplicate_it` | PASSED |
| | `test_recovering_an_interrupted_delivery_completes_it_exactly_once` | PASSED |
| | `test_recovery_locks_the_operation_row_before_re_entering_the_handler` | PASSED |
| **Replayed batches** | `test_an_accepted_operation_still_answers_duplicate` | PASSED |
| | `test_a_rejected_operation_is_terminal_and_is_not_re_run` | PASSED |
| **Severed connections** | `test_a_response_lost_on_the_wire_does_not_duplicate_the_batch` | PASSED |
| | `test_a_partially_applied_batch_is_resumed_not_restarted` | PASSED |
| **Clock skew** | `test_a_skewed_device_clock_changes_no_outcome_including_on_recovery` | PASSED |
| **Exhausted storage** | `test_a_full_disk_leaves_the_operation_recoverable_not_stranded` | PASSED |

**Where the gate's two words are actually asserted.** *Zero loss* —
`replaying_an_interrupted_operation_must_not_lose_the_visit`. *Zero duplicates* —
`recovering_work_that_already_committed_does_not_duplicate_it`,
`recovering_an_interrupted_delivery_completes_it_exactly_once` and
`a_response_lost_on_the_wire_does_not_duplicate_the_batch`.

### 3.1 The defect this suite found, and why it is adversarial rather than integration

`02` §18: *"A green happy-path suite is not evidence for these requirements."* The suite's own
docstring records that **test B failed on its first run**: one `SyncOperation` at `RECEIVED`,
**zero** `Visit` rows, and a `DUPLICATE` verdict — which `05` §11.2 tells the client means
*"Delete from the outbox. This is success."* A device would have deleted the only copy of work
the server never performed.

The window is real and structural: `04` T-26 requires the operation row be written *before* the
business effect is attempted, so `_process_one` uses **two sibling transactions** and A is
released before B is entered. `5efff82 fix(sync): recover interrupted operations` repaired it —
an existing row now routes through `_settle_existing`, `RECEIVED` is recovered under a row lock
— and `4d4854e test(sync): close adversarial integrity gate` is the suite.

## 4. What this gate does NOT prove

Stated explicitly, because a gate that is cited beyond its evidence is worse than no gate.

1. **Nothing about `SyncConflict`.** `02` FR-SYN-005 requires conflicts persisted in
   `PENDING_RESOLUTION`; `05` §11.4 says *"no conflict resolution console is built, because none
   is needed"*. `SyncConflict` exists in no schema, no endpoint and no model. The suite cannot
   test an entity that does not exist and does not attempt to. **Open item 5 is untouched by
   this report.**
2. **Nothing about the stock snapshot.** **D-M9.4-1**'s recorded CONTRACT GAP against `04`
   N-03/E-01 and ADR-008 is unclosed. `FR-SYN-007`'s pull covers customers and deliveries only.
3. **Nothing about orphaned `RECEIVED` recovery as a scheduled process.** The suite proves an
   orphan is *recoverable on replay*. `05` §11.5 defers a sweeper *"to M9.4/M10"*; M9.4 shipped
   without one, so nothing reclaims an orphan that is never replayed.
4. **No concurrency beyond one row lock.** `recovery_locks_the_operation_row_before_re_entering_the_handler`
   proves the lock is taken. Multi-device contention, and two servers racing on one operation,
   are not exercised.
5. **No volume or endurance claim.** Every case is a handful of rows. `NFR-PER-004` and the
   200-operation batch ceiling are not stressed here.
6. **No network layer.** *"Severed connections"* is injected at the service boundary by
   discarding a response, not by cutting a socket. What is proven is that the **server** is
   idempotent under a lost reply; the transport is not under test.

## 5. M9 remains open — the register, unchanged

Two rows of `PROJECT_STATE.md`'s *Open at M9* are closed by evidence:

| # | Item | New state |
| --: | --- | --- |
| 6 | M9 → M10 gate — adversarial sync suite | **CLOSED** — this report, §2–§3 |
| 7 | M8 → M9 gate — outbox survives kill, restart, storage exhaustion | **CLOSED** — `M8_Design_Review` §5.6.1 (2026-09-01) and §5.6.2 (2026-09-04); `docs/M8_Verification_Report.md` |

Six remain, and **five of them are questions no engineer may answer alone**:

| # | Item | Owner |
| --: | --- | --- |
| 1 | FR-RPT-009 sync health report — placed at M9 by **A-5**, unbuilt, no endpoint in `05` | Product Architect |
| 2 | FR-SYN-009 — `05` §11.5 claims coverage **D-M9.3-1** makes unreachable | Product Architect |
| 3 | Orphaned `RECEIVED` recovery — deferred *"to M9.4/M10"*; arrived at M10 by default | Engineering |
| 4 | FR-SYN-007 remainder / stock snapshot — **D-M9.4-1**'s CONTRACT GAP | Product Architect |
| 5 | FR-SYN-005/013/014 conflict console — direct contradiction between `02` and `05` | Product Architect |
| 8 | TD-41 / FR-SYN-010 — launch-only trigger, no connectivity mechanism | Engineering |

**No milestone number is proposed here.** `00` §19.1 defines M9 = Sync and M10 = Hardening and
defines no sub-milestones; `M9.1`–`M9.4` are working labels for four commits.

## 6. Reproduction

```
make verify
```

and, for the gate alone, with the stack up:

```
docker compose -f docker/compose.yml -f docker/compose.dev.yml --env-file .env \
  exec -T -w /app -e PYTHONPATH=/app/backend app \
  pytest backend/tests/adversarial/test_sync_integrity.py -v
```
