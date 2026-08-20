// M9.4 step B — the cache repositories and the cursor store.
//
// Against a **real in-memory SQLite database**. The properties here are engine behaviours —
// upsert on a primary key, delete by explicit id, a single-row constraint — and a fake would
// agree with whatever the code did rather than with SQLite.
//
// **One `AppDatabase` per test**, registered by `wire()`.
import 'package:districore/core/clock.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/repositories/customer_cache.dart';
import 'package:districore/data/repositories/delivery_cache.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/data/repositories/identity_cache.dart';
import 'package:districore/data/repositories/sync_cursor_store.dart';
import 'package:districore/domain/customer/customer.dart';
import 'package:districore/domain/delivery/delivery.dart';
import 'package:districore/domain/identity/role.dart';
import 'package:districore/domain/identity/session.dart';
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

final _now = DateTime.utc(2026, 8, 16, 12);

const _session = Session(
  userId: 12,
  fullName: 'Ramesh Kumar',
  roles: {Role.salesman},
  customerId: null,
);

typedef Env = ({
  AppDatabase db,
  CustomerCache customers,
  DeliveryCache deliveries,
  SyncCursorStore cursor,
});

Env wire() {
  final db = AppDatabase(NativeDatabase.memory());
  addTearDown(db.close);
  return (
    db: db,
    customers: CustomerCache(db),
    deliveries: DeliveryCache(db),
    cursor: SyncCursorStore(db, FixedClock(_now)),
  );
}

Customer customer({int id = 142, String shopName = 'Sharma Kirana', String phone = ''}) =>
    Customer(
      id: id,
      code: 'CUS-000$id',
      shopName: shopName,
      ownerName: 'Ramesh Sharma',
      phone: phone,
      zoneName: 'Patna East',
    );

Delivery delivery({
  int id = 3312,
  DeliveryStatus status = DeliveryStatus.dispatched,
  String? recipientName,
  DateTime? deliveredAt,
}) =>
    Delivery(
      id: id,
      orderNumber: 'SO-$id',
      customerName: 'Sharma Kirana',
      status: status,
      recipientName: recipientName,
      deliveredAt: deliveredAt,
    );

void main() {
  group('customer cache', () {
    test('1. an insert round-trips every field', () async {
      final env = wire();

      await env.customers.save([customer()]);

      final stored = (await env.customers.read()).single;
      expect(stored.id, 142);
      expect(stored.code, 'CUS-000142');
      expect(stored.shopName, 'Sharma Kirana');
      expect(stored.ownerName, 'Ramesh Sharma');
      expect(stored.zoneName, 'Patna East');
      // Not visited: the cache holds the server's facts, never the outbox's.
      expect(stored.visitedThisRound, isFalse);
    });

    test('2. a resend of the same id replaces rather than duplicates', () async {
      // **The property that makes D-M9.4-4 safe.** `updated_at >= since` resends the
      // boundary row on every pull; without upsert-on-server-id that is a duplicate shop
      // on screen each time.
      final env = wire();

      await env.customers.save([customer(shopName: 'Sharma Kirana')]);
      await env.customers.save([customer(shopName: 'Sharma Kirana & Sons')]);

      final rows = await env.customers.read();
      expect(rows, hasLength(1));
      expect(rows.single.shopName, 'Sharma Kirana & Sons');
    });

    test('3. delete removes exactly the ids given', () async {
      final env = wire();
      await env.customers.save([customer(id: 1), customer(id: 2), customer(id: 3)]);

      final removed = await env.customers.remove([2]);

      expect(removed, 1);
      expect((await env.customers.read()).map((c) => c.id).toList(), [1, 3]);
    });

    test('4. a customer absent from a save is untouched', () async {
      // D-M9.4-3: absence is not deletion. A delta pull returns only what changed, so this
      // is the normal case on every incremental sync.
      final env = wire();
      await env.customers.save([customer(id: 1), customer(id: 2)]);

      await env.customers.save([customer(id: 1, shopName: 'Renamed')]);

      final rows = await env.customers.read();
      expect(rows.map((c) => c.id).toList(), [1, 2]);
      expect(rows.firstWhere((c) => c.id == 1).shopName, 'Renamed');
    });

    test('an empty save and an empty delete are no-ops', () async {
      final env = wire();
      await env.customers.save([customer()]);

      await env.customers.save(const []);
      expect(await env.customers.remove(const []), 0);

      expect(await env.customers.read(), hasLength(1));
    });
  });

  group('delivery cache', () {
    test('5. an insert round-trips every field, including the nullable ones', () async {
      final env = wire();
      final at = DateTime.utc(2026, 8, 16, 9, 41, 10);

      await env.deliveries.save([
        delivery(status: DeliveryStatus.delivered, recipientName: 'Sharma ji', deliveredAt: at),
      ]);

      final stored = (await env.deliveries.read()).single;
      expect(stored.id, 3312);
      expect(stored.orderNumber, 'SO-3312');
      expect(stored.status, DeliveryStatus.delivered);
      expect(stored.recipientName, 'Sharma ji');
      expect(stored.deliveredAt, at);
    });

    test('nulls survive as nulls, not as empty strings', () async {
      final env = wire();

      await env.deliveries.save([delivery()]);

      final stored = (await env.deliveries.read()).single;
      expect(stored.recipientName, isNull);
      expect(stored.deliveredAt, isNull);
      expect(stored.canComplete, isTrue);
    });

    test('6. a resend of the same id replaces rather than duplicates', () async {
      final env = wire();

      await env.deliveries.save([delivery(status: DeliveryStatus.dispatched)]);
      await env.deliveries.save([
        delivery(status: DeliveryStatus.delivered, recipientName: 'Sharma ji'),
      ]);

      final rows = await env.deliveries.read();
      expect(rows, hasLength(1));
      expect(rows.single.status, DeliveryStatus.delivered);
      expect(rows.single.recipientName, 'Sharma ji');
    });

    test('an unknown status degrades rather than throwing', () async {
      // A server that adds a state must not brick an installed app; `unknown` offers no
      // action, so the row is visible and read-only.
      final env = wire();
      await env.db.customStatement(
        "INSERT INTO cached_delivery (id, order_number, customer_name, status) "
        "VALUES (99, 'SO-99', 'Shop', 'QUANTUM_SUPERPOSITION')",
      );

      final stored = (await env.deliveries.read()).single;
      expect(stored.status, DeliveryStatus.unknown);
      expect(stored.canComplete, isFalse);
    });
  });

  group('sync cursor', () {
    test('7. it starts empty — no pull has ever completed', () async {
      final env = wire();

      // `null`, not "" and not an epoch: the next request omits `since` entirely and P-1
      // makes it a full bootstrap.
      expect(await env.cursor.read(), isNull);
    });

    test('8. a write/read round trip preserves the exact server string', () async {
      // **Verbatim.** Parsing and re-rendering would put a device-side formatter between
      // the value that arrived and the value that goes back — the drift `05` warns about.
      final env = wire();
      const serverTime = '2026-08-05T11:20:05.123456Z';

      await env.cursor.write(serverTime);

      expect(await env.cursor.read(), serverTime);
    });

    test('9. a second write replaces the first, leaving one row', () async {
      final env = wire();

      await env.cursor.write('2026-08-05T11:20:05Z');
      await env.cursor.write('2026-08-06T07:00:00Z');

      expect(await env.cursor.read(), '2026-08-06T07:00:00Z');
      expect(await env.db.select(env.db.syncCursors).get(), hasLength(1));
    });
  });

  group('the cache never touches the promise', () {
    test('10 & 11. outbox rows and the cached identity are untouched', () async {
      // §5.2: a cache is a convenience, an outbox is a promise. These three repositories
      // write only their own tables, and this is the assertion that keeps it true.
      final env = wire();
      final outbox = DriftOutboxRepository(env.db);
      await outbox.append(
        clientUuid: '11111111-2222-4333-8444-555555555555',
        operationType: 'DELIVERY_COMPLETE',
        clientCreatedAt: _now,
        payload: <String, Object?>{'delivery_id': 3312, 'amount': '1180.00'},
      );
      await IdentityCache(env.db).save(_session);
      final before = await env.db.select(env.db.outboxOperations).get();

      await env.customers.save([customer(id: 1), customer(id: 2)]);
      await env.customers.remove([1]);
      await env.deliveries.save([delivery()]);
      await env.cursor.write('2026-08-06T07:00:00Z');

      final after = await env.db.select(env.db.outboxOperations).get();
      expect(after.map((r) => r.sequence).toList(), before.map((r) => r.sequence).toList());
      expect(after.single.payload, before.single.payload);
      expect(after.single.status, before.single.status);

      final identity = await IdentityCache(env.db).read();
      expect(identity, isNotNull);
      expect(identity!.userId, 12);
      expect(identity.roles, {Role.salesman});
    });
  });
}
