// M8 T6 — the customer round and visit capture.
//
// Same two levels as the delivery slice: the repository against a **real in-memory SQLite
// outbox** and a real `ApiClient`, the screen against the `CustomerRepository` port with a
// hand-written fake. One `wire()` per test — `wire` registers `addTearDown(db.close)`, so a
// second call in one test would leave two live `AppDatabase` objects.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/core/clock.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/core/result.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/data/repositories/outbox_customer_repository.dart';
import 'package:districore/domain/customer/customer.dart';
import 'package:districore/domain/customer/customer_repository.dart';
import 'package:districore/domain/outbox/outbox_repository.dart';
import 'package:districore/domain/outbox/outbox_status.dart';
import 'package:districore/domain/visit/visit_outcome.dart';
import 'package:districore/features/customers/customer_controller.dart';
import 'package:districore/features/customers/customer_providers.dart';
import 'package:districore/features/customers/customers_screen.dart';
import 'package:drift/native.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';

final _now = DateTime.utc(2026, 8, 16, 11);

Map<String, dynamic> _row({int id = 142}) => <String, dynamic>{
      'id': id,
      'code': 'CUS-000$id',
      'shop_name': 'Sharma Kirana',
      'owner_name': 'Ramesh Sharma',
      'phone': '+919876543210',
      'zone': <String, dynamic>{'id': 7, 'name': 'Patna East'},
      // Money on the wire (AD-02). It must reach no Dart field — P-3.
      'credit_limit_amount': '25000.00',
      'is_active': true,
    };

const _customer = Customer(id: 142, code: 'CUS-000142', shopName: 'Sharma Kirana');

typedef Env = ({
  CustomerRepository customers,
  OutboxRepository outbox,
  AppDatabase db,
  FakeAdapter adapter,
});

Env wire({FutureOr<ResponseBody> Function(RequestOptions, int)? script}) {
  final adapter =
      FakeAdapter(script ?? (_, __) async => jsonBody(200, {'results': [_row()]}));
  final db = AppDatabase(NativeDatabase.memory());
  addTearDown(db.close);
  final outbox = DriftOutboxRepository(db);
  return (
    customers: OutboxCustomerRepository(
      api: ApiClient(
        baseUrl: 'https://api.test',
        tokens: FakeTokens(),
        dio: Dio()..httpClientAdapter = adapter,
        refreshDio: Dio()..httpClientAdapter = adapter,
      ),
      outbox: outbox,
      clock: FixedClock(_now),
    ),
    outbox: outbox,
    db: db,
    adapter: adapter,
  );
}

T ok<T>(Result<T> result) => result.fold((v) => v, (f) => fail('expected Ok, got $f'));

void main() {
  group('reading the round', () {
    test('parses the list and asks the server for active shops only', () async {
      final env = wire();

      final list = ok(await env.customers.customers());

      expect(list.single.id, 142);
      expect(list.single.shopName, 'Sharma Kirana');
      expect(list.single.zoneName, 'Patna East');
      expect(list.single.visitedThisRound, isFalse);
      expect(env.adapter.requests.single.path, '/customers');
    });

    test('a row without shop_name is refused — it is not a shop anyone can find', () async {
      final env = wire(
        script: (_, __) async => jsonBody(200, {
          'results': [
            {'id': 1, 'code': 'C1'},
          ],
        }),
      );

      expect(await env.customers.customers(), isA<Err<List<Customer>>>());
    });

    test('an offline read is Err — an empty round would be a lie', () async {
      final env = wire(
        script: (_, __) => throw DioException.connectionError(
          requestOptions: RequestOptions(),
          reason: 'no signal',
        ),
      );

      expect((await env.customers.customers() as Err<List<Customer>>).failure, isA<Offline>());
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

    test('the action succeeds with no network at all', () async {
      final env = wire(
        script: (_, __) => throw DioException.connectionError(
          requestOptions: RequestOptions(),
          reason: 'no signal',
        ),
      );

      final result = await env.customers.recordVisit(
        customer: _customer,
        outcome: VisitOutcome.orderTaken,
      );

      expect(result, isA<Ok<Customer>>());
      expect(ok(await env.outbox.depth()), 1);
      expect(env.adapter.requests, isEmpty, reason: 'P-2 — a user action never posts');
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
    test('a queued visit is overlaid on the server list', () async {
      final env = wire();
      await env.customers.recordVisit(customer: _customer, outcome: VisitOutcome.orderTaken);

      final list = ok(await env.customers.customers());

      expect(list.single.visitedThisRound, isTrue);
      expect(list.single.lastOutcome, VisitOutcome.orderTaken);
      expect(list.single.visitedAt, _now);
    });

    test('the latest visit wins the overlay, and it survives a restart', () async {
      final env = wire();
      await env.customers.recordVisit(customer: _customer, outcome: VisitOutcome.shopClosed);
      await env.customers.recordVisit(customer: _customer, outcome: VisitOutcome.orderTaken);

      // A fresh repository over the same database — the app killed and relaunched.
      final relaunched = OutboxCustomerRepository(
        api: ApiClient(
          baseUrl: 'https://api.test',
          tokens: FakeTokens(),
          dio: Dio()..httpClientAdapter = env.adapter,
          refreshDio: Dio()..httpClientAdapter = env.adapter,
        ),
        outbox: DriftOutboxRepository(env.db),
        clock: FixedClock(_now.add(const Duration(hours: 3))),
      );

      final list = ok(await relaunched.customers());

      expect(list.single.lastOutcome, VisitOutcome.orderTaken,
          reason: 'sequence order (D-C2) decides, not the clock');
      expect(list.single.visitedAt, _now);
    });

    test('a delivery queued alongside does not appear as a visit', () async {
      // One outbox, several operation types. The overlay must read only its own.
      final env = wire();
      await env.outbox.append(
        clientUuid: '11111111-2222-4333-8444-555555555555',
        operationType: 'DELIVERY_COMPLETE',
        clientCreatedAt: _now,
        payload: <String, Object?>{'delivery_id': 3312, 'recipient_name': 'Sharma ji'},
      );

      final list = ok(await env.customers.customers());

      expect(list.single.visitedThisRound, isFalse);
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
  _FakeCustomers({this.listResult, this.hold});

  final Result<List<Customer>>? listResult;
  final Completer<void>? hold;

  final List<(int, VisitOutcome)> visits = [];

  @override
  Future<Result<List<Customer>>> customers() async => listResult ?? const Ok([_customer]);

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
