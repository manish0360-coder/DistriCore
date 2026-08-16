import 'package:flutter/foundation.dart';

/// Which credential the user is offering. OTP is the field default; password is the
/// internal fallback for staff who have one (M8 §8.1).
enum LoginMode { otp, password }

/// How far through the OTP exchange we are. The code field does not exist until the server
/// has accepted a request — offering it earlier would invite a user to type a code that was
/// never sent.
enum LoginStage { phone, code }

/// Everything the login screen draws itself from.
///
/// **No credential is a field here, and that is deliberate.** The code and the password live
/// in `TextEditingController`s for as long as they are being typed and are passed to the
/// controller as arguments. A state object is the thing most likely to end up in a log line,
/// a crash report or a `toString()` during debugging — FR-IAM-015 — so the safest design is
/// one that has nothing to leak. [phone] is here because it is an identity the user can see
/// on screen, and because verification must be sent the same string the request was.
@immutable
final class LoginState {
  const LoginState({
    this.mode = LoginMode.otp,
    this.stage = LoginStage.phone,
    this.phone = '',
    this.busy = false,
    this.message,
    this.attemptsAllowed,
    this.secondsRemaining = 0,
  });

  final LoginMode mode;
  final LoginStage stage;
  final String phone;

  /// A request is in flight. The single source of the duplicate-submission guard: a second
  /// OTP costs an SMS and consumes one of three in the server's fifteen-minute window.
  final bool busy;

  /// User-visible, client-owned prose. Never a raw server `detail`.
  final String? message;

  /// From the challenge. Safe to show: it is `settings.OTP_MAX_ATTEMPTS`, a constant, not
  /// something derived from whether the account exists.
  final int? attemptsAllowed;

  /// Counts down to zero. **A budget, not an expiry** (P-4) — reaching zero re-enables
  /// "Send a new code" and nothing else. The server decides whether a code is still valid.
  final int secondsRemaining;

  bool get canResend => secondsRemaining <= 0;

  LoginState copyWith({
    LoginMode? mode,
    LoginStage? stage,
    String? phone,
    bool? busy,
    String? message,
    bool clearMessage = false,
    int? attemptsAllowed,
    bool clearChallenge = false,
    int? secondsRemaining,
  }) =>
      LoginState(
        mode: mode ?? this.mode,
        stage: stage ?? this.stage,
        phone: phone ?? this.phone,
        busy: busy ?? this.busy,
        message: clearMessage ? null : (message ?? this.message),
        attemptsAllowed: clearChallenge ? null : (attemptsAllowed ?? this.attemptsAllowed),
        secondsRemaining: clearChallenge ? 0 : (secondsRemaining ?? this.secondsRemaining),
      );

  /// Shape only. There is no credential in this object, and there must not be one added
  /// without revisiting this method.
  @override
  String toString() =>
      'LoginState(mode: $mode, stage: $stage, busy: $busy, hasMessage: ${message != null})';
}
