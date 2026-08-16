import 'dart:convert';

/// Builds a refresh token carrying the two claims D-D1 depends on.
///
/// **The signature is a placeholder, and that is the honest shape of the test.** The client
/// verifies no signature — it cannot, the key is on the server and P-9 forbids shipping it —
/// so a test that produced a *validly signed* token would be asserting a property the
/// production code does not have.
String refreshTokenJwt({required DateTime issuedAt, required DateTime expiresAt}) {
  String segment(Map<String, Object?> claims) =>
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');

  final header = segment(<String, Object?>{'alg': 'HS256', 'typ': 'JWT'});
  final payload = segment(<String, Object?>{
    'sub': 12,
    'iat': issuedAt.toUtc().millisecondsSinceEpoch ~/ 1000,
    'exp': expiresAt.toUtc().millisecondsSinceEpoch ~/ 1000,
  });
  return '$header.$payload.not-a-real-signature';
}
