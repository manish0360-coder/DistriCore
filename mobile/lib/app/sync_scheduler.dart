import 'dart:async';

import '../core/failure.dart';
import '../data/sync/sync_round.dart';

/// **How often a device retries a round** (TD-41; `02` FR-SYN-010, FR-SYN-017).
///
/// FR-SYN-010 gives the whole operation **120 seconds from reconnection**. That budget is
/// spent twice over: once noticing there is a connection, and once actually syncing. Sixty
/// seconds is half of it, which leaves the other half for a push and a pull — at the DR-8
/// envelope a device's *entire typical day* is about 200 operations, and `05` §13 caps a
/// batch at 200, so a normal day is one push plus a few pull pages against a 30-second
/// per-request timeout.
///
/// **It is also exactly the `05` §13 ceiling of 60 pushes per device per hour**, which is the
/// upper bound on how fast this may go. A shorter interval would breach the rate limit in the
/// pathological case where every attempt has work and the server defers all of it.
///
/// A structural contract pins this at or under the 120-second budget; raising it past that is
/// a build failure, not a review comment.
const Duration syncRetryInterval = Duration(seconds: 60);

/// One-shot scheduling, injected.
///
/// **Why a port rather than a bare `Timer`:** the properties worth proving here are temporal
/// — *"a further attempt happens within 60 seconds"*, *"ten failures do not stretch that"* —
/// and a test that proves them by waiting is a test that takes ten minutes and flakes. The
/// alternative is `package:fake_async`, which arrives only as a transitive dependency of
/// `flutter_test`; `pubspec.yaml` already records why that is not acceptable (*"an imported
/// package must be a declared dependency, not a transitive one"*), and declaring it would be
/// a new dependency this milestone agreed not to take. Four lines of interface costs less
/// than either.
///
/// One-shot rather than periodic **because the scheduler re-arms itself after each attempt**.
/// A periodic timer would keep firing into a round that is still in flight.
abstract interface class SyncTicker {
  /// Runs [onTick] once after [delay], replacing any tick already pending.
  void schedule(Duration delay, void Function() onTick);

  /// Cancels a pending tick. Safe to call when none is armed.
  void cancel();
}

/// The real one. The only part of this file that touches wall-clock time.
final class TimerSyncTicker implements SyncTicker {
  Timer? _timer;

  @override
  void schedule(Duration delay, void Function() onTick) {
    _timer?.cancel();
    _timer = Timer(delay, onTick);
  }

  @override
  void cancel() {
    _timer?.cancel();
    _timer = null;
  }
}

/// **The retry trigger** (TD-41).
///
/// Before this existed, sync happened **once per process launch** and never again. `02`
/// FR-SYN-017 requires that partial progress be *"retained **and retried**"* — the retaining
/// half was built in M9.2, and nothing retried. This is the retry.
///
/// ## What this class deliberately does **not** do
///
/// **It does not detect reconnection, and no in-process mechanism can.** A connectivity event
/// reports *link* state, not reachability: a phone behind a captive portal reports connected
/// and cannot reach the server. The authoritative test of "reconnected" is a request that
/// succeeds, so the mechanism that discharges FR-SYN-010 is a bounded-latency *attempt*, and
/// a connectivity signal would be a battery optimisation layered on top. That is why this
/// milestone takes no new dependency.
///
/// **It does not stop when the app is backgrounded.** There is no `paused` handler here, and
/// its absence is a decision rather than an omission — please do not add one. Whether a Dart
/// timer survives backgrounding is Android's decision (Doze, App Standby); cancelling it here
/// as well would add a *second, self-inflicted* reason to miss the 120-second bound on top of
/// the one the OS already imposes. The cadence stops only when the app detaches or the
/// container is disposed.
///
/// **It does not make FR-SYN-010 satisfied.** The bound is *"sync **completes** within 2
/// minutes of reconnection"*; this bounds when an attempt *starts*. Completion at the DR-8
/// envelope over a real network is B1, and B1 is a timed measurement on a device or staging —
/// `02` NFR-PER-004 names the method itself: *"Timed sync at representative volume."* Until
/// that measurement exists, nothing here may be cited as discharging the requirement. The
/// background case is a separate, open specification gap (**TD-47**).
final class SyncScheduler {
  SyncScheduler({
    required SyncRound round,
    SyncTicker? ticker,
    Duration interval = syncRetryInterval,
  })  : _round = round,
        _ticker = ticker ?? TimerSyncTicker(),
        _interval = interval;

  final SyncRound _round;
  final SyncTicker _ticker;
  final Duration _interval;

  bool _started = false;
  bool _stopped = false;
  bool _inFlight = false;

  /// True once a round returned [Unauthenticated]. Terminal: see [_attempt].
  bool get isStopped => _stopped;

  /// Arms the cadence. **Does not sync immediately**, because the caller just did: the launch
  /// chain's own round is the first one, and attempting here as well would spend a request on
  /// a queue that was drained microseconds ago.
  void start() {
    if (_started || _stopped) return;
    _started = true;
    _arm();
  }

  /// The app returned to the foreground.
  ///
  /// Fires one attempt **now** rather than waiting out the remaining cadence. If the OS did
  /// suspend the timer while the app was away, this is the moment that fact becomes visible,
  /// and waiting a further 60 seconds after the user is already looking at the screen would
  /// be the worst possible time to be patient.
  void resumed() {
    if (!_started || _stopped) return;
    unawaited(_attempt());
  }

  /// Stops the cadence for good. Called when the app detaches, and from the container's
  /// `onDispose` so a test cannot leak a live timer into the next one.
  void dispose() {
    _started = false;
    _ticker.cancel();
  }

  void _arm() {
    if (!_started || _stopped) return;
    _ticker.schedule(_interval, () => unawaited(_attempt()));
  }

  Future<void> _attempt() async {
    if (!_started || _stopped) return;

    // **Dropped, never queued.** A trigger arriving mid-round is redundant by construction:
    // the round in flight already drained everything committed before it began. Queueing
    // would turn a burst of n triggers into n sequential rounds and spend a device's 60
    // pushes an hour on attempts that are empty by construction. [SyncRound] guards itself
    // as well; this flag is the scheduler's own bookkeeping, so that one attempt re-arms the
    // cadence exactly once.
    if (_inFlight) return;
    _inFlight = true;
    _ticker.cancel();

    try {
      final result = await _round.run();
      final failure = result.fold<Failure?>((_) => null, (value) => value);

      // **`Unauthenticated` is the one terminal outcome.** The credential is finished and no
      // amount of waiting revives it; retrying would spend the `05` §13 backstop of 1,000
      // requests an hour on a guaranteed 401. Every other failure is retried on the same
      // fixed cadence — including `StorageFull`, because space can be freed by the user and a
      // device that stopped trying would never notice that it had been.
      if (failure is Unauthenticated) _stopped = true;
    } finally {
      _inFlight = false;
      // **Re-armed in `finally`, so a throw cannot silently end the cadence.** A defect that
      // escapes `SyncRound` should surface as an unhandled async error *and* leave the device
      // still syncing; losing the cadence for the life of the process would reproduce exactly
      // the launch-only behaviour this class removes. `_arm` is a no-op once stopped.
      _arm();
    }
  }
}
