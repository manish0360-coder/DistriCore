// D-C3 — storage exhaustion becomes StorageFull, and nothing else does.
//
// This tests the real mapping function against real `SqliteException` values. Filling a
// device's disk is an `integration_test` concern (see the verification gate); what can be
// proven hermetically is the classification, and that is where the misclassification risk
// actually lives.
// `show`, not a bare import: drift exports its own `isNull`/`isNotNull` query
// builders, which collide with matcher's. Naming what is used keeps both usable.
import 'package:drift/drift.dart'
    show CouldNotRollBackException, DriftWrappedException;

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

  // ---------------------------------------------------------------- wrapped causes
  //
  // The storage gate found these on 2026-09-04. A SQLITE_FULL raised at COMMIT never reaches
  // the repository as a bare SqliteException: SQLite rolls back itself, Drift's own ROLLBACK
  // then finds no transaction, and the real error arrives wrapped. Before this, the wrapper
  // returned null and `append` rethrew — so a genuinely full disk surfaced as a crash rather
  // than as StorageFull, which is precisely the misclassification D-C3 exists to prevent.

  test('SQLITE_FULL wrapped by drift maps to StorageFull', () {
    final failure = storageFailureFor(
      DriftWrappedException(
        message: 'commit failed',
        cause: SqliteException(extendedResultCode: 13, message: 'database or disk is full'),
        trace: StackTrace.current,
      ),
    );
    expect(failure, isA<StorageFull>());
  });

  test('a wrapper does NOT widen the rule — a wrapped constraint violation is still null', () {
    // The property that keeps unwrapping honest: it can reveal a StorageFull that a wrapper
    // hid, never invent one. A duplicate client_uuid inside a wrapped failure is still a bug
    // to fix, not a disk to clear.
    expect(
      storageFailureFor(
        DriftWrappedException(
          message: 'insert failed',
          cause: SqliteException(extendedResultCode: 19, message: 'UNIQUE constraint failed'),
          trace: StackTrace.current,
        ),
      ),
      isNull,
    );
  });

  test('a wrapper around nothing recognisable is still null', () {
    expect(
      storageFailureFor(
        DriftWrappedException(
          message: 'something else',
          cause: StateError('not a sqlite error'),
          trace: StackTrace.current,
        ),
      ),
      isNull,
    );
  });

  // ---------------------------------------------------- the shape the device actually threw
  //
  // Reproduced from drift 2.34.3's own source rather than from memory:
  //
  //   CouldNotRollBackException(this.cause, this.originalStackTrace, this.exception)
  //
  // `cause` is the error that caused the rollback — the SQLITE_FULL. `exception` is the
  // rollback's own failure. Reading the wrong one classifies "cannot rollback" instead of
  // "disk is full", which is how this could look fixed while still failing on a device.

  test('the exact CouldNotRollBackException the storage gate threw maps to StorageFull', () {
    final failure = storageFailureFor(
      CouldNotRollBackException(
        // cause — what the COMMIT raised
        SqliteException(extendedResultCode: 13, message: 'database or disk is full'),
        StackTrace.current,
        // exception — what the ROLLBACK then raised, because SQLite had already rolled back
        SqliteException(
          extendedResultCode: 1,
          message: 'cannot rollback - no transaction is active',
        ),
      ),
    );
    expect(failure, isA<StorageFull>());
  });

  test('the ROLLBACK failure is not what gets classified', () {
    // Inverted: if `exception` were read instead of `cause`, this would come back StorageFull
    // and the test above would pass for the wrong reason.
    final failure = storageFailureFor(
      CouldNotRollBackException(
        SqliteException(extendedResultCode: 19, message: 'UNIQUE constraint failed'),
        StackTrace.current,
        SqliteException(extendedResultCode: 13, message: 'database or disk is full'),
      ),
    );
    expect(failure, isNull);
  });

  test('a cause nested two wrappers deep is still found', () {
    // The chain is walked, not peeled once. `CouldNotRollBackException` — the wrapper the
    // storage gate actually produced — is handled by the same loop and type-checked by the
    // analyzer; it is not constructed here because its constructor arity is not part of
    // drift's documented surface and guessing it is how this file failed to compile once.
    final failure = storageFailureFor(
      DriftWrappedException(
        message: 'outer',
        cause: DriftWrappedException(
          message: 'inner',
          cause: SqliteException(extendedResultCode: 13, message: 'database or disk is full'),
          trace: StackTrace.current,
        ),
        trace: StackTrace.current,
      ),
    );
    expect(failure, isA<StorageFull>());
  });

  test('three wrappers deep — the depth the isolate path actually produces', () {
    // DriftRemoteException -> CouldNotRollBackException -> SqliteException is the real chain
    // when the database runs under `NativeDatabase.createInBackground`. DriftRemoteException
    // has a private constructor and cannot be built here, so DriftWrappedException stands in
    // for the outer layer; what this pins is that `_maxCauseDepth` reaches three levels down.
    final failure = storageFailureFor(
      DriftWrappedException(
        message: 'remote',
        cause: CouldNotRollBackException(
          SqliteException(extendedResultCode: 13, message: 'database or disk is full'),
          StackTrace.current,
          SqliteException(extendedResultCode: 1, message: 'cannot rollback'),
        ),
        trace: StackTrace.current,
      ),
    );
    expect(failure, isA<StorageFull>());
  });
}
