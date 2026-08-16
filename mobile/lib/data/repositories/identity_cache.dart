import 'dart:convert';

import 'package:drift/drift.dart';

import '../../domain/identity/role.dart';
import '../../domain/identity/session.dart';
import '../db/app_database.dart';

/// The cached identity, on the encrypted local database (M8 §8.2, §14.12 D-D6).
///
/// One row, read at cold start so a device with no signal can still know who is holding it.
/// **It stores no credential** — the refresh token and `device_id` stay in the keystore —
/// so on its own this row unlocks nothing. All three of D-D6's conditions must hold.
final class IdentityCache {
  const IdentityCache(this._db);

  final AppDatabase _db;

  /// The cached user, or `null` if there is none **or it cannot be trusted**.
  ///
  /// **Fails closed, and the two cases are folded together on purpose.** A row whose `roles`
  /// will not parse, or which parses to no known role, is indistinguishable to a caller from
  /// no row at all — and both must end at a login screen rather than at a session with an
  /// empty role set, which P-7 would then compose into a shell with no tabs. This is M2's
  /// rule for `/auth/me` payloads applied to the same data at rest.
  Future<Session?> read() async {
    final row = await _db.select(_db.localIdentities).getSingleOrNull();
    if (row == null) return null;

    final roles = _decodeRoles(row.roles);
    if (roles.isEmpty) return null;

    return Session(
      userId: row.userId,
      fullName: row.fullName,
      roles: roles,
      customerId: row.customerId,
    );
  }

  /// Write the identity of a freshly authenticated user.
  ///
  /// `insertOnConflictUpdate` against the fixed primary key: the row is replaced, never
  /// accumulated. Signing in as a different user must not leave the previous one readable.
  Future<void> save(Session session) =>
      _db.into(_db.localIdentities).insertOnConflictUpdate(
            LocalIdentitiesCompanion.insert(
              id: const Value(1),
              userId: session.userId,
              fullName: session.fullName,
              roles: jsonEncode([for (final role in session.roles) role.code]),
              customerId: Value(session.customerId),
            ),
          );

  /// Sign-out, or a credential the server has rejected.
  ///
  /// **Deletes the identity row and nothing else.** `outbox_operation` is in the same
  /// database and is not touched — §8.3: the outbox is not readable after lockout, and it is
  /// *not erased*.
  Future<void> clear() => _db.delete(_db.localIdentities).go();

  Set<Role> _decodeRoles(String raw) {
    final Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      return const {};
    }
    if (decoded is! List) return const {};
    // `Role.fromCodes` drops unknown codes rather than throwing, so a server that adds a
    // role cannot brick an installed app that has not been updated (M2).
    return Role.fromCodes(decoded.whereType<String>());
  }
}
