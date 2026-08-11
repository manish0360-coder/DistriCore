// D-B1, D-B2, D-B3. These are the tests the frozen decisions exist for.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';

/// One `ApiClient` wired to a scripted adapter shared by both its Dio instances, so the
/// test sees the refresh call and the retries in one ordered list.
({ApiClient client, FakeAdapter adapter, FakeTokens tokens}) build({
  required FutureOr<ResponseBody> Function(RequestOptions, int) script,
}) {
  final adapter = FakeAdapter(script);
  final tokens = FakeTokens();
  final dio = Dio()..httpClientAdapter = adapter;
  final refreshDio = Dio()..httpClientAdapter = adapter;
  final client = ApiClient(
    baseUrl: 'https://api.test',
    tokens: tokens,
    dio: dio,
    refreshDio: refreshDio,
  );
  return (client: client, adapter: adapter, tokens: tokens);
}

ResponseBody _refreshOk() => jsonBody(200, {
      'access_token': 'access-2',
      'refresh_token': 'refresh-2',
      'expires_in': 900,
      'user': <String, dynamic>{},
    });

void main() {
  test('THREE concurrent 401s cause exactly ONE refresh (D-B1)', () async {
    // The server sets ROTATE_REFRESH_TOKENS and BLACKLIST_AFTER_ROTATION. A second parallel
    // refresh presents a blacklisted token, reuse detection treats it as an attack, and a
    // working session is signed out by nothing but its own concurrency.
    var refreshCalls = 0;
    final env = build(script: (options, _) async {
      if (options.path.contains('/auth/refresh')) {
        refreshCalls += 1;
        await Future<void>.delayed(const Duration(milliseconds: 20));
        return _refreshOk();
      }
      final retried = options.headers['Authorization'] == 'Bearer access-2';
      return retried ? jsonBody(200, {'ok': true}) : tokenExpired();
    });

    final results = await Future.wait([
      env.client.get<Object?>('/deliveries', decode: (b) => b),
      env.client.get<Object?>('/customers', decode: (b) => b),
      env.client.get<Object?>('/media', decode: (b) => b),
    ]);

    expect(refreshCalls, 1, reason: 'concurrent 401s must share one refresh operation');
    expect(results.every((r) => r.isOk), isTrue, reason: 'all three waiters retried and won');
    expect(env.tokens.saves, 1);
    expect(env.tokens.refreshToken, 'refresh-2', reason: 'the rotated token replaced the old');
  });

  test('a request is retried EXACTLY once; a second 401 is terminal (C-7, D-B1)', () async {
    var refreshCalls = 0;
    final env = build(script: (options, _) async {
      if (options.path.contains('/auth/refresh')) {
        refreshCalls += 1;
        return _refreshOk();
      }
      return tokenExpired(); // never recovers
    });

    final result = await env.client.get<Object?>('/deliveries', decode: (b) => b);

    expect(result.isOk, isFalse);
    expect(refreshCalls, 1, reason: 'no second refresh after the retry also failed');
    final attempts =
        env.adapter.requests.where((r) => r.path.contains('/deliveries')).length;
    expect(attempts, 2, reason: 'original + exactly one retry');
    expect(env.tokens.clears, 1, reason: 'terminal 401 signs out');
  });

  test('the retry replays the ORIGINAL body, including client_uuid (D-B3, P-6)', () async {
    final env = build(script: (options, _) async {
      if (options.path.contains('/auth/refresh')) return _refreshOk();
      return options.headers['Authorization'] == 'Bearer access-2'
          ? jsonBody(200, {'ok': true})
          : tokenExpired();
    });

    const uuid = '11111111-2222-3333-4444-555555555555';
    await env.client.post<Object?>(
      '/deliveries/7/complete',
      body: <String, dynamic>{'client_uuid': uuid, 'recipient_name': 'Ravi'},
      decode: (b) => b,
    );

    final writes =
        env.adapter.requests.where((r) => r.path.contains('/complete')).toList();
    expect(writes, hasLength(2));
    for (final attempt in writes) {
      expect(attempt.body['client_uuid'], uuid,
          reason: 'a regenerated UUID defeats server idempotency (C-2)');
      expect(attempt.body['recipient_name'], 'Ravi');
      expect(attempt.method, 'POST');
    }
    // Two independent snapshots, so this compares the first attempt's identity with the
    // second's rather than an object with itself (P-6, C-2).
    expect(writes.first.body['client_uuid'], writes.last.body['client_uuid']);
  });

  test('the retry carries the NEW access token, not the one that just failed', () async {
    final env = build(script: (options, _) async {
      if (options.path.contains('/auth/refresh')) return _refreshOk();
      return options.headers['Authorization'] == 'Bearer access-2'
          ? jsonBody(200, {'ok': true})
          : tokenExpired();
    });
    await env.client.get<Object?>('/deliveries', decode: (b) => b);
    final attempts = env.adapter.requests.where((r) => r.path.contains('/deliveries')).toList();
    expect(attempts.first.headers['Authorization'], 'Bearer access-1');
    expect(attempts.last.headers['Authorization'], 'Bearer access-2');
  });

  test('the refresh call itself carries NO Authorization header (D-B2)', () async {
    final env = build(script: (options, _) async {
      if (options.path.contains('/auth/refresh')) return _refreshOk();
      return options.headers['Authorization'] == 'Bearer access-2'
          ? jsonBody(200, {'ok': true})
          : tokenExpired();
    });
    await env.client.get<Object?>('/deliveries', decode: (b) => b);
    final refresh = env.adapter.requests.firstWhere((r) => r.path.contains('/auth/refresh'));
    expect(refresh.headers.containsKey('Authorization'), isFalse,
        reason: 'the refresh client carries neither AuthInterceptor nor RefreshInterceptor');
  });

  test('a 401 ON the refresh call does not recurse (D-B2)', () async {
    var refreshCalls = 0;
    final env = build(script: (options, _) async {
      if (options.path.contains('/auth/refresh')) {
        refreshCalls += 1;
        return jsonBody(401, {'code': 'REFRESH_EXPIRED'});
      }
      return tokenExpired();
    });

    final result = await env.client.get<Object?>('/deliveries', decode: (b) => b);

    expect(result.isOk, isFalse);
    expect(refreshCalls, 1, reason: 'a failing refresh must not trigger itself');
    expect(env.tokens.clears, 1, reason: 'REFRESH_EXPIRED ends the session');
  });

  test('OFFLINE during refresh does NOT sign the user out (FR-IAM-016)', () async {
    // The app has a configured window of local use. Wiping the keystore because a refresh
    // could not reach the server would end that window at the first tunnel.
    final env = build(script: (options, _) async {
      if (options.path.contains('/auth/refresh')) {
        throw DioException(requestOptions: options, type: DioExceptionType.connectionError);
      }
      return tokenExpired();
    });

    await env.client.get<Object?>('/deliveries', decode: (b) => b);

    expect(env.tokens.clears, 0, reason: 'no signal is not the same as no credential');
    expect(env.tokens.refreshToken, 'refresh-1', reason: 'the session survives');
  });

  test('a non-expiry 401 never triggers a refresh', () async {
    var refreshCalls = 0;
    final env = build(script: (options, _) async {
      if (options.path.contains('/auth/refresh')) refreshCalls += 1;
      return jsonBody(401, {'code': 'TOKEN_INVALID'});
    });
    await env.client.get<Object?>('/deliveries', decode: (b) => b);
    expect(refreshCalls, 0);
  });
}
