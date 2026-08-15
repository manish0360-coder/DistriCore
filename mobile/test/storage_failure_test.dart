// D-C3 — storage exhaustion becomes StorageFull, and nothing else does.
//
// This tests the real mapping function against real `SqliteException` values. Filling a
// device's disk is an `integration_test` concern (see the verification gate); what can be
// proven hermetically is the classification, and that is where the misclassification risk
// actually lives.
import 'package:districore/core/failure.dart';
import 'package:districore/data/outbox/storage_failure.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqlite3/common.dart';

void main() {
  test('SQLITE_FULL maps to StorageFull', () {
    final failure = storageFailureFor(
      SqliteException(extendedResultCode: 13, message: 'database or disk is full'),
    );
    expect(failure, isA<StorageFull>());
  });

  test('SQLITE_IOERR_WRITE maps to StorageFull — how a full filesystem often surfaces', () {
    final failure = storageFailureFor(
      SqliteException(extendedResultCode: 778, message: 'disk I/O error'),
    );
    expect(failure, isA<StorageFull>());
  });

  test('a constraint violation is NOT StorageFull', () {
    // The misclassification that would matter: telling a user to free space to fix a
    // duplicate client_uuid.
    expect(
      storageFailureFor(
        SqliteException(extendedResultCode: 19, message: 'UNIQUE constraint failed'),
      ),
      isNull,
    );
  });

  test('corruption and busy are NOT StorageFull', () {
    expect(
      storageFailureFor(
        SqliteException(extendedResultCode: 11, message: 'database disk image is malformed'),
      ),
      isNull,
    );
    expect(
      storageFailureFor(
        SqliteException(extendedResultCode: 5, message: 'database is locked'),
      ),
      isNull,
    );
  });

  test('a non-SQLite error is not classified at all', () {
    expect(storageFailureFor(StateError('unrelated')), isNull);
  });

  test('StorageFull is distinct from Offline — they demand opposite behaviour', () {
    const full = StorageFull();
    expect(full, isNot(isA<Offline>()));
    expect(full, isA<Failure>());
  });
}
