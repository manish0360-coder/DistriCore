import 'package:drift/drift.dart';

/// The outbox table (M8 §5.3; row shape frozen by `04` T-26 and `05` §11.2).
///
/// **Six columns, and the absences are as deliberate as the presences.** There is no
/// `device_id` (D-C4 — `05` §11.2 carries it once per batch, from the keystore), no
/// `retry_count` (that is `04` T-26's *server* row), and no separate sequence column
/// (D-C1 — the primary key is the sequence).
@DataClassName('OutboxRow')
class OutboxOperations extends Table {
  @override
  String get tableName => 'outbox_operation';

  /// **D-C1.** Drift's `autoIncrement()` emits `INTEGER PRIMARY KEY AUTOINCREMENT`, which
  /// is the whole decision: plain `INTEGER PRIMARY KEY` assigns `max(rowid) + 1`, so
  /// purging the highest acknowledged row would **reissue a value already used** and break
  /// the ordering guarantee. `AUTOINCREMENT` is the only SQLite construct that forbids
  /// reuse, and §5.3 requires that purge.
  IntColumn get sequence => integer().autoIncrement()();

  /// **P-6 / C-2 / AD-09.** Unique because I-6 is explicit that the guarantee is *"a
  /// database unique constraint, not an application check — a concurrent double-submit
  /// would defeat an application check."*
  TextColumn get clientUuid => text().named('client_uuid').unique()();

  TextColumn get operationType => text().named('operation_type')();

  /// ISO-8601 UTC text, matching `05`'s wire form exactly.
  ///
  /// Stored as text rather than through Drift's `dateTime()`, which persists epoch
  /// **seconds** and would silently truncate sub-second precision on a value the server
  /// will echo back. It is metadata (D-C2), but metadata that round-trips.
  TextColumn get clientCreatedAt => text().named('client_created_at')();

  /// The request body M9 will send, as JSON text. Stored verbatim and never rewritten.
  TextColumn get payload => text()();

  /// The `OutboxStatus.code` string, not an ordinal: reordering the enum must not
  /// reinterpret rows already sitting on a device.
  TextColumn get status => text()();
}
