// M8 T6 — the customer round and visit capture, **cache-first since M9.4**.
//
// Same two levels as the delivery slice: the repository against a real in-memory SQLite
// cache and outbox, the screen against the `CustomerRepository` port with a hand-written
// fake. One `wire()` per test — it registers `addTearDown(db.close)`, so a second call in one
// test would leave two live `AppDatabase` objects.
//
// **The network is gone from this file**, because it is gone from the repository. Fetching,
// parsing and payload validation moved to `PullService` (`pull_slice_test.dart`). What stays
// here is what T6 still owns: the visit overlay, `client_uuid` behaviour, and the screen.
import 'dart:async';

import 'package:districore/core/clock.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/core/result.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/repositories/customer_cache.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/data/repositories/outbox_customer_repository.dart';
import 'package:districore/data/repositories/sync_cursor_store.dart';
import 'package:districore/domain/customer/customer.dart';
import 'package:districore/domain/customer/customer_repository.dart';
import 'package:districore/domain/outbox/outbox_repository.dart';
import 'package:districore/domain/outbox/outbox_status.dart';
import 'package:districore/domain/sync/cached_round.dart';
import 'package:districore/domain/visit/visit_outcome.dart';
import 'package:districore/features/customers/customer_controller.dart';
import 'package:districore/features/customers/customer_providers.dart';
import 'package:districore/features/customers/customers_screen.dart';
import 'package:drift/native.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

final _now = DateTime.utc(2026, 8, 16, 11);
const _pulledAt = '2026-08-16T08:00:00.000000Z';

const _customer = Customer(
  id: 142,
  code: 'CUS-000142',
  shopName: 'Sharma Kirana',
  ownerName: 'Ramesh Sharma',
  phone: '+919876543210',
  zoneName: 'Patna East',
);

typedef Env = ({
  CustomerRepository customers,
  OutboxRepository outbox,
  CustomerCache cache,
  SyncCursorStore cursor,
  AppDatabase db,
});

Env wire() {
  final db = AppDatabase(NativeDatabase.memory());
  addTearDown(db.close);
  final outbox = DriftOutboxRepository(db);
  final cache = CustomerCache(db);
  final cursor = SyncCursorStore(db, FixedClock(_now));
  return (
    customers: OutboxCustomerRepository(
      cache: cache,
      outbox: outbox,
      cursor: cursor,
      clock: FixedClock(_now),
    ),
    outbox: outbox,
    cache: cache,
    cursor: cursor,
    db: db,
  );
}

T ok<T>(Result<T> result) => result.fold((v) => v, (f) => fail('expected Ok, got $f'));

void main() {
  group('cache-first reads (M9.4)', () {
    test('the round comes from the cache, with no network anywhere', () async {
      final env = wire();
      await env.cache.save([_customer]);
      await env.cursor.write(_pulledAt);

      final round = ok(await env.customers.customers());

      expect(round.rows.single.id, 142);
      expect(round.rows.single.shopName, 'Sharma Kirana');
      expect(round.rows.single.zoneName, 'Patna East');
      expect(round.rows.single.visitedThisRound, isFalse);
    });

    test('asOf is the server_time of the last completed pull', () async {
      final env = wire();
      await env.cache.save([_customer]);
      await env.cursor.write(_pulledAt);

      expect(ok(await env.customers.customers()).asOf, DateTime.utc(2026, 8, 16, 8));
    });

    test('asOf is null before the first pull, and the round is simply empty', () async {
      // `null` means *never synced* — a different claim from a round taken this morning.
      final env = wire();

      final round = ok(await env.customers.customers());

      expect(round.asOf, isNull);
      expect(round.rows, isEmpty);
    });
  });

  group('recording a visit', () {
    test('writes exactly one durable PENDING VISIT_CREATE with the frozen payload', () async {
      final env = wire();

      final visited = ok(await env.customers.recordVisit(
        customer: _customer,
        outcome: VisitOutcome.noOrder,
      ));

      final queued = ok(await env.outbox.pending());
      expect(queued, hasLength(1));
      final operation = queued.single;
      expect(operation.operationType, 'VISIT_CREATE');
      expect(operation.status, OutboxStatus.pending);
      expect(operation.payload['customer_id'], 142);
      // `ck_visit_outcome` permits exactly three values; this is one of them.
      expect(operation.payload['outcome'], 'NO_ORDER');
      expect(operation.payload['visited_at'], _now.toIso8601String());
      // Task 6 owns GPS and the photo. Absent, not zeroed — a false fix is worse than none.
      expect(operation.payload.containsKey('latitude'), isFalse);
      expect(operation.payload.containsKey('photo_media_id'), isFalse);
      // D-C4 — `device_id` rides once per batch, not per row.
      expect(operation.payload.containsKey('device_id'), isFalse);
      expect(visited.lastOutcome, VisitOutcome.noOrder);
    });

    test('notes are carried only when there are any', () async {
      final env = wire();

      await env.customers.recordVisit(
        customer: _customer,
        outcome: VisitOutcome.shopClosed,
        notes: 'Shutter down, back Monday',
      );

      final payload = ok(await env.outbox.pending()).single.payload;
      expect(payload['notes'], 'Shutter down, back Monday');
      expect(payload['outcome'], 'SHOP_CLOSED');
    });

    test('the action needs no network at all', () async {
      // Structural since M9.4: this repository holds no HTTP client, so there is nothing a
      // visit could await.
      final env = wire();

      final result = await env.customers.recordVisit(
        customer: _customer,
        outcome: VisitOutcome.orderTaken,
      );

      expect(result, isA<Ok<Customer>>());
      expect(ok(await env.outbox.depth()), 1, reason: 'on disk before it returns (§5.3)');
    });

    test('two calls on one shop are TWO visits, not a replay', () async {
      // **The deliberate difference from a delivery.** `04` T-visit has no per-customer
      // uniqueness, and a salesman may legitimately return in the afternoon. Collapsing
      // these — which is right for a parcel — would silently discard a real call.
      final env = wire();

      await env.customers.recordVisit(customer: _customer, outcome: VisitOutcome.shopClosed);
      await env.customers.recordVisit(customer: _customer, outcome: VisitOutcome.orderTaken);

      final queued = ok(await env.outbox.pending());
      expect(queued, hasLength(2));
      expect(queued.map((op) => op.clientUuid).toSet(), hasLength(2));
      expect(queued.map((op) => op.sequence).toList(), [1, 2]);
    });

    test('each visit carries a well-formed v4 client_uuid', () async {
      final env = wire();
      await env.customers.recordVisit(customer: _customer, outcome: VisitOutcome.noOrder);

      expect(
        ok(await env.outbox.pending()).single.clientUuid,
        matches(
          RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'),
        ),
      );
    });
  });

  group('the local result is what the salesman sees', () {
    test('a queued visit is overlaid on the cached round', () async {
      final env = wire();
      await env.cache.save([_customer]);
      await env.customers.recordVisit(customer: _customer, outcome: VisitOutcome.orderTaken);

      final round = ok(await env.customers.customers());

      expect(round.rows.single.visitedThisRound, isTrue);
      expect(round.rows.single.lastOutcome, VisitOutcome.orderTaken);
      expect(round.rows.single.visitedAt, _now);
    });

    test('the overlay leaves the cache itself untouched', () async {
      // A read-time projection, not a write. The cache keeps holding the server's facts.
      final env = wire();
      await env.cache.save([_customer]);
      await env.customers.recordVisit(customer: _customer, outcome: VisitOutcome.orderTaken);

      expect((await env.cache.read()).single.visitedThisRound, isFalse);
    });

    test('the latest visit wins the overlay, and it survives a restart', () async {
      final env = wire();
      await env.cache.save([_customer]);
      await env.customers.recordVisit(customer: _customer, outcome: VisitOutcome.shopClosed);
      await env.customers.recordVisit(customer: _customer, outcome: VisitOutcome.orderTaken);

      // A fresh repository over the same database — the app killed and relaunched.
      final relaunched = OutboxCustomerRepository(
        cache: CustomerCache(env.db),
        outbox: DriftOutboxRepository(env.db),
        cursor: SyncCursorStore(env.db, FixedClock(_now)),
        clock: FixedClock(_now.add(const Duration(hours: 3))),
      );

      final round = ok(await relaunched.customers());

      expect(round.rows.single.lastOutcome, VisitOutcome.orderTaken,
          reason: 'sequence order (D-C2) decides, not the clock');
      expect(round.rows.single.visitedAt, _now);
    });

    test('a delivery queued alongside does not appear as a visit', () async {
      // One outbox, several operation types. The overlay must read only its own.
      final env = wire();
      await env.cache.save([_customer]);
      await env.outbox.append(
        clientUuid: '11111111-2222-4333-8444-555555555555',
        operationType: 'DELIVERY_COMPLETE',
        clientCreatedAt: _now,
        payload: <String, Object?>{'delivery_id': 3312, 'recipient_name': 'Sharma ji'},
      );

      final round = ok(await env.customers.customers());

      expect(round.rows.single.visitedThisRound, isFalse);
    });
  });

  // ------------------------------------------------------------------ the screen
  group('the screen', () {
    testWidgets('lists the round', (tester) async {
      await _pump(tester, _FakeCustomers());
      await tester.pumpAndSettle();

      expect(find.text('Sharma Kirana'), findsOneWidget);
      expect(find.byKey(const Key('customer.visit.142')), findsOneWidget);
      expect(find.byKey(const Key('customers.empty')), findsNothing);
    });

    testWidgets('the as_of line appears when the round has one', (tester) async {
      await _pump(tester, _FakeCustomers(asOf: DateTime.utc(2026, 8, 16, 8, 5)));
      await tester.pumpAndSettle();

      expect(
        tester.widget<Text>(find.byKey(const Key('customers.asOf'))).data,
        'Round as of 2026-08-16 08:05 UTC',
      );
    });

    testWidgets('there is no as_of line before the first pull', (tester) async {
      await _pump(tester, _FakeCustomers());
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('customers.asOf')), findsNothing);
    });

    testWidgets('logging a visit reaches the port with the chosen outcome', (tester) async {
      final fake = _FakeCustomers();
      await _pump(tester, fake);
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('customer.visit.142')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('customers.outcome.ORDER_TAKEN')));
      await tester.pumpAndSettle();

      expect(fake.visits, [(142, VisitOutcome.orderTaken)]);
      expect(find.byKey(const Key('customer.visited')), findsOneWidget);
      expect(find.text('CUS-000142 · Order taken'), findsOneWidget);
    });

    testWidgets('cancelling the sheet records nothing', (tester) async {
      final fake = _FakeCustomers();
      await _pump(tester, fake);
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('customer.visit.142')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('customers.cancel')));
      await tester.pumpAndSettle();

      expect(fake.visits, isEmpty);
    });

    testWidgets('a failed load explains itself in our words', (tester) async {
      // The port may still fail — a cache read can fail on a full or corrupt disk — so the
      // screen's message path is still live even though the network is gone.
      await _pump(tester, _FakeCustomers(listResult: const Err(Offline())));
      await tester.pumpAndSettle();

      expect(
        tester.widget<Text>(find.byKey(const Key('customers.message'))).data,
        contains('No connection'),
      );
    });

    testWidgets('a second visit while one is in flight is dropped', (tester) async {
      final gate = Completer<void>();
      final fake = _FakeCustomers(hold: gate);
      final container = await _pump(tester, fake);
      await tester.pumpAndSettle();
      final controller = container.read(customerListProvider.notifier);

      unawaited(
        controller.recordVisit(customer: _customer, outcome: VisitOutcome.noOrder),
      );
      unawaited(
        controller.recordVisit(customer: _customer, outcome: VisitOutcome.orderTaken),
      );
      await tester.pump();

      expect(fake.visits, hasLength(1));
      gate.complete();
      await tester.pumpAndSettle();
    });
  });
}

Future<ProviderContainer> _pump(WidgetTester tester, _FakeCustomers fake) async {
  final container = ProviderContainer(
    overrides: [customerRepositoryProvider.overrideWithValue(fake)],
  );
  addTearDown(container.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: CustomersScreen()),
    ),
  );
  return container;
}

/// A hand-written [CustomerRepository] that records what was asked of it.
final class _FakeCustomers implements CustomerRepository {
  _FakeCustomers({this.listResult, this.hold, this.asOf});

  final Result<CachedRound<Customer>>? listResult;
  final Completer<void>? hold;
  final DateTime? asOf;

  final List<(int, VisitOutcome)> visits = [];

  @override
  Future<Result<CachedRound<Customer>>> customers() async =>
      listResult ?? Ok(CachedRound<Customer>(rows: const [_customer], asOf: asOf));

  @override
  Future<Result<Customer>> recordVisit({
    required Customer customer,
    required VisitOutcome outcome,
    String notes = '',
  }) async {
    visits.add((customer.id, outcome));
    await hold?.future;
    return Ok(customer.visitedLocally(outcome: outcome, at: _now));
  }
}
