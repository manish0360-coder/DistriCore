/// P-4: **the device clock labels; it never orders or expires.**
///
/// A phone's clock is wrong more often than anyone expects — manually set, drifting after
/// a flat battery, or shifted by a timezone the user changed while travelling. `05` C-5
/// already forbids using it as a sync cursor. This type exists so that every remaining use
/// is written down and injectable, rather than `DateTime.now()` scattered through the app
/// where it cannot be found or faked.
///
/// **Server time is authoritative wherever both exist.** M9's `server_time` replaces this
/// for cursors; until then nothing in M8 may compare two device timestamps to decide order.
abstract interface class Clock {
  /// The device's idea of now, in UTC. Suitable for *display* and for labelling a capture.
  DateTime nowUtc();
}

final class SystemClock implements Clock {
  const SystemClock();

  @override
  DateTime nowUtc() => DateTime.now().toUtc();
}

/// Injected by tests so a date rollover cannot decide whether the suite passes.
/// TD-31 is four instances of exactly that defect, on the other side of the wire.
final class FixedClock implements Clock {
  const FixedClock(this._instant);
  final DateTime _instant;

  @override
  DateTime nowUtc() => _instant;
}
