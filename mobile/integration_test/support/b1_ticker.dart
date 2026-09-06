import 'package:districore/app/sync_scheduler.dart';

/// **A real cadence, observed** (B1, FR-SYN-010).
///
/// B1 must time **the shipped mechanism**, not a re-implementation of it. A test that called
/// `SyncRound.run()` on its own 60-second loop would measure a loop the test wrote; the
/// evidence would say nothing about `SyncScheduler`.
///
/// So this delegates every call to a real [TimerSyncTicker] — the cadence is genuine wall-clock
/// time — and only *records* when each tick fired. `syncTickerProvider` already exists as an
/// override seam, so nothing in production changes to make this possible.
///
/// **[lastTickAt] is `t0`.** The conservative definition, per the approved B1 plan: the device
/// clock at the last attempt *before* the one that succeeded. Reconnection necessarily happened
/// at or after that instant and strictly before the next tick, so
///
/// ```
/// lastTickAt <= reconnection < lastTickAt + syncRetryInterval <= the successful attempt
/// ```
///
/// and measuring from `lastTickAt` **overstates** elapsed-time-since-reconnection by up to one
/// full cadence. It charges the whole 60-second wait to the 120-second budget. A pass measured
/// this way satisfies FR-SYN-010 *a fortiori*; it can never flatter the result.
///
/// Both timestamps come from the device clock, so no host-to-device skew enters the number —
/// which is why the plan chose this over an `adb`-written marker file.
final class B1Ticker implements SyncTicker {
  B1Ticker({DateTime Function()? now}) : _now = now ?? DateTime.now;

  final SyncTicker _real = TimerSyncTicker();
  final DateTime Function() _now;

  /// When the most recent tick fired. `null` until the cadence has run once.
  DateTime? lastTickAt;

  /// When the tick *before* that fired.
  ///
  /// **This is the one the measurement needs.** The round that finally succeeds runs during
  /// `lastTickAt`, so timing from there would measure only how long the sync itself took —
  /// not the reconnection wait the requirement is about. The attempt before it is the last
  /// one that failed, and therefore the last instant at which the device was provably still
  /// offline.
  DateTime? previousTickAt;

  /// How many ticks have fired. Reported so the evidence shows how many attempts the
  /// measurement spans rather than implying there was exactly one.
  int ticks = 0;

  @override
  void schedule(Duration delay, void Function() onTick) {
    _real.schedule(delay, () {
      ticks += 1;
      previousTickAt = lastTickAt;
      lastTickAt = _now();
      onTick();
    });
  }

  @override
  void cancel() => _real.cancel();
}
