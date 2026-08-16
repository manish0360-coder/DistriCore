/// What the server tells the client after accepting an OTP request (`05` §10.1).
///
/// **Says nothing about whether the phone is registered, and neither may any caller.**
/// `identity.services.request_otp` answers the same `202` either way — same shape, same
/// delay, no SMS for an unknown number — because FR-IAM-004 makes the endpoint deliberately
/// silent on account existence. A screen that branched on this would rebuild the enumeration
/// oracle the server is careful not to be.
///
/// Both fields are safe to display: [attemptsAllowed] is `settings.OTP_MAX_ATTEMPTS`, a
/// constant, not something derived from the account.
///
/// Lives in `domain/` rather than beside the parser because `features/` may see `domain/`
/// and never `data/` — the same reason `Session` is here and `UserDto` is not.
final class OtpChallenge {
  const OtpChallenge({
    required this.expiresInSeconds,
    required this.attemptsAllowed,
  });

  /// **A budget for a countdown, not an expiry the client may enforce.**
  ///
  /// P-4: the device clock labels; it never expires. When this runs out the client may only
  /// offer a new code — the server's `OTP_EXPIRED` remains the authority on whether a
  /// submitted code is still good.
  final int expiresInSeconds;

  final int attemptsAllowed;
}
