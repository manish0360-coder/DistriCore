// M8 task 4 M4 — the composition root, executed rather than reviewed.
//
// `bootstrap()` itself cannot be unit-tested: `ensureInitialized`, the platform keystore and
// `runApp` all need a device. So the decisions worth proving were extracted into
// `buildRootContainer` and `startSessionRestoration`, and those are what run here — against
// a **real `ApiClient`** with a scripted adapter, the same shape as
// `session_restoration_test.dart`, so the wiring under test is the wiring that ships.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/app/bootstrap.dart';
import 'package:districore/app/config.dart';
import 'package:districore/app/providers.dart';
import 'package:districore/data/repositories/token_session_repository.dart';
import 'package:districore/domain/identity/session.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';
import 'support/memory_database.dart';

/// A path prefix on purpose: the API is mounted at `/api/v1/` while the client declares
/// `/auth/me`, so a base URL without one would not reach an endpoint on a real deployment.
const _baseUrl = 'https://api.test/api/v1';

Map<String, dynamic> _user() => <String, dynamic>{
      'id': 12,
      'full_name': 'Ramesh Kumar',
      'phone': '+919876543210',
      'language': 'hi',
      'roles': <String>['SALESMAN'],
      'customer_id': null,
    };

ResponseBody _serverError() => jsonBody(500, {
      'code': 'INTERNAL',
      'status': 500,
      'title': 'Server error',
      'detail': 'boom',
      'errors': <dynamic>[],
    });

/// A container wired exactly as `bootstrap` wires it, with the transport scripted.
///
/// [refreshToken] `null` reproduces a fresh install; a value reproduces a cold start with
/// credentials already in the keystore.
({ProviderContainer container, FakeTokens tokens, FakeAdapter adapter}) wire({
  String? refreshToken = 'refresh-1',
  FutureOr<ResponseBody> Function(RequestOptions, int)? script,
}) {
  // Cold start: the access token is memory-only (§8.2), so after a restart there is none.
  final tokens = FakeTokens(accessToken: null, refreshToken: refreshToken);
  final adapter = FakeAdapter(script ?? (_, __) async => jsonBody(200, _user()));

  final container = buildRootContainer(
    config: AppConfig.parse(_baseUrl),
    tokens: tokens,
    database: memoryIdentity().db,
  );
  addTearDown(container.dispose);

  // Installed on the client the *container* built, not on one the test built — so every
  // assertion below is about the object the app would actually use.
  container.read(apiClientProvider).raw.httpClientAdapter = adapter;

  return (container: container, tokens: tokens, adapter: adapter);
}

void main() {
  group('buildRootContainer', () {
    test('binds the token store that was opened at start-up', () {
      final env = wire();
      expect(identical(env.container.read(tokenStoreProvider), env.tokens), isTrue);
    });

    test('the ApiClient carries the validated base URL', () {
      final env = wire();
      expect(env.container.read(apiClientProvider).raw.options.baseUrl, _baseUrl);
    });

    test('the ApiClient reads its store from the container, not from a copy', () async {
      // Asserted through behaviour rather than identity: a client holding a *different*
      // store would still type-check and would still be a `TokenStore`. What it could not do
      // is present a token saved through the bound one.
      final env = wire();
      await env.tokens.save(accessToken: 'access-9', refreshToken: 'refresh-9');

      await env.container
          .read(apiClientProvider)
          .get<Object?>('/ping', decode: (body) => body);

      expect(env.adapter.requests.single.headers['Authorization'], 'Bearer access-9');
    });

    test('a container without the overrides refuses by name', () {
      // The guard `providers.dart` installs. Without it, a forgotten override surfaces as a
      // request with no `Authorization` header instead of as a failure at the wiring.
      final bare = ProviderContainer();
      addTearDown(bare.dispose);

      expect(() => bare.read(tokenStoreProvider), throwsA(isA<StateError>()));
      expect(() => bare.read(apiClientProvider), throwsA(isA<StateError>()));
    });
  });

  group('sessionRepositoryProvider is bound to the real repository', () {
    test('it resolves to TokenSessionRepository', () {
      final env = wire();
      expect(env.container.read(sessionRepositoryProvider), isA<TokenSessionRepository>());
    });

    test('it is the SAME instance bootstrap restores', () {
      // **The defect this exists for.** A `sessionRepositoryProvider` that *constructed* its
      // own `TokenSessionRepository` would satisfy the test above, compile, and give the app
      // two repositories — bootstrap restoring one while the UI watches the other. The
      // symptom would be a permanent login screen, and nothing else would look wrong.
      final env = wire();
      expect(
        identical(
          env.container.read(sessionRepositoryProvider),
          env.container.read(tokenSessionRepositoryProvider),
        ),
        isTrue,
      );
    });
  });

  group('the first frame', () {
    test('the seed is null, and reading it touches no network', () async {
      final env = wire();

      // `.future` resolves with the first value the stream actually delivers, so this
      // distinguishes "seeded with null" from "still AsyncLoading" — which `valueOrNull`
      // alone cannot, since both read as null.
      expect(await env.container.read(sessionProvider.future), isNull);
      expect(env.container.read(sessionProvider), isA<AsyncData<Session?>>());
      expect(env.adapter.requests, isEmpty);
    });

    test('current() is Ok(null) before restoration — the shell can render offline', () {
      final env = wire();
      final repository = env.container.read(sessionRepositoryProvider);

      expect(repository.current().fold((session) => session, (_) => null), isNull);
    });
  });

  group('startSessionRestoration', () {
    test('returns before restoration completes — runApp is never blocked', () async {
      // Scope item 7. If `bootstrap` ever `await`ed this, a van with no signal would show a
      // blank window for the length of the receive timeout.
      //
      // The response is held open by a gate rather than a `Future.delayed`, so the test is
      // deterministic *and* leaves nothing in flight: a request that landed after teardown
      // would add to a closed `StreamController` and fail an unrelated test later.
      final gate = Completer<ResponseBody>();
      final env = wire(script: (_, __) => gate.future);

      final restored = Completer<Session>();
      unawaited(startSessionRestoration(env.container));
      env.container.listen<AsyncValue<Session?>>(sessionProvider, (_, next) {
        final session = next.valueOrNull;
        if (session != null && !restored.isCompleted) restored.complete(session);
      });

      // `/auth/me` has not been answered, and the app is *already* renderable and signed
      // out — which it could not be if restoration were awaited.
      expect(await env.container.read(sessionProvider.future), isNull);
      expect(env.container.read(sessionProvider), isA<AsyncData<Session?>>());
      expect(restored.isCompleted, isFalse,
          reason: 'restoration had genuinely not finished at this point');

      gate.complete(jsonBody(200, _user()));
      final session = await restored.future.timeout(const Duration(seconds: 5));
      expect(session.userId, 12);
    });

    test('a restored session reaches a listener that subscribes AFTER it starts', () async {
      // **The ordering this milestone turns on.** In the app, `runApp` returns and the first
      // frame attaches listeners *later*, so the listener here is attached after
      // `startSessionRestoration` — exactly as in production. `changes()` is a broadcast
      // stream with no replay: unless `sessionProvider` subscribed synchronously inside
      // `startSessionRestoration`, this emission lands in a stream nobody is listening to,
      // and the device sits on the login screen holding a valid refresh token.
      final env = wire();

      unawaited(startSessionRestoration(env.container));

      final restored = Completer<Session>();
      env.container.listen<AsyncValue<Session?>>(
        sessionProvider,
        (_, next) {
          final session = next.valueOrNull;
          if (session != null && !restored.isCompleted) restored.complete(session);
        },
        fireImmediately: true,
      );

      final session = await restored.future.timeout(
        const Duration(seconds: 5),
        onTimeout: () => throw StateError('the restored session never reached the UI'),
      );

      expect(session.userId, 12);
      expect(env.adapter.requests.single.path, '/auth/me');
    });

    test('a failed restoration still publishes, so the shell can move to login', () async {
      // A listener that only ever heard about success would wait forever on a device with no
      // signal. Observed on the repository's own stream rather than through `sessionProvider`
      // because null -> null is deduplicated by `AsyncValue` equality — the provider is
      // silent here for a legitimate reason, and a test that expected it to fire would be
      // asserting the wrong thing.
      final env = wire(script: (_, __) async => _serverError());
      final published = Completer<void>();
      final subscription = env.container
          .read(tokenSessionRepositoryProvider)
          .changes()
          .listen((_) {
        if (!published.isCompleted) published.complete();
      });
      addTearDown(subscription.cancel);

      unawaited(startSessionRestoration(env.container));

      await published.future.timeout(
        const Duration(seconds: 5),
        onTimeout: () => throw StateError('a failed restoration published nothing'),
      );

      expect(await env.container.read(sessionProvider.future), isNull);
      expect(
        env.container.read(sessionProvider),
        isA<AsyncData<Session?>>(),
        reason: 'a shell left in AsyncLoading shows a spinner that never resolves',
      );
    });

    test('a fresh install makes no network call at all', () async {
      // §8.2 — no refresh token means no request, so an offline first launch does not wait
      // on a timeout before it can show a login screen.
      final env = wire(refreshToken: null);

      unawaited(startSessionRestoration(env.container));
      // `startSessionRestoration` is fire-and-forget by design, so the test needs its own
      // settle point. With no credentials `restore()` is pure, and repeating it changes
      // neither the store nor the adapter.
      await env.container.read(tokenSessionRepositoryProvider).restore();

      expect(env.adapter.requests, isEmpty);
      expect(await env.container.read(sessionProvider.future), isNull);
    });
  });
}
