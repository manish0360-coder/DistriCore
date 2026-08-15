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

  return NativeDatabase.createInBackground(
    file,
    setup: (database) async {
      final key = await keys.key();
      if (key != null) {
        // SQLCipher requires the key before any other statement on the connection.
        database.execute("PRAGMA key = '$key'");
      }
      // NFR-OFF-005: the outbox must survive a kill. WAL plus FULL synchronous is what
      // makes "committed" mean "on disk" rather than "in a page cache the OS may lose".
      database.execute('PRAGMA journal_mode = WAL');
      database.execute('PRAGMA synchronous = FULL');
    },
  );
}
