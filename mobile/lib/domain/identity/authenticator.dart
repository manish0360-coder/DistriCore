import '../../core/result.dart';
import 'otp_challenge.dart';
import 'session.dart';

/// The two sign-in paths as the **presentation layer** sees them (M8 §8.1).
///
/// `features/` may import `domain/` and `core/` and nothing else, so a screen cannot name
/// `AuthService` — which is the rule that keeps a login form from acquiring a `Dio`. This is
/// the interface it asks for instead; `data/identity/auth_service.dart` implements it and
/// the composition root decides which implementation a screen receives.
///
/// **Read-only in the same sense `SessionRepository` is**: every method here either fails or
/// results in a session being persisted and published by the implementation. There is no way
/// for a screen to install a session itself, so there is still exactly one source of truth
/// for who is signed in.
///
/// Method names match `AuthService`'s existing ones exactly. A port that renamed them would
/// buy nothing and would make the implementation harder to find from the interface.
abstract interface class Authenticator {
  /// Ask the server to send a code. See [OtpChallenge] for why the answer is uninformative.
  Future<Result<OtpChallenge>> requestOtp(String phone);

  /// Exchange a code for a session. On success the session is already published.
  Future<Result<Session>> verifyOtp({required String phone, required String code});

  /// Internal fallback (§8.1), for staff who have a password.
  Future<Result<Session>> loginWithPassword({
    required String phone,
    required String password,
  });
}
