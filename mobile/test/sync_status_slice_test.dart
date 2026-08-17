// M8 T7 — the sync-status screen, over the real outbox.
//
// The controller runs against a **real in-memory SQLite outbox** written through the real
// delivery and customer repositories, so what the screen counts is what those milestones
// actually queue — not a fixture that agrees with the test.
import 'dart:async';

import 'package:districore/core/clock.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/core/result.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/repositories/drift_outbox_repository.dart';
import 'package:districore/domain/outbox/outbox_operation.dart';
import 'package:districore/domain/outbox/outbox_repository.dart';
import 'package:districore/domain/outbox/outbox_status.dart';
import 'package:districore/features/sync_status/sync_controller.dart';
import 'package:districore/features/sync_status/sync_providers.dart';
import 'package:districore/features/sync_status/sync_status_screen.dart';
import 'package:drift/native.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

final _now = DateTime.utc(2026, 8, 16, 14, 5);

typedef Env = ({OutboxRepository outbox, AppDatabase db});

/// One `AppDatabase` per test — `wire` registers its own tear-down.
Env wire() {
  final db = AppDatabase(NativeDatabase.memory());
  addTearDown(db.close);
  return (outbox: DriftOutboxRepository(db), db: db);
}

Future<void> seed(
  OutboxRepository outbox, {
  int deliveries = 0,
  int visits = 0,
}) async {
  var n = 0;
  for (var i = 0; i < deliveries; i++) {
    await outbox.append(
      clientUuid: 'd${n++}111111-2222-4333-8444-555555555555',
      operationType: 'DELIVERY_COMPLETE',
      clientCreatedAt: _now.subtract(Duration(minutes: 60 - i)),
      payload: <String, Object?>{'delivery_id': 3300 + i, 'recipient_name': 'Sharma ji'},
    );
  }
  for (var i = 0; i < visits; i++) {
    await outbox.append(
      clientUuid: 'v${n++}111111-2222-4333-8444-555555555555',
      operationType: 'VISIT_CREATE',
      clientCreatedAt: _now.subtract(Duration(minutes: 30 - i)),
      payload: <String, Object?>{'customer_id': 140 + i, 'outcome': 'NO_ORDER'},
    );
  }
}

Future<ProviderContainer> pump(
  WidgetTester tester,
  OutboxRepository outbox, {
  Clock? clock,
}) async {
  final container = ProviderContainer(
    overrides: [
      outboxPortProvider.overrideWithValue(outbox),
      syncClockProvider.overrideWithValue(clock ?? FixedClock(_now)),
    ],
  );
  addTearDown(container.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: SyncStatusScreen()),
    ),
  );
  return container;
}

void main() {
  group('the count', () {
    testWidgets('an empty queue says so, and does not say zero waiting', (tester) async {
      final env = wire();
      await pump(tester, env.outbox);
      await tester.pumpAndSettle();

      expect(
        tester.widget<Text>(find.byKey(const Key('sync.pending'))).data,
        'Nothing waiting',
      );
      expect(find.byKey(const Key('sync.sampleLabel')), findsNothing);
    });

    testWidgets('counts what T5 and T6 actually queue', (tester) async {
      final env = wire();
      await seed(env.outbox, deliveries: 2, visits: 3);

      await pump(tester, env.outbox);
      await tester.pumpAndSettle();

      expect(
        tester.widget<Text>(find.byKey(const Key('sync.pending'))).data,
        '5 waiting to sync',
      );
    });

    test('the headline is depth(), not the sample size', () async {
      // The distinction that matters once a round is longer than the sample: the count is
      // the whole queue, the list is the oldest few.
      final env = wire();
      await seed(env.outbox, deliveries: kOldestSample + 4);
      final container = ProviderContainer(
        overrides: [
          outboxPortProvider.overrideWithValue(env.outbox),
          syncClockProvider.overrideWithValue(FixedClock(_now)),
        ],
      );
      addTearDown(container.dispose);

      await container.read(syncStatusProvider.notifier).load();
      final state = container.read(syncStatusProvider);

      expect(state.pending, kOldestSample + 4);
      expect(state.oldest, hasLength(kOldestSample));
    });
  });

  group('the detail list', () {
    testWidgets('is oldest first, by sequence', (tester) async {
      // D-C2: the sequence is the order, not the device clock.
      final env = wire();
      await seed(env.outbox, deliveries: 2, visits: 1);

      final container = await pump(tester, env.outbox);
      await tester.pumpAndSettle();

      final sequences = container
          .read(syncStatusProvider)
          .oldest
          .map((operation) => operation.sequence)
          .toList();
      expect(sequences, [1, 2, 3]);
      expect(find.byKey(const Key('sync.operation.1')), findsOneWidget);
    });

    testWidgets('labels the two operation types a field user recognises', (tester) async {
      final env = wire();
      await seed(env.outbox, deliveries: 1, visits: 1);

      await pump(tester, env.outbox);
      await tester.pumpAndSettle();

      expect(find.text('Delivery completed'), findsOneWidget);
      expect(find.text('Customer visit'), findsOneWidget);
      // Everything M8 writes is PENDING (§5.3), and the screen shows the real value.
      expect(find.text(OutboxStatus.pending.code), findsNWidgets(2));
    });

    testWidgets('says "oldest N of M" only when the queue is longer than the sample',
        (tester) async {
      final env = wire();
      await seed(env.outbox, deliveries: 3);

      await pump(tester, env.outbox);
      await tester.pumpAndSettle();

      expect(
        tester.widget<Text>(find.byKey(const Key('sync.sampleLabel'))).data,
        'Oldest first',
      );
    });
  });

  group('FR-SYN-008, answered as honestly as M8 can', () {
    testWidgets('last sync, conflicts and as_of are all present', (tester) async {
      final env = wire();
      await seed(env.outbox, visits: 1);

      await pump(tester, env.outbox);
      await tester.pumpAndSettle();

      // "Not synced yet" rather than a blank field: §10 records task 9 as necessarily
      // partial until M9, and blank would read as "unknown" rather than "not built".
      expect(find.byKey(const Key('sync.lastSync')), findsOneWidget);
      // Zero by construction — M8 writes PENDING and nothing else, so nothing can be
      // refused.
      expect(find.byKey(const Key('sync.conflicts')), findsOneWidget);
      // P-8: a count is shown with the time it was taken.
      expect(
        tester.widget<Text>(find.byKey(const Key('sync.asOf'))).data,
        'Counted at 14:05 UTC',
      );
    });

    testWidgets('the screen offers no way to send, retry or clear', (tester) async {
      // M8 has no drain (§1.2). A button that appeared to send would be M9 logic wearing an
      // M8 label — and one that silently did nothing would be worse than none.
      final env = wire();
      await seed(env.outbox, deliveries: 2);

      await pump(tester, env.outbox);
      await tester.pumpAndSettle();

      expect(find.byType(FilledButton), findsNothing);
      expect(find.byType(ElevatedButton), findsNothing);
      expect(find.byType(TextButton), findsNothing);
      expect(find.textContaining('Retry'), findsNothing);
      expect(find.textContaining('Sync now'), findsNothing);
    });

    testWidgets('reading does not change the queue', (tester) async {
      final env = wire();
      await seed(env.outbox, deliveries: 2, visits: 2);
      final before = (await env.outbox.pending()).fold((ops) => ops, (f) => fail('$f'));

      final container = await pump(tester, env.outbox);
      await tester.pumpAndSettle();
      await container.read(syncStatusProvider.notifier).load();

      final after = (await env.outbox.pending()).fold((ops) => ops, (f) => fail('$f'));
      expect(after.map((o) => o.sequence).toList(), before.map((o) => o.sequence).toList());
      expect(after.map((o) => o.status).toSet(), {OutboxStatus.pending});
    });
  });

  group('failure', () {
    test('a queue that cannot be read never reports zero', () async {
      // Reporting zero is the single worst answer available: it is the one that says
      // "nothing is waiting" to someone deciding whether to re-enter a delivery.
      final container = ProviderContainer(
        overrides: [
          outboxPortProvider.overrideWithValue(_BrokenOutbox()),
          syncClockProvider.overrideWithValue(FixedClock(_now)),
        ],
      );
      addTearDown(container.dispose);

      await container.read(syncStatusProvider.notifier).load();
      final state = container.read(syncStatusProvider);

      expect(state.message, isNotNull);
      expect(state.asOf, isNull, reason: 'no reading was taken, so there is no as_of');
      expect(state.loading, isFalse);
    });
  });
}

/// An outbox whose reads fail — the D-C3 storage path, from the reader's side.
final class _BrokenOutbox implements OutboxRepository {
  @override
  Future<Result<OutboxOperation>> append({
    required String clientUuid,
    required String operationType,
    required DateTime clientCreatedAt,
    required Map<String, Object?> payload,
  }) async =>
      const Err(StorageFull());

  @override
  Future<Result<int>> depth() async => const Err(StorageFull());

  @override
  Future<Result<List<OutboxOperation>>> pending({int limit = 100}) async =>
      const Err(StorageFull());

  @override
  Future<Result<int>> purgeAcknowledgedBefore(DateTime before) async =>
      const Err(StorageFull());

  // The M9.2 drain methods. **Every method on this fake fails the same way** — that is its
  // entire contract, and the status screen never calls these. Returning a plausible success
  // would be inventing sync behaviour inside a double built to prove one thing: that a queue
  // which cannot be read is never reported as a queue with nothing in it.
  @override
  Future<Result<List<OutboxOperation>>> claimBatch({int limit = 200}) async =>
      const Err(StorageFull());

  @override
  Future<Result<int>> reclaimInFlight() async => const Err(StorageFull());

  @override
  Future<Result<int>> settle(Map<String, OutboxStatus> byClientUuid) async =>
      const Err(StorageFull());
}
