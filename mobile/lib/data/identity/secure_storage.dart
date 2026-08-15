/// The narrow slice of a platform keystore this app actually uses.
///
/// **The seam exists so the token store is testable without a device.**
/// `flutter_secure_storage` is a plugin: on the Dart VM every call throws
/// `MissingPluginException`, so a unit test that touched it directly could only ever assert
/// that it throws. Depending on this interface instead means the security invariants —
/// *the access token is never persisted*, *the device id survives* — are asserted against
/// real reads and writes of a real map.
///
/// Deliberately three methods. `readAll`/`deleteAll` are not here: `deleteAll` in particular
/// is how a sign-out quietly takes the device identity with it (§8.4).
abstract interface class SecureStorage {
  Future<String?> read(String key);

  Future<void> write(String key, String value);

  Future<void> delete(String key);
}
