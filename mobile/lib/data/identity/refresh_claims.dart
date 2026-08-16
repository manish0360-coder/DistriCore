import 'dart:convert';

/// The two claims D-D1 makes the offline window depend on: `iat` and `exp`.
///
/// **Read, never trusted for identity.** §14.12 D-D1 permits decoding the refresh token to
/// recover the instants the *server* stamped on it, and nothing more. Who the user is comes
/// from `/auth/me` or from the cached identity row — never from here — because this parser
/// verifies **no signature**. It cannot: the signing key lives on the server and P-9 forbids
/// shipping it. A payload read without verification is a hint about time, not an authority
/// about people, and the distinction is the whole reason this class exposes two `DateTime`s
/// and no user id.
///
/// **Nothing here holds or prints the token.** FR-IAM-015: credentials must not reach logs,
/// error messages or crash reports, and a parser is a natural place to break that by
/// accident.
final class RefreshClaims {
  const RefreshClaims({required this.issuedAt, required this.expiresAt});

  final DateTime issuedAt;
  final DateTime expiresAt;

  /// `null` for anything that is not a JWT carrying a sane `iat`/`exp` pair.
  ///
  /// **Returning `null` rather than throwing is deliberate.** A refresh token this cannot
  /// read is not necessarily invalid — it may simply not be a JWT — and the caller's correct
  /// response is to fall back to the server, not to sign anyone out. That fallback is also
  /// what keeps every M2 test behaving exactly as it did.
  static RefreshClaims? tryParse(String token) {
    final parts = token.split('.');
    if (parts.length != 3) return null;

    final Object? payload;
    try {
      payload = jsonDecode(utf8.decode(base64Url.decode(base64Url.normalize(parts[1]))));
    } on FormatException {
      // Covers all three failure modes — bad base64, bad UTF-8, bad JSON — and deliberately
      // catches nothing broader, so a genuine bug here is not swallowed as "not a JWT".
      return null;
    }

    if (payload is! Map) return null;
    final issued = payload['iat'];
    final expires = payload['exp'];
    if (issued is! int || expires is! int) return null;

    // A token that expires before it was issued describes no window at all. Refusing here
    // means `OfflineWindow` never has to consider a negative `credentialLife`.
    if (expires <= issued) return null;

    return RefreshClaims(
      issuedAt: DateTime.fromMillisecondsSinceEpoch(issued * 1000, isUtc: true),
      expiresAt: DateTime.fromMillisecondsSinceEpoch(expires * 1000, isUtc: true),
    );
  }

  /// Instants only. There is no token here to leak, and this documents that on purpose.
  @override
  String toString() => 'RefreshClaims(iat: $issuedAt, exp: $expiresAt)';
}
