import 'role.dart';

/// Who is signed in, and what the UI may therefore draw.
///
/// **`roles` is a set, never a single "primary role"** (`05` C-12, P-7). A salesman who
/// also delivers is the client's normal case, and collapsing the array to one value is how
/// the delivery tab disappears for the person who needs it most.
final class Session {
  const Session({
    required this.userId,
    required this.fullName,
    required this.roles,
    this.customerId,
  });

  final int userId;
  final String fullName;
  final Set<Role> roles;

  /// The shop this user *is*, for a `RETAILER`. `null` for internal staff.
  ///
  /// Part of identity rather than of a screen: `05` AD-11 derives a retailer's entire
  /// customer scope from it, so a session that omitted it would force every retailer screen
  /// to ask the server who it is talking to. `app_user.customer_id` on the server side, and
  /// the reason it is carried now rather than at M12 is that adding a field to a shipped
  /// session object is a migration of live installs.
  ///
  /// **Optional, so no existing construction site changes.**
  final int? customerId;

  bool hasAny(Set<Role> wanted) => roles.intersection(wanted).isNotEmpty;
}
