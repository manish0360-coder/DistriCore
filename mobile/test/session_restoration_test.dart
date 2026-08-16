// M8 task 4 M2 — cold-start session restoration (§8.2).
//
// Driven through a **real `ApiClient`** with a scripted `HttpClientAdapter`, so the refresh
// path under test is the one the app ships — `RefreshInterceptor` — rather than a stand-in
// that agrees with the test. That is the only way to prove restoration *delegates* the
// refresh instead of duplicating it.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/core/result.dart';
import 'package:districore/core/clock.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:districore/data/identity/session_restorer.dart';
import 'package:districore/data/repositories/identity_cache.dart';
import 'package:districore/data/repositories/token_session_repository.dart';
import 'package:districore/domain/identity/role.dart';
import 'package:districore/domain/identity/session.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';
import 'support/memory_database.dart';

Map<String, dynamic> _user({
  List<String> roles = const ['SALESMAN', 'DELIVERY'],
  Object? customerId,
}) =>
    <String, dynamic>{
      'id': 12,
      'full_name': 'Ramesh Kumar',
      'phone': '+919876543210',
      'language': 'hi',
      'roles': roles,
      'customer_id': customerId,
    };

({
  SessionRestorer restorer,
  FakeAdapter adapter,
  FakeTokens tokens,
  IdentityCache identity,
}) build({
  required FutureOr<ResponseBody> Function(RequestOptions, int) script,
  String? refreshToken = 'refresh-1',
}) {
  final adapter = FakeAdapter(script);
  // Cold start: the access token is memory-only (§8.2), so after a restart there is none.
  final tokens = FakeTokens(accessToken: null, refreshToken: refreshToken);
  final api = ApiClient(
    baseUrl: 'https://api.test',
    tokens: tokens,
    dio: Dio()..httpClientAdapter = adapter,
    refreshDio: Dio()..httpClientAdapter = adapter,
  );
  // A real in-memory database. **The M6 window logic is inert in this file on purpose**:
  // these fakes carry `'refresh-1'`, which is not a JWT, so `RefreshClaims.tryParse` returns
  // null and every assertion below still describes the server round-trip it always did.
  final store = memoryIdentity();
  return (
    restorer: SessionRestorer(
      tokens: tokens,
      api: api,
      identity: store.identity,
      clock: const SystemClock(),
      offlineWindow: const Duration(days: 7),
    ),
    adapter: adapter,
    tokens: tokens,
    identity: store.identity,
  );
}

void main() {
  group('no credentials', () {
    test('returns Ok(null) and makes no network call', () async {
      final env = build(script: (_, __) async => jsonBody(200, _user()), refreshToken: null);

      final result = await env.restorer.restore();

      expect(result, isA<Ok<Session?>>());
      expect((result as Ok<Session?>).value, isNull);
      expect(env.adapter.requests, isEmpty,
          reason: 'an offline first launch must not wait on a timeout to show a login screen');
    });
  });

  group('restore succeeds', () {
    test('builds a Session with roles and customerId', () async {
      final env = build(
        script: (_, __) async => jsonBody(200, _user(roles: ['SALESMAN'], customerId: 142)),
      );

      final result = await env.restorer.restore();
      final session = (result as Ok<Session?>).value!;

      expect(session.userId, 12);
      expect(session.fullName, 'Ramesh Kumar');
      expect(session.roles, {Role.salesman});
      expect(session.customerId, 142);
    });

    test('internal staff have a null customerId', () async {
      final env = build(script: (_, __) async => jsonBody(200, _user()));
      final session = ((await env.restorer.restore()) as Ok<Session?>).value!;
      expect(session.customerId, isNull);
      expect(session.roles, {Role.salesman, Role.delivery});
    });

    test('a retailer payload preserves customerId (AD-11)', () async {
      final env = build(
        script: (_, __) async => jsonBody(200, _user(roles: ['RETAILER'], customerId: 501)),
      );
      final session = ((await env.restorer.restore()) as Ok<Session?>).value!;
      expect(session.roles, {Role.retailer});
      expect(session.customerId, 501);
    });

    test('an unknown role alongside a known one keeps the known one', () async {
      // Forward compatibility: a server that adds a role must not brick an installed app.
      final env = build(
        script: (_, __) async => jsonBody(200, _user(roles: ['WAREHOUSE', 'DELIVERY'])),
      );
      final session = ((await env.restorer.restore()) as Ok<Session?>).value!;
      expect(session.roles, {Role.delivery});
    });

    test('the Session carries exactly the four identity values and nothing else', () async {
      // `Session` has no field a token could occupy — that is a compile-time property, not
      // something a runtime assertion can demonstrate. What this *can* check is that
      // restoration smuggles nothing extra in: every value present came from the payload.
      final env = build(script: (_, __) async => jsonBody(200, _user(customerId: 7)));
      final session = ((await env.restorer.restore()) as Ok<Session?>).value!;

      expect(session.userId, 12);
      expect(session.fullName, 'Ramesh Kumar');
      expect(session.roles, {Role.salesman, Role.delivery});
      expect(session.customerId, 7);
      expect(session.fullName, isNot(env.tokens.refreshToken));
    });
  });

  group('refresh is delegated, never duplicated', () {
    test('a 401 TOKEN_EXPIRED is handled by RefreshInterceptor, and /auth/me is retried',
        () async {
      // The restorer must NOT call /auth/refresh itself. The server rotates AND blacklists
      // refresh tokens, so a second refresh path would present a blacklisted token (D-B1).
      var refreshCalls = 0;
      final env = build(script: (options, _) async {
        if (options.path.contains('/auth/refresh')) {
          refreshCalls += 1;
          return jsonBody(200, {
            'access_token': 'access-2',
            'refresh_token': 'refresh-2',
            'expires_in': 900,
          });
        }
        return options.headers['Authorization'] == 'Bearer access-2'
            ? jsonBody(200, _user())
            : tokenExpired();
      });

      final result = await env.restorer.restore();

      expect(result, isA<Ok<Session?>>());
      expect(refreshCalls, 1, reason: 'exactly one refresh, performed by the interceptor');
      final order = env.adapter.requests.map((r) => r.path).toList();
      expect(order.first, contains('/auth/me'),
          reason: 'restoration starts at /auth/me; it never pre-refreshes');
      expect(env.tokens.refreshToken, 'refresh-2', reason: 'the rotated token was stored');
    });
  });

  group('failures', () {
    test('REFRESH_EXPIRED becomes Unauthenticated and clears the tokens', () async {
      final env = build(script: (options, _) async {
        if (options.path.contains('/auth/refresh')) {
          return jsonBody(401, {'code': 'REFRESH_EXPIRED'});
        }
        return tokenExpired();
      });

      final result = await env.restorer.restore();

      expect((result as Err<Session?>).failure, isA<Unauthenticated>());
      expect(env.tokens.clears, greaterThanOrEqualTo(1));
      expect(env.tokens.refreshToken, isNull);
    });

    test('TOKEN_INVALID becomes Unauthenticated and clears the tokens', () async {
      final env = build(
        script: (_, __) async => jsonBody(401, {'code': 'TOKEN_INVALID'}),
      );
      final result = await env.restorer.restore();
      expect((result as Err<Session?>).failure, isA<Unauthenticated>());
      expect(env.tokens.refreshToken, isNull);
    });

    test('Offline PRESERVES the tokens', () async {
      // No signal is not a revoked session. Wiping the keystore here would force a re-login
      // on a device that was never signed out.
      final env = build(script: (options, _) async {
        throw DioException(requestOptions: options, type: DioExceptionType.connectionError);
      });

      final result = await env.restorer.restore();

      expect((result as Err<Session?>).failure, isA<Offline>());
      expect(env.tokens.refreshToken, 'refresh-1');
      expect(env.tokens.clears, 0);
    });

    test('an empty role array is MalformedResponse', () async {
      final env = build(script: (_, __) async => jsonBody(200, _user(roles: [])));
      final result = await env.restorer.restore();
      expect((result as Err<Session?>).failure, isA<MalformedResponse>());
    });

    test('an all-unknown role set is MalformedResponse', () async {
      final env = build(script: (_, __) async => jsonBody(200, _user(roles: ['WAREHOUSE'])));
      final result = await env.restorer.restore();
      expect((result as Err<Session?>).failure, isA<MalformedResponse>());
    });

    test('a missing roles field is MalformedResponse', () async {
      final env = build(script: (_, __) async {
        final body = _user()..remove('roles');
        return jsonBody(200, body);
      });
      expect(((await env.restorer.restore()) as Err<Session?>).failure,
          isA<MalformedResponse>());
    });

    test('a malformed user payload is MalformedResponse', () async {
      final env = build(script: (_, __) async => jsonBody(200, {'id': 'twelve'}));
      expect(((await env.restorer.restore()) as Err<Session?>).failure,
          isA<MalformedResponse>());
    });

    test('the failure message names no credential (FR-IAM-015)', () async {
      final env = build(script: (_, __) async => jsonBody(200, _user(roles: [])));
      final failure = ((await env.restorer.restore()) as Err<Session?>).failure;
      expect(failure.message, isNot(contains('refresh-1')));
    });
  });

  group('TokenSessionRepository', () {
    TokenSessionRepository repositoryFor(
      ({
        SessionRestorer restorer,
        FakeAdapter adapter,
        FakeTokens tokens,
        IdentityCache identity,
      }) env,
    ) =>
        TokenSessionRepository(
          tokens: env.tokens,
          restorer: env.restorer,
          identity: env.identity,
        );

    test('current() before restoration is Ok(null), never a throw', () async {
      final env = build(script: (_, __) async => jsonBody(200, _user()));
      final repository = repositoryFor(env);
      final result = repository.current();
      expect(result, isA<Ok<Session?>>());
      expect((result as Ok<Session?>).value, isNull);
      repository.dispose();
    });

    test('restoration emits exactly once, and current() then agrees', () async {
      final env = build(script: (_, __) async => jsonBody(200, _user()));
      final repository = repositoryFor(env);
      final seen = <Session?>[];
      final subscription = repository.changes().listen(seen.add);

      await repository.restore();
      await Future<void>.delayed(Duration.zero);

      expect(seen, hasLength(1));
      expect(seen.single!.userId, 12);
      expect(((repository.current()) as Ok<Session?>).value!.userId, 12);
      await subscription.cancel();
      repository.dispose();
    });

    test('a failed restoration still emits once, with null', () async {
      final env = build(script: (options, _) async {
        throw DioException(requestOptions: options, type: DioExceptionType.connectionError);
      });
      final repository = repositoryFor(env);
      final seen = <Session?>[];
      final subscription = repository.changes().listen(seen.add);

      await repository.restore();
      await Future<void>.delayed(Duration.zero);

      expect(seen, [null], reason: 'a listener that only heard success would wait forever');
      await subscription.cancel();
      repository.dispose();
    });

    test('signOut emits null, clears tokens and KEEPS the device id', () async {
      final env = build(script: (_, __) async => jsonBody(200, _user()));
      final repository = repositoryFor(env);
      await repository.restore();
      final identity = env.tokens.deviceId;
      final seen = <Session?>[];
      final subscription = repository.changes().listen(seen.add);

      await repository.signOut();
      await Future<void>.delayed(Duration.zero);

      expect(seen, [null]);
      expect(((repository.current()) as Ok<Session?>).value, isNull);
      expect(env.tokens.refreshToken, isNull);
      expect(env.tokens.deviceId, identity, reason: 'sign-out is not revocation (§8.4)');
      await subscription.cancel();
      repository.dispose();
    });
  });
}
