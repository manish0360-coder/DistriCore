// M9.2 — two independent callers racing one refresh.
//
// Restoration and the outbox drain both issue their first request through the **same**
// `ApiClient`. On a cold start the access token is memory-only and therefore absent (§8.2),
// so if they run together **both meet `401 TOKEN_EXPIRED` at once**.
//
// D-B1 says refresh is single-flight. M2's tests pin that for one caller; this is the first
// time two independent callers race it, and a second refresh would present a token the
// server has already rotated and blacklisted — the precise failure D-B1 exists to prevent.
//
// **M9.4 step F serialised the launch chain**, so `bootstrap` no longer creates this overlap
// itself. The guarantee still has to hold and this test still has to exist: `SyncEngine` and
// `SessionRestorer` are shared objects reachable from anywhere, and TD-41's reconnection
// trigger — which is deferred, not cancelled — will fire while a launch chain may still be
// in flight. This asserts the property, not the caller.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/core/clock.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/identity/session_restorer.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/data/repositories/identity_cache.dart';
import 'package:districore/data/sync/sync_engine.dart';
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';

final _now = DateTime.utc(2026, 8, 16, 9);

Map<String, dynamic> _user() => <String, dynamic>{
      'id': 12,
      'full_name': 'Ramesh Kumar',
      'phone': '+919876543210',
      'language': 'hi',
      'roles': <String>['SALESMAN', 'DELIVERY'],
      'customer_id': null,
    };

void main() {
  // **`test`, not `testWidgets`.** There is no widget here, and `testWidgets` runs the body
  // inside `FakeAsync` — which intercepts `scheduleMicrotask` as well as `Timer`, and only
  // flushes on a `pump()`. With nothing to pump, the first `await` below never resumed and
  // the harness timed out after ten minutes without evaluating a single assertion.
  test('two concurrent callers trigger exactly one refresh', () async {
    var refreshes = 0;
    var meCalls = 0;
    var pushes = 0;

    // Both callers must be able to make progress only *after* a refresh, so the adapter
    // answers 401 until the rotated token appears on the wire.
    final adapter = FakeAdapter((options, _) async {
      if (options.path.contains('/auth/refresh')) {
        refreshes += 1;
        return jsonBody(200, {
          'access_token': 'access-2',
          'refresh_token': 'refresh-2',
          'expires_in': 900,
        });
      }
      final authorised = options.headers['Authorization'] == 'Bearer access-2';
      if (options.path.contains('/auth/me')) {
        meCalls += 1;
        return authorised ? jsonBody(200, _user()) : tokenExpired();
      }
      pushes += 1;
      return authorised
          ? jsonBody(202, {'server_time': '2026-08-16T09:00:00Z', 'results': <dynamic>[]})
          : tokenExpired();
    });

    // A cold start: refresh token in the keystore, access token gone (§8.2).
    final tokens = FakeTokens(accessToken: null, refreshToken: 'refresh-1');
    final api = ApiClient(
      baseUrl: 'https://api.test',
      tokens: tokens,
      dio: Dio()..httpClientAdapter = adapter,
      refreshDio: Dio()..httpClientAdapter = adapter,
    );

    // **One database, exactly as `bootstrap` opens one.** The outbox and the identity cache
    // are two readers of the same local file in production; giving the test two would be
    // both unfaithful and — since `memoryIdentity()` opens its own — two live `AppDatabase`
    // instances at once, which is what drift's warning is for.
    final db = AppDatabase(NativeDatabase.memory());
    addTearDown(db.close);
    final outbox = DriftOutboxRepository(db);
    await outbox.append(
      clientUuid: '11111111-2222-4333-8444-555555555555',
      operationType: 'DELIVERY_COMPLETE',
      clientCreatedAt: _now,
      payload: <String, Object?>{'delivery_id': 3312, 'recipient_name': 'Sharma ji'},
    );

    final restorer = SessionRestorer(
      tokens: tokens,
      api: api,
      identity: IdentityCache(db),
      clock: FixedClock(_now),
      offlineWindow: const Duration(days: 7),
    );
    final engine = SyncEngine(api: api, outbox: outbox, tokens: tokens);

    // **Deliberately overlapped**: both started, neither awaited. This is the adversarial
    // case D-B1 must survive, not a reproduction of what `bootstrap` now does.
    final restoring = restorer.restore();
    final syncing = engine.sync();
    await Future.wait<void>([restoring, syncing]);

    expect(refreshes, 1, reason: 'D-B1: refresh is single-flight across concurrent callers');
    expect(tokens.refreshToken, 'refresh-2', reason: 'the rotated token was stored once');
    // Both callers reached the server after the shared refresh: neither was starved, and
    // neither issued its own.
    expect(meCalls, greaterThanOrEqualTo(2), reason: '/auth/me retried after the refresh');
    expect(pushes, greaterThanOrEqualTo(2), reason: '/sync/push retried after the refresh');
  });
}
