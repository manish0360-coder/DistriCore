// M8 task 4 M6 — schema migration 1 → 2, against a real file on disk.
//
// **The v1 database is built by Drift itself, not by hand-written DDL.** Opening at v2 and
// then removing `local_identity` leaves `outbox_operation` byte-identical to what a v1
// device actually has — including the `AUTOINCREMENT` sequence (D-C1). A hand-written
// CREATE TABLE would prove that *my* idea of v1 migrates, which is not the question.
import 'dart:io';

import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/data/repositories/identity_cache.dart';
import 'package:districore/domain/identity/role.dart';
import 'package:districore/domain/identity/session.dart';
import 'package:districore/domain/outbox/outbox_status.dart';
// **`package:drift/drift.dart` is deliberately not imported here.** It exports SQL
// expression builders called `isNull` and `isNotNull`, which collide with `matcher`'s
// identically named value matchers — and every reference in this file wants the matcher.
// Nothing here names a drift type: the queries go through `AppDatabase`'s generated API and
// `NativeDatabase` comes from `drift/native.dart`, so dropping the import removes the
// ambiguity without hiding anything a reader would expect to be in scope.
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late File file;

  setUp(() {
    file = File(
      '${Directory.systemTemp.createTempSync('districore-migration').path}/db.sqlite',
    );
  });

  tearDown(() {
    if (file.parent.existsSync()) file.parent.deleteSync(recursive: true);
  });

  /// A device that last ran the task-3 build: outbox rows, no `local_identity`,
  /// `user_version = 1`.
  Future<void> seedVersionOne() async {
    final db = AppDatabase(NativeDatabase(file));
    final outbox = DriftOutboxRepository(db);

    for (var i = 0; i < 3; i++) {
      await outbox.append(
        clientUuid: '1111111$i-2222-3333-4444-555555555555',
        operationType: 'DELIVERY_COMPLETE',
        clientCreatedAt: DateTime.utc(2026, 8, 14, 10, i),
        payload: <String, Object?>{'delivery_id': 3300 + i, 'amount': '1180.00'},
      );
    }

    await db.customStatement('DROP TABLE local_identity');
    await db.customStatement('PRAGMA user_version = 1');
    await db.close();
  }

  test('12. the migration preserves every outbox row untouched', () async {
    await seedVersionOne();

    final db = AppDatabase(NativeDatabase(file));
    addTearDown(db.close);
    final rows = await db.select(db.outboxOperations).get();

    expect(rows.length, 3, reason: '§8.3 — a locked-out device still owes its deliveries');
    expect(rows.map((r) => r.sequence).toList(), [1, 2, 3]);
    expect(rows.map((r) => r.status).toSet(), {OutboxStatus.pending.code});
    // Money as an exact string (P-3 / AD-02) — byte-identical across the migration.
    expect(rows.first.payload, contains('"amount":"1180.00"'));
    expect(rows.map((r) => r.clientUuid).toSet().length, 3);
  });

  test('12b. the sequence continues rather than restarting', () async {
    // D-C1: `AUTOINCREMENT` forbids reuse. A migration that rebuilt the table would reset
    // `sqlite_sequence` and silently reissue 1, 2, 3 — which M9 would read as replays.
    await seedVersionOne();

    final db = AppDatabase(NativeDatabase(file));
    addTearDown(db.close);

    final appended = await DriftOutboxRepository(db).append(
      clientUuid: '99999999-2222-3333-4444-555555555555',
      operationType: 'DELIVERY_FAIL',
      clientCreatedAt: DateTime.utc(2026, 8, 16, 9),
      payload: <String, Object?>{'delivery_id': 4000},
    );

    expect(appended.fold((op) => op.sequence, (f) => fail('$f')), 4);
  });

  test('12c. the migration creates a usable local_identity table', () async {
    await seedVersionOne();

    final db = AppDatabase(NativeDatabase(file));
    addTearDown(db.close);
    final identity = IdentityCache(db);

    expect(await identity.read(), isNull, reason: 'a migrated device starts signed out');

    await identity.save(const Session(
      userId: 12,
      fullName: 'Ramesh Kumar',
      roles: {Role.delivery},
      customerId: null,
    ));

    expect((await identity.read())!.userId, 12);
    final version = await db.customSelect('PRAGMA user_version').getSingle();
    expect(version.data.values.first, 2);
  });

  test('12d. a fresh install creates both tables at version 2', () async {
    final db = AppDatabase(NativeDatabase(file));
    addTearDown(db.close);

    await IdentityCache(db).save(
      const Session(userId: 1, fullName: 'A', roles: {Role.owner}),
    );
    final outbox = await db.select(db.outboxOperations).get();

    expect(outbox, isEmpty);
    expect(await IdentityCache(db).read(), isNotNull);
  });
}
