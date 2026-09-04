import '../../core/failure.dart';
import '../../core/result.dart';
import 'pull_service.dart';
import 'sync_engine.dart';

/// **One synchronisation round: push, then pull, and only one at a time** (TD-41, D-M9.4-7).
///
/// ## Why this type exists
///
/// The order `push → pull` is D-M9.4-7, and until now it lived inside a private function in
/// `app/bootstrap.dart` — reachable only by launching the app. TD-41 adds a second caller (a
/// repeating trigger, because `02` FR-SYN-017 requires that partial progress be *"retained
/// **and retried**"* and nothing retries today). A second caller re-stating the order would
/// duplicate the one rule this round exists to enforce, so the rule moves here and both
/// callers share it.
///
/// **Session restoration is deliberately not part of a round.** Restoration is a launch
/// concern: it reads the keystore and calls `/auth/me`. A trigger that fired this class would
/// re-authenticate on every attempt, which is why `bootstrap.dart`'s claim that a trigger can
/// simply *"call this function"* — meaning `startBackgroundSync` — was wrong. A round syncs;
/// it does not decide who is signed in.
///
/// ## The guard covers the **pair**, and that is the point
///
/// [SyncEngine.sync] is already single-flighted, and [PullService.pull] is not guarded at
/// all. Guarding only the push would still permit `pull(A)` to overlap `push(B)` — a pull
/// landing the server's stale view over work a concurrent push has not yet delivered, which
/// is the precise interleaving D-M9.4-7 exists to prevent. So the guard is here, around both
/// halves, and the engine keeps its own: `startup_refresh_race_test.dart` asserts it
/// *"asserts the property, not the caller"* — the engine is reachable from anywhere, so its
/// own guard stays exactly where it is.
///
/// A caller arriving mid-round receives **the future already in flight**, not a queued second
/// round. Queueing would turn a burst of *n* triggers into *n* sequential rounds, and every
/// round after the first is redundant by construction: the first already drained everything
/// committed before it began. It would also spend a device's `05` §13 budget — 60 pushes per
/// hour — on work that is known to be empty.
final class SyncRound {
  SyncRound({required SyncEngine engine, required PullService pull})
      : _engine = engine,
        _pull = pull;

  final SyncEngine _engine;
  final PullService _pull;

  /// The round in flight, or `null`. Same shape as [SyncEngine]'s guard and
  /// `RefreshInterceptor`'s: a third instance of an established idiom, not a new mechanism.
  Future<Result<SyncRoundReport>>? _running;

  /// Runs a round, or returns the one already running.
  ///
  /// `_run()` is `async`, so it suspends at its first `await` and returns before the
  /// assignment completes — which is what makes `??=` safe here rather than racy.
  /// `whenComplete` clears the field on **both** outcomes, so a failed round does not wedge
  /// the guard shut and strand every later attempt.
  Future<Result<SyncRoundReport>> run() =>
      _running ??= _run().whenComplete(() => _running = null);

  Future<Result<SyncRoundReport>> _run() async {
    final pushed = await _engine.sync();
    final pushFailure = pushed is Err<SyncReport> ? pushed.failure : null;

    // **`Unauthenticated` is terminal for the round.** The credential is finished; a pull
    // would only meet the same 401. Every other failure leaves the rows `PENDING` and the
    // outbox overlay preserves the local write intent, so a fresh round of server state is
    // strictly better than none — a driver whose depot Wi-Fi hiccuped should not be stuck
    // with yesterday's data all day.
    if (pushFailure is Unauthenticated) return Err(pushFailure);

    final pulled = await _pull.pull();
    if (pulled is Err<PullReport>) return Err(pulled.failure);

    // **The pull succeeding does not make the round a success.** `bootstrap` discarded the
    // push outcome because nothing consumed it; TD-41's scheduler does — it decides whether
    // to back off — and reporting `Ok` after a failed push would reset a backoff that should
    // have grown. The request sequence is unchanged either way; only the verdict is.
    if (pushFailure != null) return Err(pushFailure);

    return Ok(
      SyncRoundReport(
        push: (pushed as Ok<SyncReport>).value,
        pull: (pulled as Ok<PullReport>).value,
      ),
    );
  }
}

/// What one complete round did. Constructed **only** when both halves succeeded, so neither
/// field is nullable and no caller has to decide what a `null` half would have meant.
final class SyncRoundReport {
  const SyncRoundReport({required this.push, required this.pull});

  final SyncReport push;
  final PullReport pull;

  @override
  String toString() => 'SyncRoundReport(push: $push, pull: $pull)';
}
