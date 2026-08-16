import 'package:drift/drift.dart';

/// The cached identity that makes offline sign-in possible (M8 §8.2, §14.12 D-D6).
///
/// **Four columns, and the absences are the design.** §8.2 splits storage deliberately:
/// the refresh token and `device_id` live in the **keystore**, cached user and roles live in
/// the **encrypted database**. Copying either credential into here would put a secret in a
/// second place, and the second place is always the one that gets forgotten.
///
/// **No anchor column either.** D-D1 makes the refresh token's `iat`/`exp` the anchor and
/// ceiling — so the anchor is *already on the device*, inside the token, signed by the
/// server. Persisting a copy would create a value that can disagree with the credential it
/// describes, which is the failure `identity/phone.py` records on the other side of the wire.
@DataClassName('LocalIdentityRow')
class LocalIdentities extends Table {
  @override
  String get tableName => 'local_identity';

  /// **Always 1.** One device, one signed-in user; a second row would make "which identity?"
  /// a question every reader has to answer.
  IntColumn get id => integer().withDefault(const Constant(1))();

  IntColumn get userId => integer().named('user_id')();
  TextColumn get fullName => text().named('full_name')();

  /// A JSON array of `Role.code` strings — `["SALESMAN","DELIVERY"]`.
  ///
  /// **An array, because P-7 and `05` C-12 say roles are an array.** Flattening to a single
  /// "primary role" here would reintroduce, in storage, the exact bug the tab bar was
  /// written to avoid. Codes rather than enum indices: reordering the Dart enum must not
  /// silently reinterpret a row already sitting on a device (the same reasoning as
  /// `outbox_operation.status`).
  TextColumn get roles => text()();

  /// The shop a `RETAILER` *is* (`05` AD-11). Null for internal staff.
  IntColumn get customerId => integer().named('customer_id').nullable()();

  @override
  Set<Column> get primaryKey => {id};

  /// Single-row enforced by the **database**, not by a convention in a repository.
  ///
  /// I-6's argument, applied to a different table: an application check is defeated by the
  /// concurrent write it was meant to prevent, and the constraint is what survives.
  @override
  List<String> get customConstraints => const ['CHECK (id = 1)'];
}
