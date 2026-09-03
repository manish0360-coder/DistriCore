/// **NFR-SEC-008 — the device inspection test, run on a device.**
///
/// `02` states the requirement and its verification method in six words: *"Device local
/// storage MUST be encrypted at rest"*, method *"Device inspection test"*. FR-SYN-016 says
/// the same thing normatively. This file is that method, automated.
///
/// **Scope, stated because a gate that overclaims is worse than no gate.** This proves the
/// property on a **Pixel 8a API 34 emulator, `android-x64`**. It does **not** cover `arm64`
/// and it does **not** cover physical hardware. Any report citing this run must say so.
///
/// **Why it needs a device at all.** `flutter test` on the host proves the schema, the
/// migration and the window; none of it proves the *file* is encrypted, and three things
/// here are simply unreachable without the platform keystore: that the correct key still
/// opens the database, that a wrong one does not, and what the codec actually wrote to disk.
///
/// **Needs no network, no dev stack, no CA.** Nothing below makes an HTTP call. That is
/// unusual for a device workflow in this project and worth knowing before someone starts
/// Caddy for it.
///
/// **What this file exists to prevent, concretely.** For a milestone this app shipped an
/// APK containing `libsqlite3.so` — upstream SQLite, no codec — beside 14.5 MB of
/// `libsqlcipher.so` that no code path could open, because `package:sqlite3` 3.x removed
/// `open.overrideFor`. `PRAGMA key` is an *unrecognised pragma* against upstream SQLite: it
/// does not fail, it is ignored. The outbox was written in cleartext, every delivery a
/// salesman had not yet synced was readable with `adb`, and all 314 tests passed. Nothing in
/// the repository could see it. The two halves of the fix are the fail-closed guard in
/// `connection.dart` and this gate; `test_mobile_boundary.py` holds the third.
///
/// **Every open here is the production path.** `openGateDatabase()` builds the real
/// `PlatformDatabaseKey` over the real platform keystore and calls the real
/// `openDeviceDatabase`. The single exception is phase 3's wrong key, which substitutes only
/// the `DatabaseKeyProvider` — the seam that interface was created for.
///
/// **Phase 6 is a positive control and is not optional.** Phases 1b and 5 assert that a
/// scanner finds *nothing*. An assertion that something returns zero proves nothing unless
/// the same code is shown, on the same shape of data, capable of returning more. That is the
/// exact failure mode this milestone was about, so the scanner is exercised against a
/// deliberately unencrypted database seconds later and must find every marker there.
library;

import 'dart:convert';
import 'dart:io';

import 'package:districore/core/result.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/db/connection.dart';
import 'package:districore/data/db/database_key.dart';
import 'package:districore/domain/outbox/outbox_operation.dart';
import 'package:drift/drift.dart' show QueryRow;
import 'package:drift/native.dart';
import 'package:drift/remote.dart' show DriftRemoteException;
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqlite3/common.dart';

import 'support/device_outbox.dart';

/// The Android application id this gate runs against, used only to print a retrieval command
/// when the gate fails. `applicationIdSuffix = ".dev"` on debug builds (`build.gradle.kts`).
const _debugApplicationId = 'com.districore.app.dev';

/// SQLITE_NOTADB — the codec could not make sense of page 1.
const _sqliteNotADatabase = 26;

/// **Strings that must never appear in the bytes on disk.**
///
/// The header alone is not enough. A build that encrypted page 1 and left the rest readable
/// would pass a header check while every table name, operation type and payload stayed
/// legible — so schema names and the row's own contents are searched for too. Phase 6 proves
/// these are findable when the file is *not* encrypted.
const _plaintextMarkers = <String>[
  'SQLite format 3',
  'sqlite_master',
  'outbox_operation',
  'DELIVERY_COMPLETE',
  'Gate 0',
];

/// A key that is well-formed and certainly not the one in the keystore.
///
/// Same shape `PlatformDatabaseKey._mint()` produces — 64 hex characters — so phase 3's
/// failure is a *decryption* failure and not a rejection of a malformed passphrase. The
/// chance of `Random.secure()` having minted this value is 2^-256.
final class _WrongKey implements DatabaseKeyProvider {
  @override
  Future<String?> key() async => 'f' * 64;
}

void _evidence(String label, Object? value) => debugPrint('  PROOF | $label: $value');

/// The first cell of the first row, or `null` for an empty result set.
Object? _firstValue(List<QueryRow> rows) =>
    rows.isEmpty ? null : rows.first.data.values.first;

/// Which of [_plaintextMarkers] appear in [file]'s bytes.
///
/// `latin1` rather than `utf8`: every byte 0x00–0xFF maps to exactly one character, so no
/// input is invalid and no multi-byte sequence can straddle and hide an ASCII marker.
/// Decoding encrypted bytes as UTF-8 would throw or silently substitute, and either would
/// turn "unreadable" into a false pass.
List<String> _markersIn(File file) {
  final text = latin1.decode(file.readAsBytesSync(), allowInvalid: true);
  return [
    for (final marker in _plaintextMarkers)
      if (text.contains(marker)) marker,
  ];
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'NFR-SEC-008 — the device database is encrypted, keyed, and readable only with that key',
    (tester) async {
      // **The phase label is the diagnostic.** A failing `expect` unwinds before any later
      // line runs, so without this the output names an assertion but not where the run
      // reached. Updated at every boundary and printed by a tear-down that runs on pass and
      // on failure alike.
      var phase = '0 — precondition';
      var passed = false;

      final databasePath = await deviceDatabasePath();
      final walPath = '$databasePath-wal';
      AppDatabase? open;

      // **Registration order is reverse execution order** (tear-downs run LIFO), so these
      // three are declared bottom-up: close, then delete-or-preserve, then the phase line
      // last where it is easy to find.
      addTearDown(() => _evidence('last phase entered', phase));
      addTearDown(() async {
        if (passed) {
          await deleteDeviceDatabase();
          _evidence('cleanup', 'passed — test database removed');
          return;
        }
        // **Preserved deliberately.** Phase 0 guarantees the next run starts clean, so
        // deleting here would buy nothing and destroy the one artefact worth examining.
        _evidence('cleanup', 'FAILED — database preserved at $databasePath');
        _evidence(
          'retrieve it with',
          'adb exec-out run-as $_debugApplicationId cat '
              '${p.relative(databasePath, from: '/data/user/0/$_debugApplicationId')}'
              ' > failure.sqlite',
        );
      });
      addTearDown(() async {
        try {
          await open?.close();
        } catch (_) {
          // A connection that never opened cannot be closed cleanly. Closing is hygiene —
          // a leaked handle holds the WAL and poisons the next run — not evidence.
        }
      });

      _evidence('target', 'Pixel 8a API 34 emulator, android-x64 (NOT arm64, NOT physical)');
      _evidence('database path', databasePath);

      // ---- PHASE 0 — start from no database at all ---------------------------------
      //
      // Owned by the test, not by the runner. `adb shell pm clear` would do the same thing
      // but only if someone remembers it, and a forgotten clear makes every assertion below
      // pass against rows an earlier run left behind. `outbox_kill_test` makes the same
      // argument for the same reason.
      await deleteDeviceDatabase();
      expect(
        File(databasePath).existsSync(),
        isFalse,
        reason: 'PHASE 0 — the database survived deletion, so nothing below is about a '
            'freshly created file',
      );

      // ---- PHASE 1 — a fresh database through the production path ------------------
      phase = '1 — create and write';
      open = await openGateDatabase();
      final database = open;

      // The guard in `connection.dart` has already enforced this — the open above throws
      // `StateError` otherwise — but asserting it here is what turns "the app did not crash"
      // into a recorded measurement that a reader can check.
      final cipher = await database.customSelect('PRAGMA cipher;').get();
      expect(
        cipher,
        isNotEmpty,
        reason: 'PHASE 1 — PRAGMA cipher returned nothing: the loaded library has no '
            'encryption codec, so PRAGMA key is a silent no-op and the outbox is plaintext',
      );

      // **Recorded, not asserted.** Pinning `chacha20` or a version string would make a
      // routine SQLite3MultipleCiphers upgrade look like a security regression, and the
      // cipher *choice* is already pinned structurally by
      // `test_mobile_boundary.py::test_the_build_hook_selects_an_encrypting_sqlite`.
      // An assertion repeated in a fourth place is one that gets deleted rather than updated.
      _evidence('PRAGMA cipher', _firstValue(cipher));
      _evidence(
        'PRAGMA cipher_version (empty distinguishes sqlite3mc from sqlcipher)',
        _firstValue(await database.customSelect('PRAGMA cipher_version;').get()),
      );
      _evidence(
        'sqlite_version',
        _firstValue(await database.customSelect('SELECT sqlite_version();').get()),
      );

      final journalMode =
          _firstValue(await database.customSelect('PRAGMA journal_mode;').get());
      _evidence('journal_mode (NFR-OFF-005)', journalMode);
      expect(
        journalMode,
        'wal',
        reason: 'PHASE 1 — journal_mode is not WAL, so phase 1b would scan a file that '
            'never receives the write it is meant to inspect',
      );

      final uuid = gateClientUuids().first;
      final appended = await outboxOf(database).append(
        clientUuid: uuid,
        operationType: gateOperationType,
        clientCreatedAt: gateCreatedAt,
        payload: gatePayload(0),
      );
      expect(
        appended,
        isA<Ok<OutboxOperation>>(),
        reason: 'PHASE 1 — the row never committed, so every later phase would prove nothing',
      );

      // ---- PHASE 1b — the WAL, inspected WHILE the connection is open --------------
      //
      // **Order matters and this is the reason.** Closing first lets SQLite checkpoint and
      // delete the `-wal`, and scanning a file that no longer exists finds nothing for the
      // wrong reason. Held open, the WAL provably contains the row just written — so a clean
      // scan here is evidence rather than an accident of timing.
      phase = '1b — WAL bytes';
      final wal = File(walPath);
      expect(
        wal.existsSync(),
        isTrue,
        reason: 'PHASE 1b — no -wal beside an open WAL database after a committed write',
      );
      _evidence('-wal size', '${wal.lengthSync()} bytes');
      expect(
        _markersIn(wal),
        isEmpty,
        reason: 'PHASE 1b — plaintext found in the write-ahead log. The newest writes live '
            'here, so a readable WAL is a readable outbox no matter how the main file looks',
      );

      phase = '1c — close';
      await database.close();
      open = null;
      _evidence('phase 1', 'wrote client_uuid=$uuid and closed');

      // ---- PHASE 2 — reopen with the real keystore key -----------------------------
      //
      // `openGateDatabase` builds `PlatformDatabaseKey` over the real platform keystore: same
      // file, same key source, no test double.
      phase = '2 — reopen with the keystore key';
      open = await openGateDatabase();
      final reread = await outboxOf(open).pending(limit: 10);
      final rows = reread.fold((value) => value, (_) => const <OutboxOperation>[]);

      expect(
        rows.map((row) => row.clientUuid),
        contains(uuid),
        reason: 'PHASE 2 — the row written in phase 1 is not readable with the keystore key. '
            'An encrypted database nobody can open is worse than no encryption: §8.3 says a '
            'device locked out with three days of unsent deliveries must still hand them over',
      );
      expect(
        rows.first.payload,
        gatePayload(0),
        reason: 'PHASE 2 — the payload did not survive the round trip intact',
      );
      _evidence('phase 2', 'keystore key recovered ${rows.length} row(s) with payload intact');

      await open.close();
      open = null;

      // ---- PHASE 3 — the negative control ------------------------------------------
      //
      // **A real read must be issued.** `PRAGMA key` validates nothing by itself: the codec
      // accepts any passphrase and only discovers the mismatch when it decrypts page 1. A
      // test that sets a wrong key and asserts no throw would pass against an *unencrypted*
      // database and prove the opposite of what it claims.
      //
      // Drift connects lazily, so the open and the first query are both inside the try: the
      // rejection may surface at `PRAGMA journal_mode` inside `setup` — which reads page 1 —
      // or at the query itself. Where it throws is an implementation detail; that it throws,
      // and as what, is the assertion.
      phase = '3 — wrong key must be refused';
      final wrong = AppDatabase(await openDeviceDatabase(_WrongKey()));
      Object? thrown;
      try {
        final leaked = await wrong.customSelect('SELECT count(*) FROM sqlite_master;').get();
        _evidence('phase 3 LEAK', 'a wrong key read ${_firstValue(leaked)} schema objects');
      } catch (error) {
        thrown = error;
      }
      try {
        await wrong.close();
      } catch (_) {
        // Expected: a connection that never opened cannot be closed cleanly.
      }

      // **Unwrapped, not weakened.** `createInBackground` runs SQLite in a spawned isolate,
      // so the engine's failure arrives as a `DriftRemoteException` carrying the original in
      // `remoteCause`. Accepting that wrapper as the evidence would be the weakening this
      // control exists to prevent — a locked file, a missing table and a serialisation fault
      // all arrive as the same wrapper. The bar is unchanged: a `SqliteException` with code
      // 26. The ternary still accepts an unwrapped throw, so this does not depend on drift
      // continuing to wrap.
      _evidence('phase 3 thrown type', thrown?.runtimeType);
      final Object? cause = thrown is DriftRemoteException ? thrown.remoteCause : thrown;
      _evidence('phase 3 unwrapped cause type', cause?.runtimeType);
      if (cause is SqliteException) {
        _evidence(
          'phase 3 wrong key REJECTED',
          'resultCode=${cause.resultCode} extended=${cause.extendedResultCode} '
          '"${cause.message}"',
        );
      }

      expect(
        cause,
        isA<SqliteException>(),
        reason: 'PHASE 3 — a deliberately wrong key did not fail as a decryption failure. If '
            'nothing threw at all the key is decorative: the file is either unencrypted or '
            'encrypted with something other than the keystore value, and every other '
            'assertion in this file is satisfied vacuously',
      );
      expect(
        (cause as SqliteException).resultCode,
        _sqliteNotADatabase,
        reason: 'PHASE 3 — the wrong key failed, but not as a decryption failure. Another '
            'cause (a lock, an I/O error) would make this control pass for the wrong reason',
      );

      // ---- PHASE 4 — the control did no damage -------------------------------------
      //
      // Phase 3 ran `PRAGMA journal_mode = WAL` against the file with a wrong key. Proving
      // the row is still there is what separates a negative control from a destructive test.
      phase = '4 — the wrong-key attempt was non-destructive';
      open = await openGateDatabase();
      expect(
        (await outboxOf(open).depth()).fold((depth) => depth, (_) => -1),
        1,
        reason: 'PHASE 4 — the wrong-key attempt damaged the database',
      );
      _evidence('phase 4', 'row survives the wrong-key attempt; depth=1');

      phase = '5 — database bytes after close';
      await open.close();
      open = null;

      // ---- PHASE 5 — the main file, after the checkpoint ---------------------------
      final main = File(databasePath);
      final header = main.readAsBytesSync().take(16).toList();
      _evidence(
        'first 16 bytes',
        '${header.map((b) => b.toRadixString(16).padLeft(2, '0')).join(' ')}  '
        '"${latin1.decode(header, allowInvalid: true)}"',
      );
      _evidence('database size', '${main.lengthSync()} bytes');
      expect(
        main.lengthSync(),
        greaterThan(4096),
        reason: 'PHASE 5 — the database is smaller than one page. A scan of an empty file '
            'finds no plaintext for a reason that has nothing to do with encryption',
      );
      expect(
        _markersIn(main),
        isEmpty,
        reason: 'PHASE 5 — plaintext found on disk. NFR-SEC-008 is not met: the file can be '
            'read with adb and any SQLite browser',
      );

      // ---- PHASE 6 — the positive control ------------------------------------------
      //
      // **Phases 1b and 5 assert that a scanner finds nothing.** Nothing is also what a
      // broken scanner, a truncated read and a mis-decoded byte stream find. So the identical
      // function is run against a deliberately *unencrypted* database holding the same row,
      // where it must find the markers. Without this the two assertions above are
      // unfalsifiable — which is precisely the condition that let a plaintext outbox ship.
      //
      // Not `openDeviceDatabase`: a plain `NativeDatabase` with no key, in the cache
      // directory, deleted below. No production path is involved and no real data is written.
      phase = '6 — positive control (the scanner can find plaintext)';
      final controlPath =
          p.join((await getTemporaryDirectory()).path, 'plaintext_control.sqlite');
      final control = AppDatabase(NativeDatabase(File(controlPath)));
      await outboxOf(control).append(
        clientUuid: uuid,
        operationType: gateOperationType,
        clientCreatedAt: gateCreatedAt,
        payload: gatePayload(0),
      );
      await control.close();

      final found = _markersIn(File(controlPath));
      _evidence('phase 6 markers found in the plaintext control', found);
      for (final suffix in const ['', '-wal', '-shm']) {
        final residue = File('$controlPath$suffix');
        if (residue.existsSync()) residue.deleteSync();
      }

      expect(
        found,
        containsAll(<String>['SQLite format 3', 'outbox_operation', 'DELIVERY_COMPLETE']),
        reason: 'PHASE 6 — the scanner could not find plaintext in a file that is definitely '
            'plaintext. Phases 1b and 5 therefore proved nothing, and this gate is broken '
            'rather than passing',
      );

      passed = true;
    },
  );
}
