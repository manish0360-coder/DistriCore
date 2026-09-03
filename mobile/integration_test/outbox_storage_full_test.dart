/// **M8 → M9 gate, storage exhaustion — a genuinely full filesystem.**
///
/// `M8_Design_Review` §14.11 draws the line this file exists to cross:
///
/// > *"Task 3 proves the outbox **classifies** a full disk correctly; task 10 proves it
/// > **survives** one. The first is a mapping and needs no device; the second is a system
/// > property and **cannot be faked without one**."*
///
/// `mobile/test/storage_failure_test.dart` is the classification half — six cases mapping
/// `SQLITE_FULL` (13) and `SQLITE_IOERR_WRITE` (778) onto `StorageFull`, and proving a
/// constraint violation, corruption and a busy database are **not** it. It never fills
/// anything. That is exactly the substitution §14.11 refuses, and it is why this file may not
/// mock a `SqliteException`.
///
/// **What only a real exhaustion can decide:** which code the engine actually raises under
/// `ENOSPC` — `storage_failure.dart` handles both because the answer is genuinely unknown in
/// advance; whether SQLCipher's page encryption fails the same way as plain SQLite; whether
/// WAL checkpointing degrades safely with no room for the `-wal` file; and, above all,
/// **whether rows already committed survive the event**.
///
/// ## Running it — external setup, not automated test code
///
/// The ballast is placed and removed by the runner, on a **disposable AVD**. Automating it
/// from inside Dart would mean the test could leave a device full if it crashed mid-run.
///
/// Use `make mobile-device-storage BALLAST_MB=<N>`, which runs exactly this:
///
/// ```
/// adb shell df /data                                           # record free space first
/// adb shell dd if=/dev/zero of=/data/local/tmp/gate.ballast bs=1M count=<N>
/// flutter drive --driver=test_driver/integration_test.dart \
///   --target=integration_test/outbox_storage_full_test.dart --keep-app-running \
///   --dart-define=GATE_PHASE=full
/// adb shell rm /data/local/tmp/gate.ballast                    # always, reversible
/// flutter drive --driver=test_driver/integration_test.dart \
///   --target=integration_test/outbox_storage_full_test.dart --keep-app-running \
///   --dart-define=GATE_PHASE=drained
/// ```
///
/// **`flutter drive`, never `flutter test`, and the distinction decides this gate.**
/// `flutter test` on an integration_test file **uninstalls its package at teardown**, which
/// deletes `/data/user/0/<id>/` and the database with it — measured 2026-08-25, including
/// after a run that passed. The two phases below are two processes that must share
/// app-private state: phase B opens the database phase A left behind. Under `flutter test`
/// phase B would find an empty database and fail with *"exhaustion destroyed committed
/// work"* — **a false negative wearing the costume of the defect this gate detects.**
/// `--keep-app-running` leaves the install and its data in place; a rebuild between phases
/// is an update-install, which preserves the data directory.
///
/// Size `N` so free space lands just under one SQLite page allocation. Determinism comes from
/// **measuring** free space first, never from guessing a number.
library;

import 'package:districore/core/failure.dart';
import 'package:districore/core/result.dart';
import 'package:districore/domain/outbox/outbox_operation.dart';
import 'package:districore/domain/outbox/outbox_status.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'support/device_outbox.dart';

/// Which half is running. Two processes, because the ballast is removed between them and
/// only the runner can remove it.
const String _phase = String.fromEnvironment('GATE_PHASE', defaultValue: 'full');

/// Enough attempts to exhaust the remaining slack, few enough to end in seconds.
const int _attempts = 2000;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('storage exhaustion — $_phase', (tester) async {
    if (_phase == 'full') {
      await _underExhaustion();
    } else {
      await _afterDrain();
    }
  });
}

/// Phase A — the disk is full. **A write must fail as `StorageFull`, and as nothing else.**
Future<void> _underExhaustion() async {
  await deleteDeviceDatabase();

  final database = await openGateDatabase();
  final outbox = outboxOf(database);

  var committed = 0;
  Failure? refusal;

  for (var i = 0; i < _attempts && refusal == null; i++) {
    final appended = await outbox.append(
      clientUuid: '5eff8201-0000-4000-8000-${i.toString().padLeft(12, '0')}',
      operationType: gateOperationType,
      clientCreatedAt: gateCreatedAt,
      // Padded so each row consumes real pages rather than fitting in slack forever.
      payload: <String, Object?>{...gatePayload(i), 'ballast': 'x' * 4096},
    );
    appended.fold(
      (operation) => committed += 1,
      (failure) => refusal = failure,
    );
  }

  // **The anti-vacuity guard, and the reason this test is worth writing.** A storage gate
  // that passes on a device with free space proves nothing at all. If no write was refused,
  // the ballast did not exhaust the partition the app writes to — which is a setup error,
  // and it must read as a failure rather than as a pass.
  expect(
    refusal,
    isNotNull,
    reason: 'no write was refused after $_attempts appends: /data was not actually full, '
        'or the ballast is on a different partition from ${await deviceDatabasePath()}. '
        'Re-measure with `adb shell df` and enlarge the ballast',
  );

  // D-C3, and the distinction `failure.dart` calls out: `StorageFull` and `Offline` "demand
  // opposite behaviour". Telling a salesman to wait for signal when the disk is full is the
  // defect this narrowness exists to prevent.
  expect(
    refusal,
    isA<StorageFull>(),
    reason: 'a full disk surfaced as ${refusal.runtimeType}. The engine raised a result code '
        '`storageFailureFor` does not map — record which one, because that mapping is the '
        'whole of D-C3 and it was written without a real exhaustion to check it against',
  );

  // The rows that did commit are the ones phase B must still find.
  expect(committed, greaterThan(0), reason: 'nothing committed before the disk filled');
  // ignore: avoid_print — this number is the artefact `docs/M8_Verification_Report.md` needs.
  print('GATE:storage committed=$committed refusal=${refusal.runtimeType}');
}

/// Phase B — the ballast is gone. **Everything committed before the failure is still there.**
Future<void> _afterDrain() async {
  final database = await openGateDatabase();
  final outbox = outboxOf(database);

  final rows = (await outbox.pending(limit: 100000)).fold(
    (operations) => operations,
    (failure) => <OutboxOperation>[],
  );

  expect(
    rows,
    isNotEmpty,
    reason: 'the database is empty after the disk filled and drained. Either phase A never '
        'ran, or exhaustion destroyed committed work — which is the loss BR-014 and '
        'NFR-OFF-005 forbid absolutely',
  );
  expect(
    rows.every((row) => row.status == OutboxStatus.pending),
    isTrue,
    reason: 'a row survived exhaustion in a state the drain will not pick up',
  );

  // Not corrupt: every surviving row decodes, and its payload is intact.
  for (final row in rows) {
    expect(row.clientUuid, isNotEmpty);
    expect(row.operationType, gateOperationType);
    expect(row.payload['delivery_id'], isNotNull);
  }

  final highest = rows.map((row) => row.sequence).reduce((a, b) => a > b ? a : b);

  // The database is usable again, and D-C1 held across the outage.
  final appended = await outbox.append(
    clientUuid: '5eff8201-ffff-4000-8000-000000000000',
    operationType: gateOperationType,
    clientCreatedAt: gateCreatedAt,
    payload: gatePayload(0),
  );
  expect(
    appended,
    isA<Ok<OutboxOperation>>(),
    reason: 'the outbox did not recover once space was returned',
  );
  expect(
    appended.fold((operation) => operation.sequence, (failure) => -1),
    highest + 1,
    reason: 'the sequence did not continue across the exhaustion (D-C1); a reused number '
        'is indistinguishable, to the server, from a replay of different work',
  );
}
