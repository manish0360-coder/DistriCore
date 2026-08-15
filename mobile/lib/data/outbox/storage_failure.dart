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
Failure? storageFailureFor(Object error) {
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
