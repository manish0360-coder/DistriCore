// M9.4 step A — schema migration 2 → 3, against a real file on disk.
//
// **The v2 database is built by Drift itself, not by hand-written DDL.** Opening at v3 and
// then dropping the three new tables leaves `outbox_operation` and `local_identity`
// byte-identical to what a v2 device actually has — including the `AUTOINCREMENT` sequence
// (D-C1). Hand-written CREATE TABLE would prove that *my* idea of v2 migrates, which is not
// the question. Same strategy as `migration_test.dart` used for 1 → 2.
import 'dart:io';

import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/data/repositories/identity_cache.dart';
import 'package:districore/domain/identity/role.dart';
import 'package:districore/domain/identity/session.dart';
import 'package:districore/domain/outbox/outbox_status.dart';
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

const _session = Session(
  userId: 12,
  fullName: 'Ramesh Kumar',
  roles: {Role.salesman, Role.delivery},
  customerId: null,
);

void main() {
  late File file;

  setUp(() {
    file = File(
      '${Directory.systemTemp.createTempSync('districore-v3').path}/db.sqlite',
    );
  });

  tearDown(() {
    if (file.parent.existsSync()) file.parent.deleteSync(recursive: true);
  });

  /// A device that last ran the M6 build: outbox rows, a cached identity, no v3 tables,
  /// `user_version = 2`.
  Future<void> seedVersionTwo() async {
    final db = AppDatabase(NativeDatabase(file));
    final outbox = DriftOutboxRepository(db);

    for (var i = 0; i < 3; i++) {
      await outbox.append(
        clientUuid: '2222222$i-3333-4333-8444-555555555555',
        operationType: 'DELIVERY_COMPLETE',
        clientCreatedAt: DateTime.utc(2026, 8, 16, 10, i),
        payload: <String, Object?>{'delivery_id': 3300 + i, 'amount': '1180.00'},
      );
    }
    await IdentityCache(db).save(_session);

    await db.customStatement('DROP TABLE cached_customer');
    await db.customStatement('DROP TABLE cached_delivery');
    await db.customStatement('DROP TABLE sync_cursor');
    await db.customStatement('PRAGMA user_version = 2');
    await db.close();
  }

  test('1 & 2. the migration preserves every outbox row untouched', () async {
    await seedVersionTwo();

    final db = AppDatabase(NativeDatabase(file));
    addTearDown(db.close);
    final rows = await db.select(db.outboxOperations).get();

    expect(rows.length, 3, reason: '§8.3 — a device mid-round still owes its deliveries');
    expect(rows.map((r) => r.sequence).toList(), [1, 2, 3]);
    expect(rows.map((r) => r.status).toSet(), {OutboxStatus.pending.code});
    // Money as an exact string (P-3 / AD-02) — byte-identical across the migration.
    expect(rows.first.payload, contains('"amount":"1180.00"'));

    final version = await db.customSelect('PRAGMA user_version').getSingle();
    expect(version.data.values.first, 3);
  });

  test('3. the AUTOINCREMENT sequence continues rather than restarting', () async {
    // D-C1: a migration that rebuilt the table would reset `sqlite_sequence` and reissue
    // 1, 2, 3 — which M9 would read as replays of work already sent.
    await seedVersionTwo();

    final db = AppDatabase(NativeDatabase(file));
    addTearDown(db.close);

    final appended = await DriftOutboxRepository(db).append(
      clientUuid: '99999999-3333-4333-8444-555555555555',
      operationType: 'VISIT_CREATE',
      clientCreatedAt: DateTime.utc(2026, 8, 16, 11),
      payload: <String, Object?>{'customer_id': 142, 'outcome': 'NO_ORDER'},
    );

    expect(appended.fold((op) => op.sequence, (f) => fail('$f')), 4);
  });

  test('2b. the cached identity survives unchanged', () async {
    await seedVersionTwo();

    final db = AppDatabase(NativeDatabase(file));
    addTearDown(db.close);

    final restored = await IdentityCache(db).read();
    expect(restored, isNotNull);
    expect(restored!.userId, 12);
    expect(restored.roles, {Role.salesman, Role.delivery});
  });

  test('4 & 5. the three new tables exist and start empty', () async {
    await seedVersionTwo();

    final db = AppDatabase(NativeDatabase(file));
    addTearDown(db.close);

    expect(await db.select(db.cachedCustomers).get(), isEmpty);
    expect(await db.select(db.cachedDeliveries).get(), isEmpty);
    // `null` server_time is *"no successful pull yet"*, so the next pull omits `since`
    // entirely and P-1 makes it a bootstrap. An empty table says the same thing.
    expect(await db.select(db.syncCursors).get(), isEmpty);
  });

  test('6. a fresh install creates all v3 tables at once', () async {
    final db = AppDatabase(NativeDatabase(file));
    addTearDown(db.close);

    // Touching each table is what forces the schema to exist; a query that throws here
    // means `onCreate` did not create it.
    expect(await db.select(db.cachedCustomers).get(), isEmpty);
    expect(await db.select(db.cachedDeliveries).get(), isEmpty);
    expect(await db.select(db.syncCursors).get(), isEmpty);
    expect(await db.select(db.outboxOperations).get(), isEmpty);
    expect(await IdentityCache(db).read(), isNull);

    final version = await db.customSelect('PRAGMA user_version').getSingle();
    expect(version.data.values.first, 3);
  });

  test('the single-row cursor constraint is enforced by the database', () async {
    final db = AppDatabase(NativeDatabase(file));
    addTearDown(db.close);

    await db.customStatement(
      "INSERT INTO sync_cursor (id, server_time, updated_at) "
      "VALUES (1, '2026-08-16T09:00:00Z', '2026-08-16T09:00:01Z')",
    );

    // One device, one cursor. A second row would make "which cursor?" a question every
    // reader has to answer, and I-6's argument applies: the constraint is what survives.
    await expectLater(
      db.customStatement(
        "INSERT INTO sync_cursor (id, server_time, updated_at) "
        "VALUES (2, '2026-08-16T10:00:00Z', '2026-08-16T10:00:01Z')",
      ),
      throwsA(anything),
    );
  });
}
