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
