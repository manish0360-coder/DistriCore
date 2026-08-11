/// What the API layer needs from the session, and nothing more.
///
/// Task 4 implements this over `flutter_secure_storage` and the Android Keystore (M8 §8.2).
/// Task 2 defines only the seam, so the interceptors can be built and tested now without
/// dragging sign-in, the offline window or secure storage into this milestone.
abstract interface class TokenStore {
  /// In memory only. Re-derived from the refresh token on cold start (§8.2).
  String? get accessToken;

  /// Platform keystore. `null` when signed out.
  String? get refreshToken;

  /// Generated once and stored in the keystore (§8.4, C-10, FR-IAM-009).
  String? get deviceId;

  /// Called after a successful refresh. The server **rotates** the refresh token, so the
  /// new one must replace the old — keeping the old is a guaranteed lockout on next use.
  Future<void> save({required String accessToken, required String refreshToken});

  /// The refresh chain is finished: sign out (C-7).
  Future<void> clear();
}
