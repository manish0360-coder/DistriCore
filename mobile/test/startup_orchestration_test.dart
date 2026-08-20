// M9.4 step F — the start-up chain, executed rather than reviewed.
//
// Until now `bootstrap` fired restoration and the outbox drain independently and unawaited,
// and M9.4 added a third task. Started independently the three race: a pull that won would
// write the server's view of a delivery over the cache describing a handover the push had
// not yet delivered. `startBackgroundSync` replaces them with one order —
// **restore → push → pull** — and these tests are what that order costs if it is ever
// reversed by a later edit.
//
// **`SyncEngine` and `PullService` are `final class`**, so neither can be faked. The order is
// therefore asserted where it is actually observable: the sequence of request paths that
// reached a single shared `FakeAdapter`. That is also the stronger assertion — a test double
// would prove the orchestration called two objects, not that the device made two requests in
// that order.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/app/bootstrap.dart';
import 'package:districore/app/config.dart';
import 'package:districore/app/providers.dart';
import 'package:districore/domain/identity/session.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';
import 'support/memory_database.dart';

/// A path prefix on purpose: the API is mounted at `/api/v1/`, so a base URL without one
/// would not reach an endpoint on a real deployment.
const _baseUrl = 'https://api.test/api/v1';

/// P-6: one operation, one `client_uuid`, never regenerated.
const _clientUuid = '11111111-2222-4333-8444-555555555555';

final _queuedAt = DateTime.utc(2026, 8, 20, 8);

Map<String, dynamic> _user() => <String, dynamic>{
      'id': 12,
      'full_name': 'Ramesh Kumar',
      'phone': '+919876543210',
      'language': 'hi',
      'roles': <String>['SALESMAN', 'DELIVERY'],
      'customer_id': null,
    };

ResponseBody _problem(int status, String code) => jsonBody(status, {
      'code': code,
      'status': status,
      'title': code,
      'detail': 'scripted',
      'errors': <dynamic>[],
    });

/// `05` §11.2 — every operation settled, so the drain makes exactly one request.
ResponseBody _pushAccepted() => jsonBody(202, {
      'server_time': '2026-08-20T09:00:00Z',
      'results': [
        {'client_uuid': _clientUuid, 'status': 'ACCEPTED'},
      ],
    });

/// `05` §11.1 — a single terminal page, so the pull makes exactly one request.
ResponseBody _emptyPull() => jsonBody(200, {
      'server_time': '2026-08-20T09:00:00Z',
      'has_more': false,
      'customers': {'updated': <dynamic>[], 'deactivated_ids': <dynamic>[]},
      'deliveries': {'updated': <dynamic>[]},
    });

/// A container wired exactly as `bootstrap` wires it, with the transport scripted.
///
/// [queueOperation] seeds one `PENDING` row. **Without it the drain returns `Ok` having sent
/// nothing**, and every ordering assertion below would pass against an orchestration that
/// never pushed at all — a test that cannot fail.
Future<({ProviderContainer container, FakeAdapter adapter})> _wire({
  required FutureOr<ResponseBody> Function(RequestOptions options, int callIndex) script,
  String? refreshToken = 'refresh-1',
  bool queueOperation = true,
}) async {
  final adapter = FakeAdapter(script);

  // Cold start: the access token is memory-only (§8.2), so after a restart there is none.
  final container = buildRootContainer(
    config: AppConfig.parse(_baseUrl),
    tokens: FakeTokens(accessToken: null, refreshToken: refreshToken),
    // **One database**, exactly as `bootstrap` opens one. Two would be two live
    // `AppDatabase` instances, which is what drift's multiple-database warning is for.
    database: memoryIdentity().db,
  );
  addTearDown(container.dispose);

  // Installed on the client the *container* built, so every assertion is about the object
  // the app would actually use.
  container.read(apiClientProvider).raw.httpClientAdapter = adapter;

  if (queueOperation) {
    await container.read(outboxRepositoryProvider).append(
          clientUuid: _clientUuid,
          operationType: 'DELIVERY_COMPLETE',
          clientCreatedAt: _queuedAt,
          payload: <String, Object?>{'delivery_id': 3312, 'recipient_name': 'Sharma ji'},
        );
  }

  return (container: container, adapter: adapter);
}

/// Let the event loop run until the chain has nothing left to do.
///
/// `startBackgroundSync` returns `void` by design — the whole point is that `runApp` is never
/// blocked — so a test cannot await it. Draining turns *after* the last request the chain
/// should have made is what turns *"has not happened yet"* into *"will not happen"*. Each
/// `Duration.zero` delay flushes the entire microtask queue, so this is far more than the
/// short chains here need.
Future<void> _settle() async {
  for (var turn = 0; turn < 25; turn += 1) {
    await Future<void>.delayed(Duration.zero);
  }
}

List<String> _paths(FakeAdapter adapter) =>
    [for (final request in adapter.requests) request.path];

Future<void> _reached(Completer<void> gate, String what) => gate.future.timeout(
      const Duration(seconds: 5),
      onTimeout: () => throw StateError('$what never happened'),
    );

void main() {
  // **`test`, not `testWidgets`.** There is no widget here, and `testWidgets` runs the body
  // inside `FakeAsync`, which intercepts `scheduleMicrotask` as well as `Timer` and only
  // flushes on a `pump()`. With nothing to pump, `_settle` would never resume.
  group('startBackgroundSync', () {
    test('restores, then pushes, then pulls — in that order', () async {
      final pulled = Completer<void>();
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/auth/me')) return jsonBody(200, _user());
        if (options.path.contains('/sync/push')) return _pushAccepted();
        if (!pulled.isCompleted) pulled.complete();
        return _emptyPull();
      });

      startBackgroundSync(env.container);

      await _reached(pulled, 'the pull');
      await _settle();

      // **The whole milestone, in one assertion.** Local writes reach the server before a
      // pull can overwrite the cache that describes them.
      expect(_paths(env.adapter), ['/auth/me', '/sync/push', '/sync/pull']);
    });

    test('a failed restoration pushes nothing and pulls nothing', () async {
      // No session means no useful sync: the push would 401 and the pull would return
      // someone else's nothing. Both would look like work and be neither.
      final answered = Completer<void>();
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/auth/me')) {
          if (!answered.isCompleted) answered.complete();
          return _problem(500, 'INTERNAL');
        }
        return _problem(500, 'THIS_REQUEST_SHOULD_NOT_HAVE_BEEN_MADE');
      });

      startBackgroundSync(env.container);

      await _reached(answered, '/auth/me');
      await _settle();

      expect(_paths(env.adapter), ['/auth/me']);
    });

    test('a fresh install — Ok(null) — pushes nothing and pulls nothing', () async {
      // **Restoration succeeded. There is simply no session.** §8.2: no refresh token means
      // no request, so `restore()` returns `Ok(null)` without touching the network — and the
      // chain must stop for the same reason it stops on `Err`. Letting `Ok(null)` through
      // would make every first launch fire two requests that are guaranteed 401, on the one
      // device that can least afford them.
      //
      // A row is queued, so "no push" is a decision the orchestration made rather than an
      // empty queue making it for us.
      final env = await _wire(
        refreshToken: null,
        script: (options, _) async => _problem(500, 'THIS_REQUEST_SHOULD_NOT_HAVE_BEEN_MADE'),
      );

      startBackgroundSync(env.container);
      await _settle();

      expect(_paths(env.adapter), isEmpty);
    });

    test('an unauthenticated push stops the chain — no pull is attempted', () async {
      // `TOKEN_INVALID` is terminal (`05` §5.1): it is not `TOKEN_EXPIRED`, so no refresh is
      // attempted and the credential is finished. A pull would only repeat the same 401.
      final pushed = Completer<void>();
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/auth/me')) return jsonBody(200, _user());
        if (options.path.contains('/sync/push')) {
          if (!pushed.isCompleted) pushed.complete();
          return _problem(401, 'TOKEN_INVALID');
        }
        return _emptyPull();
      });

      startBackgroundSync(env.container);

      await _reached(pushed, 'the push');
      await _settle();

      expect(_paths(env.adapter), ['/auth/me', '/sync/push']);
    });

    test('a transient push failure does not stop the pull', () async {
      // **The distinction the orchestration exists to make.** `503` leaves the rows `PENDING`
      // and the outbox overlay preserves the local write intent, so a fresh round is strictly
      // better than none. Treating every push failure as terminal would leave a driver whose
      // depot Wi-Fi hiccuped with yesterday's round all day.
      final pulled = Completer<void>();
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/auth/me')) return jsonBody(200, _user());
        if (options.path.contains('/sync/push')) {
          return _problem(503, 'SERVICE_UNAVAILABLE');
        }
        if (!pulled.isCompleted) pulled.complete();
        return _emptyPull();
      });

      startBackgroundSync(env.container);

      await _reached(pulled, 'the pull');
      await _settle();

      expect(_paths(env.adapter), ['/auth/me', '/sync/push', '/sync/pull']);
    });

    test('the session subscription is established synchronously, before any await', () async {
      // **The M4 ordering, carried through M9.4's rewrite.** `_restoreThenSync` is `async`,
      // so everything up to its first `await` runs in the calling turn — and that includes
      // the `container.read(sessionProvider)` inside `startSessionRestoration`. If a later
      // edit moved that read after an `await`, `changes()` — a broadcast stream with no
      // replay — would emit into a stream nobody is listening to, and the device would sit on
      // the login screen holding a valid refresh token.
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/auth/me')) return jsonBody(200, _user());
        if (options.path.contains('/sync/push')) return _pushAccepted();
        return _emptyPull();
      });

      expect(
        env.container.exists(sessionProvider),
        isFalse,
        reason: 'nothing has read it yet — otherwise the assertion below proves nothing',
      );

      startBackgroundSync(env.container);

      // **No `await` between the line above and this one**, so this observes the state of the
      // container in the same turn the chain was started.
      expect(env.container.exists(sessionProvider), isTrue);

      // And the consequence, behaviourally: a listener attached *after* the chain started —
      // as the first frame attaches listeners after `runApp` returns — still receives the
      // restored session.
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
      await _settle();
    });
  });
}
