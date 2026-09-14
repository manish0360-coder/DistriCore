import '../../core/failure.dart';
import 'login_state.dart';

/// A [Failure] becomes something a person standing in a market can act on.
///
/// **Client-owned prose, keyed on `code`.** `05` §5 says `title` and `detail` may be
/// reworded without breaking a client, so a screen that rendered the server's `detail`
/// would be a screen a copy-edit can change — and, for an unrecognised code, a screen that
/// shows whatever the server happened to put there. That is the "raw problem details"
/// exposure this avoids.
///
/// The one exception is `VALIDATION_FAILED`, where `05` §5.4 defines `errors[]` as
/// field-level messages written *for the user*. Using one of those is reading a documented
/// user-facing contract, not echoing a diagnostic.
///
/// `Failure` is sealed, so this switch is exhaustive at compile time: a new member fans out
/// here rather than silently falling into a default.
String messageForFailure(Failure failure, {required LoginMode mode}) => switch (failure) {
      Offline() => 'No connection. Check your signal and try again.',
      Unauthenticated() => 'Your session has ended. Please sign in again.',
      MalformedResponse() =>
        'The server sent something we could not read. Try again in a moment.',
      // Distinct from `MalformedResponse` on purpose (see that type's own doc): the chain
      // did not verify, which is worth saying plainly rather than folding into "try again".
      CertificateRejected() =>
        "Can't verify this is the right server. Contact the office if this continues.",
      StorageFull() => failure.message,
      Refused(:final code) => _refusal(code, mode, const []),
      ProblemFailure(:final code, :final errors) => _refusal(code, mode, errors),
    };

String _refusal(String code, LoginMode mode, List<FieldError> errors) => switch (code) {
      // --- requesting a code -------------------------------------------------------
      'OTP_RATE_LIMITED' =>
        'Too many code requests. Wait a few minutes before trying again.',

      // --- verifying a code --------------------------------------------------------
      'OTP_INVALID' => 'That code is not correct.',
      'OTP_EXPIRED' => 'That code has expired. Ask for a new one.',
      'OTP_ATTEMPTS_EXCEEDED' =>
        'Too many incorrect attempts. Ask for a new code.',

      // --- either path -------------------------------------------------------------
      //
      // **Says which credential, never which half was wrong.** The server is deliberate
      // about this — `authenticate_password` raises the identical error for an unknown
      // number and a wrong password — and a client that distinguished them would hand back
      // the account-enumeration oracle the server just refused to be.
      'INVALID_CREDENTIALS' => switch (mode) {
          LoginMode.otp => 'That phone number or code was not accepted.',
          LoginMode.password => 'Incorrect phone number or password.',
        },
      'ACCOUNT_INACTIVE' => 'This account has been deactivated. Contact the office.',
      'VALIDATION_FAILED' => _firstFieldMessage(errors) ?? 'Check what you entered and try again.',

      // An unrecognised code is a client that is older than the server. Say something true
      // and unhelpful rather than something specific and wrong.
      _ => 'Sign-in failed. Try again, or contact the office if it keeps happening.',
    };

String? _firstFieldMessage(List<FieldError> errors) {
  for (final error in errors) {
    if (error.message.isNotEmpty) return error.message;
  }
  return null;
}
