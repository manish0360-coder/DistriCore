// The defect found 2026-09-14: the password-login screen showed "The server sent
// something we could not read. Try again in a moment." for a rejected TLS certificate — the
// exact same text it shows for an HTML error page or a slow decode. `messageForFailure`
// pattern-matched on `MalformedResponse()`, and until this fix a rejected certificate WAS a
// `MalformedResponse`, so the one generic string covered both. `failure.dart` now gives the
// two causes separate sealed types; this file proves the screen actually tells them apart.
import 'package:districore/core/failure.dart';
import 'package:districore/features/auth/login_messages.dart';
import 'package:districore/features/auth/login_state.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('a rejected certificate reads differently from an unreadable response', () {
    final certificateText =
        messageForFailure(const CertificateRejected(), mode: LoginMode.password);
    final malformedText =
        messageForFailure(const MalformedResponse('irrelevant'), mode: LoginMode.password);

    expect(certificateText, isNot(equals(malformedText)));
  });

  test('MalformedResponse keeps its original generic text — anti-vacuity', () {
    // Guards against the fix over-correcting: an actual malformed body (HTML 502, truncated
    // JSON) must still show the retry-later text, not the certificate wording.
    expect(
      messageForFailure(const MalformedResponse('irrelevant'), mode: LoginMode.password),
      'The server sent something we could not read. Try again in a moment.',
    );
  });

  test('a rejected certificate does not read as "no connection"', () {
    // The prior fix (problem.dart) already proved this at the Failure level. This proves it
    // survives all the way to the string a person standing in front of the phone reads.
    final text = messageForFailure(const CertificateRejected(), mode: LoginMode.password);
    expect(text, isNot(contains('No connection')));
    expect(text, isNot(contains('check your signal')));
  });

  test('the certificate message does not depend on login mode', () {
    // Unlike INVALID_CREDENTIALS, which is deliberately worded differently for OTP vs
    // password (05 §5's account-enumeration rule), a rejected certificate is a transport
    // fact that happened before either credential was evaluated — the wording must not
    // imply the entered phone number or code/password was itself the problem.
    expect(
      messageForFailure(const CertificateRejected(), mode: LoginMode.otp),
      messageForFailure(const CertificateRejected(), mode: LoginMode.password),
    );
  });
}
