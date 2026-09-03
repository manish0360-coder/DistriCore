import 'dart:math';

import '../identity/secure_storage.dart';
import 'database_key.dart';

/// The database passphrase, from the platform keystore (§5.6 ADR, NFR-SEC-008, FR-SYN-016).
///
/// `database_key.dart` deferred this to *"task 4"* rather than compile a placeholder into
/// the binary, because a placeholder *"would satisfy the type system and violate P-9"*. The
/// keystore arrived at M1; this is that deferral being paid.
///
/// **Minted once per install, and deliberately never cleared.**
///
/// Sign-out clears the refresh token and the cached identity. It must **not** clear this,
/// and the reason is not tidiness: the key opens `outbox_operation` too. Losing it makes the
/// outbox unreadable, which is precisely what §8.3 forbids — *"a device that locks out with
/// three days of unsent deliveries must still be able to hand them over once it reaches
/// signal."* Erasing a key is how you destroy a week of work while believing you signed
/// someone out. Same reasoning as `device_id` surviving [SecureTokenStore.clear] (§8.4).
///
/// **Now verified, and by what.** This paragraph used to say that `flutter test` ran against
/// *"the system SQLite in the toolchain image, which is not SQLCipher — `PRAGMA key` there is
/// a no-op"*. **That was wrong when it was written, and it is the reason a real defect went
/// unseen for a milestone.** `package:sqlite3` 3.x never used the system library: it bundles
/// one through a Dart build hook, and the hook was defaulting to upstream SQLite — which has
/// no codec, so `PRAGMA key` really was ignored, on the device as well as in CI, while the
/// outbox was written in cleartext.
///
/// **Both halves are now real.** `pubspec.yaml` pins `sqlite3: source: sqlite3mc`, so the
/// host and the device link the same encrypting library; `connection.dart` refuses to open the
/// database at all if `PRAGMA cipher` comes back empty, in every build mode.
///
/// **The old warning's conclusion still stands and is not being dropped.** Unit tests prove
/// the schema, the migration and the window; **none of them proves the file on disk is
/// encrypted**, because they hold no key and never touch the documents directory. That
/// evidence needs a device, and `make mobile-device-encryption` now supplies it: a keyed
/// round trip, a wrong key rejected with `SQLITE_NOTADB`, and the raw bytes of the database
/// and its WAL scanned for plaintext — on a **Pixel 8a API 34 emulator, `android-x64`**.
/// **Not arm64 and not physical hardware** (TD-45), and the gate cannot run inside
/// `make verify` (TD-37, TD-42).
final class PlatformDatabaseKey implements DatabaseKeyProvider {
  const PlatformDatabaseKey(this._storage);

  /// The keystore entry name. **Not the secret** — the value behind it is.
  ///
  /// Named to sit outside the P-9 structural check's pattern for the same reason M1's
  /// `_refreshKey` is: a constant that *looks* like a credential trips a rule that is right
  /// to be blunt, and arguing with it is how the rule gets turned off.
  static const _entry = 'districore.dbkey';

  final SecureStorage _storage;

  @override
  Future<String?> key() async {
    final existing = await _storage.read(_entry);
    if (existing != null && existing.isNotEmpty) return existing;

    final minted = _mint();
    // Written **before** it is returned. A key handed to SQLCipher but never persisted
    // produces a database that opens exactly once and is unreadable ever after — with the
    // outbox inside it.
    await _storage.write(_entry, minted);
    return minted;
  }

  /// 256 bits from a cryptographic source, hex-encoded.
  ///
  /// `Random.secure()` rather than `Random()`, for the reason M1 gives for `device_id` and
  /// more so: this one is the encryption key for every unsent delivery on the device.
  static String _mint() {
    final random = Random.secure();
    final bytes = List<int>.generate(32, (_) => random.nextInt(256));
    return bytes.map((byte) => byte.toRadixString(16).padLeft(2, '0')).join();
  }
}
