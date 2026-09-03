/// **M8 → M9 gate, kill — phase 2 of 2: reopen and account for everything.**
///
/// A new process, on the same device, opening the same file that
/// `outbox_kill_test.dart` left behind when it was killed. **This phase is the gate's
/// oracle**, and it is also the evidence that phase 1 ran at all — phase 1 dies by design, so
/// its exit code says nothing, and only the state found here can distinguish
/// *"killed after committing"* from *"crashed on line one"*.
///
/// Three assertions, matching `00` §19.2 clause by clause:
///
/// | Gate wording | Asserted here |
/// | --- | --- |
/// | all committed rows remain | five operations, by `client_uuid`, with their payloads |
/// | status remains correct | three `IN_FLIGHT`, two `PENDING` — and `reclaimInFlight` returns exactly the three |
/// | sequence continues without reuse | the next append is `committedOperations + 1` (D-C1) |
///
/// **Nothing here is written to pass on an empty database.** Every count is an exact
/// equality against a non-zero constant, so a device whose app data was wiped between the two
/// phases fails immediately and visibly — which is the failure mode that would otherwise make
/// this whole gate vacuous while reporting green.
///
/// **The total is read status-agnostically, and that is not a stylistic choice.** Until
/// 2026-08-25 this file counted survivors with `OutboxRepository.pending()`, which filters
/// `status = 'PENDING'` (`drift_outbox_repository.dart:64`). Phase 1 commits five and claims
/// three, so that query can only ever return two — and the gate reported *"a committed local
/// transaction was lost across a process kill"* against a database in which all five rows were
/// present and correct. A read-only probe of the artefact confirmed it: 5 rows, `IN_FLIGHT` at
/// sequences 1–3, `PENDING` at 4–5, all five `client_uuid`s.
///
/// **Read with raw SQL rather than through a new repository method.** `OutboxRepository`
/// exposes what the application needs and deliberately no more — *"There is no send, no drain
/// and no state transition here"*. A status-agnostic `all()` would exist for this test alone,
/// and a production API that only a test calls is one nobody maintains against a real
/// requirement. The cost is that this file knows the table's physical name; that is the
/// smaller debt.
library;

import 'dart:io';

import 'package:districore/domain/outbox/outbox_operation.dart';
import 'package:districore/domain/outbox/outbox_status.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'support/device_outbox.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('phase 2 — every committed operation survived the kill', (tester) async {
    // ---------------------------------------------------------------- PRECONDITION
    //
    // **A missing file is a harness fault. Wrong contents are a durability fault.**
    // Everything below this block asserts exact non-zero counts, so an absent database fails
    // them all at once and reads as *"five committed operations were lost"* — the most
    // alarming possible message for what is usually tooling. It happened: until 2026-08-25
    // this gate ran under `flutter test`, which uninstalls its package at the end of a run
    // and takes /data/user/0/<id>/ with it. These two assertions name that cause before the
    // row counts get a chance to misattribute it.
    // **One page is the correct size for the main file here, and that is not an edge case.**
    // `connection.dart` runs in WAL, and phase 1 dies without closing — deliberately, because
    // a clean close checkpoints. So the five appends and the three claims are in `-wal`, and
    // `districore.sqlite` still holds only its 4 KiB header page. Measured 2026-08-25 after a
    // successful kill: main 4096, `-wal` 117 KiB, `-shm` 32 KiB.
    //
    // An earlier draft asserted `main > 4096`, which is a demand that a checkpoint has
    // happened — the opposite of this gate's premise. It was carried over from
    // `encryption_at_rest_test.dart`, where the database *is* closed before inspection, and it
    // failed a run that had in fact succeeded.
    const sqlitePageSize = 4096;
    final path = await deviceDatabasePath();
    final file = File(path);
    final wal = File('$path-wal');
    expect(
      file.existsSync(),
      isTrue,
      reason: 'PHASE 2 PRECONDITION — no database at ${file.path}. Phase 1 either never ran '
          'or the package was removed between the phases. **This is a harness failure, not '
          'data loss.** Check `adb shell pm list packages | grep districore` before reading '
          'anything below as a durability result',
    );
    // Recorded before the assertion so a failure names the shape of what it found rather
    // than only the number it rejected.
    final walBytes = wal.existsSync() ? wal.lengthSync() : 0;
    debugPrint('GATE-P2: database=${file.lengthSync()}B wal=${walBytes}B '
        'shm=${File('$path-shm').existsSync() ? "present" : "absent"}');

    expect(
      file.lengthSync() + walBytes,
      greaterThan(sqlitePageSize),
      reason: 'PHASE 2 PRECONDITION — the database and its write-ahead log together are no '
          'larger than a single SQLite page, so the artefact holds nothing beyond an empty '
          'header and phase 1 left nothing to survive. **Still a harness failure, not data '
          'loss:** a real loss shows up below as wrong counts against a real file',
    );

    // **Opened, not created.** No `deleteDeviceDatabase` here: the file phase 1 left is the
    // subject. If phase 1 never ran, the assertions below fail rather than a fresh database
    // being silently created and reported as a pass.
    final database = await openGateDatabase();
    final outbox = outboxOf(database);
    final keys = gateClientUuids();

    // **Every row, whatever its status.** `pending()` is the wrong instrument here; see the
    // header. Ordered by sequence so the assertions below can name positions, not just counts.
    final raw = await database.customSelect(
      'SELECT sequence, client_uuid, operation_type, status '
      'FROM outbox_operation ORDER BY sequence;',
    ).get();
    final rows = [
      for (final row in raw)
        (
          sequence: row.read<int>('sequence'),
          clientUuid: row.read<String>('client_uuid'),
          operationType: row.read<String>('operation_type'),
          // Throws `ArgumentError` on an unrecognised code rather than defaulting — a status
          // this build does not know about is a finding, not a row to skip.
          status: OutboxStatus.fromCode(row.read<String>('status')),
        ),
    ];

    // ---------------------------------------------------------------- all rows remain
    expect(
      rows.length,
      committedOperations,
      reason: 'NFR-OFF-005: a committed local transaction was lost across a process kill. '
          'Every one of these had returned Ok() to the caller before the process died',
    );
    expect(
      rows.map((row) => row.clientUuid).toSet(),
      keys.toSet(),
      reason: 'the rows that survived are not the rows that were committed (P-6)',
    );
    expect(
      rows.every((row) => row.operationType == gateOperationType),
      isTrue,
      reason: 'an operation survived with the wrong type; the payload did not round-trip',
    );

    // ---------------------------------------------------------------- status is correct
    final inFlight = rows.where((r) => r.status == OutboxStatus.inFlight).toList();
    final stillPending = rows.where((r) => r.status == OutboxStatus.pending).toList();

    expect(
      inFlight.length,
      claimedOperations,
      reason: 'claimBatch had committed before the kill; those rows must still read '
          'IN_FLIGHT, not have reverted and not have been lost',
    );
    expect(stillPending.length, committedOperations - claimedOperations);

    // **Which rows, not merely how many.** `claimBatch` takes the oldest by sequence (D-C2),
    // so the split across a kill is positional and checkable: the claim landed on 1–3 and
    // left 4–5 alone. A count alone would pass if the kill had somehow shuffled which rows
    // were claimed, which would be a different and worse defect than losing one.
    expect(
      inFlight.map((row) => row.sequence).toList(),
      List<int>.generate(claimedOperations, (i) => i + 1),
      reason: 'the IN_FLIGHT rows are not the oldest ones claimBatch committed before the kill',
    );
    expect(
      stillPending.map((row) => row.sequence).toList(),
      List<int>.generate(
        committedOperations - claimedOperations,
        (i) => claimedOperations + i + 1,
      ),
      reason: 'the PENDING rows are not the ones the claim left behind',
    );

    // ---------------------------------------------------------------- recovery works
    // The M9.2 path, against a real process death for the first time. `SyncEngine` calls
    // this before every push precisely so an interrupted send is resumable (FR-SYN-004).
    final reclaimed = (await outbox.reclaimInFlight()).fold((n) => n, (failure) => -1);
    expect(
      reclaimed,
      claimedOperations,
      reason: 'reclaimInFlight did not recover the interrupted claim; those operations '
          'would never be sent again',
    );

    final afterRecovery = (await outbox.pending(limit: 1000)).fold(
      (operations) => operations,
      (failure) => <OutboxOperation>[],
    );
    expect(afterRecovery.length, committedOperations);
    expect(
      afterRecovery.every((row) => row.status == OutboxStatus.pending),
      isTrue,
      reason: 'recovery left an operation in a state the drain will not pick up',
    );

    // ---------------------------------------------------------------- sequence continues
    // **D-C1.** `AUTOINCREMENT` forbids reuse, and the kill must not have reset the
    // sequence: a reissued number is a row M9 would read as a replay of different work.
    final appended = await outbox.append(
      clientUuid: '5eff8200-0000-4000-8000-0000000000ff',
      operationType: gateOperationType,
      clientCreatedAt: gateCreatedAt,
      payload: gatePayload(99),
    );
    expect(
      appended.fold((operation) => operation.sequence, (failure) => -1),
      committedOperations + 1,
      reason: 'the sequence did not continue after the kill (D-C1). A restarted or reused '
          'sequence is indistinguishable, to the server, from a replay of other work',
    );

    // And the ordering guarantee the sequence exists for (D-C2) is intact end to end.
    final ordered = (await outbox.pending(limit: 1000)).fold(
      (operations) => operations,
      (failure) => <OutboxOperation>[],
    );
    final sequences = ordered.map((row) => row.sequence).toList();
    expect(sequences, List<int>.from(sequences)..sort());
    expect(sequences.toSet().length, sequences.length, reason: 'a sequence number repeated');
  });
}
