import 'package:drift/drift.dart';

import 'local_identity_table.dart';
import 'outbox_table.dart';

part 'app_database.g.dart';

/// The device's local database (M8 §5.6 ADR: Drift + SQLCipher).
///
/// **Task 3 creates one table.** The cache §5.2 describes — products, customers,
/// deliveries — is disposable and arrives with the screens that need it. Conflating the two
/// stores is the defect §5.2 names: *"a cache is a convenience, an outbox is a promise."*
@DriftDatabase(tables: [OutboxOperations, LocalIdentities])
class AppDatabase extends _$AppDatabase {
  AppDatabase(super.executor);

  /// **2 — M6 adds `local_identity`.**
  ///
  /// The warning that stood here at version 1 was right and is repeated rather than
  /// deleted: every bump runs on hardware that cannot be wiped and may be carrying a week
  /// of unsent work (AR-3). This one is the cheapest shape a bump can have — **one new
  /// table, nothing altered, nothing dropped** — because §8.3 requires a device that locks
  /// out with three days of unsent deliveries to still hand them over.
  @override
  int get schemaVersion => 2;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onCreate: (m) => m.createAll(),
        onUpgrade: (m, from, to) async {
          // **1 → 2 creates a table and touches nothing else.** `outbox_operation` is not
          // altered, not rebuilt and not copied: its `AUTOINCREMENT` sequence (D-C1) must
          // continue across this migration, and the surest way to keep it is to leave the
          // table alone. Asserted by `migration_test.dart`.
          if (from < 2) await m.createTable(localIdentities);
        },
        beforeOpen: (details) async {
          // Foreign keys are off by default in SQLite and must be enabled per connection.
          // No table here declares one yet; enabling it now means the first table that does
          // is not relying on a pragma someone remembered to add later.
          await customStatement('PRAGMA foreign_keys = ON');
        },
      );
}
