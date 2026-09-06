// **The cold-start-offline credential state, which B1 found and no unit test covered.**
//
// The access token is memory-only (§8.2), so a restart loses it. Restoration normally recovers
// one as a side effect: `/auth/me` presents the *expired* token, meets `401 TOKEN_EXPIRED`, and
// `RefreshInterceptor` refreshes once and replays (D-B1, D-B3). **Inside the offline window with
// a cached identity that never happens** — `SessionRestorer` answers from disk and *"makes no
// request at all"* (FR-IAM-016). The process is then left holding a live refresh token and no
// access token, and every request it sends goes out **bare**.
//
// A bare request is refused `NotAuthenticated` -> **`TOKEN_INVALID`**
// (`backend/api/v1/exception_handler.py:114`), not `TOKEN_EXPIRED`. Before the fix no refresh
// was attempted, `problem.dart` mapped it to `Unauthenticated`, `SyncRound` returned terminal
// and `SyncScheduler` stopped for good. **B1 measured it**: `ticks=2 … stopped=true`, with the
// radio independently proven restored and the host reachable. A device that cold-started
// offline never synced again until relaunched — the launch-only behaviour TD-41 removes.
//
// These tests are that scenario at the unit level, where it costs seconds rather than a device
// run and a Docker stack.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';

/// One `ApiClient` over a scripted adapter shared by both Dio instances, so the refusal, the
/// refresh and the replay appear in **one ordered list**.
({ApiClient client, FakeAdapter adapter, FakeTokens tokens}) build({
  required FutureOr<ResponseBody> Function(RequestOptions, int) script,
  String? accessToken,
  String? refreshToken = 'refresh-1',
}) {
  final adapter = FakeAdapter(script);
  final tokens = FakeTokens(accessToken: accessToken, refreshToken: refreshToken);
  final client = ApiClient(
    baseUrl: 'https://api.test',
    tokens: tokens,
    dio: Dio()..httpClientAdapter = adapter,
    refreshDio: Dio()..httpClientAdapter = adapter,
  );
  return (client: client, adapter: adapter, tokens: tokens);
}

ResponseBody _refreshOk() => jsonBody(200, {
      'access_token': 'access-2',
      'refresh_token': 'refresh-2',
      'expires_in': 900,
    });

/// What the server actually returns for a request carrying no `Authorization` header.
///
/// **Not `tokenExpired()`** — that is the path that already worked, and using it here would
/// test the case that was never broken.
ResponseBody _tokenInvalid() => jsonBody(401, {
      'code': 'TOKEN_INVALID',
      'status': 401,
      'title': 'Authentication required',
      'detail': 'Authentication credentials were not supplied.',
      'errors': <dynamic>[],
    });

List<String> _paths(FakeAdapter adapter) =>
    [for (final request in adapter.requests) request.path];

void main() {
  test('1. a bare request refused TOKEN_INVALID refreshes once and replays', () async {
    final env = build(
      accessToken: null,
      script: (options, _) async {
        if (options.path.contains('/auth/refresh')) return _refreshOk();
        return options.headers['Authorization'] == 'Bearer access-2'
            ? jsonBody(200, {'ok': true})
            : _tokenInvalid();
      },
    );

    final result = await env.client.get<Object?>('/deliveries', decode: (body) => body);

    expect(
      _paths(env.adapter),
      ['/deliveries', '/auth/refresh', '/deliveries'],
      reason: 'refuse, refresh, replay — the same shape TOKEN_EXPIRED already had. Stopping '
          'at the first entry is the defect: it is what stops SyncScheduler for good',
    );
    expect(result.isOk, isTrue);
    expect(env.adapter.requests.last.headers['Authorization'], 'Bearer access-2');
    expect(env.tokens.refreshToken, 'refresh-2', reason: 'the rotated token was stored');
  });

  test('2. concurrent bare requests still cause exactly ONE refresh (D-B1)', () async {
    // The server sets ROTATE_REFRESH_TOKENS with BLACKLIST_AFTER_ROTATION: a second parallel
    // refresh presents a blacklisted token, reuse detection reads it as an attack, and a
    // working session is signed out by nothing but its own concurrency. This is why the fix
    // reacts to the 401 instead of pre-empting it — every caller lands on the one flight.
    var refreshCalls = 0;
    final env = build(
      accessToken: null,
      script: (options, _) async {
        if (options.path.contains('/auth/refresh')) {
          refreshCalls += 1;
          await Future<void>.delayed(const Duration(milliseconds: 20));
          return _refreshOk();
        }
        return options.headers['Authorization'] == 'Bearer access-2'
            ? jsonBody(200, {'ok': true})
            : _tokenInvalid();
      },
    );

    final results = await Future.wait([
      env.client.get<Object?>('/deliveries', decode: (body) => body),
      env.client.get<Object?>('/customers', decode: (body) => body),
      env.client.get<Object?>('/media', decode: (body) => body),
    ]);

    expect(refreshCalls, 1, reason: 'D-B1: one flight, joined — not three');
    expect(results.every((result) => result.isOk), isTrue);
  });

  test('3. TOKEN_INVALID on a request that DID carry a token stays terminal', () async {
    // **The semantic this fix must not erode.** A presented-and-rejected credential is dead;
    // refreshing it would loop against a server that has already refused it. Only the absence
    // of a header makes TOKEN_INVALID recoverable.
    final env = build(
      accessToken: 'access-1',
      script: (options, _) async => _tokenInvalid(),
    );

    final result = await env.client.get<Object?>('/deliveries', decode: (body) => body);

    expect(_paths(env.adapter), ['/deliveries'], reason: 'no refresh may be attempted');
    expect(result.fold((_) => null, (failure) => failure), isA<Unauthenticated>());
  });

  test('4. no refresh token: nothing to refresh with, and the refusal stands', () async {
    // A signed-out device must not acquire a network call it never had. `_performRefresh`
    // returns early without posting when the keystore holds no refresh token.
    final env = build(
      accessToken: null,
      refreshToken: null,
      script: (options, _) async => _tokenInvalid(),
    );

    final result = await env.client.get<Object?>('/deliveries', decode: (body) => body);

    expect(
      _paths(env.adapter).where((path) => path.contains('/auth/refresh')),
      isEmpty,
      reason: 'no credential to present, so no request is made',
    );
    expect(result.fold((_) => null, (failure) => failure), isA<Unauthenticated>());
  });

  test('5. an offline failure clears nothing and stays retryable', () async {
    // **FR-IAM-016.** A transport failure carries no response, so it is not a 401 and never
    // reaches the refresh path at all — the credential survives the outage untouched. The
    // caller sees `Offline`, which is what keeps `SyncScheduler` retrying instead of stopping.
    final env = build(
      accessToken: null,
      script: (options, _) async => throw DioException(
        requestOptions: options,
        type: DioExceptionType.connectionError,
        error: 'no route to host',
      ),
    );

    final result = await env.client.get<Object?>('/deliveries', decode: (body) => body);

    expect(env.tokens.clears, 0, reason: 'an outage must not sign the user out');
    expect(env.tokens.refreshToken, 'refresh-1', reason: 'the credential survives');
    expect(result.fold((_) => null, (failure) => failure), isA<Offline>());
    expect(_paths(env.adapter), ['/deliveries']);
  });

  test('6. restoration is unchanged: /auth/me first, then refresh, then retry', () async {
    // `SessionRestorer` *"never calls `/auth/refresh` itself"* — recovery is delegated so
    // there is exactly one refresh path (D-B1, D-B3). An earlier attempt at this fix
    // refreshed *before* the request and made restoration begin with `/auth/refresh`, which
    // broke `session_restoration_test.dart` and `startup_refresh_race_test.dart`. This pins
    // the order so that never recurs.
    final env = build(
      accessToken: null,
      script: (options, _) async {
        if (options.path.contains('/auth/refresh')) return _refreshOk();
        return options.headers['Authorization'] == 'Bearer access-2'
            ? jsonBody(200, {'ok': true})
            : tokenExpired();
      },
    );

    final result = await env.client.get<Object?>('/auth/me', decode: (body) => body);

    expect(_paths(env.adapter), ['/auth/me', '/auth/refresh', '/auth/me']);
    expect(result.isOk, isTrue);
  });
}
