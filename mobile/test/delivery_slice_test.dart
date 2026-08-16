// M8 T5 — the delivery vertical slice.
//
// The repository half runs against a **real in-memory SQLite outbox** and a real `ApiClient`
// with a scripted adapter; the screen half runs against the `DeliveryRepository` port with a
// hand-written fake. Two levels, and the seam between them is the domain interface — which
// is the property the layering rule buys.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/core/clock.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/core/result.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/data/repositories/outbox_delivery_repository.dart';
import 'package:districore/domain/delivery/delivery.dart';
import 'package:districore/domain/delivery/delivery_repository.dart';
import 'package:districore/domain/outbox/outbox_repository.dart';
import 'package:districore/domain/outbox/outbox_status.dart';
import 'package:districore/features/deliveries/deliveries_screen.dart';
import 'package:districore/features/deliveries/delivery_controller.dart';
import 'package:districore/features/deliveries/delivery_providers.dart';
import 'package:drift/native.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';

final _now = DateTime.utc(2026, 8, 16, 9, 30);

Map<String, dynamic> _row({int id = 3312, String status = 'DISPATCHED'}) =>
    <String, dynamic>{
      'id': id,
      'sales_order_id': 4471,
      'order_number': 'SO-0000$id',
      'customer_name': 'Sharma Kirana',
      'status': status,
      'recipient_name': '',
      'delivered_at': null,
    };

const _dispatched = Delivery(
  id: 3312,
  orderNumber: 'SO-4471',
  customerName: 'Sharma Kirana',
  status: DeliveryStatus.dispatched,
);

typedef Env = ({
  DeliveryRepository deliveries,
  OutboxRepository outbox,
  AppDatabase db,
  FakeAdapter adapter,
});

Env wire({FutureOr<ResponseBody> Function(RequestOptions, int)? script}) {
  final adapter = FakeAdapter(script ?? (_, __) async => jsonBody(200, {'results': [_row()]}));
  final db = AppDatabase(NativeDatabase.memory());
  addTearDown(db.close);
  final outbox = DriftOutboxRepository(db);
  return (
    deliveries: OutboxDeliveryRepository(
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
  group('2. reading through the existing API abstraction', () {
    test('parses the list and asks the server to scope it', () async {
      final env = wire();

      final list = ok(await env.deliveries.assignedToMe());

      expect(list.single.id, 3312);
      expect(list.single.customerName, 'Sharma Kirana');
      expect(list.single.status, DeliveryStatus.dispatched);
      expect(list.single.canComplete, isTrue);
      // Scoping stays on the server, where N-06 re-authorises it.
      expect(env.adapter.requests.single.path, '/deliveries');
    });

    // **One `wire()` per test, and that is a lifecycle rule rather than a style.** `wire`
    // registers `addTearDown(db.close)`, so a database it opens stays live until the test
    // ends — two calls in one test means two live `AppDatabase` objects at once, which is
    // exactly what drift's multiple-database warning is for. These two assertions were one
    // test; splitting them is the smallest fix that keeps both and closes each database.
    test('a body that is neither a list nor an envelope is refused', () async {
      final env = wire(script: (_, __) async => jsonBody(200, {'x': 1}));

      expect((await env.deliveries.assignedToMe()), isA<Err<List<Delivery>>>());
    });

    test('a bare array is accepted, not only a paginated envelope', () async {
      final env = wire(
        script: (_, __) async => ResponseBody.fromString(
          '[{"id":1,"status":"PENDING"}]',
          200,
          headers: {
            Headers.contentTypeHeader: [Headers.jsonContentType],
          },
        ),
      );

      expect(ok(await env.deliveries.assignedToMe()).single.id, 1);
    });

    test('an unknown status degrades to unknown and offers no action', () async {
      final env = wire(
        script: (_, __) async => jsonBody(200, {
          'results': [_row(status: 'QUANTUM_SUPERPOSITION')],
        }),
      );

      final delivery = ok(await env.deliveries.assignedToMe()).single;

      expect(delivery.status, DeliveryStatus.unknown);
      expect(delivery.canComplete, isFalse, reason: 'never offer an action the server refuses');
    });

    test('an offline read is Err — an empty list would be a lie', () async {
      final env = wire(
        script: (_, __) => throw DioException.connectionError(
          requestOptions: RequestOptions(),
          reason: 'no signal',
        ),
      );

      final result = await env.deliveries.assignedToMe();

      expect((result as Err<List<Delivery>>).failure, isA<Offline>());
    });
  });

  group('4 & 6. the action writes exactly one durable PENDING operation', () {
    test('4. one row, DELIVERY_COMPLETE, PENDING, with the frozen payload', () async {
      final env = wire();

      final completed = ok(await env.deliveries.complete(
        delivery: _dispatched,
        recipientName: 'Sharma ji',
      ));

      final queued = ok(await env.outbox.pending());
      expect(queued, hasLength(1));
      final operation = queued.single;
      expect(operation.operationType, 'DELIVERY_COMPLETE');
      expect(operation.status, OutboxStatus.pending);
      expect(operation.payload['delivery_id'], 3312);
      expect(operation.payload['recipient_name'], 'Sharma ji');
      // D-C4 — `05` §11.2 carries `device_id` once per batch, not per row.
      expect(operation.payload.containsKey('device_id'), isFalse);
      // The operation's identity, not part of its payload.
      expect(operation.payload.containsKey('client_uuid'), isFalse);
      expect(completed.status, DeliveryStatus.delivered);
    });

    test('the client_uuid is a well-formed v4 UUID the server will accept', () async {
      final env = wire();
      await env.deliveries.complete(delivery: _dispatched, recipientName: 'Sharma ji');

      final uuid = ok(await env.outbox.pending()).single.clientUuid;

      expect(
        uuid,
        matches(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')),
      );
    });

    test('6. completing twice appends once and keeps the original client_uuid', () async {
      // P-6: generated before the first attempt and **never regenerated**. A second tap, or
      // a relaunch after a kill, is the same attempt.
      final env = wire();

      await env.deliveries.complete(delivery: _dispatched, recipientName: 'Sharma ji');
      final first = ok(await env.outbox.pending()).single;
      await env.deliveries.complete(delivery: _dispatched, recipientName: 'Someone else');

      final queued = ok(await env.outbox.pending());
      expect(queued, hasLength(1), reason: 'one parcel, one handover');
      expect(queued.single.clientUuid, first.clientUuid);
      expect(queued.single.sequence, first.sequence);
      expect(queued.single.payload['recipient_name'], 'Sharma ji',
          reason: 'the first attempt is the record; a retry does not rewrite it');
    });

    test('7. the action succeeds with no network at all', () async {
      // The whole reason for the milestone. The adapter throws for every request; the
      // handover is still on disk when `complete` returns.
      final env = wire(
        script: (_, __) => throw DioException.connectionError(
          requestOptions: RequestOptions(),
          reason: 'no signal',
        ),
      );

      final result = await env.deliveries.complete(
        delivery: _dispatched,
        recipientName: 'Sharma ji',
      );

      expect(result, isA<Ok<Delivery>>());
      expect(ok(await env.outbox.depth()), 1);
      expect(env.adapter.requests, isEmpty, reason: 'P-2 — a user action never posts');
    });
  });

  group('5 & restart. the local result is what the user sees', () {
    test('5. a queued completion is overlaid on the server list', () async {
      // The server still says DISPATCHED until M9 syncs. Showing that verbatim would tell a
      // driver to deliver a parcel they have already handed over.
      final env = wire();
      await env.deliveries.complete(delivery: _dispatched, recipientName: 'Sharma ji');

      final list = ok(await env.deliveries.assignedToMe());

      expect(list.single.status, DeliveryStatus.delivered);
      expect(list.single.recipientName, 'Sharma ji');
      expect(list.single.deliveredAt, _now);
    });

    test('the overlay survives a restart, because the outbox does', () async {
      // A fresh repository over the same database — the app killed and relaunched.
      final env = wire();
      await env.deliveries.complete(delivery: _dispatched, recipientName: 'Sharma ji');

      final relaunched = OutboxDeliveryRepository(
        api: ApiClient(
          baseUrl: 'https://api.test',
          tokens: FakeTokens(),
          dio: Dio()..httpClientAdapter = env.adapter,
          refreshDio: Dio()..httpClientAdapter = env.adapter,
        ),
        outbox: DriftOutboxRepository(env.db),
        clock: FixedClock(_now.add(const Duration(hours: 2))),
      );

      final list = ok(await relaunched.assignedToMe());

      expect(list.single.status, DeliveryStatus.delivered);
      expect(list.single.deliveredAt, _now, reason: 'the original capture time, not now');
    });
  });

  // ------------------------------------------------------------------ the screen
  group('1 & 3. the screen', () {
    testWidgets('1. lists what the repository returns', (tester) async {
      await _pump(tester, _FakeDeliveries());
      await tester.pumpAndSettle();

      expect(find.text('Sharma Kirana'), findsOneWidget);
      expect(find.byKey(const Key('delivery.complete.3312')), findsOneWidget);
      expect(find.byKey(const Key('deliveries.empty')), findsNothing);
    });

    testWidgets('3. the first frozen action reaches the port with the typed name',
        (tester) async {
      final fake = _FakeDeliveries();
      await _pump(tester, fake);
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('delivery.complete.3312')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('deliveries.recipient')), 'Sharma ji');
      await tester.tap(find.byKey(const Key('deliveries.confirm')));
      await tester.pumpAndSettle();

      expect(fake.completions, [('3312', 'Sharma ji')]);
      expect(find.byKey(const Key('delivery.done')), findsOneWidget);
      expect(find.text('SO-4471 · Received by Sharma ji'), findsOneWidget);
    });

    testWidgets('cancelling the dialog records nothing', (tester) async {
      final fake = _FakeDeliveries();
      await _pump(tester, fake);
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('delivery.complete.3312')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('deliveries.cancel')));
      await tester.pumpAndSettle();

      expect(fake.completions, isEmpty);
    });

    testWidgets('a failed load explains itself in our words', (tester) async {
      await _pump(tester, _FakeDeliveries(listResult: const Err(Offline())));
      await tester.pumpAndSettle();

      expect(
        tester.widget<Text>(find.byKey(const Key('deliveries.message'))).data,
        contains('No connection'),
      );
    });

    testWidgets('a second completion while one is in flight is dropped', (tester) async {
      final gate = Completer<void>();
      final fake = _FakeDeliveries(hold: gate);
      final container = await _pump(tester, fake);
      await tester.pumpAndSettle();
      final controller = container.read(deliveryListProvider.notifier);

      unawaited(controller.complete(delivery: _dispatched, recipientName: 'A'));
      unawaited(controller.complete(delivery: _dispatched, recipientName: 'B'));
      await tester.pump();

      expect(fake.completions, hasLength(1));
      gate.complete();
      await tester.pumpAndSettle();
    });
  });
}

Future<ProviderContainer> _pump(WidgetTester tester, _FakeDeliveries fake) async {
  final container = ProviderContainer(
    overrides: [deliveryRepositoryProvider.overrideWithValue(fake)],
  );
  addTearDown(container.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: DeliveriesScreen()),
    ),
  );
  return container;
}

/// A hand-written [DeliveryRepository]. Records what was asked of it, which a mock's
/// "was called" cannot.
final class _FakeDeliveries implements DeliveryRepository {
  _FakeDeliveries({this.listResult, this.hold});

  final Result<List<Delivery>>? listResult;
  final Completer<void>? hold;

  final List<(String, String)> completions = [];

  @override
  Future<Result<List<Delivery>>> assignedToMe() async =>
      listResult ?? const Ok([_dispatched]);

  @override
  Future<Result<Delivery>> complete({
    required Delivery delivery,
    required String recipientName,
  }) async {
    completions.add(('${delivery.id}', recipientName));
    await hold?.future;
    return Ok(delivery.completedLocally(recipientName: recipientName, at: _now));
  }
}
