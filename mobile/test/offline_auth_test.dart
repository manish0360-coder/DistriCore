// M8 task 4 M6 — offline authentication, end to end through the real restorer.
//
// Driven through a real `ApiClient`, a real in-memory SQLite database and the real
// `TokenSessionRepository`. The only fakes are the transport adapter and the keystore —
// the two things a laptop genuinely does not have.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/core/clock.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/core/result.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/identity/session_restorer.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/data/repositories/identity_cache.dart';
import 'package:districore/data/repositories/token_session_repository.dart';
import 'package:districore/domain/identity/role.dart';
import 'package:districore/domain/identity/session.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';
import 'support/jwt.dart';
import 'support/memory_database.dart';

final _issued = DateTime.utc(2026, 8, 1, 9);
final _expires = _issued.add(const Duration(days: 30));

const _session = Session(
  userId: 12,
  fullName: 'Ramesh Kumar',
  roles: {Role.salesman, Role.delivery},
  customerId: null,
);

Map<String, dynamic> _user() => <String, dynamic>{
      'id': 12,
      'full_name': 'Ramesh Kumar',
      'phone': '+919876543210',
      'language': 'hi',
      'roles': <String>['SALESMAN', 'DELIVERY'],
      'customer_id': null,
    };

typedef Env = ({
  SessionRestorer restorer,
  TokenSessionRepository sessions,
  FakeAdapter adapter,
  FakeTokens tokens,
  IdentityCache identity,
  AppDatabase db,
});

Env build({
  required DateTime now,
  FutureOr<ResponseBody> Function(RequestOptions, int)? script,
  DateTime? issuedAt,
  DateTime? expiresAt,
  bool jwt = true,
  Duration offlineWindow = const Duration(days: 7),
}) {
  final adapter = FakeAdapter(script ?? (_, __) async => jsonBody(200, _user()));
  final tokens = FakeTokens(
    accessToken: null,
    refreshToken: jwt
        ? refreshTokenJwt(issuedAt: issuedAt ?? _issued, expiresAt: expiresAt ?? _expires)
        : 'refresh-1',
  );
  final api = ApiClient(
    baseUrl: 'https://api.test',
    tokens: tokens,
    dio: Dio()..httpClientAdapter = adapter,
    refreshDio: Dio()..httpClientAdapter = adapter,
  );
  final store = memoryIdentity();
  final restorer = SessionRestorer(
    tokens: tokens,
    api: api,
    identity: store.identity,
    clock: FixedClock(now),
    offlineWindow: offlineWindow,
  );
  final sessions = TokenSessionRepository(
    tokens: tokens,
    restorer: restorer,
    identity: store.identity,
  );
  addTearDown(sessions.dispose);
  return (
    restorer: restorer,
    sessions: sessions,
    adapter: adapter,
    tokens: tokens,
    identity: store.identity,
    db: store.db,
  );
}

void main() {
  group('1. inside the window, a cold start needs no network', () {
    test('restores the cached identity and makes zero requests', () async {
      final env = build(now: _issued.add(const Duration(days: 3)));
      await env.identity.save(_session);

      final result = await env.restorer.restore();

      final session = (result as Ok<Session?>).value!;
      expect(session.userId, 12);
      expect(session.roles, {Role.salesman, Role.delivery});
      expect(env.adapter.requests, isEmpty,
          reason: 'FR-IAM-016: a van with no signal must reach its deliveries');
    });

    test('roles survive the round trip through storage as an array (P-7)', () async {
      final env = build(now: _issued.add(const Duration(hours: 1)));
      await env.identity.save(const Session(
        userId: 9,
        fullName: 'Owner',
        roles: {Role.owner, Role.delivery},
        customerId: 501,
      ));

      final session = ((await env.restorer.restore()) as Ok<Session?>).value!;

      expect(session.roles, {Role.owner, Role.delivery});
      expect(session.customerId, 501);
    });
  });

  group('2 & 3. at and beyond the boundary', () {
    test('2. exactly seven days denies and falls through to the server', () async {
      final env = build(now: _issued.add(const Duration(days: 7)));
      await env.identity.save(_session);

      await env.restorer.restore();

      expect(env.adapter.requests, isNotEmpty, reason: 'equality denies (§14.12.2)');
    });

    test('3. beyond the window, offline, is Unauthenticated', () async {
      final env = build(
        now: _issued.add(const Duration(days: 9)),
        script: (_, __) => throw DioException.connectionError(
          requestOptions: RequestOptions(),
          reason: 'no route to host',
        ),
      );
      await env.identity.save(_session);

      final result = await env.restorer.restore();

      expect((result as Err<Session?>).failure, isA<Unauthenticated>());
    });
  });

  test('4. a credential shorter than the window is the ceiling', () async {
    final env = build(
      now: _issued.add(const Duration(days: 3)),
      expiresAt: _issued.add(const Duration(days: 2)),
    );
    await env.identity.save(_session);

    await env.restorer.restore();

    expect(env.adapter.requests, isNotEmpty,
        reason: '`05` §7.2 — bounded by refresh-token validity');
  });

  group('5 & 15. authentication caches identity and re-anchors', () {
    test('5. adopt writes the cached identity before it publishes', () async {
      final env = build(now: _issued);
      final emissions = <Session?>[];
      final subscription = env.sessions.changes().listen(emissions.add);
      addTearDown(subscription.cancel);

      await env.sessions.adopt(_session);

      expect(await env.identity.read(), isNotNull,
          reason: 'persisted before announced (§14.12 item 10)');
      expect(emissions.single?.userId, 12);
    });

    test('15. a fresh token re-anchors the window', () async {
      // The same cached identity, the same "now" — only the token changed. Under the old
      // anchor this is expired; under the new one it is not. That is D-D3 with nothing
      // written to record it.
      final now = _issued.add(const Duration(days: 9));
      final env = build(now: now, issuedAt: now.subtract(const Duration(hours: 2)));
      await env.identity.save(_session);

      final result = await env.restorer.restore();

      expect((result as Ok<Session?>).value, isNotNull);
      expect(env.adapter.requests, isEmpty);
    });

    test('6. a server round-trip caches the identity for the next cold start', () async {
      final env = build(now: _issued.add(const Duration(days: 10)));

      final result = await env.restorer.restore();

      expect((result as Ok<Session?>).value!.userId, 12);
      expect(await env.identity.read(), isNotNull,
          reason: 'the next launch can now answer offline');
    });
  });

  group('7 & 8. an expired window is not a revocation', () {
    test('7 & 8. the refresh token survives expiry with no signal', () async {
      final env = build(
        now: _issued.add(const Duration(days: 20)),
        script: (_, __) => throw DioException.connectionError(
          requestOptions: RequestOptions(),
          reason: 'no signal',
        ),
      );
      await env.identity.save(_session);

      await env.restorer.restore();

      // §17: clearing here "would end FR-IAM-016's offline window at the first tunnel".
      expect(env.tokens.refreshToken, isNotNull);
      expect(env.tokens.clears, 0);
    });

    test('a server rejection after expiry does clear — existing semantics', () async {
      final env = build(
        now: _issued.add(const Duration(days: 20)),
        script: (options, _) async => options.path.contains('/auth/refresh')
            ? jsonBody(401, {'code': 'REFRESH_EXPIRED'})
            : tokenExpired(),
      );
      await env.identity.save(_session);

      final result = await env.restorer.restore();

      expect((result as Err<Session?>).failure, isA<Unauthenticated>());
      expect(env.tokens.refreshToken, isNull);
      expect(await env.identity.read(), isNull, reason: 'a rejected identity is not kept');
    });
  });

  test('9. an expired window leaves every outbox row untouched', () async {
    final env = build(
      now: _issued.add(const Duration(days: 40)),
      script: (_, __) => throw DioException.connectionError(
        requestOptions: RequestOptions(),
        reason: 'no signal',
      ),
    );
    final outbox = DriftOutboxRepository(env.db);
    for (var i = 0; i < 3; i++) {
      await outbox.append(
        clientUuid: '0000000$i-2222-3333-4444-555555555555',
        operationType: 'DELIVERY_COMPLETE',
        clientCreatedAt: _issued,
        payload: <String, Object?>{'delivery_id': i, 'amount': '1180.00'},
      );
    }
    final before = await env.db.select(env.db.outboxOperations).get();
    await env.identity.save(_session);

    await env.restorer.restore();
    await env.sessions.signOut();

    final after = await env.db.select(env.db.outboxOperations).get();
    expect(after.length, 3);
    expect(after.map((r) => r.sequence).toList(), before.map((r) => r.sequence).toList());
    expect(after.map((r) => r.payload).toList(), before.map((r) => r.payload).toList());
    expect(after.map((r) => r.status).toList(), before.map((r) => r.status).toList());
  });

  group('10 & 11. cached identity fails closed', () {
    test('10. a missing row does not unlock, even inside the window', () async {
      final env = build(now: _issued.add(const Duration(days: 1)));

      await env.restorer.restore();

      expect(env.adapter.requests, isNotEmpty,
          reason: 'all three D-D6 conditions must hold, not two');
    });

    test('11. an unreadable roles column does not unlock', () async {
      final env = build(now: _issued.add(const Duration(days: 1)));
      await env.identity.save(_session);
      await env.db.customStatement("UPDATE local_identity SET roles = 'not json'");

      expect(await env.identity.read(), isNull);
      await env.restorer.restore();
      expect(env.adapter.requests, isNotEmpty);
    });

    test('11b. a row whose roles are all unknown does not unlock', () async {
      // An empty role set would compose a shell with no tabs (P-7) — worse than a login
      // screen, because it looks like it worked.
      final env = build(now: _issued.add(const Duration(days: 1)));
      await env.identity.save(_session);
      await env.db.customStatement('UPDATE local_identity SET roles = \'["WAREHOUSE"]\'');

      expect(await env.identity.read(), isNull);
    });

    test('the identity table holds one row, enforced by the database', () async {
      final env = build(now: _issued);
      await env.identity.save(_session);
      await env.identity.save(const Session(userId: 77, fullName: 'B', roles: {Role.owner}));

      final rows = await env.db.select(env.db.localIdentities).get();
      expect(rows.length, 1);
      expect(rows.single.userId, 77, reason: 'replaced, never accumulated');
    });
  });

  test('14. sign-out clears the identity and keeps device_id', () async {
    final env = build(now: _issued);
    await env.identity.save(_session);
    final deviceId = env.tokens.deviceId;

    await env.sessions.signOut();

    expect(await env.identity.read(), isNull);
    expect(env.tokens.refreshToken, isNull);
    // §8.4 / FR-IAM-009 — one physical device must present as one device.
    expect(env.tokens.deviceId, deviceId);
    expect(env.tokens.deviceId, isNotNull);
  });

  test('a non-JWT refresh token falls back to the server (M1–M5 behaviour)', () async {
    // The property that keeps every M2 and M3 test describing what it always did.
    final env = build(now: _issued, jwt: false);
    await env.identity.save(_session);

    final result = await env.restorer.restore();

    expect((result as Ok<Session?>).value, isNotNull);
    expect(env.adapter.requests, isNotEmpty);
  });
}
