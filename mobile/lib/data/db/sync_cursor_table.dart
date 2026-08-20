import 'package:drift/drift.dart';

/// The pull cursor — one row, one device (M9.4, `05` §11.1 P-2).
///
/// **`server_time` is stored verbatim, as the server's own ISO-8601 string.** Parsing it into
/// a `DateTime` and re-rendering it would put a device-side formatter between the value that
/// arrived and the value that goes back out, and `05` is explicit about why that matters:
/// *"a device whose clock is five minutes fast would send a `since` in the future and
/// permanently skip every record written in that window."* The bytes that came in are the
/// bytes that leave.
///
/// **`null` means no successful pull has ever completed**, so the next request omits `since`
/// entirely and P-1 makes it a full bootstrap. That is not the same as an empty string or an
/// epoch, and it is the reason the column is nullable.
///
/// **Written only after the final page of a pull is durably applied** (D-M9.4-5). Advancing
/// page by page would let a crash mid-sequence skip every page not yet fetched, permanently —
/// FR-SYN-004 and FR-SYN-017 both forbid it.
@DataClassName('SyncCursorRow')
class SyncCursors extends Table {
  @override
  String get tableName => 'sync_cursor';

  /// **Always 1.** One device, one cursor; a second row would make "which cursor?" a
  /// question every reader has to answer. Enforced by the database, as `local_identity` is.
  IntColumn get id => integer().withDefault(const Constant(1))();

  TextColumn get serverTime => text().named('server_time').nullable()();

  /// When this device last wrote the cursor. Diagnostic only — the *server's* instant is
  /// `server_time`, and this one never reaches the wire.
  TextColumn get updatedAt => text().named('updated_at')();

  @override
  Set<Column> get primaryKey => {id};

  @override
  List<String> get customConstraints => const ['CHECK (id = 1)'];
}
