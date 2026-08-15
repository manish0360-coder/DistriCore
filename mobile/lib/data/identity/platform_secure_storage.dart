import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'secure_storage.dart';

/// [SecureStorage] over the platform keystore — Android Keystore, iOS Keychain (§8.2).
///
/// The only file in the app that imports the plugin, so the seam has exactly one
/// implementation to audit.
final class PlatformSecureStorage implements SecureStorage {
  /// §8.2 — *"No token in shared preferences."*
  ///
  /// The v11 defaults already guarantee that, so no options are passed. Verified against
  /// `AndroidOptions` in flutter_secure_storage 11.0.0: the class has **no
  /// `encryptedSharedPreferences` parameter**, because encryption is no longer opt-in —
  /// its default constructor is documented as *"AES-GCM with RSA OAEP key wrapping … strong
  /// security"*, and `sharedPreferencesName` was removed in the same major version.
  ///
  /// **Dropping the argument does not relax anything**: the behaviour it used to request is
  /// now the only behaviour available.
  const PlatformSecureStorage([this._storage = const FlutterSecureStorage()]);

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}
