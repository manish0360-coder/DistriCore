// M8 task 4 M5 — the V1 login experience.
//
// **The first widget tests in this repository.** They are cheap because M5 introduced the
// `Authenticator` port: the screen depends on one small interface, so these override a hand
// -written fake and never construct a `Dio`, an `ApiClient` or a keystore. That is the
// payoff for the layering rule, stated as a test rather than as a claim.
import 'dart:async';

import 'package:districore/app/app.dart';
import 'package:districore/app/providers.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/core/result.dart';
import 'package:districore/data/repositories/in_memory_session_repository.dart';
import 'package:districore/domain/identity/authenticator.dart';
import 'package:districore/domain/identity/otp_challenge.dart';
import 'package:districore/domain/identity/role.dart';
import 'package:districore/domain/identity/session.dart';
import 'package:districore/features/auth/auth_providers.dart';
import 'package:districore/features/auth/login_controller.dart';
import 'package:districore/features/auth/login_screen.dart';
import 'package:districore/features/deliveries/deliveries_screen.dart';
import 'package:districore/features/deliveries/delivery_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/empty_deliveries.dart';

const _phone = '9876543210';
const _code = '482913';
const _password = 'correct-horse-battery-staple';

const _session = Session(userId: 12, fullName: 'Ramesh Kumar', roles: {Role.delivery});

/// **`expiresInSeconds: 0` by default, and that is a test-infrastructure decision worth
/// naming.** A non-zero challenge starts a `Timer.periodic`, and `testWidgets` fails any test
/// that ends with a timer still pending. Zero means no ticker, so only the one test that is
/// actually about the countdown has to drain it.
const _challenge = OtpChallenge(expiresInSeconds: 0, attemptsAllowed: 5);

/// A hand-written [Authenticator]. Records calls so the tests can assert *what was sent*,
/// which a mock's "was called" cannot.
final class FakeAuthenticator implements Authenticator {
  FakeAuthenticator({
    this.otp = const Ok(_challenge),
    this.verification = const Ok(_session),
    this.password = const Ok(_session),
    this.hold,
  });

  final Result<OtpChallenge> otp;
  final Result<Session> verification;
  final Result<Session> password;

  /// When present, every call waits on it — so a test can hold a request in flight and
  /// observe the busy state instead of racing it.
  final Completer<void>? hold;

  int otpRequests = 0;
  int verifications = 0;
  int passwordAttempts = 0;
  final List<String> phonesSeen = [];
  final List<String> codesSeen = [];

  @override
  Future<Result<OtpChallenge>> requestOtp(String phone) async {
    otpRequests += 1;
    phonesSeen.add(phone);
    await hold?.future;
    return otp;
  }

  @override
  Future<Result<Session>> verifyOtp({required String phone, required String code}) async {
    verifications += 1;
    phonesSeen.add(phone);
    codesSeen.add(code);
    await hold?.future;
    return verification;
  }

  @override
  Future<Result<Session>> loginWithPassword({
    required String phone,
    required String password,
  }) async {
    passwordAttempts += 1;
    phonesSeen.add(phone);
    await hold?.future;
    return this.password;
  }
}

Finder _key(String name) => find.byKey(Key(name));

Future<ProviderContainer> pumpLogin(WidgetTester tester, FakeAuthenticator auth) async {
  final container = ProviderContainer(
    overrides: [authenticatorProvider.overrideWithValue(auth)],
  );
  addTearDown(container.dispose);

  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: LoginScreen()),
    ),
  );
  return container;
}

/// Drive the OTP path as far as the code field.
///
/// **Zero-duration pumps, never `pumpAndSettle`.** `pumpAndSettle` advances the fake clock
/// until no frame is scheduled, and the countdown ticker schedules one every second — so it
/// would quietly run the whole challenge to zero before the test had looked at it. Two bare
/// pumps flush the fake's microtask and rebuild without moving time at all.
Future<ProviderContainer> pumpAtCodeStage(
  WidgetTester tester,
  FakeAuthenticator auth,
) async {
  final container = await pumpLogin(tester, auth);
  await tester.enterText(_key('login.phone'), _phone);
  await tester.tap(_key('login.submit'));
  await tester.pump();
  await tester.pump();
  return container;
}

String _renderedText(WidgetTester tester) => tester
    .widgetList<Text>(find.byType(Text))
    .map((text) => text.data ?? text.textSpan?.toPlainText() ?? '')
    .join(' │ ');

void main() {
  // ---------------------------------------------------------------- 1. signed-out state
  testWidgets('1. the signed-out screen offers a phone number and nothing else', (
    tester,
  ) async {
    await pumpLogin(tester, FakeAuthenticator());

    expect(_key('login.phone'), findsOneWidget);
    expect(_key('login.code'), findsNothing,
        reason: 'a code field before a code was sent invites typing one that does not exist');
    expect(_key('login.password'), findsNothing, reason: 'OTP is the field default (§8.1)');
    expect(_key('login.message'), findsNothing);
    expect(find.text('Send code'), findsOneWidget);
    expect(find.text('Sign in with a password instead'), findsOneWidget);
  });

  // ------------------------------------------------------------------- 2. request OTP
  testWidgets('2. requesting a code sends the number as typed, trimmed only', (tester) async {
    final auth = FakeAuthenticator();
    await pumpLogin(tester, auth);

    await tester.enterText(_key('login.phone'), '  $_phone  ');
    await tester.tap(_key('login.submit'));
    await tester.pumpAndSettle();

    expect(auth.otpRequests, 1);
    // Not `+91…`. `identity/phone.py` canonicalises on both read and write, and that module
    // exists because the rule was once duplicated and drifted. A second implementation here
    // would be a third.
    expect(auth.phonesSeen.single, _phone);
  });

  // ------------------------------------------------- 3. OTP screen appears after success
  testWidgets('3. the code field appears only after the request succeeds', (tester) async {
    final auth = FakeAuthenticator();
    await pumpAtCodeStage(tester, auth);

    expect(_key('login.code'), findsOneWidget);
    expect(find.text('Verify and sign in'), findsOneWidget);
    expect(_renderedText(tester), contains('You have 5 attempts'));
    // The number is frozen: verification must present the same string the challenge used.
    expect(tester.widget<TextField>(_key('login.phone')).enabled, isFalse);
  });

  testWidgets('3b. the countdown ticks down and then offers a new code', (tester) async {
    final auth = FakeAuthenticator(
      otp: const Ok(OtpChallenge(expiresInSeconds: 3, attemptsAllowed: 5)),
    );
    final container = await pumpAtCodeStage(tester, auth);

    expect(_renderedText(tester), contains('expires in 0:03'));
    expect(tester.widget<TextButton>(_key('login.resend')).onPressed, isNull);

    await tester.pump(const Duration(seconds: 1));
    expect(container.read(loginControllerProvider).secondsRemaining, 2);

    // Drains the periodic timer as well as finishing the countdown: a test that ended here
    // with one pending would fail on plumbing.
    await tester.pump(const Duration(seconds: 3));
    expect(container.read(loginControllerProvider).canResend, isTrue);
    expect(tester.widget<TextButton>(_key('login.resend')).onPressed, isNotNull);
  });

  // ---------------------------------------------------------------- 4. request failure
  testWidgets('4. a failed request explains itself and stays on the phone step', (
    tester,
  ) async {
    final auth = FakeAuthenticator(otp: const Err(Offline()));
    await pumpLogin(tester, auth);

    await tester.enterText(_key('login.phone'), _phone);
    await tester.tap(_key('login.submit'));
    await tester.pumpAndSettle();

    expect(_key('login.code'), findsNothing);
    expect(
      tester.widget<Text>(_key('login.message')).data,
      'No connection. Check your signal and try again.',
    );
  });

  testWidgets('4b. an empty number is refused without a round trip', (tester) async {
    final auth = FakeAuthenticator();
    await pumpLogin(tester, auth);

    await tester.tap(_key('login.submit'));
    await tester.pumpAndSettle();

    expect(auth.otpRequests, 0, reason: 'an SMS costs money; do not spend one on a blank field');
    expect(tester.widget<Text>(_key('login.message')).data, 'Enter your phone number.');
  });

  // ----------------------------------------------------------------- 5. verify success
  testWidgets('5. a correct code is sent with the requested number and clears the field', (
    tester,
  ) async {
    final auth = FakeAuthenticator();
    await pumpAtCodeStage(tester, auth);

    await tester.enterText(_key('login.code'), _code);
    await tester.tap(_key('login.submit'));
    await tester.pumpAndSettle();

    expect(auth.verifications, 1);
    expect(auth.codesSeen.single, _code);
    expect(auth.phonesSeen.last, _phone);
    expect(_key('login.message'), findsNothing);
    expect(tester.widget<TextField>(_key('login.code')).controller?.text, isEmpty);
  });

  // ----------------------------------------------------------------- 6. verify failure
  testWidgets('6. a rejected code says so in our words, not the server\'s', (tester) async {
    final auth = FakeAuthenticator(
      verification: const Err(
        ProblemFailure(
          code: 'OTP_INVALID',
          status: 422,
          // Deliberately distinctive: if this string ever reaches the screen, the client is
          // rendering server prose that `05` §5 says may be reworded at any time.
          detail: 'RAW-SERVER-DETAIL-otp mismatch for hash 9f2a',
        ),
      ),
    );
    await pumpAtCodeStage(tester, auth);

    await tester.enterText(_key('login.code'), _code);
    await tester.tap(_key('login.submit'));
    await tester.pumpAndSettle();

    expect(tester.widget<Text>(_key('login.message')).data, 'That code is not correct.');
    expect(_renderedText(tester), isNot(contains('RAW-SERVER-DETAIL')));
    expect(_key('login.code'), findsOneWidget, reason: 'still on the code step to retry');
  });

  // --------------------------------------------------------------- 7. password fallback
  testWidgets('7. the password fallback submits through the same port', (tester) async {
    final auth = FakeAuthenticator();
    await pumpLogin(tester, auth);

    await tester.tap(_key('login.mode'));
    await tester.pumpAndSettle();

    final field = tester.widget<TextField>(_key('login.password'));
    expect(field.obscureText, isTrue);
    expect(field.enableSuggestions, isFalse);
    expect(field.autocorrect, isFalse);

    await tester.enterText(_key('login.phone'), _phone);
    await tester.enterText(_key('login.password'), _password);
    await tester.tap(_key('login.submit'));
    await tester.pumpAndSettle();

    expect(auth.passwordAttempts, 1);
    expect(auth.otpRequests, 0);
  });

  // ---------------------------------------------------------------- 8. password failure
  testWidgets('8. wrong credentials never say which half was wrong', (tester) async {
    final auth = FakeAuthenticator(
      password: const Err(
        ProblemFailure(
          code: 'INVALID_CREDENTIALS',
          status: 401,
          detail: 'Incorrect phone number or password.',
        ),
      ),
    );
    await pumpLogin(tester, auth);

    await tester.tap(_key('login.mode'));
    await tester.pumpAndSettle();
    await tester.enterText(_key('login.phone'), _phone);
    await tester.enterText(_key('login.password'), _password);
    await tester.tap(_key('login.submit'));
    await tester.pumpAndSettle();

    // The server raises the identical error for an unknown number and a wrong password. A
    // client that distinguished them would hand back the enumeration oracle.
    expect(
      tester.widget<Text>(_key('login.message')).data,
      'Incorrect phone number or password.',
    );
    expect(tester.widget<TextField>(_key('login.password')).controller?.text, isEmpty);
  });

  // ------------------------------------------------------------ 9. duplicate submission
  testWidgets('9. a second submission while one is in flight is dropped', (tester) async {
    final hold = Completer<void>();
    final auth = FakeAuthenticator(hold: hold);
    final container = await pumpLogin(tester, auth);
    final controller = container.read(loginControllerProvider.notifier);

    // Called directly, twice, with no rebuild in between. **The disabled button is a
    // drawing; `state.busy` is the guard**, and this is the only way to prove which one is
    // actually doing the work.
    unawaited(controller.requestOtp(_phone));
    unawaited(controller.requestOtp(_phone));
    await tester.pump();

    expect(auth.otpRequests, 1);

    hold.complete();
    await tester.pumpAndSettle();
    expect(auth.otpRequests, 1);
  });

  // -------------------------------------------------------- 10. loading/error transitions
  testWidgets('10. busy hides the label, disables every action, then resolves', (
    tester,
  ) async {
    final hold = Completer<void>();
    final auth = FakeAuthenticator(hold: hold, otp: const Err(Offline()));
    await pumpLogin(tester, auth);

    await tester.enterText(_key('login.phone'), _phone);
    await tester.tap(_key('login.submit'));
    await tester.pump();

    expect(_key('login.busy'), findsOneWidget);
    expect(find.text('Send code'), findsNothing);
    expect(tester.widget<FilledButton>(_key('login.submit')).onPressed, isNull);
    expect(tester.widget<TextButton>(_key('login.mode')).onPressed, isNull);
    expect(tester.widget<TextField>(_key('login.phone')).enabled, isFalse);

    hold.complete();
    await tester.pumpAndSettle();

    expect(_key('login.busy'), findsNothing);
    expect(find.text('Send code'), findsOneWidget);
    expect(tester.widget<FilledButton>(_key('login.submit')).onPressed, isNotNull);
    expect(_key('login.message'), findsOneWidget);
  });

  // ------------------------------------------------------ 11. the session reaches the shell
  testWidgets('11. a published session moves the app to the shell, with no navigation in '
      'the login screen', (tester) async {
    // Driven through the *real* router and `sessionProvider`. `InMemorySessionRepository` is
    // the seam M4 kept for exactly this: a session without a keystore, a network or a
    // `--dart-define`.
    final repository = InMemorySessionRepository();
    addTearDown(repository.dispose);

    final container = ProviderContainer(
      overrides: [
        sessionRepositoryProvider.overrideWithValue(repository),
        authenticatorProvider.overrideWithValue(FakeAuthenticator()),
        // **Required because this test reaches the shell, not because it is about
        // deliveries.** Landing on `/deliveries` builds `DeliveriesScreen`, whose `initState`
        // reads the override-required delivery port. Without this the `StateError` is thrown
        // inside a frame and reappears as a `pumpAndSettle` timeout — a failure that names
        // the wrong layer, which this project has paid for before.
        deliveryRepositoryProvider.overrideWithValue(const EmptyDeliveryRepository()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(container: container, child: const DistriCoreApp()),
    );
    await tester.pumpAndSettle();

    expect(find.byType(LoginScreen), findsOneWidget);

    // Exactly what `AuthService._authenticate` does on success: publish, and nothing else.
    repository.set(_session);
    await tester.pumpAndSettle();

    expect(find.byType(LoginScreen), findsNothing);
    expect(find.byType(DeliveriesScreen), findsOneWidget);
  });

  // ------------------------------------------------------------------- 12. no leakage
  testWidgets('12. no credential reaches the rendered tree, the state, or a message', (
    tester,
  ) async {
    final auth = FakeAuthenticator(
      password: const Err(
        ProblemFailure(code: 'INVALID_CREDENTIALS', status: 401, detail: 'nope'),
      ),
    );
    final container = await pumpLogin(tester, auth);

    await tester.tap(_key('login.mode'));
    await tester.pumpAndSettle();
    await tester.enterText(_key('login.phone'), _phone);
    await tester.enterText(_key('login.password'), _password);
    await tester.tap(_key('login.submit'));
    await tester.pumpAndSettle();

    final state = container.read(loginControllerProvider);
    expect(state.toString(), isNot(contains(_password)));
    expect(state.message, isNot(contains(_password)));
    expect(_renderedText(tester), isNot(contains(_password)));

    // And the same for the OTP path's code.
    final otpAuth = FakeAuthenticator(
      verification: const Err(
        ProblemFailure(code: 'OTP_INVALID', status: 422, detail: 'nope'),
      ),
    );
    final otpContainer = await pumpAtCodeStage(tester, otpAuth);
    await tester.enterText(_key('login.code'), _code);
    await tester.tap(_key('login.submit'));
    await tester.pumpAndSettle();

    expect(otpContainer.read(loginControllerProvider).toString(), isNot(contains(_code)));
    expect(_renderedText(tester), isNot(contains(_code)));
  });
}
