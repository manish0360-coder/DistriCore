import 'package:drift/drift.dart';

import 'outbox_table.dart';

part 'app_database.g.dart';

/// The device's local database (M8 §5.6 ADR: Drift + SQLCipher).
///
/// **Task 3 creates one table.** The cache §5.2 describes — products, customers,
/// deliveries — is disposable and arrives with the screens that need it. Conflating the two
/// stores is the defect §5.2 names: *"a cache is a convenience, an outbox is a promise."*
@DriftDatabase(tables: [OutboxOperations])
class AppDatabase extends _$AppDatabase {
  AppDatabase(super.executor);

  /// **1, and it stays 1 until a shipped device needs a different shape.** Every bump from
  /// here is a migration running on hardware that cannot be wiped and may be carrying a
  /// week of unsent work (AR-3) — which is why §5.3 has us build all four states now
  /// rather than grow them at M9.
  @override
  int get schemaVersion => 1;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onCreate: (m) => m.createAll(),
        beforeOpen: (details) async {
          // Foreign keys are off by default in SQLite and must be enabled per connection.
          // No table here declares one yet; enabling it now means the first table that does
          // is not relying on a pragma someone remembered to add later.
          await customStatement('PRAGMA foreign_keys = ON');
        },
      );
}
