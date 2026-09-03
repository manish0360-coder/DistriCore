import 'dart:io';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'database_key.dart';

/// Opens the on-device database file.
///
/// Separated from `AppDatabase` so the schema can be tested against an in-memory SQLite —
/// real storage, real transactions, real constraints — without a device, a path provider or
/// a key. The tests exercise the same `AppDatabase`; only the executor differs.
Future<QueryExecutor> openDeviceDatabase(DatabaseKeyProvider keys) async {
  final directory = await getApplicationDocumentsDirectory();
  final file = File(p.join(directory.path, 'districore.sqlite'));

  // **Read the key HERE, on the main isolate, before the executor exists.**
  //
  // `PlatformDatabaseKey` reads the platform keystore over a `MethodChannel`, and
  // `createInBackground` runs its `setup` callback in a **spawned isolate** that has no
  // binary messenger bound to the platform thread. Awaiting the plugin in there does not
  // fail — it never returns, and the isolate boundary swallows the fact.
  //
  // **The symptom was a login screen that spun forever after a `200`.** The first Drift
  // query on a device is `IdentityCache.save` at sign-in — nothing before it touches the
  // database, because `SessionRestorer` short-circuits on a fresh install without reading.
  // So the app reached a login screen, authenticated successfully, and then hung on the
  // connection it had never yet opened.
  //
  // **The second fault in the same four lines:** `DatabaseSetup` is
  // `void Function(Database)`, so an `async` closure compiles silently and its `Future` is
  // discarded. Even on the main isolate that would let Drift use the connection *before*
  // `PRAGMA key` had run — and SQLCipher requires the key before any other statement.
  // Reading the key up front removes both faults at once: the closure below is synchronous
  // and awaits nothing.
  final key = await keys.key();

  return NativeDatabase.createInBackground(
    file,
    setup: (database) {
      if (key != null) {
        // **A keyed pragma against a non-cipher build is a silent no-op.** Upstream SQLite
        // ignores unrecognised pragmas, so `PRAGMA key` "succeeds" and writes a plaintext
        // database. That is not a hypothesis: the APK built on 2026-08-24 contained
        // `lib/x86_64/libsqlite3.so` with a `native_assets.json` resolving `package:sqlite3`
        // to it, while the 14.5 MB of `libsqlcipher.so` beside it — shipped by
        // `sqlcipher_flutter_libs` — was never opened, because `package:sqlite3` 3.x removed
        // the `open.overrideFor` API that was the only way to reach it. The outbox was
        // written in cleartext and all 314 tests passed. This line is what makes that
        // combination impossible to reach again.
        //
        // **Not an `assert`, deliberately.** Drift's own documentation suggests one; asserts
        // are stripped from release builds, so a regressed `hooks:` block in `pubspec.yaml`
        // would ship a cleartext outbox to a field device with nothing raising a hand.
        // FR-SYN-016 and NFR-SEC-008 are MUSTs, so this fails closed in every build mode —
        // the same rule `AppConfig` applies to a missing base URL.
        //
        // **The probe is cipher-specific.** SQLite3MultipleCiphers answers `PRAGMA cipher`;
        // SQLCipher answers `PRAGMA cipher_version`; upstream SQLite answers neither, which
        // is what makes either one a probe rather than a formality. They are not
        // interchangeable, so this line and the `source:` in `pubspec.yaml` must agree —
        // a pairing `test_mobile_boundary.py` asserts, because getting it wrong would fail
        // closed on a correct build and send someone looking in the wrong place.
        if (database.select('PRAGMA cipher;').isEmpty) {
          throw StateError(
            'The bundled SQLite has no cipher support, so the outbox would be written in '
            'cleartext (FR-SYN-016, NFR-SEC-008). Check the `hooks:` block in '
            'pubspec.yaml — it must set `sqlite3: source: sqlite3mc`.',
          );
        }
        // The key must be set before any other statement on the connection: an encrypted
        // database cannot be read until the codec has one, and a page read first would fail.
        database.execute("PRAGMA key = '$key'");
      }
      // NFR-OFF-005: the outbox must survive a kill. WAL plus FULL synchronous is what
      // makes "committed" mean "on disk" rather than "in a page cache the OS may lose".
      database.execute('PRAGMA journal_mode = WAL');
      database.execute('PRAGMA synchronous = FULL');
    },
  );
}
