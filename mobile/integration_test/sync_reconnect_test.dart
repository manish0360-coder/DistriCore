/// **B1 — FR-SYN-010 acceptance, on a device against a real server.**
///
/// `02` FR-SYN-010, verbatim and unweakened:
///
/// > *"Full sync of a typical daily volume MUST complete within 2 minutes of reconnection at
/// > the DR-8 envelope."*
///
/// `02` NFR-PER-004 names the method — *"Timed sync at representative volume"* — and this is
/// that measurement. **It is the only evidence that can discharge FR-SYN-010.** TD-41 shipped a
/// mechanism that bounds when an attempt *starts*; the requirement is about when a sync
/// *completes*, and no unit test or structural contract can stand in for a stopwatch on a
/// device talking to a real server over a real socket.
///
/// ## The three phases, and why there are three
///
/// ```
/// GATE_PHASE=online    network up    log in, pull, cache an identity and customers
/// GATE_PHASE=queue     network DOWN  queue N real VISIT_CREATE operations
/// GATE_PHASE=measure   down -> up    time the reconnection to a completed round
/// ```
///
/// They are three `flutter drive` invocations because the runner must change the radio state
/// *between* them, and Dart cannot toggle a radio. `--keep-app-running` preserves the app's
/// data directory across invocations, which is the same property the kill and storage gates
/// depend on; under `flutter test` the package is uninstalled at teardown and phase two would
/// open an empty database.
///
/// **The `online` phase is not setup for its own sake.** `session_restorer.dart` answers a
/// cold start from the cached identity and *"makes no request at all"* inside the offline
/// window — which is what lets `measure` restore a session with the radio off, reach
/// `Ok(session)`, and arm the cadence. Without a prior online login there is no cached
/// identity, restoration falls through to the server, returns `Err(Offline)`, and the
/// scheduler is never armed. The phase order is load-bearing.
///
/// ## What is measured, and what is deliberately not
///
/// `t0` is the **conservative** definition approved in the B1 plan: the device clock at the
/// last attempt that failed, before the one that succeeded. Reconnection happened at or after
/// `t0` and strictly before the next attempt, so the measured interval **overstates**
/// elapsed-time-since-reconnection by up to one full cadence. It charges the whole 60-second
/// wait to the 120-second budget. A pass measured this way satisfies FR-SYN-010 *a fortiori*.
/// Both timestamps come from the device clock, so no host-to-device skew enters the number.
///
/// `t1` is the completion of **the whole `SyncRound`** — push drained *and* a pull finished —
/// not the moment a request was sent.
///
/// **Volume is recorded, not asserted.** The ~200 operations are a derivation from DR-8
/// (`01` NFR-4: 10,000 lines/day ÷ 50 devices), and `01` §16.3 **CF-4** still lists the DR-8
/// envelope itself as unconfirmed, *"test targets remain provisional"*. The 200–400 KB pull
/// figure is `03` §369's sizing commentary, not a requirement in `02`. So this file asserts
/// **one** thing — the 120-second budget — and reports every other quantity as measured fact.
///
/// **`x86_64` emulator only — TD-45.** Reproduced in the evidence line so no reader has to
/// remember it.
library;

import 'package:dio/dio.dart';
import 'package:districore/app/bootstrap.dart';
import 'package:districore/app/config.dart';
import 'package:districore/app/providers.dart';
// For `syncRetryInterval` only — the cadence the evidence reports, read from the shipping
// constant rather than restated here, so the two cannot drift.
import 'package:districore/app/sync_scheduler.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/identity/platform_secure_storage.dart';
import 'package:districore/data/identity/secure_token_store.dart';
import 'package:districore/domain/customer/customer.dart';
import 'package:districore/domain/visit/visit_outcome.dart';
import 'package:districore/features/customers/customer_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'support/b1_ticker.dart';
import 'support/device_outbox.dart';

/// Which phase is running.
const String _phase = String.fromEnvironment('GATE_PHASE', defaultValue: 'online');

/// The derived DR-8 device-day. **A sizing input, never an assertion.**
const int _operations = int.fromEnvironment('B1_OPERATIONS', defaultValue: 200);

/// Seeded by `scripts/seed-b1.sh`. Acceptance credentials on a local dev stack, never secrets.
const String _phone = String.fromEnvironment('B1_PHONE', defaultValue: '+919876500001');
const String _password =
    String.fromEnvironment('B1_PASSWORD', defaultValue: 'b1-acceptance-only');

/// `02` FR-SYN-010, in milliseconds. **The only pass condition in this file.**
const int _budgetMs = 120 * 1000;

/// How long to wait for the runner to restore the radio and the cadence to carry a round.
const Duration _measureCeiling = Duration(minutes: 8);

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('B1 — FR-SYN-010: $_phase', (tester) async {
    switch (_phase) {
      case 'online':
        await _online();
      case 'queue':
        await _queue();
      case 'measure':
        await _measure();
      default:
        fail('unknown GATE_PHASE "$_phase" — expected online, queue or measure');
    }
  });
}

// ---------------------------------------------------------------------------- the harness

/// Counts **successful responses only**, and the distinction is not pedantry.
///
/// This implements `onResponse`, and Dio routes any non-2xx to `onError` — so a request that
/// was made, reached the server and came back `401` increments **nothing** here. A zero
/// therefore means *"no 2xx response"*, never *"no request was attempted"*. Reading it the
/// second way cost a diagnosis: a phase-3 run showed `push=0` and was described as a cadence
/// that never reached the wire, when in fact every attempt reached the server and was refused.
///
/// Test-only: installed on the container's own `ApiClient`, changing nothing.
final class _Wire {
  int pull2xx = 0;
  int pullBytes = 0;
  int push2xx = 0;

  Interceptor get interceptor => InterceptorsWrapper(
        onResponse: (response, handler) {
          final path = response.requestOptions.path;
          if (path.contains('/sync/pull')) {
            pull2xx += 1;
            pullBytes += _sizeOf(response);
          } else if (path.contains('/sync/push')) {
            push2xx += 1;
          }
          handler.next(response);
        },
      );

  /// `Content-Length` when the server sent one; otherwise the decoded body's length, which is
  /// an approximation and is labelled as measured-on-device rather than as the wire size.
  static int _sizeOf(Response<dynamic> response) {
    final declared = response.headers.value(Headers.contentLengthHeader);
    final parsed = declared == null ? null : int.tryParse(declared);
    if (parsed != null) return parsed;
    return response.data.toString().length;
  }
}

/// A container wired exactly as `bootstrap` wires it, against the **real** base URL this build
/// was compiled with. No adapter is substituted: B1 is worthless without a real socket.
Future<({ProviderContainer container, _Wire wire, AppDatabase database})> _wire({
  B1Ticker? ticker,
}) async {
  final config = AppConfig.fromEnvironment();
  final database = await openGateDatabase();
  final container = buildRootContainer(
    config: config,
    // The production keystore, opened exactly as `bootstrap` opens it. `SecureTokenStore`
    // hydrates before anything can hold it (§8.2), which is why this is awaited here and
    // not built lazily.
    tokens: await SecureTokenStore.open(const PlatformSecureStorage()),
    database: database,
    overrides: [
      if (ticker != null) syncTickerProvider.overrideWithValue(ticker),
    ],
  );
  final wire = _Wire();
  container.read(apiClientProvider).raw.interceptors.add(wire.interceptor);

  // ignore: avoid_print
  print('GATE:b1 phase=$_phase base_url=${config.baseUrl}');
  return (container: container, wire: wire, database: database);
}

void _emit(String line) {
  // ignore: avoid_print — stdout is the evidence channel every device gate here uses.
  print('GATE:b1 $line');
}

// ------------------------------------------------------------------------- phase: online

/// Authenticate for real, and let the pull fill the cache.
///
/// Establishes the two things `measure` cannot run without: a refresh token in the keystore
/// and a **cached identity row**, which is what lets a later cold start restore a session with
/// no network.
Future<void> _online() async {
  await deleteDeviceDatabase();
  final env = await _wire();

  final session = await env.container
      .read(authServiceProvider)
      .loginWithPassword(phone: _phone, password: _password);

  expect(
    session.isOk,
    isTrue,
    reason: 'login failed against ${AppConfig.fromEnvironment().baseUrl}. Check the stack is '
        'up, `scripts/seed-b1.sh` has run, Caddy is serving 10.0.2.2 and the dev CA reached '
        'this build through --dart-define=DISTRICORE_DEV_CA_B64',
  );

  final pulled = await env.container.read(pullServiceProvider).pull();
  expect(pulled.isOk, isTrue, reason: 'the first pull failed; there is nothing to visit');

  final customers = await env.container.read(customerCacheProvider).read();
  expect(
    customers,
    isNotEmpty,
    reason: 'the pull returned no customers. `visible_customers` scopes a SALESMAN to '
        'zone__assigned_user, so the seeded zone is probably not assigned to this user',
  );

  _emit('online customers_cached=${customers.length} '
      'pull_pages=${env.wire.pull2xx} pull_bytes=${env.wire.pullBytes}');
  _emit('online pull_size_target=200000..400000B (03 §369 sizing guide, not a pass condition)');
}

// -------------------------------------------------------------------------- phase: queue

/// Queue the device-day, offline, **through the real repository**.
///
/// `OutboxCustomerRepository.recordVisit` mints the `client_uuid` and builds the frozen
/// `VISIT_CREATE` payload. Appending rows by hand here would queue operations the app does not
/// produce, and B1 would measure a shape the server has never been asked to accept.
Future<void> _queue() async {
  final env = await _wire();

  final customers = await env.container.read(customerCacheProvider).read();
  expect(customers, isNotEmpty, reason: 'run GATE_PHASE=online first');

  final repository = env.container.read(customerRepositoryProvider);
  for (var index = 0; index < _operations; index += 1) {
    // Cycled, so the seed needs fewer customers than operations. `04` T-visit has no
    // per-customer uniqueness — two calls on one shop are two visits, not a replay — so every
    // row is still a legitimate, server-acceptable operation.
    final Customer customer = customers[index % customers.length];
    final recorded = await repository.recordVisit(
      customer: customer,
      outcome: VisitOutcome.noOrder,
    );
    expect(recorded.isOk, isTrue, reason: 'queueing operation $index failed');
  }

  final pending = await _pendingCount(env.container);
  expect(pending, _operations, reason: 'the outbox does not hold the volume to be measured');

  // **Prove the radio is off with a request that can actually fail.**
  //
  // The assertion here used to be `pushResponses == 0`, which this phase can never violate:
  // it only appends to the local outbox and never syncs, so the count is zero by
  // construction. It would have passed with the radio fully on, and the `offline=true` line
  // below would then be a false entry in the evidence record. A guard that cannot fail is
  // worse than no guard, because it is read as one.
  //
  // `pushResponses` could not be repaired in place either: a failed request produces no
  // response, so the interceptor's `onResponse` never fires and the count stays zero whether
  // the radio is off or the server is merely unreachable. It is not a discriminator at all.
  final probe = await env.container.read(syncRoundProvider).run();
  expect(
    probe.isOk,
    isFalse,
    reason: 'a sync round SUCCEEDED with the radio supposedly off. `svc wifi/data disable` '
        'did not cut this emulator off from the host — AVDs frequently route around it. '
        'Try `adb shell cmd connectivity airplane-mode enable`. Continuing from here would '
        'time a reconnection that never happened',
  );

  // A failed round reclaims its batch (`SyncEngine._run`), so the volume the measure phase
  // starts from is intact rather than stranded `IN_FLIGHT`.
  expect(
    await _pendingCount(env.container),
    _operations,
    reason: 'the failed probe must leave every queued row PENDING',
  );

  _emit('queued=$pending offline=true probe=round-failed-as-expected');
}

// ------------------------------------------------------------------------ phase: measure

/// The measurement.
Future<void> _measure() async {
  final ticker = B1Ticker();
  final env = await _wire(ticker: ticker);

  final queued = await _pendingCount(env.container);
  expect(queued, greaterThan(0), reason: 'nothing is queued; run GATE_PHASE=queue first');

  // Restoration must succeed **from the cache, with the radio off**. This is the property
  // `session_restorer.dart` documents and the reason the online phase exists.
  final restored = await startSessionRestoration(env.container);
  expect(
    restored.fold((session) => session, (_) => null),
    isNotNull,
    reason: 'no session was restored offline. Either the online phase never ran, or the '
        'offline window has closed since it did',
  );

  // **`t0` — the last provably-offline attempt.** One real round through the shipped object,
  // expected to fail while the radio is still down.
  final beforeReconnect = await env.container.read(syncRoundProvider).run();
  expect(
    beforeReconnect.isOk,
    isFalse,
    reason: 'a round succeeded before reconnection: the radio was still up, so there is no '
        'reconnection to measure and the number would be meaningless',
  );
  var t0 = DateTime.now();

  // **The failure type, not just the fact of failure.** `Offline` is the expected shape and
  // means the cadence will keep retrying. `Unauthenticated` is terminal — `SyncScheduler`
  // stops for good on it — so a probe that failed that way would explain a silent run
  // completely, and without this field the two are indistinguishable in the evidence.
  final probeFailure = beforeReconnect.fold<Object?>((_) => null, (failure) => failure);
  _emit('t0=${t0.millisecondsSinceEpoch} reason=offline-attempt-failed '
      'failure=${probeFailure.runtimeType}');

  // The shipped cadence, running for real.
  final scheduler = env.container.read(syncSchedulerProvider);
  scheduler.start();
  _emit('cadence armed interval=${syncRetryInterval.inSeconds}s '
      'stopped=${scheduler.isStopped}');

  final deadline = DateTime.now().add(_measureCeiling);
  final pullsBefore = env.wire.pull2xx;
  DateTime? t1;

  // **A heartbeat, because a silent wait is unreadable.** The first run of this phase produced
  // no `t1` and no explanation: the radio was provably restored and the server logged no
  // request, which left "the scheduler never ticked" and "it ticked but never reached the
  // wire" equally consistent with the evidence. One line a minute separates them live, and
  // costs a print.
  var beat = 0;
  while (DateTime.now().isBefore(deadline)) {
    await Future<void>.delayed(const Duration(seconds: 1));
    final pending = await _pendingCount(env.container);
    if (pending == 0 && env.wire.pull2xx > pullsBefore) {
      t1 = DateTime.now();
      break;
    }
    beat += 1;
    if (beat % 60 == 0) {
      _emit('waiting ${beat}s ticks=${ticker.ticks} pending=$pending '
          'push_2xx=${env.wire.push2xx} pull_2xx=${env.wire.pull2xx} '
          'stopped=${scheduler.isStopped}');
    }
  }

  if (t1 == null) {
    // **Everything the next diagnosis needs, before the assertion fires.** `ticks=0` means the
    // cadence never fired at all; `ticks>0` with `push=0` means it fired and no request reached
    // the wire; `stopped=true` means a round returned `Unauthenticated` and the scheduler shut
    // itself down by design. These are three different defects and the bare timeout message
    // distinguished none of them.
    _emit('timeout=${_measureCeiling.inMinutes}m ticks=${ticker.ticks} '
        'last_tick=${ticker.lastTickAt?.millisecondsSinceEpoch} '
        'prev_tick=${ticker.previousTickAt?.millisecondsSinceEpoch} '
        'pending=${await _pendingCount(env.container)} '
        'push_2xx=${env.wire.push2xx} '
        'pull_2xx=${env.wire.pull2xx} '
        'scheduler_stopped=${scheduler.isStopped} '
        'probe_failure=${probeFailure.runtimeType}');
  }

  expect(
    t1,
    isNotNull,
    reason: 'no complete round in ${_measureCeiling.inMinutes} minutes. Read the GATE:b1 '
        'timeout line above. ticks=0 is a cadence that never fired. scheduler_stopped=true is '
        'a terminal Unauthenticated — a credential fault, not a latency one. push_2xx=0 means '
        'no SUCCESSFUL response, NOT that nothing was attempted: this counter is blind to '
        'non-2xx, which Dio routes to onError, so a run that was refused 401 on every attempt '
        'looks identical here to one that never opened a socket. Separate the two from the '
        'server access log, never from this number. A candidate FR-SYN-010 failure is only a '
        'run where attempts reached the server, were accepted, and simply took too long',
  );

  // The last attempt *before* the successful one, if the cadence carried more than one.
  t0 = ticker.previousTickAt ?? t0;
  final elapsed = t1!.difference(t0);

  _emit('t1=${t1.millisecondsSinceEpoch} elapsed_ms=${elapsed.inMilliseconds}');
  _emit('operations=$queued ticks=${ticker.ticks} push_2xx=${env.wire.push2xx}');
  _emit('pull_pages=${env.wire.pull2xx - pullsBefore} '
      'pull_bytes=${env.wire.pullBytes}');
  _emit('device=x86_64-emulator-api34 (TD-45: arm64 and physical hardware unproven)');
  _emit('t0_basis=last-failed-attempt (conservative: includes the full cadence wait)');
  _emit('verdict=${elapsed.inMilliseconds <= _budgetMs ? "PASS" : "FAIL"} '
      'budget_ms=$_budgetMs');

  expect(
    elapsed.inMilliseconds,
    lessThanOrEqualTo(_budgetMs),
    reason: '02 FR-SYN-010: full sync of a typical daily volume must complete within 2 minutes '
        'of reconnection. Measured ${elapsed.inMilliseconds}ms from the last failed attempt '
        'to a completed round',
  );
}

// ------------------------------------------------------------------------------- helpers

/// **`depth()`, not `pending()`, and the difference matters here.**
///
/// The measure loop calls this once a second *inside the interval being timed*. `pending()`
/// loads and decodes every waiting row — 200 of them, every second — which is real work
/// competing with the sync it is supposed to be observing. `depth()` is the count *"without
/// loading them"* (`OutboxRepository`), so the observation stays cheap enough not to perturb
/// the measurement. A stopwatch that slows the thing it times reports its own overhead.
Future<int> _pendingCount(ProviderContainer container) async {
  final depth = await container.read(outboxRepositoryProvider).depth();
  return depth.fold((count) => count, (_) => -1);
}
