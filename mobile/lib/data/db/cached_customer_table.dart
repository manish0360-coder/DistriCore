import 'package:drift/drift.dart';

/// The customer round, as the last successful pull left it (M9.4, `05` §11.1).
///
/// **A cache, not a promise.** §5.2's distinction is the one that matters here: losing this
/// table costs a pull, losing `outbox_operation` costs a delivery. That is why this one may
/// be rebuilt from the server and the outbox may not.
///
/// **The primary key is the server's `id`.** D-M9.4-4 makes the cursor comparison
/// `updated_at >= since`, which can resend a boundary row — safe only because an upsert on
/// an immutable server key replaces it rather than inserting a second copy. A local
/// autoincrement key here would turn that safety into duplicate shops on the screen.
///
/// **No money column, deliberately.** `CustomerSerializer` carries `credit_limit_amount` as
/// a decimal string; not storing it keeps P-3 off this path entirely rather than relying on
/// a decoder to stay careful.
@DataClassName('CachedCustomerRow')
class CachedCustomers extends Table {
  @override
  String get tableName => 'cached_customer';

  /// The server's id. Never generated locally.
  IntColumn get id => integer()();

  TextColumn get code => text()();
  TextColumn get shopName => text().named('shop_name')();
  TextColumn get ownerName => text().named('owner_name')();
  TextColumn get phone => text()();
  TextColumn get zoneName => text().named('zone_name')();

  @override
  Set<Column> get primaryKey => {id};
}
