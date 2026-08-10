/// The four seeded roles (`04` T-02), mirroring `core.permissions.Role` on the server.
///
/// **Presentation only.** `02A` §9.3 and P-9: the binary is public and must be assumed
/// decompiled, so a role here decides which tabs are drawn and nothing else. Every request
/// is authorised again in CORE (N-06, BR-003). Editing this enum in a patched APK gains
/// the attacker a tab and no data.
enum Role {
  owner('OWNER'),
  salesman('SALESMAN'),
  delivery('DELIVERY'),
  retailer('RETAILER');

  const Role(this.code);

  /// The wire code. `05` sends roles as an array of these strings.
  final String code;

  /// Unknown codes are **dropped, not thrown**: a server that adds a role must not brick
  /// an installed app that has not been updated yet.
  static Set<Role> fromCodes(Iterable<String> codes) {
    final byCode = {for (final role in Role.values) role.code: role};
    return {
      for (final code in codes)
        if (byCode[code] case final role?) role,
    };
  }
}
