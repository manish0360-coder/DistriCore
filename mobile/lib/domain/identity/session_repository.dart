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

  /// Sign out (C-7). Clears the tokens and the cached identity, then emits `null` through
  /// [changes] — which is what redirects the router; no screen navigates by hand.
  ///
  /// **Declared here because the presentation layer is the only caller there can be.**
  /// `TokenSessionRepository` has implemented it since M8 and
  /// `session_restoration_test.dart` has covered it since M8, but it was absent from this
  /// interface — so `features/` could not name it, and `M8_Design_Review` §3.1's
  /// *"Settings / about | Version, device id, sign out"* had no way to be built. A
  /// capability missing from the seam is a capability the product cannot ship.
  ///
  /// **The device id, the database key and unsent `outbox_operation` rows all survive**
  /// (§8.3, §8.4 / FR-IAM-009): signing out is not revocation, and a signed-out device
  /// still owes the business its work.
  Future<void> signOut();
}
