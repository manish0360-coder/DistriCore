import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/repositories/identity_cache.dart';
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

/// A real in-memory SQLite database and the identity cache over it.
///
/// **Not a fake.** `outbox_test.dart` states the reason for the outbox and it holds here
/// too: the single-row `CHECK`, the `insertOnConflictUpdate` replacement and the JSON
/// round-trip are behaviours of the engine, and asserting them against a stand-in asserts
/// nothing. Registers its own tear-down, so a caller cannot leak a connection.
///
/// **It is not encrypted, and that is not a gap.** Since `source: sqlite3mc` the test host
/// links the same encrypting library the device does — the old claim that `flutter test`
/// links *"the system SQLite"* was never accurate — but `NativeDatabase.memory()` is opened
/// with **no key and no file**, so nothing here proves anything about encryption at rest.
/// That evidence is a device's to give: `make mobile-device-encryption`.
({AppDatabase db, IdentityCache identity}) memoryIdentity() {
  final db = AppDatabase(NativeDatabase.memory());
  addTearDown(db.close);
  return (db: db, identity: IdentityCache(db));
}
