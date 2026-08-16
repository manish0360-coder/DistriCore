import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'login_controller.dart';
import 'login_state.dart';

/// Sign in (M8 §8.1, `05` §10.1, FR-IAM-015).
///
/// **Deliberately plain.** This is a screen used standing up, outdoors, possibly in sunlight,
/// by someone who wants to get on with a delivery round. Large targets, one decision at a
/// time, and no ornament.
///
/// **It contains no navigation.** On success `AuthService` persists the tokens and publishes
/// the session, `router.dart`'s redirect sees it through `sessionProvider`, and the app
/// moves. A `context.go` here would be a second answer to "who is signed in", and the two
/// would eventually disagree.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _phone = TextEditingController();
  final _code = TextEditingController();
  final _password = TextEditingController();

  @override
  void dispose() {
    // Dropped as early as we can. **This is not secure erasure and must not be described as
    // such** — Dart strings are immutable, so the bytes stay wherever the runtime put them
    // until they are collected. What it does buy is that the credential is no longer
    // reachable from a live widget when a crash reporter walks the tree.
    _code.clear();
    _password.clear();
    _phone.dispose();
    _code.dispose();
    _password.dispose();
    super.dispose();
  }

  void _onSubmit() => unawaited(_submit());

  Future<void> _submit() async {
    final controller = ref.read(loginControllerProvider.notifier);
    final state = ref.read(loginControllerProvider);

    switch ((state.mode, state.stage)) {
      case (LoginMode.otp, LoginStage.phone):
        await controller.requestOtp(_phone.text);
      case (LoginMode.otp, LoginStage.code):
        await controller.verifyOtp(_code.text);
        // **The guard is load-bearing, not defensive habit.** On success the router redirects
        // and this State is disposed while the await is still suspended; clearing a disposed
        // `TextEditingController` throws.
        if (!mounted) return;
        _code.clear();
      case (LoginMode.password, _):
        await controller.signInWithPassword(
          rawPhone: _phone.text,
          password: _password.text,
        );
        if (!mounted) return;
        // Cleared on success *and* failure: a wrong password is retyped, and a right one is
        // finished with.
        _password.clear();
    }
  }

  void _onResend() {
    final controller = ref.read(loginControllerProvider.notifier);
    unawaited(controller.requestOtp(ref.read(loginControllerProvider).phone));
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(loginControllerProvider);
    final controller = ref.read(loginControllerProvider.notifier);
    final theme = Theme.of(context);
    final atCode = state.stage == LoginStage.code;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('DistriCore', style: theme.textTheme.headlineMedium),
                  const SizedBox(height: 4),
                  Text('Sign in to continue', style: theme.textTheme.bodyMedium),
                  const SizedBox(height: 24),

                  TextField(
                    key: const Key('login.phone'),
                    controller: _phone,
                    // Locked once a code is outstanding: verification must present the same
                    // number the challenge was issued against, and an editable field here
                    // would let the two drift apart in the user's hand.
                    enabled: !state.busy && !atCode,
                    keyboardType: TextInputType.phone,
                    autocorrect: false,
                    enableSuggestions: false,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(
                      labelText: 'Phone number',
                      border: OutlineInputBorder(),
                    ),
                  ),

                  if (state.mode == LoginMode.password) ...[
                    const SizedBox(height: 16),
                    TextField(
                      key: const Key('login.password'),
                      controller: _password,
                      enabled: !state.busy,
                      obscureText: true,
                      autocorrect: false,
                      enableSuggestions: false,
                      onSubmitted: (_) => _onSubmit(),
                      decoration: const InputDecoration(
                        labelText: 'Password',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ],

                  if (atCode) ...[
                    const SizedBox(height: 16),
                    TextField(
                      key: const Key('login.code'),
                      controller: _code,
                      enabled: !state.busy,
                      keyboardType: TextInputType.number,
                      autocorrect: false,
                      enableSuggestions: false,
                      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                      onSubmitted: (_) => _onSubmit(),
                      decoration: const InputDecoration(
                        labelText: 'Code from SMS',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      _challengeLine(state),
                      key: const Key('login.challenge'),
                      style: theme.textTheme.bodySmall,
                    ),
                  ],

                  if (state.message case final message?) ...[
                    const SizedBox(height: 16),
                    Text(
                      message,
                      key: const Key('login.message'),
                      style: theme.textTheme.bodyMedium
                          ?.copyWith(color: theme.colorScheme.error),
                    ),
                  ],

                  const SizedBox(height: 24),
                  FilledButton(
                    key: const Key('login.submit'),
                    onPressed: state.busy ? null : _onSubmit,
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(52),
                    ),
                    child: state.busy
                        ? const SizedBox(
                            key: Key('login.busy'),
                            height: 22,
                            width: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(_submitLabel(state)),
                  ),

                  if (atCode)
                    TextButton(
                      key: const Key('login.resend'),
                      onPressed: state.busy || !state.canResend ? null : _onResend,
                      child: Text(
                        state.canResend
                            ? 'Send a new code'
                            : 'Send a new code in ${state.secondsRemaining}s',
                      ),
                    ),

                  if (atCode)
                    TextButton(
                      key: const Key('login.change'),
                      onPressed: state.busy ? null : controller.changeNumber,
                      child: const Text('Use a different number'),
                    ),

                  TextButton(
                    key: const Key('login.mode'),
                    onPressed: state.busy
                        ? null
                        : () => controller.useMode(
                              state.mode == LoginMode.otp
                                  ? LoginMode.password
                                  : LoginMode.otp,
                            ),
                    child: Text(
                      state.mode == LoginMode.otp
                          ? 'Sign in with a password instead'
                          : 'Sign in with a code instead',
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  String _submitLabel(LoginState state) => switch ((state.mode, state.stage)) {
        (LoginMode.otp, LoginStage.phone) => 'Send code',
        (LoginMode.otp, LoginStage.code) => 'Verify and sign in',
        (LoginMode.password, _) => 'Sign in',
      };

  /// What the user is told about the outstanding challenge.
  ///
  /// `attemptsAllowed` is safe to show: the server answers the same `202` whether or not the
  /// number is registered, and the value is a constant rather than anything account-derived.
  String _challengeLine(LoginState state) {
    final attempts = state.attemptsAllowed;
    final sent = 'We sent a code to ${state.phone}.';
    final expiry = state.secondsRemaining > 0
        ? ' It expires in ${_mmss(state.secondsRemaining)}.'
        : '';
    final tries = attempts == null ? '' : ' You have $attempts attempts.';
    return '$sent$expiry$tries';
  }

  static String _mmss(int seconds) {
    final minutes = seconds ~/ 60;
    final rest = (seconds % 60).toString().padLeft(2, '0');
    return '$minutes:$rest';
  }
}
