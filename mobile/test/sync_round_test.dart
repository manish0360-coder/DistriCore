// TD-41 step 1 — the round, in isolation from the launch chain.
//
// **`SyncEngine` and `PullService` are `final class`**, so neither can be faked —
// `startup_orchestration_test.dart` records the same constraint and the same remedy. The
// round is therefore driven with real collaborators over a scripted `FakeAdapter`, and every
// assertion is about **the sequence of requests that reached the wire**. That is the stronger
// assertion anyway: a test double would prove the round called two objects, not that the
// device made two requests in that order.
//
// **What this file adds that `startup_orchestration_test.dart` does not.** That suite already
// pins push-before-pull through `bootstrap`, and it keeps doing so — it becomes the
// regression net for step 3, when `_restoreThenSync` starts delegating here. What is new is
// the guard: nothing anywhere has ever asserted that two triggers produce one round, because
// until TD-41 there was only ever one trigger. The ordering cases below are stated at *this*
// unit because this is the unit that now owns the rule; without them, moving the rule out of
// `bootstrap` would move it out of test coverage too.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/app/bootstrap.dart';
import 'package:districore/app/config.dart';
import 'package:districore/app/providers.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/data/sync/sync_round.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';
import 'support/memory_database.dart';

/// A path prefix on purpose: the API is mounted at `/api/v1/`, so a base URL without one
/// would not reach an endpoint on a real deployment.
const _baseUrl = 'https://api.test/api/v1';

/// P-6: one operation, one `client_uuid`, never regenerated.
const _first = '11111111-2222-4333-8444-555555555555';
const _second = '66666666-7777-4888-8999-000000000000';

final _queuedAt = DateTime.utc(2026, 9, 4, 8);

ResponseBody _problem(int status, String code) => jsonBody(status, {
      'code': code,
      'status': status,
      'title': code,
      'detail': 'scripted',
      'errors': <dynamic>[],
    });

/// `05` §11.2 — every operation in the batch settled, so the drain makes exactly one request
/// and the engine's progress check ends the loop.
ResponseBody _pushAccepted(List<String> clientUuids) => jsonBody(202, {
      'server_time': '2026-09-04T09:00:00Z',
      'results': [
        for (final clientUuid in clientUuids)
          {'client_uuid': clientUuid, 'status': 'ACCEPTED'},
      ],
    });

/// `05` §11.1 — a single terminal page, so the pull makes exactly one request.
ResponseBody _emptyPull() => jsonBody(200, {
      'server_time': '2026-09-04T09:00:00Z',
      'has_more': false,
      'customers': {'updated': <dynamic>[], 'deactivated_ids': <dynamic>[]},
      'deliveries': {'updated': <dynamic>[]},
    });

/// A container wired exactly as `bootstrap` wires it, plus the round under test.
///
/// The round is built by hand rather than read from a provider because TD-41 step 4 is what
/// adds `syncRoundProvider`; this step must not touch `providers.dart`. It is built from the
/// **container's own** engine and pull service, so the collaborators are the objects the app
/// would really use.
Future<({ProviderContainer container, FakeAdapter adapter, SyncRound round})> _wire({
  required FutureOr<ResponseBody> Function(RequestOptions options, int callIndex) script,
}) async {
  final adapter = FakeAdapter(script);

  final container = buildRootContainer(
    config: AppConfig.parse(_baseUrl),
    // An access token is present: a round is not a launch, and nothing here should provoke a
    // refresh. A `/auth/me` or `/auth/refresh` in any assertion below would be a defect.
    tokens: FakeTokens(),
    // **One database**, exactly as `bootstrap` opens one.
    database: memoryIdentity().db,
  );
  addTearDown(container.dispose);

  container.read(apiClientProvider).raw.httpClientAdapter = adapter;

  return (
    container: container,
    adapter: adapter,
    round: SyncRound(
      engine: container.read(syncEngineProvider),
      pull: container.read(pullServiceProvider),
    ),
  );
}

/// Seeds one `PENDING` row.
///
/// **Without a queued row the drain returns `Ok` having sent nothing**, and every ordering
/// assertion below would pass against a round that never pushed at all — a test that cannot
/// fail, which is worse than one that does.
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

void main() {
  // **`test`, not `testWidgets`.** There is no widget here, and `testWidgets` runs the body
  // inside `FakeAsync`, which intercepts `scheduleMicrotask` as well as `Timer` and only
  // flushes on a `pump()`. With nothing to pump, an awaited round would never resume.

  group('SyncRound — A4, the order the round owns', () {
    test('pushes before it pulls', () async {
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/sync/push')) return _pushAccepted([_first]);
        return _emptyPull();
      });
      await _queue(env.container, _first);

      final result = await env.round.run();

      // D-M9.4-7, at the unit that now owns it. Local durable writes reach the server before
      // a pull can overwrite the cache that describes them.
      expect(_paths(env.adapter), ['/sync/push', '/sync/pull']);
      expect(result.isOk, isTrue);
      expect(result.fold((report) => report.push.acknowledged, (_) => -1), 1);
    });

    test('an unauthenticated push stops the round — no pull is attempted', () async {
      // `TOKEN_INVALID` is terminal (`05` §5.1): it is not `TOKEN_EXPIRED`, so no refresh is
      // attempted and the credential is finished. A pull would only repeat the same 401.
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/sync/push')) return _problem(401, 'TOKEN_INVALID');
        return _emptyPull();
      });
      await _queue(env.container, _first);

      final result = await env.round.run();

      expect(_paths(env.adapter), ['/sync/push']);
      expect(
        result.fold((_) => null, (failure) => failure),
        isA<Unauthenticated>(),
        reason: 'the scheduler reads this verdict to decide it must stop retrying; anything '
            'else would leave it hammering a credential the server has finished with',
      );
    });

    test('a transient push failure still pulls, and still reports the failure', () async {
      // **The distinction the round exists to make.** `503` leaves the rows `PENDING`, so a
      // fresh round of server state is strictly better than none — but the round is *not* a
      // success, and saying otherwise would reset a backoff that should have grown. The
      // request sequence is identical to a healthy round; only the verdict differs.
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/sync/push')) {
          return _problem(503, 'SERVICE_UNAVAILABLE');
        }
        return _emptyPull();
      });
      await _queue(env.container, _first);

      final result = await env.round.run();

      expect(_paths(env.adapter), ['/sync/push', '/sync/pull']);
      expect(result.isOk, isFalse);
      expect(
        result.fold((_) => null, (failure) => failure),
        isNot(isA<Unauthenticated>()),
        reason: 'a 503 is retryable; classifying it as terminal would stop the scheduler',
      );
    });
  });

  group('SyncRound — A3, one round at a time', () {
    test('three concurrent calls collapse into a single round', () async {
      // The push is held open so the second and third calls arrive **while the first round is
      // genuinely in flight**. Without the gate the first would complete before the others
      // were made, and the assertion would pass against a class with no guard at all.
      final release = Completer<void>();
      final env = await _wire(script: (options, _) async {
        if (options.path.contains('/sync/push')) {
          await release.future;
          return _pushAccepted([_first]);
        }
        return _emptyPull();
      });
      await _queue(env.container, _first);

      final first = env.round.run();
      final second = env.round.run();
      final third = env.round.run();

      // The sharpest statement of the guard: not three equal results, the *same future*.
      expect(identical(first, second), isTrue);
      expect(identical(first, third), isTrue);

      release.complete();
      await Future.wait([first, second, third]);

      // One round, not three. Three would have spent three of the 60 pushes `05` §13 allows
      // a device in an hour, on two attempts that were empty by construction.
      expect(_paths(env.adapter), ['/sync/push', '/sync/pull']);
    });

    test('the guard releases: a later round runs in full', () async {
      final env = await _wire(script: (options, callIndex) async {
        if (options.path.contains('/sync/push')) {
          // Settle whichever row this batch carried; the second round carries the second.
          return _pushAccepted(callIndex == 0 ? [_first] : [_second]);
        }
        return _emptyPull();
      });

      await _queue(env.container, _first);
      await env.round.run();

      // A second operation, so the second round has real work. Reusing an empty queue would
      // prove only that a pull happened, not that a whole round did.
      await _queue(env.container, _second);
      await env.round.run();

      expect(
        _paths(env.adapter),
        ['/sync/push', '/sync/pull', '/sync/push', '/sync/pull'],
        reason: 'the guard must clear on completion; a round that never releases it would '
            'strand every attempt the scheduler makes for the life of the process',
      );
    });

    test('a failed round still releases the guard', () async {
      // **The defect `whenComplete` exists to prevent.** Clearing the field only on success
      // would mean the first offline attempt wedges the guard shut, and a device that lost
      // signal once never syncs again until it is relaunched — which is precisely the
      // launch-only behaviour TD-41 is removing.
      final env = await _wire(script: (options, callIndex) async {
        if (options.path.contains('/sync/push')) {
          return callIndex == 0
              ? _problem(503, 'SERVICE_UNAVAILABLE')
              : _pushAccepted([_first]);
        }
        return _emptyPull();
      });
      await _queue(env.container, _first);

      final failed = await env.round.run();
      expect(failed.isOk, isFalse);

      final recovered = await env.round.run();

      expect(recovered.isOk, isTrue);
      expect(
        _paths(env.adapter),
        ['/sync/push', '/sync/pull', '/sync/push', '/sync/pull'],
        reason: 'the row stayed PENDING after the 503, so the retry re-sent it — FR-SYN-017: '
            'partial progress is retained and retried, never restarted from the beginning',
      );
    });
  });
}
