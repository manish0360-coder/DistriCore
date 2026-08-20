import 'package:drift/drift.dart';

import '../../domain/delivery/delivery.dart';
import '../db/app_database.dart';

/// The cached delivery round (M9.4, `05` §11.1).
///
/// **No removal method exists, and that is the contract rather than an omission.** §11.1
/// gives deliveries `{updated}` and no `deactivated_ids` — a delivery is never deactivated,
/// it reaches a terminal status and stays visible. D-M9.4-3 forbids inferring a deletion
/// from absence, so there is nothing here that could delete a row.
final class DeliveryCache {
  const DeliveryCache(this._db);

  final AppDatabase _db;

  /// Every cached delivery, in server id order — the order the round was assigned in.
  Future<List<Delivery>> read() async {
    final rows = await (_db.select(_db.cachedDeliveries)
          ..orderBy([(row) => OrderingTerm.asc(row.id)]))
        .get();
    return [
      for (final row in rows)
        Delivery(
          id: row.id,
          orderNumber: row.orderNumber,
          customerName: row.customerName,
          // Unknown codes degrade rather than throw: a server that adds a state must not
          // brick an installed app, and `unknown` offers no action.
          status: DeliveryStatus.fromCode(row.status),
          recipientName:
              row.recipientName != null && row.recipientName!.isNotEmpty
                  ? row.recipientName
                  : null,
          deliveredAt: row.deliveredAt == null
              ? null
              : DateTime.tryParse(row.deliveredAt!)?.toUtc(),
        ),
    ];
  }

  /// **Upsert on the server's `id`** — the same reason as `CustomerCache.save`: D-M9.4-4's
  /// `>=` cursor resends boundary rows, and only an immutable-key upsert makes that harmless.
  Future<void> save(Iterable<Delivery> deliveries) async {
    if (deliveries.isEmpty) return;
    await _db.batch((batch) {
      batch.insertAllOnConflictUpdate(_db.cachedDeliveries, [
        for (final delivery in deliveries)
          CachedDeliveriesCompanion.insert(
            id: Value(delivery.id),
            orderNumber: delivery.orderNumber,
            customerName: delivery.customerName,
            // The code, never an ordinal: reordering the Dart enum must not reinterpret a
            // row already on a device.
            status: delivery.status.code,
            recipientName: Value(delivery.recipientName),
            deliveredAt: Value(delivery.deliveredAt?.toUtc().toIso8601String()),
          ),
      ]);
    });
  }
}
