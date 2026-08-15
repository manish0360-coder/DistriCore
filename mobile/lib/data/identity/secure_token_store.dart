import 'dart:math';

import '../api/tokens.dart';
import 'secure_storage.dart';

/// The real [TokenStore] (M8 §8.2, §8.4).
///
/// **Three values, three different lifetimes:**
///
/// | Value | Where | Survives |
/// | --- | --- | --- |
/// | Access token | **Memory only** | Nothing. Re-derived from the refresh token on cold start |
/// | Refresh token | Keystore | Restart. Replaced on every rotation |
/// | Device id | Keystore | Restart **and sign-out** — see [clear] |
///
/// `TokenStore`'s getters are synchronous and a keystore is not, so the persisted values are
/// read once by [open] and held in memory afterwards. That is why construction is a factory
/// and not a constructor: a store whose getters returned `null` until some later `await`
/// would hand `AuthInterceptor` an empty header on the first request after launch.
final class SecureTokenStore implements TokenStore {
  SecureTokenStore._(this._storage, this._refreshToken, this._deviceId);

  /// The keystore entry names. **Not secrets** — the values behind them are.
  static const _refreshKey = 'districore.refresh';
  static const _deviceKey = 'districore.device';

  final SecureStorage _storage;

  /// **Never written to storage.** §8.2: *"Access token — memory. Re-derived from refresh on
  /// cold start."* Losing it on restart is the design, not a gap.
  String? _accessToken;

  String? _refreshToken;
  String _deviceId;

  /// Hydrate from the keystore, minting a device id on first run.
  ///
  /// The device id is generated **once per install** (§8.4) and written before the store is
  /// handed out, so `deviceId` is non-null for every caller from the first frame.
  static Future<SecureTokenStore> open(SecureStorage storage) async {
    final refreshToken = await storage.read(_refreshKey);

    var deviceId = await storage.read(_deviceKey);
    if (deviceId == null || deviceId.isEmpty) {
      deviceId = _mintDeviceId();
      await storage.write(_deviceKey, deviceId);
    }

    return SecureTokenStore._(storage, refreshToken, deviceId);
  }

  /// 32 hex characters from a cryptographic source, well inside `04` T-26's
  /// `device_id VARCHAR(64)`.
  ///
  /// `Random.secure()` rather than `Random()`: the identity that attributes every field
  /// write in the audit trail (FR-IAM-009) should not be guessable from a seed. No `uuid`
  /// dependency is added for one string.
  static String _mintDeviceId() {
    final random = Random.secure();
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  }

  @override
  String? get accessToken => _accessToken;

  @override
  String? get refreshToken => _refreshToken;

  @override
  String? get deviceId => _deviceId;

  /// Rotation (§8.2, D-B1).
  ///
  /// **The persisted write happens first, and the access token becomes visible only after it
  /// succeeds.** If the keystore write throws, this store still reports the previous pair:
  /// advertising a session whose refresh token was never stored would produce a device that
  /// works until the access token expires and then cannot recover.
  ///
  /// One write, so there is no partial state *inside* this store. This is **not** a claim of
  /// cross-process atomicity — the keystore API offers no transaction and none is invented.
  @override
  Future<void> save({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(_refreshKey, refreshToken);
    _refreshToken = refreshToken;
    _accessToken = accessToken;
  }

  /// Sign out (C-7).
  ///
  /// **The device id is deliberately kept.** §8.4 says it is *"generated once, stored in the
  /// keystore"*, and FR-IAM-009 requires a device to be *"uniquely identifiable in every
  /// transaction it produces"* — a fresh id per sign-out would make one physical device
  /// present as several. FR-IAM-010's revocation erases *local business data*, which is a
  /// different event with a different trigger, and `02A` §13 defers it to Edition 2.
  ///
  /// Nothing here reads or reports a token value: FR-IAM-015 keeps credentials out of logs,
  /// audit records, error messages and crash reports.
  @override
  Future<void> clear() async {
    await _storage.delete(_refreshKey);
    _refreshToken = null;
    _accessToken = null;
  }

  /// Presence, never values — so an accidental interpolation into a log or a crash report
  /// cannot leak a credential (FR-IAM-015, §8.2).
  @override
  String toString() =>
      'SecureTokenStore(access: ${_accessToken != null}, '
      'refresh: ${_refreshToken != null})';
}
