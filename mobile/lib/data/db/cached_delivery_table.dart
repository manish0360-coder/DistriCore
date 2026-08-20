import 'package:drift/drift.dart';

/// The delivery round, as the last successful pull left it (M9.4, `05` §11.1).
///
/// Same contract as `cached_customer`: server `id` as the primary key, so D-M9.4-4's
/// inclusive cursor resends a row into an upsert rather than into a duplicate.
///
/// **`05` §11.1 gives deliveries `{updated}` and no `deactivated_ids`** — a delivery is never
/// deactivated, it reaches a terminal status and stays visible. There is therefore no removal
/// path for this table at all, and D-M9.4-3 forbids inventing one from absence.
@DataClassName('CachedDeliveryRow')
class CachedDeliveries extends Table {
  @override
  String get tableName => 'cached_delivery';

  /// The server's id. Never generated locally.
  IntColumn get id => integer()();

  TextColumn get orderNumber => text().named('order_number')();
  TextColumn get customerName => text().named('customer_name')();

  /// `DeliveryStatus.code`, not an ordinal: reordering the Dart enum must not reinterpret a
  /// row already sitting on a device — the same rule `outbox_operation.status` follows.
  TextColumn get status => text()();

  TextColumn get recipientName => text().named('recipient_name').nullable()();

  /// ISO-8601 UTC text, matching the wire form. **Device time** (`05` §10.3) and a label
  /// only — P-4 keeps it off any ordering path.
  TextColumn get deliveredAt => text().named('delivered_at').nullable()();

  @override
  Set<Column> get primaryKey => {id};
}
