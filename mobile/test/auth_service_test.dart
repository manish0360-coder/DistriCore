// M8 task 4 M3 — the authentication engine (§8.1).
//
// Driven through a real `ApiClient` and the existing scripted adapter, so `DeviceInterceptor`
// and `RefreshInterceptor` are the ones the app ships. No second HTTP fake.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/core/result.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:districore/data/identity/auth_dto.dart';
import 'package:districore/data/identity/auth_service.dart';
import 'package:districore/data/identity/session_restorer.dart';
import 'package:districore/data/repositories/token_session_repository.dart';
import 'package:districore/domain/identity/role.dart';
import 'package:districore/domain/identity/session.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';

const _phone = '+919876543210';
const _code = '482913';
const _password = 'correct-horse-battery-staple';

Map<String, dynamic> _user({List<String> roles = const ['SALESMAN'], Object? customerId}) =>
    <String, dynamic>{
      'id': 12,
      'full_name': 'Ramesh Kumar',
      'phone': _phone,
      'language': 'hi',
      'roles': roles,
      'customer_id': customerId,
    };

Map<String, dynamic> _bundle({Map<String, dynamic>? user}) => <String, dynamic>{
      'access_token': 'access-1',
      'refresh_token': 'refresh-2',
      'expires_in': 900,
      'user': user ?? _user(),
    };

({AuthService auth, FakeAdapter adapter, FakeTokens tokens, TokenSessionRepository sessions})
    build({required FutureOr<ResponseBody> Function(RequestOptions, int) script}) {
  final adapter = FakeAdapter(script);
  // A signed-out device that has already minted its identity (M1).
  final tokens = FakeTokens(accessToken: null, refreshToken: null);
  final api = ApiClient(
    baseUrl: 'https://api.test',
    tokens: tokens,
    dio: Dio()..httpClientAdapter = adapter,
    refreshDio: Dio()..httpClientAdapter = adapter,
  );
  final sessions = TokenSessionRepository(
    tokens: tokens,
    restorer: SessionRestorer(tokens: tokens, api: api),
  );
  return (
    auth: AuthService(api: api, tokens: tokens, sessions: sessions),
    adapter: adapter,
    tokens: tokens,
    sessions: sessions,
  );
}

void main() {
  group('requestOtp', () {
    test('decodes the challenge exactly', () async {
      final env = build(
        script: (_, __) async =>
            jsonBody(202, {'expires_in_seconds': 300, 'attempts_allowed': 5}),
      );

      final result = await env.auth.requestOtp(_phone);
      final challenge = (result as Ok<OtpChallenge>).value;

      expect(challenge.expiresInSeconds, 300);
      expect(challenge.attemptsAllowed, 5);
      expect((env.adapter.requests.single.data as Map)['phone'], _phone);
    });

    test('a rate-limited request keeps the stable server code', () async {
      // The client branches on `code` (`05` §5). Inventing a bespoke failure here would
      // hide the one thing a caller can act on.
      final env = build(
        script: (_, __) async => jsonBody(429, {'code': 'OTP_RATE_LIMITED', 'detail': 'slow down'}),
      );

      final failure = ((await env.auth.requestOtp(_phone)) as Err<OtpChallenge>).failure;

      expect(failure, isA<ProblemFailure>());
      expect((failure as ProblemFailure).code, 'OTP_RATE_LIMITED');
      expect(failure.status, 429);
    });

    test('a malformed challenge is MalformedResponse', () async {
      final env = build(script: (_, __) async => jsonBody(202, {'attempts_allowed': 5}));
      final failure = ((await env.auth.requestOtp(_phone)) as Err<OtpChallenge>).failure;
      expect(failure, isA<MalformedResponse>());
    });
  });

  group('verifyOtp', () {
    test('persists the refresh token and establishes the Session', () async {
      final env = build(script: (_, __) async => jsonBody(200, _bundle()));

      final session = ((await env.auth.verifyOtp(phone: _phone, code: _code))
              as Ok<Session>)
          .value;

      expect(session.userId, 12);
      expect(session.roles, {Role.salesman});
      expect(env.tokens.refreshToken, 'refresh-2');
      expect(env.tokens.accessToken, 'access-1');
      expect(((env.sessions.current()) as Ok<Session?>).value!.userId, 12);
    });

    test('sends the stored device_id, injected by DeviceInterceptor', () async {
      // Not set by AuthService: one mechanism supplies it (C-10, §8.4). This proves the
      // interceptor really is that mechanism on the auth path too.
      final env = build(script: (_, __) async => jsonBody(200, _bundle()));

      await env.auth.verifyOtp(phone: _phone, code: _code);

      final body = env.adapter.requests.single.data as Map;
      expect(body['device_id'], env.tokens.deviceId);
      expect(body['code'], _code);
    });

    test('a malformed user payload is MalformedResponse', () async {
      final env = build(
        script: (_, __) async => jsonBody(200, _bundle(user: _user(roles: []))),
      );
      final failure =
          ((await env.auth.verifyOtp(phone: _phone, code: _code)) as Err<Session>).failure;
      expect(failure, isA<MalformedResponse>());
    });

    test('a missing access_token is MalformedResponse', () async {
      final env = build(script: (_, __) async {
        final body = _bundle()..remove('access_token');
        return jsonBody(200, body);
      });
      final failure =
          ((await env.auth.verifyOtp(phone: _phone, code: _code)) as Err<Session>).failure;
      expect(failure, isA<MalformedResponse>());
    });

    test('OTP_INVALID stays a ProblemFailure and leaks neither code nor token', () async {
      final env = build(
        script: (_, __) async => jsonBody(422, {'code': 'OTP_INVALID', 'detail': 'Wrong code'}),
      );

      final failure =
          ((await env.auth.verifyOtp(phone: _phone, code: _code)) as Err<Session>).failure;

      expect((failure as ProblemFailure).code, 'OTP_INVALID');
      expect(failure.message, isNot(contains(_code)));
      expect(failure.toString(), isNot(contains(_code)));
    });

    test('a failed verification leaves an existing session untouched', () async {
      var attempt = 0;
      final env = build(script: (_, __) async {
        attempt += 1;
        return attempt == 1
            ? jsonBody(200, _bundle())
            : jsonBody(422, {'code': 'OTP_INVALID', 'detail': 'Wrong code'});
      });

      await env.auth.verifyOtp(phone: _phone, code: _code);
      final established = ((env.sessions.current()) as Ok<Session?>).value;

      final second = await env.auth.verifyOtp(phone: _phone, code: '000000');

      expect(second, isA<Err<Session>>());
      expect(((env.sessions.current()) as Ok<Session?>).value, same(established),
          reason: 'nothing is published on failure');
      expect(env.tokens.refreshToken, 'refresh-2', reason: 'credentials survive a bad code');
    });
  });

  group('loginWithPassword', () {
    test('persists tokens and establishes the Session', () async {
      final env = build(
        script: (_, __) async => jsonBody(200, _bundle(user: _user(roles: ['OWNER']))),
      );

      final session =
          ((await env.auth.loginWithPassword(phone: _phone, password: _password))
                  as Ok<Session>)
              .value;

      expect(session.roles, {Role.owner});
      expect(env.tokens.refreshToken, 'refresh-2');
      expect(env.adapter.requests.single.path, contains('/auth/login'));
    });

    test('a wrong password maps to the server failure and reveals nothing', () async {
      final env = build(
        script: (_, __) async =>
            jsonBody(401, {'code': 'INVALID_CREDENTIALS', 'detail': 'Incorrect phone or password'}),
      );

      final failure =
          ((await env.auth.loginWithPassword(phone: _phone, password: _password))
                  as Err<Session>)
              .failure;

      expect((failure as ProblemFailure).code, 'INVALID_CREDENTIALS');
      expect(failure.message, isNot(contains(_password)));
      expect(failure.toString(), isNot(contains(_password)));
    });

    test('a malformed auth payload is MalformedResponse', () async {
      final env = build(script: (_, __) async => jsonBody(200, {'access_token': 'a'}));
      final failure =
          ((await env.auth.loginWithPassword(phone: _phone, password: _password))
                  as Err<Session>)
              .failure;
      expect(failure, isA<MalformedResponse>());
    });

    test('the password reaches the wire once and never a Failure or a toString', () async {
      final env = build(
        script: (_, __) async => jsonBody(401, {'code': 'INVALID_CREDENTIALS'}),
      );

      final result = await env.auth.loginWithPassword(phone: _phone, password: _password);

      // The password belongs in exactly one place: the request body. Asserted over the
      // headers too, because a credential in a header is the one that ends up in a proxy
      // log (FR-IAM-015).
      final sent = env.adapter.requests.single;
      expect((sent.data as Map)['password'], _password);
      expect(sent.headers.values.map((v) => '$v'), isNot(contains(_password)));
      expect(sent.path, isNot(contains(_password)));

      final failure = (result as Err<Session>).failure;
      expect(failure.message, isNot(contains(_password)));
      expect('$failure', isNot(contains(_password)));
    });
  });

  group('shared invariants', () {
    test('both tokens are handed to TokenStore in exactly one save', () async {
      // *Where* they end up is `SecureTokenStore`'s contract and M1 proves it against a
      // real keystore seam. What this owns is that authentication routes the pair through
      // `TokenStore.save` once — not that it writes them itself, and not twice.
      final env = build(script: (_, __) async => jsonBody(200, _bundle()));
      await env.auth.verifyOtp(phone: _phone, code: _code);

      expect(env.tokens.accessToken, 'access-1');
      expect(env.tokens.refreshToken, 'refresh-2');
      expect(env.tokens.saves, 1);
    });

    test('rotation replaces a previous refresh token', () async {
      final env = build(script: (_, __) async => jsonBody(200, _bundle()));
      env.tokens.refreshToken = 'refresh-OLD';

      await env.auth.loginWithPassword(phone: _phone, password: _password);

      expect(env.tokens.refreshToken, 'refresh-2');
    });

    test('one authentication produces exactly one session emission', () async {
      final env = build(script: (_, __) async => jsonBody(200, _bundle()));
      final seen = <Session?>[];
      final subscription = env.sessions.changes().listen(seen.add);

      await env.auth.verifyOtp(phone: _phone, code: _code);
      await Future<void>.delayed(Duration.zero);

      expect(seen, hasLength(1));
      expect(seen.single!.userId, 12);
      await subscription.cancel();
      env.sessions.dispose();
    });

    test('authentication never opens a second refresh path', () async {
      // Sign-in is not a refresh: /auth/refresh must not be touched, or a device would have
      // two unsynchronised rotation paths against a server that blacklists (D-B1).
      final env = build(script: (_, __) async => jsonBody(200, _bundle()));
      await env.auth.verifyOtp(phone: _phone, code: _code);
      await env.auth.loginWithPassword(phone: _phone, password: _password);

      expect(env.adapter.requests.where((r) => r.path.contains('/auth/refresh')), isEmpty);
    });

    test('Offline does not clear credentials', () async {
      final env = build(script: (options, _) async {
        throw DioException(requestOptions: options, type: DioExceptionType.connectionError);
      });
      env.tokens.refreshToken = 'refresh-OLD';

      final failure =
          ((await env.auth.verifyOtp(phone: _phone, code: _code)) as Err<Session>).failure;

      expect(failure, isA<Offline>());
      expect(env.tokens.refreshToken, 'refresh-OLD');
      expect(env.tokens.clears, 0);
    });
  });
}
