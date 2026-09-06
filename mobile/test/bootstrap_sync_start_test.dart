// TD-41 step 3 — the launch chain arms the cadence, and the cadence never re-authenticates.
//
// `startup_orchestration_test.dart` already pins the launch chain's **order** — restore, push,
// pull — and it keeps doing so; it is the regression net proving step 3's delegation to
// `SyncRound` changed no request the device makes. What is new here is the two properties that
// only exist because a repeating trigger now does:
//
//   **A6** the scheduler is armed *only* after restoration returned `Ok(session)`; and
//   **A7** a tick runs a round and **not** a session restoration.
//
// A7 is the correction to `bootstrap.dart`'s old claim that a trigger could simply "call this
// function". `startBackgroundSync` restores a session — a launch concern — so a trigger
// calling it would hit `/auth/me` every 60 seconds forever. The assertion is a count, because
// that is the shape the defect would take.
//
// **The cadence is observed through an injected `FakeTicker`**, not by waiting: "armed at 60 s"
// is the observable that distinguishes a started scheduler from a merely constructed one.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/app/bootstrap.dart';
import 'package:districore/app/config.dart';
import 'package:districore/app/providers.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';
import 'support/fake_ticker.dart';
import 'support/memory_database.dart';

const _baseUrl = 'https://api.test/api/v1';
const _clientUuid = '11111111-2222-4333-8444-555555555555';

final _queuedAt = DateTime.utc(2026, 9, 4, 8);

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

ResponseBody _pushAccepted() => jsonBody(202, {
      'server_time': '2026-09-04T09:00:00Z',
      'results': [
        {'client_uuid': _clientUuid, 'status': 'ACCEPTED'},
      ],
    });

/// Accepts **whatever the batch actually carried**, by echoing `client_uuid` back.
///
/// `05` §11.2 matches verdicts by key, not position. A canned response naming one fixed uuid
/// would leave every later row unmentioned — which `SyncEngine` correctly returns to `PENDING`
/// — so the queue would grow silently and a reader would wonder why. Echoing keeps the fixture
/// honest without weakening anything.
ResponseBody _pushEchoed(RequestOptions options) {
  final body = options.data! as Map<String, dynamic>;
  final operations = body['operations']! as List<dynamic>;
  return jsonBody(202, {
    'server_time': '2026-09-04T09:00:00Z',
    'results': [
      for (final operation in operations)
        {
          'client_uuid': (operation as Map<String, dynamic>)['client_uuid'],
          'status': 'ACCEPTED',
        },
    ],
  });
}

ResponseBody _emptyPull() => jsonBody(200, {
      'server_time': '2026-09-04T09:00:00Z',
      'has_more': false,
      'customers': {'updated': <dynamic>[], 'deactivated_ids': <dynamic>[]},
      'deliveries': {'updated': <dynamic>[]},
    });

/// A container wired exactly as `bootstrap` wires it, with **only the ticker replaced**.
///
/// Overriding `syncTickerProvider` rather than the scheduler is the point: the chain then arms
/// the *real* `syncSchedulerProvider`, built on the container's own `syncRoundProvider`, which
/// is the object the launch round also uses. Substituting the scheduler would have proved that
/// a scheduler the test built got armed — not that the app's did.
Future<
    ({
      ProviderContainer container,
      FakeAdapter adapter,
      FakeTicker ticker,
    })> _wire({
  required FutureOr<ResponseBody> Function(RequestOptions options, int callIndex) script,
  String? refreshToken = 'refresh-1',
  bool queueOperation = true,
}) async {
  final adapter = FakeAdapter(script);
  final ticker = FakeTicker();

  final tokens = FakeTokens(accessToken: null, refreshToken: refreshToken);
  final container = buildRootContainer(
    // Cold start: the access token is memory-only (§8.2), so after a restart there is none.
    config: AppConfig.parse(_baseUrl),
    tokens: tokens,
    database: memoryIdentity().db,
    overrides: [
      syncTickerProvider.overrideWithValue(ticker),
      // **Both Dio instances, not just `raw`.** D-B2 gives `/auth/refresh` a structurally
      // separate client, and `ApiClient.raw` exposes only the main one — so a fake adapter
      // installed through `raw` leaves the refresh client on Dio's **default, real-network**
      // adapter. A refresh then leaves for api.test, fails as a connection error, and is
      // invisible to `FakeAdapter`: the fixture reports "no refresh was attempted" when one
      // was, and the suite quietly makes a real network call. `refresh_interceptor_test.dart`
      // has always wired both, which is why it never saw this.
      apiClientProvider.overrideWithValue(
        ApiClient(
          baseUrl: _baseUrl,
          tokens: tokens,
          dio: Dio()..httpClientAdapter = adapter,
          refreshDio: Dio()..httpClientAdapter = adapter,
        ),
      ),
    ],
  );
  addTearDown(container.dispose);

  if (queueOperation) {
    await container.read(outboxRepositoryProvider).append(
          clientUuid: _clientUuid,
          operationType: 'DELIVERY_COMPLETE',
          clientCreatedAt: _queuedAt,
          payload: <String, Object?>{'delivery_id': 3312, 'recipient_name': 'Sharma ji'},
        );
  }

  return (container: container, adapter: adapter, ticker: ticker);
}

Future<void> _settle() async {
  for (var turn = 0; turn < 25; turn += 1) {
    await Future<void>.delayed(Duration.zero);
  }
}

/// Waits for [done], draining the event loop, and **fails loudly** if it never becomes true.
///
/// **Use this, not [_settle], to wait for something that must happen.** A fixed number of
/// turns is a guess about how many hops a chain takes; restore → push → pull takes more than
/// 25, and a test that guesses low does not fail honestly — it proceeds against a chain that
/// has not finished, and then reports whatever second-order damage that causes. `_settle` is
/// only correct for the opposite claim: draining turns to establish that something has *not*
/// happened and will not.
Future<void> _until(bool Function() done, String what) async {
  for (var turn = 0; turn < 2000; turn += 1) {
    if (done()) return;
    await Future<void>.delayed(Duration.zero);
  }
  throw StateError('$what never happened');
}

List<String> _paths(FakeAdapter adapter) =>
    [for (final request in adapter.requests) request.path];

int _countOf(FakeAdapter adapter, String path) =>
    _paths(adapter).where((each) => each.endsWith(path)).length;

Future<void> _reached(Completer<void> gate, String what) => gate.future.timeout(
      const Duration(seconds: 5),
      onTimeout: () => throw StateError('$what never happened'),
    );

void main() {
  // A binding, for the `AppLifecycleListener` group only. `device_connection_test.dart` does
  // the same in a plain-`test()` file; it starts a binding without starting a widget tree.
  TestWidgetsFlutterBinding.ensureInitialized();

  group('A6 — the cadence is armed only when there is a session to sync', () {
    test('a restored session runs the launch round and then arms the cadence', () async {
      final pulled = Completer<void>();
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/auth/me')) return jsonBody(200, _user());
        if (options.path.contains('/sync/push')) return _pushAccepted();
        if (!pulled.isCompleted) pulled.complete();
        return _emptyPull();
      });
      await startBackgroundSync(env.container);

      await _reached(pulled, 'the pull');
      await _until(() => env.ticker.isArmed, 'the chain to arm the cadence');

      // The order `startup_orchestration_test.dart` pins, unchanged by the delegation.
      expect(_paths(env.adapter), ['/auth/me', '/sync/push', '/sync/pull']);
      expect(
        env.ticker.armed,
        const Duration(seconds: 60),
        reason: 'FR-SYN-017 requires the retry; an unarmed ticker is the launch-only '
            'behaviour TD-41 exists to remove',
      );
    });

    test('a failed restoration arms nothing', () async {
      final answered = Completer<void>();
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/auth/me')) {
          if (!answered.isCompleted) answered.complete();
          return _problem(500, 'INTERNAL');
        }
        return _problem(500, 'THIS_REQUEST_SHOULD_NOT_HAVE_BEEN_MADE');
      });
      await startBackgroundSync(env.container);

      await _reached(answered, '/auth/me');
      await _settle();

      expect(_paths(env.adapter), ['/auth/me']);
      expect(env.ticker.isArmed, isFalse);
    });

    test('a fresh install — Ok(null) — arms nothing', () async {
      // Restoration *succeeded* and found no credential. D-M9.4-7 stops the chain here, and
      // the trigger inherits that: waking a signed-out phone every minute to discover it still
      // has nothing to send is exactly the battery cost this design is trying not to spend.
      final env = await _wire(
        refreshToken: null,
        script: (options, _) async => _problem(500, 'THIS_REQUEST_SHOULD_NOT_HAVE_BEEN_MADE'),
      );
      await startBackgroundSync(env.container);
      await _settle();

      expect(_paths(env.adapter), isEmpty);
      expect(env.ticker.isArmed, isFalse);
    });

    test('a launch round that ends Unauthenticated arms nothing', () async {
      // Every tick would meet the same 401 and stop the scheduler on its first attempt.
      // Arming buys one wasted round and nothing else.
      //
      // **The bare push now attempts one recovery first.** A cold start has no access token
      // (§8.2), so the push carries no `Authorization` header and the 401 is `TOKEN_INVALID` —
      // which `RefreshInterceptor` treats as recoverable *only* in that shape. The refresh
      // fails here because this fixture answers `/auth/refresh` with a pull body carrying no
      // `access_token`, so the credential is still finished. The property under test is
      // unchanged: the cadence is not armed.
      final pushed = Completer<void>();
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/auth/me')) return jsonBody(200, _user());
        if (options.path.contains('/sync/push')) {
          if (!pushed.isCompleted) pushed.complete();
          return _problem(401, 'TOKEN_INVALID');
        }
        return _emptyPull();
      });
      await startBackgroundSync(env.container);

      await _reached(pushed, 'the push');
      await _settle();

      expect(_paths(env.adapter), ['/auth/me', '/sync/push', '/auth/refresh']);
      expect(env.ticker.isArmed, isFalse);
    });

    test('a transient launch failure still arms the cadence', () async {
      // **The case the cadence exists for.** A 503 leaves the rows PENDING; the device must
      // try again without being relaunched, which is precisely FR-SYN-017.
      final pulled = Completer<void>();
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/auth/me')) return jsonBody(200, _user());
        if (options.path.contains('/sync/push')) return _problem(503, 'SERVICE_UNAVAILABLE');
        if (!pulled.isCompleted) pulled.complete();
        return _emptyPull();
      });
      await startBackgroundSync(env.container);

      await _reached(pulled, 'the pull');
      await _until(() => env.ticker.isArmed, 'the chain to arm the cadence');

      expect(env.ticker.armed, const Duration(seconds: 60));
      expect(env.container.read(syncSchedulerProvider).isStopped, isFalse);
    });
  });

  group('A7 — a tick syncs, it does not re-authenticate', () {
    test('three ticks make three rounds and exactly one /auth/me', () async {
      var pushes = 0;
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/auth/me')) return jsonBody(200, _user());
        if (options.path.contains('/sync/push')) {
          pushes += 1;
          return _pushEchoed(options);
        }
        return _emptyPull();
      });
      await startBackgroundSync(env.container);

      // **The launch chain must finish before the first tick.** An armed ticker is the signal
      // that it did: `start()` is the last statement of the chain. Firing into an unarmed
      // ticker would mean the round never ran, and the counts below would be measuring a race
      // rather than the behaviour.
      await _until(() => env.ticker.isArmed, 'the launch round to arm the cadence');

      for (var tick = 0; tick < 3; tick += 1) {
        // Fresh work each time, so a tick has something to push and "three rounds" is not
        // satisfied by three empty drains.
        await env.container.read(outboxRepositoryProvider).append(
              clientUuid: '2222222$tick-2222-4333-8444-555555555555',
              operationType: 'DELIVERY_COMPLETE',
              clientCreatedAt: _queuedAt,
              payload: <String, Object?>{'delivery_id': 40 + tick},
            );

        final before = pushes;
        env.ticker.fire();

        // `fire()` clears the pending tick and `_attempt` re-arms in its `finally`, so an
        // armed ticker again — with one more push behind it — is exactly "the round finished".
        await _until(
          () => pushes > before && env.ticker.isArmed,
          'tick ${tick + 1} to complete its round',
        );
      }

      expect(
        _countOf(env.adapter, '/auth/me'),
        1,
        reason: 'restoration is a launch concern. A trigger that re-restored would call '
            '/auth/me every 60 seconds for the life of the process — the defect the old '
            'bootstrap comment would have produced verbatim',
      );
      // One launch round plus three ticks.
      expect(pushes, 4);
      expect(_countOf(env.adapter, '/sync/pull'), 4);
    });
  });

  group('the lifecycle binding', () {
    test('binds the container scheduler and survives disposal', () {
      final container = buildRootContainer(
        config: AppConfig.parse(_baseUrl),
        tokens: FakeTokens(),
        database: memoryIdentity().db,
      );
      addTearDown(container.dispose);

      // Reading it twice must give one scheduler: two would be two cadences, and the one the
      // lifecycle resumed would not be the one the launch chain armed.
      expect(
        identical(
          container.read(syncSchedulerProvider),
          container.read(syncSchedulerProvider),
        ),
        isTrue,
      );

      final listener = bindSyncToAppLifecycle(container);
      addTearDown(listener.dispose);

      // **What this does *not* prove.** That Android actually invokes `onResume` on a real
      // resume is a device property; this asserts only that the binding is constructed against
      // the container's own scheduler and can be torn down. See TD-47 and B2/B3.
      expect(listener, isNotNull);
    });
  });
}
