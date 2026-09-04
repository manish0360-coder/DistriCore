// TD-41 step 2 — the retry cadence, proven without waiting for it.
//
// **`SyncRound`, `SyncEngine` and `PullService` are all `final class`**, so none can be faked
// — the same constraint `startup_orchestration_test.dart` and `sync_round_test.dart` record.
// The scheduler is therefore driven with a real round over a scripted `FakeAdapter`, and the
// assertions are about the requests that reached the wire and the delay that was armed.
//
// **Time is injected, not waited for.** A test that proved "a further attempt happens within
// 60 seconds" by sleeping would take minutes and flake. `SyncTicker` exists for this, and
// `support/fake_ticker.dart` is its second implementation — which is what makes it a port
// rather than an unnecessary abstraction. It lives in `support/` because
// `bootstrap_sync_start_test.dart` needs the same fake, and two private copies would drift.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/app/bootstrap.dart';
import 'package:districore/app/config.dart';
import 'package:districore/app/providers.dart';
import 'package:districore/app/sync_scheduler.dart';
import 'package:districore/data/sync/sync_round.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';
import 'support/fake_ticker.dart';
import 'support/memory_database.dart';

const _baseUrl = 'https://api.test/api/v1';
const _clientUuid = '11111111-2222-4333-8444-555555555555';

final _queuedAt = DateTime.utc(2026, 9, 4, 8);

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

ResponseBody _emptyPull() => jsonBody(200, {
      'server_time': '2026-09-04T09:00:00Z',
      'has_more': false,
      'customers': {'updated': <dynamic>[], 'deactivated_ids': <dynamic>[]},
      'deliveries': {'updated': <dynamic>[]},
    });

Future<
    ({
      ProviderContainer container,
      FakeAdapter adapter,
      FakeTicker ticker,
      SyncScheduler scheduler,
    })> _wire({
  required FutureOr<ResponseBody> Function(RequestOptions options, int callIndex) script,
}) async {
  final adapter = FakeAdapter(script);
  final container = buildRootContainer(
    config: AppConfig.parse(_baseUrl),
    tokens: FakeTokens(),
    database: memoryIdentity().db,
  );
  addTearDown(container.dispose);
  container.read(apiClientProvider).raw.httpClientAdapter = adapter;

  final ticker = FakeTicker();
  final scheduler = SyncScheduler(
    round: SyncRound(
      engine: container.read(syncEngineProvider),
      pull: container.read(pullServiceProvider),
    ),
    ticker: ticker,
  );
  // A live cadence must not outlive its test.
  addTearDown(scheduler.dispose);

  return (container: container, adapter: adapter, ticker: ticker, scheduler: scheduler);
}

/// Seeds one `PENDING` row, so a round has real work.
///
/// **Without it the drain sends nothing** and every assertion below would pass against a
/// scheduler that never ran a round — a test that cannot fail.
Future<void> _queue(ProviderContainer container, String clientUuid) async {
  await container.read(outboxRepositoryProvider).append(
        clientUuid: clientUuid,
        operationType: 'DELIVERY_COMPLETE',
        clientCreatedAt: _queuedAt,
        payload: <String, Object?>{'delivery_id': 3312, 'recipient_name': 'Sharma ji'},
      );
}

List<String> _paths(FakeAdapter adapter) =>
    [for (final request in adapter.requests) request.path];

/// Lets the event loop finish an attempt started by a tick.
///
/// A tick is fire-and-forget by construction — a `Timer` callback cannot be awaited — so
/// draining turns after it is what turns *"has not happened yet"* into *"will not happen"*.
Future<void> _settle() async {
  for (var turn = 0; turn < 25; turn += 1) {
    await Future<void>.delayed(Duration.zero);
  }
}

/// A script that answers a whole round successfully.
FutureOr<ResponseBody> _healthy(RequestOptions options, int _) async =>
    options.path.contains('/sync/push') ? _pushAccepted() : _emptyPull();

void main() {
  group('SyncScheduler — the cadence (A1)', () {
    test('the interval fits inside the FR-SYN-010 budget, with room to sync', () {
      // Not decoration: this is the arithmetic the whole design rests on. 60 s to notice,
      // leaving 60 s of the 120 s budget for a push and a pull. A structural contract pins
      // the same relationship where `make verify` can see it.
      expect(syncRetryInterval, const Duration(seconds: 60));
      expect(syncRetryInterval * 2, lessThanOrEqualTo(const Duration(seconds: 120)));
    });

    test('start() arms the cadence but does not sync immediately', () async {
      // The launch chain has just run its own round; a second one here would spend a request
      // on a queue drained microseconds ago.
      final env = await _wire(script: _healthy);
      await _queue(env.container, _clientUuid);

      env.scheduler.start();
      await _settle();

      expect(_paths(env.adapter), isEmpty);
      expect(env.ticker.armed, const Duration(seconds: 60));
    });

    test('a tick runs exactly one round and re-arms at the same interval', () async {
      final env = await _wire(script: _healthy);
      await _queue(env.container, _clientUuid);

      env.scheduler.start();
      env.ticker.fire();
      await _settle();

      expect(_paths(env.adapter), ['/sync/push', '/sync/pull']);
      expect(
        env.ticker.armed,
        const Duration(seconds: 60),
        reason: 'the cadence must survive its own attempt; a scheduler that fires once and '
            'stops is the launch-only behaviour TD-41 removes, one tick later',
      );
      expect(env.ticker.isArmed, isTrue);
    });

    test('a failed attempt retries on the same fixed cadence, never a longer one', () async {
      // **FR-SYN-017: retained *and retried*.** And no backoff, deliberately: the 120 s budget
      // is the ceiling, so any growth past 60 s would put a reconnection that lands just after
      // a failed attempt outside the bound. Backing off further is only affordable with a
      // connectivity signal to reset it, which this milestone does not take.
      final env = await _wire(
        script: (options, _) async => options.path.contains('/sync/push')
            ? _problem(503, 'SERVICE_UNAVAILABLE')
            : _emptyPull(),
      );
      await _queue(env.container, _clientUuid);

      env.scheduler.start();

      for (var attempt = 0; attempt < 10; attempt += 1) {
        env.ticker.fire();
        await _settle();
        expect(
          env.ticker.armed,
          const Duration(seconds: 60),
          reason: 'after ${attempt + 1} consecutive failures the delay must not have grown',
        );
        expect(env.ticker.armed, lessThan(const Duration(seconds: 120)));
      }

      // Ten pushes and ten pulls: the row stayed PENDING through every 503 and was re-sent
      // each time — FR-SYN-017's "never restarted from the beginning".
      expect(_paths(env.adapter).where((path) => path.endsWith('/sync/push')).length, 10);
      expect(env.scheduler.isStopped, isFalse);
    });
  });

  group('SyncScheduler — resume (A1)', () {
    test('resumed() syncs immediately instead of waiting out the cadence', () async {
      final env = await _wire(script: _healthy);
      await _queue(env.container, _clientUuid);

      env.scheduler.start();
      env.scheduler.resumed();
      await _settle();

      expect(_paths(env.adapter), ['/sync/push', '/sync/pull']);
      expect(env.ticker.armed, const Duration(seconds: 60));
    });

    test('resumed() before start() does nothing', () async {
      final env = await _wire(script: _healthy);
      await _queue(env.container, _clientUuid);

      env.scheduler.resumed();
      await _settle();

      expect(_paths(env.adapter), isEmpty);
    });
  });

  group('SyncScheduler — one attempt at a time (A3)', () {
    test('a resume during an in-flight attempt is dropped, not queued', () async {
      final release = Completer<void>();
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/sync/push')) {
          await release.future;
          return _pushAccepted();
        }
        return _emptyPull();
      });
      await _queue(env.container, _clientUuid);

      env.scheduler.start();
      env.ticker.fire();

      // Three resumes land while the push is held open.
      env.scheduler.resumed();
      env.scheduler.resumed();
      env.scheduler.resumed();

      release.complete();
      await _settle();

      expect(
        _paths(env.adapter),
        ['/sync/push', '/sync/pull'],
        reason: 'four triggers must produce one round; queueing them would spend four of the '
            'sixty pushes an hour `05` §13 allows on three attempts that are empty by '
            'construction',
      );
      expect(env.ticker.schedules, 2, reason: 'armed once by start, once by the one attempt');
    });
  });

  group('SyncScheduler — terminal and disposal', () {
    test('an unauthenticated round stops the cadence for good', () async {
      // The credential is finished; retrying spends the `05` §13 backstop on a guaranteed 401.
      final env = await _wire(
        script: (options, _) async => options.path.contains('/sync/push')
            ? _problem(401, 'TOKEN_INVALID')
            : _emptyPull(),
      );
      await _queue(env.container, _clientUuid);

      env.scheduler.start();
      env.ticker.fire();
      await _settle();

      expect(env.scheduler.isStopped, isTrue);
      expect(env.ticker.isArmed, isFalse, reason: 'nothing may be armed after a stop');

      // And it stays stopped: a later resume must not revive it.
      env.scheduler.resumed();
      await _settle();

      expect(_paths(env.adapter), ['/sync/push']);
    });

    test('dispose() cancels the cadence and later ticks do nothing', () async {
      final env = await _wire(script: _healthy);
      await _queue(env.container, _clientUuid);

      env.scheduler.start();
      expect(env.ticker.isArmed, isTrue);

      env.scheduler.dispose();

      expect(env.ticker.isArmed, isFalse);

      // Even a resume after disposal is inert — a disposed scheduler holds a container that
      // may already be gone.
      env.scheduler.resumed();
      await _settle();

      expect(_paths(env.adapter), isEmpty);
    });
  });
}
