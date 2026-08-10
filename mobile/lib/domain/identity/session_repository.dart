import '../../core/result.dart';
import 'session.dart';

/// What the app can ask about the signed-in user.
///
/// **An interface in `domain`, implemented in `data`** (M8 §9). This is the seam that lets
/// the domain compile with no Flutter, no Dio and no Drift — and it is the only thing the
/// presentation layer is allowed to see (§2.2).
abstract interface class SessionRepository {
  /// The current session, or `null` when signed out. **Reads local state only** — never
  /// the network, so the app decides what to draw with no signal (P-2).
  Result<Session?> current();

  /// Emits on sign-in and sign-out so the router can redirect without polling.
  Stream<Session?> changes();
}
