/// **The FR-IAM-016 offline window** (M8 §8.3, frozen at §14.12 D-D1…D-D3).
///
/// A pure predicate over three values, two of which the **server** authored. It imports
/// nothing — no Flutter, no Drift, no clock — so the rule that decides whether a device
/// unlocks can be read and tested in isolation, which is the whole reason it is a type and
/// not four lines inside a restorer.
///
/// **P-4 and what this does and does not buy.** [issuedAt] and [expiresAt] come from the
/// refresh token's `iat` and `exp` claims, so the *anchor* is server-issued and cannot be
/// moved by touching the device's date settings. The `now` handed to [permits] is still the
/// device clock — measuring elapsed real time offline is not possible without one — so the
/// honest statement of the residual risk is:
///
/// * Clock moved **forward** → the window closes early. Fail-closed, harmless.
/// * Clock moved **backward** → the window appears fresher and access is extended.
///
/// That second case is inherent to any offline expiry and is **not** claimed to be solved
/// here. What D-D1 removes is the larger failure: an anchor the device itself wrote, which
/// could be edited without any clock change at all.
final class OfflineWindow {
  const OfflineWindow({
    required this.issuedAt,
    required this.expiresAt,
    required this.maxOffline,
  });

  /// Server-issued `iat` of the refresh token currently held.
  final DateTime issuedAt;

  /// Server-issued `exp` of the same token.
  final DateTime expiresAt;

  /// `DISTRICORE_OFFLINE_WINDOW_DAYS` (D-D2). Default 7 days, OI-5.
  final Duration maxOffline;

  /// How long the credential itself is good for — `05` §7.2's *"bounded by refresh-token
  /// validity"*, computed from the token rather than assumed to be 30 days.
  Duration get credentialLife => expiresAt.difference(issuedAt);

  /// `min(configured window, credential life)`.
  ///
  /// The ceiling is in the predicate rather than assumed away because it stops binding the
  /// moment someone lowers `DISTRICORE_REFRESH_TOKEN_DAYS` below the window — at which point
  /// a device would otherwise keep unlocking against a credential the server has already
  /// stopped honouring.
  Duration get effective => credentialLife < maxOffline ? credentialLife : maxOffline;

  /// **Strictly less than. Equality denies** (§14.12.2).
  ///
  /// A boundary that admits `==` is a boundary chosen by accident, and this one is a
  /// security parameter.
  bool permits(DateTime now) {
    final elapsed = now.difference(issuedAt);

    // **Negative elapsed time is not a state that can honestly occur**: it says the device
    // believes it is earlier than the moment the server issued the token. Denying is the
    // conservative reading of the predicate, not a tamper-detection mechanism — no such
    // mechanism is claimed, and none is frozen.
    if (elapsed.isNegative) return false;

    return elapsed < effective;
  }
}
