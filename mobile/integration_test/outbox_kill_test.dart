/// **M8 → M9 gate, kill — phase 1 of 2: commit, then die.**
///
/// `00` §19.2: *"Outbox survives kill, restart and storage exhaustion."*
/// `02` NFR-OFF-005: *"Application termination — crash, force-close, battery exhaustion —
/// MUST NOT lose a **committed** local transaction."* Method: *"Kill-test at each write
/// boundary."*
///
/// **The word that decides the whole design is *committed*.** The claim under test is not
/// that a half-written INSERT rolls back — SQLite guarantees that, and asserting it would
/// test SQLite. It is that **once `append()` has returned `Ok`, the row is on disk** and
/// survives a death the process cannot intercept. So the signal is sent *after* the commit
/// boundary is crossed, never during it.
///
/// **This is not a UI test.** No widget is pumped, no "Saved" confirmation is looked for, and
/// nothing here depends on frame timing. The gate is a durability property of
/// `data/db/connection.dart`; the screens that sit above it are irrelevant to it.
///
/// **Two boundaries in one death.** Five operations are appended (`append` — the promise P-2
/// makes to a salesman) and three are then claimed (`claimBatch` — the commit that moves rows
/// to `IN_FLIGHT`). Killing after both means phase 2 can assert *"all committed rows remain"*
/// **and** *"status remains correct"* from a single run, which is smaller than two kill cycles
/// and strictly stronger than either alone.
///
/// **This file is expected to terminate abnormally.** It ends in `SIGKILL` to its own pid —
/// uncatchable, no Dart finaliser, no `close()`, no clean WAL checkpoint, which is what
/// *"crash, force-close, battery exhaustion"* means. The runner therefore cannot read this
/// phase's exit code as a verdict, and **must not**: the real evidence that phase 1 completed
/// is the state phase 2 finds. See `outbox_survives_kill_test.dart`.
library;

import 'dart:io';

import 'package:districore/core/result.dart';
import 'package:districore/domain/outbox/outbox_operation.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'support/device_outbox.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('phase 1 — commit five, claim three, then kill the process', (tester) async {
    // The precondition is owned here, not by the runner: see `deleteDeviceDatabase`.
    await deleteDeviceDatabase();
    // **Checkpoints, not assertions.** A SIGKILL leaves no exit status and no report — the
    // runner prints `did not complete` whether the process died here or at the intended
    // signal. These four lines are streamed as they execute, so the *last one observed* says
    // how far the phase got. Nothing below depends on them; removing them weakens diagnosis,
    // not the gate.
    debugPrint('GATE-P1: database deleted');

    final database = await openGateDatabase();
    final outbox = outboxOf(database);
    final keys = gateClientUuids();

    for (var i = 0; i < committedOperations; i++) {
      final appended = await outbox.append(
        clientUuid: keys[i],
        operationType: gateOperationType,
        clientCreatedAt: gateCreatedAt,
        payload: gatePayload(i),
      );
      // **The commit boundary.** Only an `Ok` puts the row under NFR-OFF-005's protection;
      // if the append failed, the gate has nothing to prove and must say so here rather
      // than let phase 2 report a loss that never happened.
      expect(
        appended,
        isA<Ok<OutboxOperation>>(),
        reason: 'append $i did not commit; there is no committed transaction to protect',
      );
    }

    expect(
      (await outbox.depth()).fold((depth) => depth, (failure) => -1),
      committedOperations,
      reason: 'the five appends are not all visible before the kill',
    );
    debugPrint('GATE-P1: $committedOperations appends committed');

    final claimed = await outbox.claimBatch(limit: claimedOperations);
    expect(
      claimed.fold((rows) => rows.length, (failure) => -1),
      claimedOperations,
      reason: 'claimBatch did not commit; phase 2 cannot assert IN_FLIGHT recovery',
    );
    debugPrint('GATE-P1: $claimedOperations claimed IN_FLIGHT');

    // **No `close()`, deliberately.** A clean close checkpoints the WAL and would prove the
    // opposite of what this gate is for.
    //
    // SIGKILL rather than `exit()`: `exit()` runs Dart's shutdown path, and a durability
    // claim that depends on an orderly shutdown is not a durability claim.
    // **The last line that can ever be printed.** Anything after this belongs to a process
    // that no longer exists, so seeing it in the output would itself be the finding.
    debugPrint('GATE-P1: KILL-NOW');
    Process.killPid(pid, ProcessSignal.sigkill);

    // Unreachable. If the process is still alive here the signal did not land, and the gate
    // must fail loudly rather than let phase 2 assert against an orderly shutdown.
    await tester.pump(const Duration(seconds: 5));
    fail('SIGKILL did not terminate the process; this phase proved nothing');
  });
}
