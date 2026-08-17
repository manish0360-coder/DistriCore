// M9.2 — the drain, against a real in-memory SQLite outbox and a real `ApiClient`.
//
// Nothing is mocked below the port: the transitions asserted here are the ones the engine
// actually writes to SQLite, because the property this milestone is about is durability
// under interruption and a fake would agree with whatever the code did.
//
// **One `AppDatabase` per test.** `wire()` registers its own tear-down; a second call in one
// test is two live instances, which is what drift's warning is for.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/core/result.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/data/sync/sync_engine.dart';
import 'package:districore/domain/outbox/outbox_repository.dart';
import 'package:districore/domain/outbox/outbox_status.dart';
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';

final _now = DateTime.utc(2026, 8, 16, 9);

typedef Env = ({
  SyncEngine engine,
  OutboxRepository outbox,
  AppDatabase db,
  FakeAdapter adapter,
  FakeTokens tokens,
});

Env wire({FutureOr<ResponseBody> Function(RequestOptions, int)? script}) {
  final adapter = FakeAdapter(script ?? (_, __) async => _accepted(const []));
  final tokens = FakeTokens(accessToken: 'access-1', refreshToken: 'refresh-1');
  final db = AppDatabase(NativeDatabase.memory());
  addTearDown(db.close);
  final outbox = DriftOutboxRepository(db);
  return (
    engine: SyncEngine(
      api: ApiClient(
        baseUrl: 'https://api.test',
        tokens: tokens,
        dio: Dio()..httpClientAdapter = adapter,
        refreshDio: Dio()..httpClientAdapter = adapter,
      ),
      outbox: outbox,
      tokens: tokens,
    ),
    outbox: outbox,
    db: db,
    adapter: adapter,
    tokens: tokens,
  );
}

/// A `202` whose results echo the given verdicts, keyed by `client_uuid`.
ResponseBody _results(List<Map<String, dynamic>> results) =>
    jsonBody(202, {'server_time': '2026-08-16T09:00:00Z', 'results': results});

ResponseBody _accepted(List<String> clientUuids) => _results([
      for (final uuid in clientUuids)
        {'client_uuid': uuid, 'status': 'ACCEPTED', 'entity_type': 'delivery'},
    ]);

/// Every `client_uuid` in the request, in the order it was sent.
List<String> sentUuids(RecordedRequest request) => [
      for (final operation in (request.body['operations'] as List<dynamic>))
        (operation as Map<String, dynamic>)['client_uuid'] as String,
    ];

Future<List<String>> seed(OutboxRepository outbox, int count) async {
  final uuids = <String>[];
  for (var i = 0; i < count; i++) {
    final uuid = 'e${i.toString().padLeft(7, '0')}-2222-4333-8444-555555555555';
    uuids.add(uuid);
    await outbox.append(
      clientUuid: uuid,
      operationType: 'DELIVERY_COMPLETE',
      clientCreatedAt: _now.add(Duration(seconds: i)),
      payload: <String, Object?>{'delivery_id': 3300 + i, 'recipient_name': 'Sharma ji'},
    );
  }
  return uuids;
}

/// Local status per `client_uuid`, read straight from SQLite.
Future<Map<String, OutboxStatus>> statuses(AppDatabase db) async {
  final rows = await db.select(db.outboxOperations).get();
  return {for (final row in rows) row.clientUuid: OutboxStatus.fromCode(row.status)};
}

T ok<T>(Result<T> result) => result.fold((v) => v, (f) => fail('expected Ok, got $f'));

void main() {
  // ------------------------------------------------------------------ 1
  test('1. an empty queue makes no request at all', () async {
    final env = wire();

    final report = ok(await env.engine.sync());

    expect(env.adapter.requests, isEmpty, reason: 'nothing to say, so nothing is sent');
    expect(report.total, 0);
  });

  // ------------------------------------------------------------------ 2
  test('2. operations are sent in sequence order (D-C1, PU-1)', () async {
    final env = wire();
    final uuids = await seed(env.outbox, 5);

    await env.engine.sync();

    // FR-SYN-002: creation order per device. The array position *is* that order (PU-1), so
    // this list being sorted is the whole ordering guarantee.
    expect(sentUuids(env.adapter.requests.single), uuids);
  });

  // ------------------------------------------------------------------ 3, 4
  test('3. exactly 200 operations go in one push', () async {
    final env = wire();
    await seed(env.outbox, 200);

    await env.engine.sync();

    expect(env.adapter.requests, hasLength(1), reason: '05 §13: 200 is the legal maximum');
    expect((env.adapter.requests.single.body['operations'] as List<dynamic>), hasLength(200));
  });

  test('4. 201 operations split into 200 + 1, in order, across two pushes', () async {
    // **The server has to answer for a second batch to exist.** A full batch that produces
    // no terminal verdict leaves the queue unchanged, and the engine correctly stops rather
    // than re-claiming the same rows forever. This script acknowledges everything it is
    // sent, which is what makes the 200 + 1 split reachable.
    final env = wire(script: (options, _) async => _accepted(_uuidsOf(options)));
    final uuids = await seed(env.outbox, 201);

    await env.engine.sync();

    expect(env.adapter.requests, hasLength(2));
    expect(sentUuids(env.adapter.requests[0]), uuids.sublist(0, 200));
    expect(sentUuids(env.adapter.requests[1]), uuids.sublist(200));
  });

  // ------------------------------------------------------------------ 5, 6, 7, 8
  test('5. ACCEPTED becomes ACKNOWLEDGED, not deleted', () async {
    // Ruling A: `05` §11.2's "delete from the outbox" is eventual lifecycle removal. Deleting
    // here would make D-C1's AUTOINCREMENT-and-purge design meaningless.
    final env = wire(script: (options, _) async => _accepted(_uuidsOf(options)));
    final uuids = await seed(env.outbox, 2);

    final report = ok(await env.engine.sync());

    expect(await statuses(env.db), {
      uuids[0]: OutboxStatus.acknowledged,
      uuids[1]: OutboxStatus.acknowledged,
    });
    expect(report.acknowledged, 2);
    expect(ok(await env.outbox.depth()), 0, reason: 'depth counts PENDING only');
  });

  test('6. DUPLICATE becomes ACKNOWLEDGED — a replay is success (BR-012)', () async {
    final env = wire(
      script: (options, _) async => _results([
        for (final uuid in _uuidsOf(options))
          {'client_uuid': uuid, 'status': 'DUPLICATE', 'entity_type': 'delivery'},
      ]),
    );
    final uuids = await seed(env.outbox, 1);

    final report = ok(await env.engine.sync());

    expect((await statuses(env.db))[uuids.single], OutboxStatus.acknowledged);
    expect(report.acknowledged, 1);
    expect(report.rejected, 0, reason: 'a duplicate is not an error');
  });

  test('7. DEFERRED stays PENDING — retaining the row IS the retry', () async {
    final env = wire(
      script: (options, _) async => _results([
        for (final uuid in _uuidsOf(options))
          {'client_uuid': uuid, 'status': 'DEFERRED'},
      ]),
    );
    final uuids = await seed(env.outbox, 1);

    final report = ok(await env.engine.sync());

    expect((await statuses(env.db))[uuids.single], OutboxStatus.pending);
    expect(ok(await env.outbox.depth()), 1);
    expect(report.deferred, 1);
  });

  test('8. REJECTED becomes REJECTED and is never deleted (C-3, P-5)', () async {
    final env = wire(
      script: (options, _) async => _results([
        for (final uuid in _uuidsOf(options))
          {'client_uuid': uuid, 'status': 'REJECTED', 'error_code': 'VALIDATION_FAILED'},
      ]),
    );
    final uuids = await seed(env.outbox, 1);

    final report = ok(await env.engine.sync());

    expect((await statuses(env.db))[uuids.single], OutboxStatus.rejected);
    expect(report.rejected, 1);
    expect(ok(await env.outbox.depth()), 0, reason: 'rejected is not pending');
    // The row survives. The reason lives server-side (BR-014); there is no local column.
    expect(await env.db.select(env.db.outboxOperations).get(), hasLength(1));
  });

  // ------------------------------------------------------------------ 9
  test('9. a mixed response updates each row independently', () async {
    final env = wire(
      script: (options, _) async {
        final uuids = _uuidsOf(options);
        return _results([
          {'client_uuid': uuids[0], 'status': 'ACCEPTED'},
          {'client_uuid': uuids[1], 'status': 'DEFERRED'},
          {'client_uuid': uuids[2], 'status': 'REJECTED', 'error_code': 'X'},
          {'client_uuid': uuids[3], 'status': 'DUPLICATE'},
        ]);
      },
    );
    final uuids = await seed(env.outbox, 4);

    final report = ok(await env.engine.sync());

    expect(await statuses(env.db), {
      uuids[0]: OutboxStatus.acknowledged,
      uuids[1]: OutboxStatus.pending,
      uuids[2]: OutboxStatus.rejected,
      uuids[3]: OutboxStatus.acknowledged,
    });
    expect(report.acknowledged, 2);
    expect(report.deferred, 1);
    expect(report.rejected, 1);
  });

  test('an operation the server did not mention stays PENDING', () async {
    // The one assumption that would lose a delivery is "unmentioned means accepted".
    final env = wire(script: (options, _) async => _accepted([_uuidsOf(options).first]));
    final uuids = await seed(env.outbox, 2);

    await env.engine.sync();

    expect(await statuses(env.db), {
      uuids[0]: OutboxStatus.acknowledged,
      uuids[1]: OutboxStatus.pending,
    });
  });

  // ------------------------------------------------------------------ 10, 11
  test('10. a failure on the second batch keeps the first batch acknowledged', () async {
    // FR-SYN-017: partial progress is retained, never restarted from the beginning.
    var call = 0;
    final env = wire(
      script: (options, _) async {
        call += 1;
        if (call == 1) return _accepted(_uuidsOf(options));
        throw DioException.connectionError(
          requestOptions: options,
          reason: 'signal lost mid-round',
        );
      },
    );
    final uuids = await seed(env.outbox, 201);

    final result = await env.engine.sync();

    expect(result, isA<Err<SyncReport>>());
    final byUuid = await statuses(env.db);
    expect(
      uuids.sublist(0, 200).every((u) => byUuid[u] == OutboxStatus.acknowledged),
      isTrue,
      reason: 'work already accepted is not handed back',
    );
    expect(byUuid[uuids[200]], OutboxStatus.pending, reason: 'the failed batch is retryable');
  });

  test('11. a network failure preserves every operation as PENDING', () async {
    final env = wire(
      script: (options, _) => throw DioException.connectionError(
        requestOptions: options,
        reason: 'no signal',
      ),
    );
    final uuids = await seed(env.outbox, 3);

    final result = await env.engine.sync();

    expect((result as Err<SyncReport>).failure, isNotNull);
    expect(ok(await env.outbox.depth()), 3, reason: 'nothing is lost when the network is');
    expect(
      (await statuses(env.db)).values.every((s) => s == OutboxStatus.pending),
      isTrue,
      reason: 'none stranded IN_FLIGHT',
    );
    expect(uuids, hasLength(3));
  });

  // ------------------------------------------------------------------ 12
  test('12. rows stranded IN_FLIGHT by a killed push are reclaimed and resent', () async {
    // A process killed mid-push leaves IN_FLIGHT rows. Resending is safe — a replay is
    // DUPLICATE (I-4) — and stranding them is the loss FR-SYN-004 forbids.
    final env = wire(script: (options, _) async => _accepted(_uuidsOf(options)));
    final uuids = await seed(env.outbox, 2);
    await env.db.customStatement(
      "UPDATE outbox_operation SET status = '${OutboxStatus.inFlight.code}'",
    );
    expect(ok(await env.outbox.depth()), 0, reason: 'precondition: nothing looks pending');

    await env.engine.sync();

    expect(sentUuids(env.adapter.requests.single), uuids);
    expect(
      (await statuses(env.db)).values.every((s) => s == OutboxStatus.acknowledged),
      isTrue,
    );
  });

  // ------------------------------------------------------------------ 13
  test('13. two concurrent syncs produce exactly one push', () async {
    final gate = Completer<void>();
    final env = wire(
      script: (options, _) async {
        await gate.future;
        return _accepted(_uuidsOf(options));
      },
    );
    await seed(env.outbox, 1);

    final first = env.engine.sync();
    final second = env.engine.sync();
    gate.complete();
    await Future.wait([first, second]);

    expect(env.adapter.requests, hasLength(1),
        reason: 'single-flight: 60 pushes/hour is the server limit');
  });

  // ------------------------------------------------------------------ 14
  test('14. TOKEN_EXPIRED goes through the existing interceptor, once', () async {
    var refreshes = 0;
    final env = wire(
      script: (options, _) async {
        if (options.path.contains('/auth/refresh')) {
          refreshes += 1;
          return jsonBody(200, {
            'access_token': 'access-2',
            'refresh_token': 'refresh-2',
            'expires_in': 900,
          });
        }
        return options.headers['Authorization'] == 'Bearer access-2'
            ? _accepted(_uuidsOf(options))
            : tokenExpired();
      },
    );
    await seed(env.outbox, 1);

    final report = ok(await env.engine.sync());

    // The engine has no auth code at all — C-7 and D-B1 are the interceptors' job.
    expect(refreshes, 1);
    expect(env.tokens.refreshToken, 'refresh-2');
    expect(report.acknowledged, 1);
  });

  // ------------------------------------------------------------------ 15, 16
  test('15 & 16. device_id is batch-level and appears in no payload (PU-4)', () async {
    final env = wire(script: (options, _) async => _accepted(_uuidsOf(options)));
    await seed(env.outbox, 3);

    await env.engine.sync();

    final body = env.adapter.requests.single.body;
    expect(body['device_id'], env.tokens.deviceId);
    for (final operation in body['operations'] as List<dynamic>) {
      final payload = (operation as Map<String, dynamic>)['payload'] as Map<String, dynamic>;
      // D-C4: a `device_id` here would duplicate a value the contract places once per batch,
      // and M9.1's serializer refuses the whole batch for it.
      expect(payload.containsKey('device_id'), isFalse);
    }
  });

  // ------------------------------------------------------------------ 17
  test('17. acknowledged rows leave only through the retention purge', () async {
    final env = wire(script: (options, _) async => _accepted(_uuidsOf(options)));
    await seed(env.outbox, 2);
    await env.engine.sync();

    expect(await env.db.select(env.db.outboxOperations).get(), hasLength(2),
        reason: 'sync acknowledges; it never deletes');

    final purged = ok(await env.outbox.purgeAcknowledgedBefore(_now.add(const Duration(days: 1))));

    expect(purged, 2);
    expect(await env.db.select(env.db.outboxOperations).get(), isEmpty);
  });

  test('the purge takes only ACKNOWLEDGED rows', () async {
    final env = wire(
      script: (options, _) async {
        final uuids = _uuidsOf(options);
        return _results([
          {'client_uuid': uuids[0], 'status': 'ACCEPTED'},
          {'client_uuid': uuids[1], 'status': 'REJECTED', 'error_code': 'X'},
          {'client_uuid': uuids[2], 'status': 'DEFERRED'},
        ]);
      },
    );
    await seed(env.outbox, 3);
    await env.engine.sync();

    ok(await env.outbox.purgeAcknowledgedBefore(_now.add(const Duration(days: 1))));

    // C-3 / FR-SYN-006 / P-5: a REJECTED row has no delete path at all, and a PENDING one is
    // unsent work.
    final remaining = await statuses(env.db);
    expect(remaining.values.toSet(), {OutboxStatus.rejected, OutboxStatus.pending});
  });

  // ------------------------------------------------------------------ 18
  test('18. the sync-status depth reflects the queue after a sync', () async {
    // T7 reads `depth()`, which counts PENDING. This is the whole of #18: no new UI, no new
    // control — the existing screen simply has less to report.
    final env = wire(
      script: (options, _) async {
        final uuids = _uuidsOf(options);
        return _results([
          {'client_uuid': uuids[0], 'status': 'ACCEPTED'},
          {'client_uuid': uuids[1], 'status': 'ACCEPTED'},
          {'client_uuid': uuids[2], 'status': 'DEFERRED'},
        ]);
      },
    );
    await seed(env.outbox, 3);
    expect(ok(await env.outbox.depth()), 3);

    await env.engine.sync();

    expect(ok(await env.outbox.depth()), 1, reason: 'only the deferred one still waits');
    expect(ok(await env.outbox.pending()), hasLength(1));
  });
}

/// The `client_uuid`s carried by an outgoing push, in order.
List<String> _uuidsOf(RequestOptions options) {
  final body = options.data! as Map<String, dynamic>;
  return [
    for (final operation in body['operations'] as List<dynamic>)
      (operation as Map<String, dynamic>)['client_uuid'] as String,
  ];
}
