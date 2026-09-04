/// Shared harness for the **M8 → M9 device gate** (`00` §19.2, `M8_Design_Review` §14.11).
///
/// **It opens the production path and nothing else.** Every phase below calls the real
/// `openDeviceDatabase`, so what is under test is the file `lib/data/db/connection.dart`
/// actually writes — the keystore passphrase through `PlatformDatabaseKey`,
/// `journal_mode = WAL` and `synchronous = FULL`, the two pragmas whose comment already names
/// NFR-OFF-005 and which **no hermetic test can reach**: a unit test's database lives in
/// memory or a temp path, never in the app's documents directory, and holds no key. A harness
/// that opened its own database would prove SQLite works, not that DistriCore does.
///
/// **The cipher is SQLite3MultipleCiphers via the `sqlite3` build hook (D-M9-8), not
/// SQLCipher** — an earlier version of this comment said otherwise, and said the host linked
/// the system SQLite, and neither was true. Nothing in this harness depended on which cipher
/// it was, which is why it needed no change when the answer did.
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/db/connection.dart';
import 'package:districore/data/db/platform_database_key.dart';
import 'package:districore/data/identity/platform_secure_storage.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/domain/outbox/outbox_repository.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// **The gate's fixed vocabulary.** Phase 2 runs in a process that never saw phase 1, so the
/// two agree by constant rather than by message-passing — there is no channel between a
/// process and its own corpse.
///
/// Five appended, three claimed. The split is the point: after the kill, phase 2 must find
/// **both** statuses intact, which is `00` §19.2's *"status remains correct"* and is a
/// stronger claim than a row count.
const int committedOperations = 5;
const int claimedOperations = 3;

/// Deterministic v4-shaped keys, so phase 2 asserts identity and not merely arithmetic.
/// P-6: a `client_uuid` is minted once and never regenerated.
List<String> gateClientUuids() => [
      for (var i = 0; i < committedOperations; i++)
        '5eff8200-0000-4000-8000-00000000000$i',
    ];

/// The operation the outbox exists to protect: a delivery a salesman has already handed over.
const String gateOperationType = 'DELIVERY_COMPLETE';

/// A fixed instant. **P-4 — the device clock labels, it never orders.** Reading `now()` here
/// would make a durability gate depend on a clock, which is the dependency P-4 forbids and
/// TD-31 caught four times in the backend suite.
final DateTime gateCreatedAt = DateTime.utc(2026, 8, 22, 9, 30);

Map<String, Object?> gatePayload(int index) => <String, Object?>{
      'delivery_id': 5000 + index,
      'recipient_name': 'Gate $index',
    };

/// Phase 1's precondition: **start from no database at all.**
///
/// Owned by the test rather than by the runner on purpose. `adb shell pm clear` would do the
/// same thing, but only if someone remembers it — and a forgotten clear makes phase 2's
/// sequence assertion pass against rows an earlier run left behind. Deleting here means the
/// precondition cannot be skipped, and the Makefile needs no step that could be silenced.
///
/// The `-wal` and `-shm` siblings are removed too: a stale WAL beside a deleted database is
/// how a "fresh" open silently inherits an old transaction.
Future<void> deleteDeviceDatabase() async {
  final directory = await getApplicationDocumentsDirectory();
  for (final suffix in const ['', '-wal', '-shm']) {
    final file = File(p.join(directory.path, 'districore.sqlite$suffix'));
    if (file.existsSync()) file.deleteSync();
  }
}

/// Open the on-device database through the production path.
Future<AppDatabase> openGateDatabase() async {
  const storage = PlatformSecureStorage();
  return AppDatabase(await openDeviceDatabase(const PlatformDatabaseKey(storage)));
}

OutboxRepository outboxOf(AppDatabase database) => DriftOutboxRepository(database);

/// Where the database actually is, for the storage phase's own reporting.
Future<String> deviceDatabasePath() async {
  final directory = await getApplicationDocumentsDirectory();
  return p.join(directory.path, 'districore.sqlite');
}

// ---------------------------------------------------------------- the storage ballast
//
// **The ballast is written by the app, not by the runner, and that ordering is forced.**
//
// It used to be `adb shell dd` placed by `make mobile-device-storage` before the run.
// That cannot work: `flutter drive` **always installs the APK when it starts**, and an
// install needs a few hundred megabytes. A disk filled beforehand makes the run impossible —
// `PackageInstallerService` refuses with *"Requested internal only, but not enough space"*
// before a single line of Dart executes. Measured 2026-09-04, three separate runs: plain
// `drive`, `drive --no-build` (the flag is ignored and it rebuilds), and
// `drive --use-application-binary` (the build is skipped but the install still happens).
//
// Filling from inside the app, once it is already running, is the only ordering that lets
// the install succeed **and** the write be refused. It also removes every sizing decision:
// nothing is measured, nothing is passed on a command line, nothing can go stale between
// measuring and filling.

/// 32 MiB. Large enough that filling ~9 GB is a few hundred syscalls, small enough that the
/// final chunk overshoots the true boundary by a trivial amount.
const int _ballastChunkBytes = 32 * 1024 * 1024;

/// What `fillDeviceStorage` leaves free.
///
/// The slack must sit **below** what 2000 appends can consume, or no write is ever refused
/// and phase A fails its own anti-vacuity guard; and **above** the cost of the first append,
/// or nothing commits and `committed > 0` fails instead.
///
/// **Measured, not estimated.** A run on 2026-09-04 filled to a 10 MiB slack and completed
/// all 2000 appends without a refusal, so each append costs **under 5.2 KiB** — an estimate
/// of 8-12 KiB, from assuming a 4 KiB payload spans two pages in both the database and the
/// WAL, was simply wrong. 2 MiB needs only ~1 KiB per append to exhaust, and every append
/// dirties at least one 4 KiB page, so exhaustion is certain; while 2 MiB is over a hundred
/// times the cost of a single append, so the first ones commit with room to spare.
const int deviceStorageSlackBytes = 2 * 1024 * 1024;

File _ballastFile(Directory directory) => File(p.join(directory.path, 'gate.ballast'));

/// Fill the filesystem the database lives on, then hand back [slackBytes].
///
/// Written into the app's own documents directory deliberately: that is the same partition
/// as `districore.sqlite`, so there is no way for the ballast to fill a filesystem the
/// database does not use — the failure mode the old external ballast had to warn about.
///
/// Returns the number of bytes written before the filesystem refused.
Future<int> fillDeviceStorage({int slackBytes = deviceStorageSlackBytes}) async {
  final directory = await getApplicationDocumentsDirectory();
  final handle = _ballastFile(directory).openSync(mode: FileMode.write);
  final chunk = Uint8List(_ballastChunkBytes);
  try {
    while (true) {
      try {
        handle.writeFromSync(chunk);
        // Flushed every chunk: a buffered write can be accepted and then fail at close,
        // which would report a full disk only after the loop had decided it was not.
        handle.flushSync();
      } on FileSystemException {
        break;
      }
    }

    // **Measure the file; do not count the chunks.** The write that hits `ENOSPC` can put
    // *part* of its chunk on disk before throwing, and a counter incremented per successful
    // chunk does not know about those bytes. Truncating to `counter - slack` then releases
    // the partial remainder **as well as** the slack — up to a whole chunk too much.
    //
    // Measured 2026-09-04: with a 2 MiB slack and 32 MiB chunks, all 2000 appends committed
    // and nothing was refused, because the real free space was somewhere under 34 MiB rather
    // than 2. `lengthSync()` is what the filesystem actually did, so the slack is exact
    // whatever the last write managed.
    final filled = handle.lengthSync();
    final keep = filled - slackBytes;
    handle.truncateSync(keep < 0 ? 0 : keep);
    handle.flushSync();
    return filled;
  } finally {
    handle.closeSync();
  }
}

/// Remove the ballast. Safe to call when it was never created, and safe to call twice.
///
/// **Must run even when the phase fails**, or the device is left full and the next run
/// cannot install the APK — which is exactly the state the external ballast used to leave
/// behind when a run aborted between the `dd` and the `rm`.
Future<void> releaseDeviceStorage() async {
  final directory = await getApplicationDocumentsDirectory();
  final file = _ballastFile(directory);
  if (file.existsSync()) {
    file.deleteSync();
  }
}
