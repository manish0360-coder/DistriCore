import 'user_dto.dart';

/// The `202` from `POST /auth/otp/request` (`05` §10.1).
///
/// **Says nothing about whether the phone is registered**, and neither may any caller. The
/// server answers the same shape either way — `05` §5.1 gives `INVALID_CREDENTIALS` the note
/// *"never reveal which"* — so a client that branched on this would reintroduce the
/// enumeration oracle the server is careful not to be.
final class OtpChallenge {
  const OtpChallenge({required this.expiresInSeconds, required this.attemptsAllowed});

  factory OtpChallenge.fromJson(Object? body) {
    if (body is! Map) throw const AuthPayloadException('not an object');
    final expires = body['expires_in_seconds'];
    final attempts = body['attempts_allowed'];
    if (expires is! int) {
      throw const AuthPayloadException('expires_in_seconds missing or not an integer');
    }
    if (attempts is! int) {
      throw const AuthPayloadException('attempts_allowed missing or not an integer');
    }
    return OtpChallenge(expiresInSeconds: expires, attemptsAllowed: attempts);
  }

  final int expiresInSeconds;
  final int attemptsAllowed;
}

/// The `200` bundle returned by **both** `/auth/otp/verify` and `/auth/login`.
///
/// One parser for two endpoints because the server returns one shape — `_issue_tokens`
/// builds it in both paths. A second DTO would be a second place to update when `05` §10.1
/// changes.
final class AuthBundle {
  const AuthBundle({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
  });

  /// Reuses [UserDto.fromJson] for the nested user, so role validation and the
  /// `customer_id` rule are defined once (M2).
  factory AuthBundle.fromJson(Object? body) {
    if (body is! Map) throw const AuthPayloadException('not an object');
    final access = body['access_token'];
    final refresh = body['refresh_token'];
    if (access is! String || access.isEmpty) {
      throw const AuthPayloadException('access_token missing');
    }
    if (refresh is! String || refresh.isEmpty) {
      throw const AuthPayloadException('refresh_token missing');
    }
    return AuthBundle(
      accessToken: access,
      refreshToken: refresh,
      user: UserDto.fromJson(body['user']),
    );
  }

  final String accessToken;
  final String refreshToken;
  final UserDto user;

  /// Presence only. The two fields on this object are credentials, so the default
  /// `toString` — which would print them — is replaced rather than inherited
  /// (FR-IAM-015, §8.2).
  @override
  String toString() => 'AuthBundle(user: ${user.userId})';
}

/// The authentication payload did not match `05` §10.1.
///
/// Carries a **reason, never a value**: no token, no code, no password. An exception is a
/// string that ends up in a crash report.
final class AuthPayloadException implements Exception {
  const AuthPayloadException(this.reason);

  final String reason;

  @override
  String toString() => 'AuthPayloadException: $reason';
}
