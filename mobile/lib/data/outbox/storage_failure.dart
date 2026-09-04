import 'package:drift/drift.dart';
// `remote.dart` is where DriftRemoteException lives. It is marked experimental and
// analyze says so; the alternative is not classifying a full disk at all, because
// `NativeDatabase.createInBackground` routes every error through this type.
// ignore: implementation_imports
import 'package:drift/remote.dart';
import 'package:sqlite3/common.dart';

import '../../core/failure.dart';

/// SQLite result codes. Named rather than inlined so the mapping below can be read against
/// the SQLite documentation without a lookup.
const int _sqliteFull = 13; // SQLITE_FULL — "database or disk is full"
const int _sqliteIoErrWrite = 778; // SQLITE_IOERR_WRITE — extended (10 | 3<<8)

/// **D-C3 — storage exhaustion becomes [StorageFull]; nothing else does.**
///
/// The narrowness is the requirement. Catching `SqliteException` wholesale would map a
/// constraint violation, a corrupt file and a locked database to "disk full", and the user
/// would be told to free space to fix a bug. So exactly two codes map:
///
/// * `SQLITE_FULL` (13) — the engine says the disk or database is full.
/// * `SQLITE_IOERR_WRITE` (778) — the write itself failed at the OS layer, which is how a
///   full filesystem often surfaces rather than as 13.
///
/// **Everything else is rethrown**, keeping its original semantics for the caller above.
///
/// ## Wrapped causes, and why unwrapping does not widen this
///
/// The two codes above are what maps. But a `SQLITE_FULL` raised at **`COMMIT`** does not
/// reach a caller as a bare `SqliteException`. SQLite rolls the transaction back itself when
/// a commit fails for lack of space; Drift then issues its own `ROLLBACK`, finds no active
/// transaction, and throws [CouldNotRollBackException] carrying the original error as its
/// cause. Measured 2026-09-04 by the storage gate:
///
/// ```
/// SqliteException(13): database or disk is full ... during COMMIT
/// CouldNotRollBackException: cannot rollback - no transaction is active
/// ```
///
/// The rollback "failure" is Drift discovering work SQLite had already done, not a
/// half-committed transaction — the row simply is not there, which is what phase B asserts.
///
/// So the chain is walked and **the same two codes decide**. A wrapper cannot make something
/// `StorageFull` that a bare exception would not; it can only stop a wrapper from hiding one.
/// The depth bound exists so a cyclic `cause` cannot spin here.
Failure? storageFailureFor(Object error) {
  var candidate = error;
  for (var depth = 0; depth < _maxCauseDepth; depth++) {
    final failure = _classify(candidate);
    if (failure != null) return failure;
    final cause = _causeOf(candidate);
    if (cause == null) return null;
    candidate = cause;
  }
  return null;
}

/// How far to follow `cause`. The deepest real chain is three levels —
/// `DriftRemoteException` -> `CouldNotRollBackException` -> `SqliteException` — so four is one
/// step of slack, not a design allowance.
const int _maxCauseDepth = 4;

/// The rule itself, unchanged: exactly two result codes, and nothing else.
Failure? _classify(Object error) {
  if (error is! SqliteException) return null;
  final extended = error.extendedResultCode;
  if (error.resultCode == _sqliteFull || extended == _sqliteFull) {
    return const StorageFull();
  }
  if (extended == _sqliteIoErrWrite) {
    return const StorageFull('The device could not write to storage.');
  }
  return null;
}

/// The exception Drift hid the real one inside, or `null` when there is nothing beneath.
Object? _causeOf(Object error) {
  // **The isolate boundary, and the reason the first fix did not work.**
  //
  // `connection.dart` opens the database with `NativeDatabase.createInBackground`, which runs
  // it in a spawned isolate. Every error from that isolate reaches the caller wrapped in
  // `DriftRemoteException`, so a chain that knew only about the transaction wrappers stopped
  // one level too early and a genuinely full disk still escaped as a crash.
  //
  // The object survives the boundary intact: `connectToServer` probes the port with a plain
  // instance and, when that succeeds — as it does between isolates of one program — sets
  // `serialize = false`. Only the serialising path would replace the error with its
  // `toString()`, and that path is not taken here. So the `SqliteException` on the far side
  // is the same object, and matching it by type is sound rather than lucky.
  if (error is DriftRemoteException) return error.remoteCause;
  // `cause` is the error that CAUSED the rollback — the original SQLITE_FULL. `exception` is
  // the rollback's own failure ("cannot rollback - no transaction is active"), which is Drift
  // discovering that SQLite had already rolled back. Reading `exception` here would classify
  // the wrong one.
  if (error is CouldNotRollBackException) return error.cause;
  if (error is DriftWrappedException) return error.cause;
  return null;
}
