// M8 task 4 M6 — migration **from** schema v1, against a real file on disk.
//
// **The v1 database is built by Drift itself, not by hand-written DDL.** Opening at the
// current version and then removing `local_identity` leaves `outbox_operation`
// byte-identical to what a v1 device actually has — including the `AUTOINCREMENT` sequence
// (D-C1). A hand-written CREATE TABLE would prove that *my* idea of v1 migrates, which is
// not the question.
//
// **This file is about the oldest supported device, not about one hop.** It was written when
// the newest version was 2; M9.4 made the same seed exercise 1 → 3. Nothing here should name
// a version number except the one being migrated *from* — the destination is whatever
// `AppDatabase.schemaVersion` currently declares, and an assertion spelling it out as a
// literal is a maintenance tax that fails on every bump while proving nothing extra.
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

    // **The table exists**, stated explicitly rather than inferred from the round trip
    // below. `IdentityCache` working proves it too, but only as a side effect — and a
    // reader looking for "did the upgrade create the table" should find that question asked.
    final tables = await db
        .customSelect("SELECT name FROM sqlite_master WHERE type = 'table'")
        .get();
    expect(
      tables.map((row) => row.data['name']),
      contains('local_identity'),
    );

    // **And it is usable**: empty on arrival, then written and read back.
    expect(await identity.read(), isNull, reason: 'a migrated device starts signed out');

    await identity.save(const Session(
      userId: 12,
      fullName: 'Ramesh Kumar',
      roles: {Role.delivery},
      customerId: null,
    ));

    expect((await identity.read())!.userId, 12);

    // **Against the declared version, not a literal.**
    //
    // This assertion said `2` and broke when M9.4 bumped the schema to 3 — which is the
    // wrong thing to have been asserting. The invariant is *"the file on disk was brought
    // all the way up to the version this build declares"*, and that is what `schemaVersion`
    // names. It is not circular: `user_version` is written into the file by the migration,
    // so an `onUpgrade` that failed, or a bump someone forgot to handle, still leaves a 1
    // here.
    final version = await db.customSelect('PRAGMA user_version').getSingle();
    expect(version.data.values.first, db.schemaVersion);
  });

  test('12e. the two-step upgrade also creates the v3 cache tables', () async {
    // **A v1 device does not stop at v2.** `seedVersionOne` stamps `user_version = 1`, so
    // opening it here runs `onUpgrade(from: 1, to: 3)` and both branches must fire. Nothing
    // asserted that until now: `cache_migration_test.dart` covers 2 → 3 from a *seeded v2
    // file*, so a `from < 3` branch mistakenly written as `from == 2` would pass every test
    // in this repository and strand exactly the devices that skipped a release.
    await seedVersionOne();

    final db = AppDatabase(NativeDatabase(file));
    addTearDown(db.close);

    expect(await db.select(db.cachedCustomers).get(), isEmpty);
    expect(await db.select(db.cachedDeliveries).get(), isEmpty);
    expect(await db.select(db.syncCursors).get(), isEmpty);

    // And the promise the cache is not allowed to disturb (§8.3) is still intact.
    expect((await db.select(db.outboxOperations).get()).length, 3);
  });

  test('12d. a fresh install creates every table at the declared version', () async {
    final db = AppDatabase(NativeDatabase(file));
    addTearDown(db.close);

    await IdentityCache(db).save(
      const Session(userId: 1, fullName: 'A', roles: {Role.owner}),
    );
    final outbox = await db.select(db.outboxOperations).get();

    expect(outbox, isEmpty);
    expect(await IdentityCache(db).read(), isNotNull);

    final version = await db.customSelect('PRAGMA user_version').getSingle();
    expect(version.data.values.first, db.schemaVersion);
  });
}
