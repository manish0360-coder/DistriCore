import 'package:drift/drift.dart';

import 'cached_customer_table.dart';
import 'cached_delivery_table.dart';
import 'local_identity_table.dart';
import 'outbox_table.dart';
import 'sync_cursor_table.dart';

part 'app_database.g.dart';

/// The device's local database (M8 §5.6 ADR: Drift + SQLCipher).
///
/// **Task 3 creates one table.** The cache §5.2 describes — products, customers,
/// deliveries — is disposable and arrives with the screens that need it. Conflating the two
/// stores is the defect §5.2 names: *"a cache is a convenience, an outbox is a promise."*
@DriftDatabase(
  tables: [
    OutboxOperations,
    LocalIdentities,
    CachedCustomers,
    CachedDeliveries,
    SyncCursors,
  ],
)
class AppDatabase extends _$AppDatabase {
  AppDatabase(super.executor);

  /// **3 — M9.4 adds the pull cache and its cursor.**
  ///
  /// The warning that stood here at version 1 was right and is repeated rather than
  /// deleted: every bump runs on hardware that cannot be wiped and may be carrying a week
  /// of unsent work (AR-3). Both bumps so far have kept the cheapest shape available —
  /// **new tables only, nothing altered, nothing dropped** — because §8.3 requires a device
  /// that locks out with three days of unsent deliveries to still hand them over.
  ///
  /// **The two halves of this database are not equal.** `outbox_operation` is a promise and
  /// `local_identity` is a credential; the three tables added here are a cache §5.2 calls
  /// *"disposable"*. Losing them costs one pull. That asymmetry is why the migration below
  /// touches neither of the older tables.
  @override
  int get schemaVersion => 3;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onCreate: (m) => m.createAll(),
        onUpgrade: (m, from, to) async {
          // **1 → 2 creates a table and touches nothing else.** `outbox_operation` is not
          // altered, not rebuilt and not copied: its `AUTOINCREMENT` sequence (D-C1) must
          // continue across this migration, and the surest way to keep it is to leave the
          // table alone. Asserted by `migration_test.dart`.
          if (from < 2) await m.createTable(localIdentities);

          // **2 → 3 is the same shape again** (M9.4). Three new tables, nothing altered.
          // A device upgrading here may be carrying a week of unsent deliveries, and the
          // cache these tables hold is worth nothing beside them — so the migration that
          // adds a cache must not be able to disturb the queue.
          if (from < 3) {
            await m.createTable(cachedCustomers);
            await m.createTable(cachedDeliveries);
            await m.createTable(syncCursors);
          }
        },
        beforeOpen: (details) async {
          // Foreign keys are off by default in SQLite and must be enabled per connection.
          // No table here declares one yet; enabling it now means the first table that does
          // is not relying on a pragma someone remembered to add later.
          await customStatement('PRAGMA foreign_keys = ON');
        },
      );
}
