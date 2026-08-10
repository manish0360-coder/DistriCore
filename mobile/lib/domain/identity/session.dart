import 'role.dart';

/// Who is signed in, and what the UI may therefore draw.
///
/// **`roles` is a set, never a single "primary role"** (`05` C-12, P-7). A salesman who
/// also delivers is the client's normal case, and collapsing the array to one value is how
/// the delivery tab disappears for the person who needs it most.
final class Session {
  const Session({required this.userId, required this.fullName, required this.roles});

  final int userId;
  final String fullName;
  final Set<Role> roles;

  bool hasAny(Set<Role> wanted) => roles.intersection(wanted).isNotEmpty;
}
