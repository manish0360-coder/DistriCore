// M8 T5 — the delivery vertical slice, **cache-first since M9.4**.
//
// The repository half runs against a real in-memory SQLite cache and outbox; the screen half
// runs against the `DeliveryRepository` port with a hand-written fake. Two levels, and the
// seam between them is the domain interface.
//
// **The network is gone from this file**, because it is gone from the repository. Fetching,
// parsing and failure handling moved to `PullService` (`pull_slice_test.dart`), and status
// mapping moved to `DeliveryCache` (`cache_repository_test.dart`). What stays here is what
// T5 still owns: the outbox overlay, `client_uuid` identity, and the screen.
import 'dart:async';

import 'package:districore/core/clock.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/core/result.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/repositories/delivery_cache.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/data/repositories/outbox_delivery_repository.dart';
import 'package:districore/data/repositories/sync_cursor_store.dart';
import 'package:districore/domain/delivery/delivery.dart';
import 'package:districore/domain/delivery/delivery_repository.dart';
import 'package:districore/domain/outbox/outbox_repository.dart';
import 'package:districore/domain/outbox/outbox_status.dart';
import 'package:districore/domain/sync/cached_round.dart';
import 'package:districore/features/deliveries/deliveries_screen.dart';
import 'package:districore/features/deliveries/delivery_controller.dart';
import 'package:districore/features/deliveries/delivery_providers.dart';
import 'package:drift/native.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

final _now = DateTime.utc(2026, 8, 16, 9, 30);
const _pulledAt = '2026-08-16T08:00:00.000000Z';

const _dispatched = Delivery(
  id: 3312,
  orderNumber: 'SO-4471',
  customerName: 'Sharma Kirana',
  status: DeliveryStatus.dispatched,
);

typedef Env = ({
  DeliveryRepository deliveries,
  OutboxRepository outbox,
  DeliveryCache cache,
  SyncCursorStore cursor,
  AppDatabase db,
});

/// **One `wire()` per test.** It registers `addTearDown(db.close)`, so a second call in one
/// test leaves two live `AppDatabase` objects — which is what drift's warning is for.
Env wire() {
  final db = AppDatabase(NativeDatabase.memory());
  addTearDown(db.close);
  final outbox = DriftOutboxRepository(db);
  final cache = DeliveryCache(db);
  final cursor = SyncCursorStore(db, FixedClock(_now));
  return (
    deliveries: OutboxDeliveryRepository(
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
      // **The gap this closes.** Until M9.4 a driver opening the app in a depot with no
      // signal saw an empty round; the repository holds no `ApiClient` at all now.
      final env = wire();
      await env.cache.save([_dispatched]);
      await env.cursor.write(_pulledAt);

      final round = ok(await env.deliveries.assignedToMe());

      expect(round.rows.single.id, 3312);
      expect(round.rows.single.customerName, 'Sharma Kirana');
      expect(round.rows.single.canComplete, isTrue);
    });

    test('asOf is the server_time of the last completed pull', () async {
      // P-8: stale is acceptable, silently stale is not.
      final env = wire();
      await env.cache.save([_dispatched]);
      await env.cursor.write(_pulledAt);

      final round = ok(await env.deliveries.assignedToMe());

      expect(round.asOf, DateTime.utc(2026, 8, 16, 8));
    });

    test('asOf is null before the first pull, and the round is simply empty', () async {
      // `null` means *never synced* — a different claim from a round taken this morning, and
      // the screen must be able to tell them apart.
      final env = wire();

      final round = ok(await env.deliveries.assignedToMe());

      expect(round.asOf, isNull);
      expect(round.rows, isEmpty);
      expect(round.isEmpty, isTrue);
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

    test('7. the action needs no network at all', () async {
      // The whole reason for the milestone — and since M9.4 it is structural: this
      // repository holds no HTTP client, so there is nothing a completion could await.
      final env = wire();

      final result = await env.deliveries.complete(
        delivery: _dispatched,
        recipientName: 'Sharma ji',
      );

      expect(result, isA<Ok<Delivery>>());
      expect(ok(await env.outbox.depth()), 1, reason: 'on disk before it returns (§5.3)');
    });
  });

  group('5 & restart. the local result is what the user sees', () {
    test('5. a queued completion is overlaid on the cached round', () async {
      // The cache still says DISPATCHED until the next pull. Showing that verbatim would
      // tell a driver to deliver a parcel they have already handed over.
      final env = wire();
      await env.cache.save([_dispatched]);
      await env.deliveries.complete(delivery: _dispatched, recipientName: 'Sharma ji');

      final round = ok(await env.deliveries.assignedToMe());

      expect(round.rows.single.status, DeliveryStatus.delivered);
      expect(round.rows.single.recipientName, 'Sharma ji');
      expect(round.rows.single.deliveredAt, _now);
    });

    test('the overlay leaves the cache itself untouched', () async {
      // The overlay is a read-time projection, not a write. A pull must not have to undo it,
      // and the cache must keep holding the server's facts.
      final env = wire();
      await env.cache.save([_dispatched]);
      await env.deliveries.complete(delivery: _dispatched, recipientName: 'Sharma ji');

      expect((await env.cache.read()).single.status, DeliveryStatus.dispatched);
    });

    test('the overlay survives a restart, because the outbox does', () async {
      // A fresh repository over the same database — the app killed and relaunched.
      final env = wire();
      await env.cache.save([_dispatched]);
      await env.deliveries.complete(delivery: _dispatched, recipientName: 'Sharma ji');

      final relaunched = OutboxDeliveryRepository(
        cache: DeliveryCache(env.db),
        outbox: DriftOutboxRepository(env.db),
        cursor: SyncCursorStore(env.db, FixedClock(_now)),
        clock: FixedClock(_now.add(const Duration(hours: 2))),
      );

      final round = ok(await relaunched.assignedToMe());

      expect(round.rows.single.status, DeliveryStatus.delivered);
      expect(round.rows.single.deliveredAt, _now,
          reason: 'the original capture time, not now');
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

    testWidgets('the as_of line appears when the round has one', (tester) async {
      await _pump(tester, _FakeDeliveries(asOf: DateTime.utc(2026, 8, 16, 8, 5)));
      await tester.pumpAndSettle();

      expect(
        tester.widget<Text>(find.byKey(const Key('deliveries.asOf'))).data,
        'Round as of 2026-08-16 08:05 UTC',
      );
    });

    testWidgets('there is no as_of line before the first pull', (tester) async {
      // A zero or a placeholder would be a claim nobody measured.
      await _pump(tester, _FakeDeliveries());
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('deliveries.asOf')), findsNothing);
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
      // The port may still fail — a cache read can fail on a full or corrupt disk — so the
      // screen's message path is still live even though the network is gone.
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
  _FakeDeliveries({this.listResult, this.hold, this.asOf});

  final Result<CachedRound<Delivery>>? listResult;
  final Completer<void>? hold;
  final DateTime? asOf;

  final List<(String, String)> completions = [];

  @override
  Future<Result<CachedRound<Delivery>>> assignedToMe() async =>
      listResult ??
      Ok(CachedRound<Delivery>(rows: const [_dispatched], asOf: asOf));

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
