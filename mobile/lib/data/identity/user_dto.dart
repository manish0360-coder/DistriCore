import '../../domain/identity/role.dart';
import '../../domain/identity/session.dart';

/// The authenticated user object returned by `/auth/*` and `GET /auth/me` (`05` §10.1).
///
/// Parsed strictly. The server contract guarantees a user holds **at least one role**, so a
/// payload that yields none is a broken contract, not an unusual account — and a role-less
/// session renders a shell with nothing in it, which looks like a bug in the app rather
/// than a bad response.
final class UserDto {
  const UserDto({
    required this.userId,
    required this.fullName,
    required this.roles,
    this.customerId,
  });

  /// Throws [UserPayloadException] on anything the contract does not describe.
  ///
  /// `05` §5 fixes the shape; this refuses to guess at a body that does not match it,
  /// rather than substituting defaults and producing a plausible-looking wrong session.
  factory UserDto.fromJson(Object? body) {
    if (body is! Map) throw const UserPayloadException('not an object');

    final id = body['id'];
    if (id is! int) throw const UserPayloadException('id is missing or not an integer');

    final fullName = body['full_name'];
    if (fullName is! String) {
      throw const UserPayloadException('full_name is missing or not a string');
    }

    final rawRoles = body['roles'];
    if (rawRoles is! List) throw const UserPayloadException('roles is missing or not a list');

    // `Role.fromCodes` drops codes it does not recognise on purpose: a server that adds a
    // role must not brick an installed app. The emptiness check below is what stops that
    // tolerance from turning an entirely unknown role set into a silent, empty session.
    final roles = Role.fromCodes(rawRoles.whereType<String>());
    if (roles.isEmpty) {
      throw const UserPayloadException('no recognised role; the server guarantees at least one');
    }

    final customerId = body['customer_id'];
    if (customerId != null && customerId is! int) {
      throw const UserPayloadException('customer_id is present but not an integer');
    }

    return UserDto(
      userId: id,
      fullName: fullName,
      roles: roles,
      customerId: customerId as int?,
    );
  }

  final int userId;
  final String fullName;
  final Set<Role> roles;
  final int? customerId;

  /// `phone` and `language` are parsed by nobody yet: `Session` does not carry them, and a
  /// DTO field with no consumer is a field that drifts out of date unnoticed.
  Session toSession() => Session(
        userId: userId,
        fullName: fullName,
        roles: roles,
        customerId: customerId,
      );
}

/// The user payload did not match `05`.
///
/// Carries a **reason, never a value** — FR-IAM-015 keeps credentials out of error messages,
/// and echoing an unexpected body is how one ends up in a crash report.
final class UserPayloadException implements Exception {
  const UserPayloadException(this.reason);

  final String reason;

  @override
  String toString() => 'UserPayloadException: $reason';
}
