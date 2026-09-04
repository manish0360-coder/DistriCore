import 'package:districore/app/sync_scheduler.dart';

/// A [SyncTicker] under the test's control: records what was armed, fires on demand.
///
/// **This is why `SyncTicker` is a port rather than an abstraction for its own sake** — it has
/// a second implementation, and that implementation is what makes the cadence provable. The
/// properties worth asserting are temporal (*"a further attempt happens within 60 seconds"*,
/// *"ten failures do not stretch that"*), and a test that proved them by waiting would take
/// ten minutes and flake.
///
/// Shared by `sync_scheduler_test.dart` and `bootstrap_sync_start_test.dart`; a private copy
/// in each would be the same fake twice, and the second one would drift.
final class FakeTicker implements SyncTicker {
  /// The delay most recently armed, or `null` if nothing ever was.
  Duration? armed;

  /// How many times a tick was scheduled and cancelled. Counts, not just the latest state,
  /// because "armed exactly once per attempt" is itself an assertion.
  int schedules = 0;
  int cancels = 0;

  void Function()? _onTick;

  /// Whether a tick is currently pending.
  bool get isArmed => _onTick != null;

  @override
  void schedule(Duration delay, void Function() onTick) {
    schedules += 1;
    armed = delay;
    _onTick = onTick;
  }

  @override
  void cancel() {
    cancels += 1;
    _onTick = null;
  }

  /// Fires the pending tick, as a real timer would.
  ///
  /// Throws rather than silently doing nothing: a test that fires into an unarmed ticker is
  /// asserting against a cadence that is not running, and would pass for the wrong reason.
  void fire() {
    final tick = _onTick;
    if (tick == null) throw StateError('nothing was armed — the cadence is not running');
    _onTick = null;
    tick();
  }
}
