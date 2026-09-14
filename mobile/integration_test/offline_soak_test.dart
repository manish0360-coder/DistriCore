/// **The 8-hour offline soak — `02` NFR-OFF-001, M8 §10 task 10, the M8→M9 gate's last open
/// half.**
///
/// `02` NFR-OFF-001, verbatim: *"`S2` and `S3` MUST remain fully functional for a complete
/// working day with no connectivity."* `02` §21.2 names the method in six words: *"Soak test:
/// 8 hours offline at representative transaction volume."* `M8_Design_Review` §12 self-critique
/// item 3 recorded that this was *"specified and not designed"* — this file is that design,
/// closing the gap named there and at §5.6.3.
///
/// ## Why this is not `sync_reconnect_test.dart` (B1) run longer
///
/// B1 proves reconnection is **fast** once it happens — a device already offline, queued, and
/// then timed back onto the network. This proves something earlier in the day: that the app
/// stays **usable** for the entire offline stretch *before* any reconnection is attempted. They
/// are different claims (FR-SYN-010 vs NFR-OFF-001) with different methods, and this file
/// borrows B1's wiring — the same `_wire` shape, the same radio-off probe, the same
/// `--keep-app-running` dependency — rather than re-deriving it.
///
/// ## The three phases
///
/// ```
/// GATE_PHASE=arm     radio ON     authenticate, pull cache (customers + assigned deliveries)
/// GATE_PHASE=run      radio OFF    inject ~200 operations paced over 8 real hours
/// GATE_PHASE=verify   radio ON     reconnect; real SyncRound/SyncScheduler; confirm clean
/// ```
///
/// Three `flutter drive` invocations because the runner must change the radio state *between*
/// them and Dart cannot toggle a radio (the same reason B1 is three phases, not one). Unlike
/// B1, the radio does not move mid-phase here: `run` is offline for its entire 8 hours, and
/// reconnection is a clean phase boundary rather than a timed event inside the measurement,
/// because this file has nothing to time — it has 8 hours of writes to prove, not a stopwatch
/// on the reconnection itself.
///
/// ## Volume, pacing and the two write paths
///
/// ~200 operations is the same DR-8 derivation B1 uses (`01` NFR-4: 10,000 lines/day ÷ 50
/// devices), paced across 8 real hours — 144 seconds apart by construction (`_soakDuration ÷
/// _operations`, not a restated constant that could drift from it). Every operation is one of
/// the two write paths that exist on a device today: `OutboxCustomerRepository.recordVisit`
/// (unbounded — a visit carries no per-customer uniqueness, `04` T-visit, so the seeded
/// customers are cycled exactly as B1 cycles them) or `OutboxDeliveryRepository.complete`
/// (bounded — a delivery is terminal once completed, `Delivery.canComplete` goes false, so only
/// the assigned-and-dispatched set found in `arm` is available and the run falls back to visits
/// once it is exhausted).
///
/// **Precondition this file cannot satisfy itself:** at least one delivery must be dispatched
/// and assigned to the seeded salesman before `arm` runs, or the delivery path has nothing to
/// exercise. `scripts/seed-b1.sh` deliberately seeds customers only — its own comment explains
/// why: a delivery completion needs *"a real assigned delivery in the right state, which means
/// seeding orders and dispatch as well"*, a workflow this file does not script. `arm` fails
/// loudly rather than silently soaking visits only if none is found — an anti-vacuity guard,
/// the same shape `outbox_storage_full_test.dart` uses for its own ballast. Seed one by hand
/// against the dev stack: create an order for a customer in the B1 zone, invoice it, then
/// dispatch the resulting delivery to `B1_PHONE` — three ordinary web-admin actions, not a new
/// script.
///
/// ## Device
///
/// **Rehearsable on the AVD; only a physical-device run is authoritative.** `M8_Design_Review`
/// §10 states task 10's gate differently from every other row in that table on purpose:
/// *"Measured on a real device, not assumed."* Running this file end to end on
/// `emulator-5554` proves the harness itself is correct — the mechanics, the pacing, the
/// assertions — and does **not** close NFR-OFF-001 or move **TD-45**. Both close only on the
/// authoritative run recorded at `M8_Design_Review` §5.6.3, which must name a physical device.
///
/// ## What this file does not attempt
///
/// **NFR-OFF-004** (three days' local storage capacity without sync) is a separate, larger
/// claim and a separate, larger soak. It is not folded in here, and is recorded as its own
/// follow-up at `M8_Design_Review` §5.6.3 rather than silently claimed as covered by one
/// 8-hour run.
library;

import 'package:districore/app/bootstrap.dart';
import 'package:districore/app/config.dart';
import 'package:districore/app/providers.dart';
import 'package:districore/app/sync_scheduler.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/identity/platform_secure_storage.dart';
import 'package:districore/data/identity/secure_token_store.dart';
import 'package:districore/domain/delivery/delivery.dart';
import 'package:districore/domain/visit/visit_outcome.dart';
import 'package:districore/features/customers/customer_providers.dart';
import 'package:districore/features/deliveries/delivery_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'support/device_outbox.dart';

/// Which phase is running.
const String _phase = String.fromEnvironment('GATE_PHASE', defaultValue: 'arm');

/// The derived DR-8 device-day. **A sizing input, never an assertion** — same status B1 gives
/// the identical number.
const int _operations = int.fromEnvironment('SOAK_OPERATIONS', defaultValue: 200);

/// `02` §21.2's own method names 8 hours. Overridable so a rehearsal can compress both this and
/// `_operations` together and still pace realistically — the authoritative run uses the default.
const int _durationMinutes = int.fromEnvironment('SOAK_DURATION_MINUTES', defaultValue: 8 * 60);
final Duration _soakDuration = Duration(minutes: _durationMinutes);

/// Exact, not approximate: the loop's own arithmetic is the source of truth for the spacing
/// rather than a restated constant that could drift from it. 8h ÷ 200 = 144s by construction.
final Duration _operationInterval = Duration(
  microseconds: _soakDuration.inMicroseconds ~/ _operations,
);

/// Seeded by `scripts/seed-b1.sh`. Acceptance credentials on a local dev stack, never secrets.
const String _phone = String.fromEnvironment('SOAK_PHONE', defaultValue: '+919876500001');
const String _password =
    String.fromEnvironment('SOAK_PASSWORD', defaultValue: 'b1-acceptance-only');

/// `02` NFR-PER-002: *"S2 order capture actions MUST respond within 500ms, bounded by local
/// storage and independent of network state."* Both write paths this file exercises are S2
/// writes, and P-2 is that neither ever awaits the network — so a local commit that misses this
/// bound is a regression in the write path, not a symptom of being offline.
const int _localWriteBoundMs = 500;

/// How long `verify` waits for the drained outbox before failing. Generous relative to B1's
/// 8-minute ceiling because this phase reconnects a full day's volume, not one probe.
const Duration _verifyCeiling = Duration(minutes: 10);

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'offline soak — $_phase',
    (tester) async {
      switch (_phase) {
        case 'arm':
          await _arm();
        case 'run':
          await _run();
        case 'verify':
          await _verify();
        default:
          fail('unknown GATE_PHASE "$_phase" — expected arm, run or verify');
      }
    },
    // Defensive, not load-bearing. `IntegrationTestWidgetsFlutterBinding` already exempts
    // itself from `flutter test`'s ordinary widget-test timeout — B1's own 8-minute wait
    // needed no override — but nothing in this repository has run one `testWidgets` body for
    // 8 real hours before, so the ceiling is stated rather than assumed.
    timeout: const Timeout(Duration(hours: 9)),
  );
}

// ---------------------------------------------------------------------------- the harness

void _emit(String line) {
  // ignore: avoid_print — stdout is the evidence channel every device gate here uses.
  print('GATE:soak $line');
}

/// A container wired exactly as `bootstrap` wires it, against the **real** base URL this build
/// was compiled with — same shape as B1's `_wire`, minus the response interceptor B1 needs for
/// its own timing and this file does not.
Future<({ProviderContainer container, AppDatabase database})> _wire() async {
  final config = AppConfig.fromEnvironment();
  final database = await openGateDatabase();
  final container = buildRootContainer(
    config: config,
    tokens: await SecureTokenStore.open(const PlatformSecureStorage()),
    database: database,
  );
  _emit('phase=$_phase base_url=${config.baseUrl}');
  return (container: container, database: database);
}

Future<int> _pendingCount(ProviderContainer container) async {
  final depth = await container.read(outboxRepositoryProvider).depth();
  return depth.fold((count) => count, (_) => -1);
}

// -------------------------------------------------------------------------------- phase: arm

/// Authenticate for real, pull the cache, and confirm both write paths have something to
/// exercise. Establishes the cached identity `run` and `verify` restore offline (the same
/// property B1's `online` phase exists for).
Future<void> _arm() async {
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
  expect(pulled.isOk, isTrue, reason: 'the first pull failed; there is nothing to soak against');

  final customers = await env.container.read(customerCacheProvider).read();
  expect(customers, isNotEmpty, reason: 'the pull returned no customers. See sync_reconnect_test '
      'for the zone-assignment precondition this shares with B1');

  final round = await env.container.read(deliveryRepositoryProvider).assignedToMe();
  final deliveries = round.fold((r) => r.rows, (_) => const <Delivery>[]);
  final dispatched = deliveries.where((d) => d.canComplete).length;

  // **The anti-vacuity guard for the delivery path.** A soak that happens to have zero
  // dispatched deliveries would silently fall back to visits for all 200 operations and prove
  // nothing about `OutboxDeliveryRepository.complete` — failing here, before any of the 8
  // hours is spent, is far cheaper than discovering it at the end of `run`.
  expect(
    dispatched,
    greaterThan(0),
    reason: 'no dispatched deliveries are assigned to $_phone. The delivery write path has '
        'nothing to exercise. Dispatch at least one delivery to this salesman first: create an '
        'order for a customer in the B1 zone, invoice it, then dispatch the resulting delivery '
        '— see this file\'s own doc comment for why no script does this automatically',
  );

  _emit('armed customers=${customers.length} deliveries_assigned=${deliveries.length} '
      'deliveries_dispatched=$dispatched operations_planned=$_operations '
      'interval_s=${_operationInterval.inSeconds} duration_s=${_soakDuration.inSeconds}');
}

// -------------------------------------------------------------------------------- phase: run

/// Radio must already be OFF — the Makefile toggles it before this phase, the same division of
/// labour B1 uses because Dart cannot toggle a radio itself. Injects [_operations] real writes,
/// paced across [_soakDuration], alternating the two existing offline write paths.
Future<void> _run() async {
  final env = await _wire();

  final customers = await env.container.read(customerCacheProvider).read();
  expect(customers, isNotEmpty, reason: 'run GATE_PHASE=arm first');

  final round = await env.container.read(deliveryRepositoryProvider).assignedToMe();
  final dispatched = round.fold(
    (r) => r.rows.where((d) => d.canComplete).toList(),
    (_) => const <Delivery>[],
  );
  expect(
    dispatched,
    isNotEmpty,
    reason: 'no dispatched deliveries are visible offline. arm already checked this online; '
        'if it passed then and fails now, the cache did not carry the assignment through the '
        'pull — a cache-shape regression, not a seeding gap',
  );

  // **Prove the radio is off with a request that can actually fail** — B1's own guard, and
  // the same reason: an assertion that only counts local appends cannot distinguish "offline"
  // from "never tried to sync", and AVDs are documented to route around `svc wifi/data
  // disable` often enough that this has to be checked, not assumed.
  final probe = await env.container.read(syncRoundProvider).run();
  expect(
    probe.isOk,
    isFalse,
    reason: 'a sync round SUCCEEDED with the radio supposedly off. Try `adb shell cmd '
        'connectivity airplane-mode enable`. Continuing from here would soak a device that '
        'was never actually offline, and NFR-OFF-001 would be unproven by this run',
  );

  final customerRepository = env.container.read(customerRepositoryProvider);
  final deliveryRepository = env.container.read(deliveryRepositoryProvider);

  var deliveriesCompleted = 0;
  var visitsRecorded = 0;
  var deliveryQueueIndex = 0;
  final started = DateTime.now();

  for (var index = 0; index < _operations; index += 1) {
    final iterationStart = DateTime.now();

    // Roughly one delivery completion in three while any dispatched delivery remains; every
    // other operation, and every operation once the assigned set is exhausted, is a visit.
    // Deliveries are consumed — `canComplete` goes false once completed — so the split this
    // run actually achieves is reported at the end rather than asserted in advance.
    final useDelivery = index % 3 == 0 && deliveryQueueIndex < dispatched.length;

    final writeStart = DateTime.now();
    Duration writeLatency;
    if (useDelivery) {
      final delivery = dispatched[deliveryQueueIndex];
      deliveryQueueIndex += 1;
      final result = await deliveryRepository.complete(
        delivery: delivery,
        recipientName: 'Soak $index',
      );
      writeLatency = DateTime.now().difference(writeStart);
      expect(
        result.isOk,
        isTrue,
        reason: 'delivery completion $index failed while offline — NFR-OFF-001 requires the '
            'app to remain fully functional with no connectivity',
      );
      deliveriesCompleted += 1;
    } else {
      final customer = customers[index % customers.length];
      final result = await customerRepository.recordVisit(
        customer: customer,
        outcome: VisitOutcome.noOrder,
      );
      writeLatency = DateTime.now().difference(writeStart);
      expect(
        result.isOk,
        isTrue,
        reason: 'visit $index failed while offline — NFR-OFF-001 requires the app to remain '
            'fully functional with no connectivity',
      );
      visitsRecorded += 1;
    }

    // `02` NFR-PER-002, on the write this operation actually performed.
    expect(
      writeLatency.inMilliseconds,
      lessThanOrEqualTo(_localWriteBoundMs),
      reason: 'operation $index (${useDelivery ? "delivery" : "visit"}) took '
          '${writeLatency.inMilliseconds}ms, over the ${_localWriteBoundMs}ms NFR-PER-002 bound',
    );

    _emit('op=$index kind=${useDelivery ? "delivery" : "visit"} '
        'latency_ms=${writeLatency.inMilliseconds} deliveries=$deliveriesCompleted '
        'visits=$visitsRecorded elapsed_s=${DateTime.now().difference(started).inSeconds}');

    if (index < _operations - 1) {
      final elapsedThisIteration = DateTime.now().difference(iterationStart);
      final remaining = _operationInterval - elapsedThisIteration;
      if (remaining > Duration.zero) {
        await Future<void>.delayed(remaining);
      }
    }
  }

  final pending = await _pendingCount(env.container);
  expect(pending, _operations, reason: 'the outbox does not hold the full soaked volume');
  expect(
    deliveriesCompleted,
    greaterThan(0),
    reason: 'the delivery path was never exercised despite arm finding dispatched deliveries — '
        'a scheduling defect in this file, not a seeding gap',
  );

  final totalElapsed = DateTime.now().difference(started);
  _emit('complete operations=$_operations deliveries=$deliveriesCompleted '
      'visits=$visitsRecorded elapsed_s=${totalElapsed.inSeconds} '
      'target_s=${_soakDuration.inSeconds}');
}

// ----------------------------------------------------------------------------- phase: verify

/// Radio must already be back ON — the Makefile toggles it before this phase. Reconnects
/// through the real, unmodified `SyncRound`/`SyncScheduler` and confirms the day's volume is
/// accounted for through the real `GET /sync/status` mechanism (`05` §11.5) — the server's
/// view, not only the device's own.
Future<void> _verify() async {
  final env = await _wire();

  final queued = await _pendingCount(env.container);
  expect(queued, greaterThan(0), reason: 'nothing is queued; run GATE_PHASE=run first');

  final restored = await startSessionRestoration(env.container);
  expect(
    restored.fold((session) => session, (_) => null),
    isNotNull,
    reason: 'no session was restored offline. Either GATE_PHASE=arm never ran, or the offline '
        'window has closed since it did',
  );

  final scheduler = env.container.read(syncSchedulerProvider);
  scheduler.start();
  _emit('cadence armed interval=${syncRetryInterval.inSeconds}s queued=$queued');

  final deadline = DateTime.now().add(_verifyCeiling);
  var beat = 0;
  while (DateTime.now().isBefore(deadline)) {
    final pending = await _pendingCount(env.container);
    if (pending == 0) break;
    await Future<void>.delayed(const Duration(seconds: 1));
    beat += 1;
    if (beat % 30 == 0) {
      _emit('draining ${beat}s pending=$pending stopped=${scheduler.isStopped}');
    }
  }

  final localPending = await _pendingCount(env.container);
  expect(
    localPending,
    0,
    reason: 'the local outbox did not drain to zero within ${_verifyCeiling.inMinutes} minutes '
        'of reconnection. pending=$localPending stopped=${scheduler.isStopped}',
  );

  // **The server's view, not just the device's own** (`05` §11.5). A local outbox reaching
  // zero proves every operation was sent and acknowledged; it does not by itself prove none of
  // them was rejected — a `REJECTED` row leaves the local outbox by the same path `ACCEPTED`
  // does, and only `GET /sync/status` distinguishes them.
  final status = await env.container.read(syncStatusRepositoryProvider).fetch();
  final serverStatus = status.fold((value) => value, (_) => null);
  expect(serverStatus, isNotNull, reason: 'GET /sync/status failed after the soak drained');
  _emit('server pending=${serverStatus!.pending} rejected=${serverStatus.rejected} '
      'last_sync_at=${serverStatus.lastSyncAt}');

  // `02` NFR-OFF-002/003: zero loss, zero duplicates. `ServerSyncStatus.isHealthy` is exactly
  // `pending == 0 && rejected == 0` — the same alarm, not queue-depth, reading `05` §11.5
  // gives that field everywhere else it is used.
  expect(
    serverStatus.isHealthy,
    isTrue,
    reason: '02 NFR-OFF-002/003: zero loss, zero duplicates. Server reports '
        'pending=${serverStatus.pending} rejected=${serverStatus.rejected} after the soak '
        'drained locally to zero',
  );

  _emit('verdict=PASS operations=$queued');
}
