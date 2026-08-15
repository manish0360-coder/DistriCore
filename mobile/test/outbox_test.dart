// M8 task 3 — the outbox, against a real SQLite engine.
//
// `NativeDatabase.memory()` is a genuine SQLite database: real transactions, real
// AUTOINCREMENT, real UNIQUE constraints. **Nothing here is mocked.** A mock would prove
// that the code calls the methods the test expects, which is not the property this
// milestone is about — durability and ordering are behaviours of the engine, and asserting
// them against a fake asserts nothing.
import 'dart:io';

import 'package:districore/core/result.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/domain/outbox/outbox_repository.dart';
import 'package:districore/domain/outbox/outbox_status.dart';
import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

const _uuid = '11111111-2222-3333-4444-555555555555';
const _other = '99999999-8888-7777-6666-555555555555';

Map<String, Object?> _payload() => <String, Object?>{
      'delivery_id': 3312,
      'recipient_name': 'Sharma ji',
      'photo_media_id': 9912,
      'amount': '1180.00', // a money string (AD-02) — must survive byte-identical
    };

void main() {
  late AppDatabase db;
  late OutboxRepository outbox;

  /// The shared in-memory fixture, installed **per group rather than per file**.
  ///
  /// A top-level `setUp` opens this for *every* test, including "durability across reopen",
  /// which opens its own file-backed databases and needs none. Two live `AppDatabase`
  /// instances is precisely what drift warns about — and while these two never share a
  /// `QueryExecutor`, the right answer is to stop opening a database the test does not use,
  /// not to silence the warning that noticed.
  void useMemoryDatabase() {
    setUp(() {
      db = AppDatabase(NativeDatabase.memory());
      outbox = DriftOutboxRepository(db);
    });
    tearDown(() async => db.close());
  }

  Future<T> ok<T>(Future<Result<T>> future) async =>
      (await future).fold((value) => value, (failure) => fail('expected Ok, got $failure'));

  group('append', () {
    useMemoryDatabase();

    test('persists durably and starts PENDING — the only state M8 writes', () async {
      final op = await ok(outbox.append(
        clientUuid: _uuid,
        operationType: 'DELIVERY_COMPLETE',
        clientCreatedAt: DateTime.utc(2026, 8, 5, 6, 41, 10),
        payload: _payload(),
      ));

      expect(op.status, OutboxStatus.pending);

      // Read back through the database, not from the returned object: the claim is that
      // the row is committed, not that the method built a nice value.
      final stored = await db.select(db.outboxOperations).getSingle();
      expect(stored.status, 'PENDING');
    });

    test('persists client_uuid, operation_type, client_created_at and payload exactly',
        () async {
      final created = DateTime.utc(2026, 8, 5, 6, 41, 10);
      await ok(outbox.append(
        clientUuid: _uuid,
        operationType: 'DELIVERY_COMPLETE',
        clientCreatedAt: created,
        payload: _payload(),
      ));

      final op = (await ok(outbox.pending())).single;
      expect(op.clientUuid, _uuid);
      expect(op.operationType, 'DELIVERY_COMPLETE');
      expect(op.clientCreatedAt.toUtc(), created);
      expect(op.payload, _payload(), reason: 'the payload is stored verbatim (P-1)');
      expect(op.payload['amount'], '1180.00',
          reason: 'a money string must not become a number in transit (AD-02, P-3)');
    });

    test('assigns the first sequence, then strictly increasing ones', () async {
      final first = await ok(outbox.append(
        clientUuid: _uuid,
        operationType: 'VISIT_CREATE',
        clientCreatedAt: DateTime.utc(2026, 8, 5, 6),
        payload: const {'a': 1},
      ));
      final second = await ok(outbox.append(
        clientUuid: _other,
        operationType: 'VISIT_CREATE',
        clientCreatedAt: DateTime.utc(2026, 8, 5, 7),
        payload: const {'a': 2},
      ));

      expect(first.sequence, greaterThan(0));
      expect(second.sequence, greaterThan(first.sequence));
    });

    test('a duplicate client_uuid returns the original and creates no second row', () async {
      final first = await ok(outbox.append(
        clientUuid: _uuid,
        operationType: 'DELIVERY_COMPLETE',
        clientCreatedAt: DateTime.utc(2026, 8, 5, 6),
        payload: const {'attempt': 1},
      ));
      final replay = await ok(outbox.append(
        clientUuid: _uuid,
        operationType: 'DELIVERY_COMPLETE',
        clientCreatedAt: DateTime.utc(2026, 8, 5, 9),
        payload: const {'attempt': 2},
      ));

      expect(replay.sequence, first.sequence, reason: 'I-4: the original operation');
      expect(replay.payload, const {'attempt': 1}, reason: 'the replay did not overwrite');
      final rows = await db.select(db.outboxOperations).get();
      expect(rows, hasLength(1), reason: 'P-6: one operation identity, one row');
    });

    test('the UNIQUE constraint is the guarantee, not the lookup (I-6)', () async {
      // Bypasses the repository entirely, so this holds even if the check above is deleted.
      await ok(outbox.append(
        clientUuid: _uuid,
        operationType: 'VISIT_CREATE',
        clientCreatedAt: DateTime.utc(2026, 8, 5),
        payload: const {},
      ));
      await expectLater(
        db.into(db.outboxOperations).insert(OutboxOperationsCompanion.insert(
              clientUuid: _uuid,
              operationType: 'VISIT_CREATE',
              clientCreatedAt: '2026-08-05T00:00:00.000Z',
              payload: '{}',
              status: 'PENDING',
            )),
        throwsA(anything),
      );
    });
  });

  group('ordering (D-C2)', () {
    useMemoryDatabase();

    test('sequence, not client_created_at, decides order', () async {
      // Timestamps deliberately DESCENDING — a device whose clock was corrected backwards
      // mid-shift. If ordering came from the clock, this list would come back reversed.
      final times = [
        DateTime.utc(2026, 8, 5, 12),
        DateTime.utc(2026, 8, 5, 9),
        DateTime.utc(2026, 8, 5, 6),
      ];
      for (var i = 0; i < times.length; i++) {
        await ok(outbox.append(
          clientUuid: 'aaaaaaaa-0000-0000-0000-00000000000$i',
          operationType: 'VISIT_CREATE',
          clientCreatedAt: times[i],
          payload: {'i': i},
        ));
      }

      final ops = await ok(outbox.pending());
      expect(ops.map((o) => o.payload['i']), [0, 1, 2],
          reason: 'creation order, not clock order (P-4)');
      expect(ops.map((o) => o.sequence).toList(),
          [ops[0].sequence, ops[0].sequence + 1, ops[0].sequence + 2]);
      expect(ops.first.clientCreatedAt.isAfter(ops.last.clientCreatedAt), isTrue,
          reason: 'the fixture is exercising: timestamps really are descending');
    });

    test('depth counts pending operations', () async {
      expect(await ok(outbox.depth()), 0);
      await ok(outbox.append(
        clientUuid: _uuid,
        operationType: 'VISIT_CREATE',
        clientCreatedAt: DateTime.utc(2026, 8, 5),
        payload: const {},
      ));
      expect(await ok(outbox.depth()), 1);
    });
  });

  group('purge (§5.3)', () {
    useMemoryDatabase();

    Future<void> seed(String uuid, OutboxStatus status, DateTime at) async {
      await db.into(db.outboxOperations).insert(OutboxOperationsCompanion.insert(
            clientUuid: uuid,
            operationType: 'VISIT_CREATE',
            clientCreatedAt: at.toUtc().toIso8601String(),
            payload: '{}',
            status: status.code,
          ));
    }

    test('acknowledged rows purge; rejected and pending rows never do', () async {
      final old = DateTime.utc(2026, 7, 1);
      await seed('a0000000-0000-0000-0000-000000000001', OutboxStatus.acknowledged, old);
      await seed('a0000000-0000-0000-0000-000000000002', OutboxStatus.rejected, old);
      await seed('a0000000-0000-0000-0000-000000000003', OutboxStatus.pending, old);

      final deleted = await ok(outbox.purgeAcknowledgedBefore(DateTime.utc(2026, 8, 1)));

      expect(deleted, 1);
      final remaining = await db.select(db.outboxOperations).get();
      expect(remaining.map((r) => r.status).toSet(), {'REJECTED', 'PENDING'},
          reason: 'C-3 / P-5: a REJECTED operation is never deleted by code');
    });

    test('a purge does not let the sequence go backwards (D-C1)', () async {
      // The whole reason AUTOINCREMENT was chosen: plain INTEGER PRIMARY KEY reissues
      // max(rowid)+1, so deleting the highest row would hand its number to the next write.
      final first = await ok(outbox.append(
        clientUuid: _uuid,
        operationType: 'VISIT_CREATE',
        clientCreatedAt: DateTime.utc(2026, 7, 1),
        payload: const {},
      ));
      await (db.update(db.outboxOperations)
            ..where((r) => r.sequence.equals(first.sequence)))
          .write(const OutboxOperationsCompanion(status: Value('ACKNOWLEDGED')));
      await ok(outbox.purgeAcknowledgedBefore(DateTime.utc(2026, 8, 1)));
      expect(await db.select(db.outboxOperations).get(), isEmpty);

      final next = await ok(outbox.append(
        clientUuid: _other,
        operationType: 'VISIT_CREATE',
        clientCreatedAt: DateTime.utc(2026, 8, 5),
        payload: const {},
      ));
      expect(next.sequence, greaterThan(first.sequence),
          reason: 'AUTOINCREMENT must not reuse a purged rowid');
    });
  });

  group('durability across reopen', () {
    test('the sequence continues after the database is closed and reopened', () async {
      final file = File('${Directory.systemTemp.createTempSync('outbox').path}/o.sqlite');
      var disk = AppDatabase(NativeDatabase(file));
      var repo = DriftOutboxRepository(disk);

      final before = await ok(repo.append(
        clientUuid: _uuid,
        operationType: 'VISIT_CREATE',
        clientCreatedAt: DateTime.utc(2026, 8, 5),
        payload: const {'n': 1},
      ));
      await disk.close();

      disk = AppDatabase(NativeDatabase(file));
      repo = DriftOutboxRepository(disk);
      final after = await ok(repo.append(
        clientUuid: _other,
        operationType: 'VISIT_CREATE',
        clientCreatedAt: DateTime.utc(2026, 8, 5),
        payload: const {'n': 2},
      ));

      expect(after.sequence, greaterThan(before.sequence),
          reason: 'restart must not restart the sequence (NFR-OFF-005)');
      final all = await ok(repo.pending());
      expect(all, hasLength(2), reason: 'the first write survived the close');
      await disk.close();
      file.parent.deleteSync(recursive: true);
    });
  });
}
