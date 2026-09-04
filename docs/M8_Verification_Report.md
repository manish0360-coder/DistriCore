# M8 — Mobile App: Gate Verification Report

| Field | Value |
| --- | --- |
| Document ID | `M8_Verification_Report` |
| Version | **1.0.0** |
| Status | **GATE VERIFIED — `00` §19.2's M8 → M9 gate passes.** Kill 2026-09-01, storage 2026-09-04, both on device. **M8 itself is NOT closed** — tasks 6 and 8 have no commit; see §5 |
| Date | 2026-09-04 |
| Milestone | M8 — Mobile app (`00` §19.1) |
| Design authority | `docs/M8_Design_Review.md` v1.10.0 |
| Tree verified | `e2fbc07` |

> Every figure here is quoted from a run that happened. The device evidence is reproduced from
> `M8_Design_Review` §5.6.1 and §5.6.2, which hold it verbatim; this report does not paraphrase
> it into stronger claims.

---

## 1. Why this document exists, six milestones late

M0–M3 and M5–M7 each have a verification report. **M8 had none.** `PROJECT_STATE.md` recorded
the consequence honestly — *"no recorded evidence of this gate was found in the repository — no
commit, and no `M8_Verification_Report.md` where M0–M7 each have one"* — and was careful to add
that an absent artefact **is not proof that nothing was run**: a measurement taken on a device
leaves no trace in a repository unless someone records it.

This report is that record. It closes the artefact gap, not a question about the past.

## 2. The gate

`00` §19.2 conditions M8 → M9 on: *"Outbox survives kill, restart and storage exhaustion."*
Three clauses, two device gates, both now run.

| Clause | Gate | Date | Result |
| --- | --- | --- | --- |
| kill · restart | `make mobile-device-kill` | 2026-09-01 | **passed** — §5.6.1 |
| storage exhaustion | `make mobile-device-storage` | 2026-09-04 | **passed** — §5.6.2 |

Both on `emulator-5554`, API 34, Google APIs, `x86_64`; host Windows Flutter 3.44.7 reached from
WSL through `scripts/win-flutter.sh`; Gradle 9.1.0; JDK 18.

### 2.1 Kill and restart — 2026-09-01

```
GATE-P1: database deleted
GATE-P1: 5 appends committed
GATE-P1: 3 claimed IN_FLIGHT
GATE-P1: KILL-NOW
DriftError: ext.flutter.driver: (112) Service has disappeared
phase 1 terminated abnormally, as designed

GATE-P2: database=4096B wal=119512B shm=present
00:01 +2: All tests passed!
```

`KILL-NOW` is the last line the process can print, so reaching it proves the `SIGKILL` was sent
**after** both commit boundaries rather than during either. Phase 1's check is deliberately
**inverted** — a clean exit fails the gate.

The file sizes are themselves evidence: a 4 KiB main database beside a ~117 KiB `-wal` and a live
`-shm` is a database killed **mid-WAL, with no checkpoint** — the condition `02` NFR-OFF-005
describes. Phase 2, in a second process, found all five committed appends present, the three
`claimBatch` rows still `IN_FLIGHT`, the claim positionally on rows 1–3, and the `AUTOINCREMENT`
sequence continuing without reuse (**D-C1**).

### 2.2 Storage exhaustion — 2026-09-04

```
GATE:storage ballast=9204170752B slack=2097152B
GATE:storage committed=94 refusal=StorageFull
01:01 +2: All tests passed!          (phase A)

00:00 +0: storage exhaustion — drained
00:03 +2: All tests passed!          (phase B)
```

8.56 GB written by the app into its own data directory until the filesystem refused, then 2 MiB
handed back. 94 appends committed into that slack; the 95th was refused **as `StorageFull` and
as nothing else** — the narrowness **D-C3** exists for, since `StorageFull` and `Offline`
*"demand opposite behaviour"*. Phase B reopened the database in a fresh process and found all 94
present, `PENDING`, decodable, sequence continuing (**BR-014**, **NFR-OFF-005**).

## 3. The defect the storage gate found in shipping code

**On a genuinely full device the outbox crashed instead of returning `StorageFull`.**

`connection.dart` opens the database with `NativeDatabase.createInBackground`, so it runs in a
spawned isolate and a `SQLITE_FULL` raised at `COMMIT` arrives three wrappers deep:

```
DriftRemoteException.remoteCause
  -> CouldNotRollBackException.cause     (SQLite had already rolled back; drift's own
       -> SqliteException(13)             ROLLBACK then found no transaction)
```

`storageFailureFor` matched only a bare `SqliteException`, returned `null`, and `append`
rethrew. It now walks the `cause` chain applying **the identical two result codes** at each
level. Unwrapping can reveal a `StorageFull` a wrapper hid; it cannot invent one, and
`mobile/test/storage_failure_test.dart` pins that with a wrapped constraint violation that must
still classify as nothing.

Both facts behind the fix were read from drift 2.34.3's source, not recalled: that
`CouldNotRollBackException.cause` is the *original* error while `exception` is the rollback's own
failure, and that the isolate channel sets `serialize = false`, so the exception crosses as a
live object and matching by type is sound.

**This is `M8_Design_Review` §14.11's argument, vindicated.** *"The first is a mapping and needs
no device; the second is a system property and cannot be faked without one."* No unit test could
have found it — the classification unit tests passed throughout.

## 4. Supporting verification

| Suite | Result |
| --- | --- |
| `make verify` (backend, 2026-09-04) | **8/8** · 1108 passed · coverage 94.42% |
| `make mobile-verify` | analyze: 0 errors · **324 mobile tests, all passed** |
| `test_mobile_boundary.py` (stage 7) | **38 structural contracts**, all passed |

## 5. What this gate does NOT prove

1. **`arm64` and physical hardware are unproven** — **TD-45**. All three device gates ran on one
   `x86_64` emulator.
2. **The device gates cannot run in CI** — **TD-42**. `docker/flutter.Dockerfile` carries no
   Android SDK and no JDK, so every Android artefact comes from an unpinned host toolchain
   `make verify` cannot see. Half of TD-42 was retired on 2026-09-01 — `make` in WSL now reaches
   the Windows launcher — but the CI half stands.
3. **M8 is not closed.** Phase 2 tasks **6 and 8 have no commit**. This gate is task 10.
4. **One accepted analyzer warning** — **TD-46**. `storage_failure.dart` imports
   `package:drift/remote.dart`, which drift marks experimental; the gate passes it only because
   `--no-fatal-warnings` is set. Deliberate: without `DriftRemoteException` a full disk is not
   classified at all.
5. **No claim about runs before these dates.** §1 applies: an absent artefact is not evidence of
   absence.

## 6. Reproduction

An emulator must be running and `adb shell getprop sys.boot_completed` must print `1`.

```
cd /mnt/e/Projects/DistriCore
make mobile-device-kill
make mobile-device-storage      # DISPOSABLE AVD ONLY — the app fills its own disk
```

Neither target takes an argument. `device-gate-preflight` refuses in under a second if no device
is attached or the host Flutter launcher is unreachable.
