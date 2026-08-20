import 'package:drift/drift.dart';

import '../../core/clock.dart';
import '../db/app_database.dart';

/// The pull cursor (M9.4, `05` §11.1 P-2).
///
/// **`server_time` is carried as the server's own string, never as a `DateTime`.** Parsing
/// and re-rendering would put a device-side formatter between the value that arrived and the
/// value that goes back out, and `05` is explicit about the cost: a `since` that drifts by
/// even a little *"permanently skips every record written in that window"*, silently.
final class SyncCursorStore {
  const SyncCursorStore(this._db, this._clock);

  final AppDatabase _db;
  final Clock _clock;

  /// The `since` for the next pull, or `null` if none has ever completed.
  ///
  /// **`null` is not an empty string and not an epoch.** It means the next request omits
  /// `since` entirely, which P-1 makes a full bootstrap.
  Future<String?> read() async {
    final row = await _db.select(_db.syncCursors).getSingleOrNull();
    final value = row?.serverTime;
    return value == null || value.isEmpty ? null : value;
  }

  /// Advance the cursor. **Called once per pull, after the final page is durably applied**
  /// (D-M9.4-5).
  ///
  /// Advancing page by page would let a crash mid-sequence skip every page not yet fetched —
  /// permanently, and with nothing to report it. FR-SYN-004 and FR-SYN-017 both forbid it.
  /// This store cannot enforce that on its own; it is stated here because this is where a
  /// future reader will look for the rule.
  Future<void> write(String serverTime) =>
      _db.into(_db.syncCursors).insertOnConflictUpdate(
            SyncCursorsCompanion.insert(
              id: const Value(1),
              serverTime: Value(serverTime),
              // Diagnostic only — the *server's* instant is `serverTime`, and this one never
              // reaches the wire.
              updatedAt: _clock.nowUtc().toIso8601String(),
            ),
          );
}
