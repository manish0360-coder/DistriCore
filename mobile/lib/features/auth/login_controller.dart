import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth_providers.dart';
import 'login_messages.dart';
import 'login_state.dart';

final loginControllerProvider =
    NotifierProvider<LoginController, LoginState>(LoginController.new);

/// The login screen's decisions, with no widget in them.
///
/// **Every entry point begins `if (state.busy) return`.** That guard — not the disabled
/// button — is the duplicate-submission protection. A disabled button is a drawing; a second
/// tap can still arrive between the tap and the rebuild, and on the OTP path a duplicate
/// costs a real SMS and one of the three requests the server allows in fifteen minutes.
///
/// **No credential is ever stored here.** Codes and passwords arrive as arguments and leave
/// with the call. See [LoginState].
final class LoginController extends Notifier<LoginState> {
  Timer? _ticker;

  @override
  LoginState build() {
    ref.onDispose(_stopTicker);
    return const LoginState();
  }

  /// Ask for a code.
  ///
  /// **The phone number is trimmed and otherwise sent exactly as typed.**
  /// `identity/phone.py` canonicalises on both read and write — that module exists *because*
  /// the rule was once applied on read only, and a superuser created as `7903324153` could
  /// never sign in. Re-implementing it here would make a third copy, on the far side of a
  /// network boundary, where a divergence is silent. Non-emptiness is a UI affordance; the
  /// canonical form is an identity rule the server owns.
  Future<void> requestOtp(String rawPhone) async {
    if (state.busy) return;

    final phone = rawPhone.trim();
    if (phone.isEmpty) {
      state = state.copyWith(message: 'Enter your phone number.');
      return;
    }

    state = state.copyWith(busy: true, phone: phone, clearMessage: true);
    final result = await ref.read(authenticatorProvider).requestOtp(phone);

    result.fold(
      (challenge) {
        state = state.copyWith(
          busy: false,
          stage: LoginStage.code,
          attemptsAllowed: challenge.attemptsAllowed,
          secondsRemaining: challenge.expiresInSeconds,
          clearMessage: true,
        );
        _startTicker();
      },
      (failure) {
        state = state.copyWith(
          busy: false,
          message: messageForFailure(failure, mode: LoginMode.otp),
        );
      },
    );
  }

  /// Returns whether the code was accepted. **Nothing here navigates**: on success
  /// `AuthService` has already published the session and `router.dart`'s redirect moves the
  /// app. A second mechanism would be a second answer to "who is signed in".
  Future<bool> verifyOtp(String rawCode) async {
    if (state.busy) return false;

    final code = rawCode.trim();
    if (code.isEmpty) {
      state = state.copyWith(message: 'Enter the code we sent you.');
      return false;
    }

    state = state.copyWith(busy: true, clearMessage: true);
    // `state.phone`, not the field's current text: verification must present the same string
    // the challenge was issued against.
    final result =
        await ref.read(authenticatorProvider).verifyOtp(phone: state.phone, code: code);

    return result.fold(
      (_) {
        _stopTicker();
        state = state.copyWith(busy: false, clearMessage: true, clearChallenge: true);
        return true;
      },
      (failure) {
        state = state.copyWith(
          busy: false,
          message: messageForFailure(failure, mode: LoginMode.otp),
        );
        return false;
      },
    );
  }

  /// Internal fallback (§8.1).
  Future<bool> signInWithPassword({
    required String rawPhone,
    required String password,
  }) async {
    if (state.busy) return false;

    final phone = rawPhone.trim();
    // The password is deliberately **not** trimmed: leading or trailing whitespace is part
    // of a password, and silently removing it would make a correct one fail.
    if (phone.isEmpty || password.isEmpty) {
      state = state.copyWith(message: 'Enter your phone number and password.');
      return false;
    }

    state = state.copyWith(busy: true, phone: phone, clearMessage: true);
    final result = await ref
        .read(authenticatorProvider)
        .loginWithPassword(phone: phone, password: password);

    return result.fold(
      (_) {
        state = state.copyWith(busy: false, clearMessage: true);
        return true;
      },
      (failure) {
        state = state.copyWith(
          busy: false,
          message: messageForFailure(failure, mode: LoginMode.password),
        );
        return false;
      },
    );
  }

  /// Switch credential. Returns to the phone step: a code issued for the OTP path is not a
  /// thing the password path can use, and leaving it on screen would suggest otherwise.
  void useMode(LoginMode mode) {
    if (state.busy) return;
    _stopTicker();
    state = state.copyWith(
      mode: mode,
      stage: LoginStage.phone,
      clearMessage: true,
      clearChallenge: true,
    );
  }

  /// "Wrong number" — back to the first step without leaving the screen.
  void changeNumber() {
    if (state.busy) return;
    _stopTicker();
    state = state.copyWith(
      stage: LoginStage.phone,
      clearMessage: true,
      clearChallenge: true,
    );
  }

  /// **A tick, not a clock read** (P-4). The device clock is wrong more often than anyone
  /// expects, and this counts down a budget the server handed us rather than comparing two
  /// timestamps. Reaching zero re-enables "send a new code" and nothing else — whether a
  /// submitted code is still valid is the server's answer (`OTP_EXPIRED`), never ours.
  void _startTicker() {
    _stopTicker();
    if (state.secondsRemaining <= 0) return;
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      final next = state.secondsRemaining - 1;
      state = state.copyWith(secondsRemaining: next < 0 ? 0 : next);
      if (next <= 0) _stopTicker();
    });
  }

  void _stopTicker() {
    _ticker?.cancel();
    _ticker = null;
  }
}
