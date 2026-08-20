import 'package:drift/drift.dart';

import '../../domain/customer/customer.dart';
import '../db/app_database.dart';

/// The cached customer round (M9.4, `05` §11.1).
///
/// Plain futures rather than `Result`, following `IdentityCache`: these are local reads and
/// writes inside `data/`, and the repository that calls them is the one that owes the caller
/// a `Failure`.
final class CustomerCache {
  const CustomerCache(this._db);

  final AppDatabase _db;

  /// Every cached shop, ordered by name so a round reads the same way twice.
  Future<List<Customer>> read() async {
    final rows = await (_db.select(_db.cachedCustomers)
          ..orderBy([(row) => OrderingTerm.asc(row.shopName)]))
        .get();
    return [
      for (final row in rows)
        Customer(
          id: row.id,
          code: row.code,
          shopName: row.shopName,
          ownerName: row.ownerName,
          phone: row.phone,
          zoneName: row.zoneName,
        ),
    ];
  }

  /// **Upsert on the server's `id`.** This is what makes D-M9.4-4's inclusive cursor safe:
  /// `updated_at >= since` can resend the boundary row on every pull, and an upsert replaces
  /// it where an insert would stack duplicates of one shop.
  ///
  /// One batch, so a page applies whole or not at all.
  Future<void> save(Iterable<Customer> customers) async {
    if (customers.isEmpty) return;
    await _db.batch((batch) {
      batch.insertAllOnConflictUpdate(_db.cachedCustomers, [
        for (final customer in customers)
          CachedCustomersCompanion.insert(
            id: Value(customer.id),
            code: customer.code,
            shopName: customer.shopName,
            ownerName: customer.ownerName,
            phone: customer.phone,
            zoneName: customer.zoneName,
          ),
      ]);
    });
  }

  /// **The only removal path** (D-M9.4-3), and it takes explicit ids.
  ///
  /// There is deliberately no "delete everything not in this list": under P-5 a delta pull
  /// returns only what changed, so absence describes almost every row the device holds, and
  /// deleting on absence would empty the cache on the first incremental pull.
  Future<int> remove(Iterable<int> ids) async {
    final targets = ids.toList();
    if (targets.isEmpty) return 0;
    return (_db.delete(_db.cachedCustomers)..where((row) => row.id.isIn(targets))).go();
  }
}
