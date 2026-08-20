// M9.4 step C — PullService, against a real SQLite cache and a real ApiClient.
//
// **Nothing below the HTTP boundary is faked.** The properties under test are the Drift
// transaction boundary, the cursor-advance point and the removal rule — all three are
// behaviours of the database, and a fake would agree with whatever the code did.
//
// One `AppDatabase` per test, registered by `wire()`.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/core/clock.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/core/result.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:districore/data/db/app_database.dart';
import 'package:districore/data/repositories/customer_cache.dart';
import 'package:districore/data/repositories/delivery_cache.dart';
import 'package:districore/data/repositories/sync_cursor_store.dart';
import 'package:districore/data/sync/pull_service.dart';
import 'package:districore/domain/delivery/delivery.dart';
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';

final _now = DateTime.utc(2026, 8, 16, 12);

const _t1 = '2026-08-16T09:00:00.000000+00:00';
const _t2 = '2026-08-16T10:00:00.000000+00:00';
const _t3 = '2026-08-16T11:00:00.000000+00:00';

Map<String, dynamic> _customer(int id) => <String, dynamic>{
      'id': id,
      'code': 'CUS-$id',
      'shop_name': 'Shop $id',
      'owner_name': 'Owner $id',
      'phone': '+9198765432$id',
      'zone': <String, dynamic>{'id': 7, 'name': 'Patna East'},
    };

Map<String, dynamic> _delivery(int id, {String status = 'DISPATCHED'}) => <String, dynamic>{
      'id': id,
      'order_number': 'SO-$id',
      'customer_name': 'Shop $id',
      'status': status,
    };

ResponseBody page({
  required String serverTime,
  bool hasMore = false,
  String? nextToken,
  List<Map<String, dynamic>> customers = const [],
  List<int> deactivated = const [],
  List<Map<String, dynamic>> deliveries = const [],
}) =>
    jsonBody(200, {
      'server_time': serverTime,
      'since': null,
      'has_more': hasMore,
      if (nextToken != null) 'next_page_token': nextToken,
      'customers': {'updated': customers, 'deactivated_ids': deactivated},
      'deliveries': {'updated': deliveries},
    });

typedef Env = ({
  PullService pull,
  AppDatabase db,
  CustomerCache customers,
  DeliveryCache deliveries,
  SyncCursorStore cursor,
  List<Map<String, dynamic>> queries,
});

/// [script] is called per request with its zero-based call index, so a test can fail the
/// second page without touching the first.
Env wire(FutureOr<ResponseBody> Function(int call) script) {
  final queries = <Map<String, dynamic>>[];
  final adapter = FakeAdapter((options, call) {
    // `RecordedRequest` does not carry query parameters, so what actually reached the wire
    // is captured here rather than inferred.
    queries.add(Map<String, dynamic>.of(options.queryParameters));
    return script(call);
  });

  final db = AppDatabase(NativeDatabase.memory());
  addTearDown(db.close);
  final customers = CustomerCache(db);
  final deliveries = DeliveryCache(db);
  final cursor = SyncCursorStore(db, FixedClock(_now));

  return (
    pull: PullService(
      api: ApiClient(
        baseUrl: 'https://api.test',
        tokens: FakeTokens(),
        dio: Dio()..httpClientAdapter = adapter,
        refreshDio: Dio()..httpClientAdapter = adapter,
      ),
      db: db,
      customers: customers,
      deliveries: deliveries,
      cursor: cursor,
    ),
    db: db,
    customers: customers,
    deliveries: deliveries,
    cursor: cursor,
    queries: queries,
  );
}

T ok<T>(Result<T> result) => result.fold((v) => v, (f) => fail('expected Ok, got $f'));

void main() {
  group('the request', () {
    test('1 & 3. the first pull omits both since and page_token', () async {
      // `null` cursor is P-1's full bootstrap — not an empty string, not an epoch.
      final env = wire((_) async => page(serverTime: _t1, customers: [_customer(1)]));

      ok(await env.pull.pull());

      expect(env.queries.single.containsKey('since'), isFalse);
      expect(env.queries.single.containsKey('page_token'), isFalse);
    });

    test('2. a later pull sends the exact stored server_time', () async {
      // Verbatim: the string that arrived is the string that goes back out. Re-rendering is
      // how a cursor drifts and silently skips records.
      final env = wire((_) async => page(serverTime: _t2));
      await env.cursor.write(_t1);

      ok(await env.pull.pull());

      expect(env.queries.single['since'], _t1);
    });
  });

  group('paging', () {
    test('4 & 5. every page reuses the same since and carries the returned token', () async {
      final env = wire((call) async => switch (call) {
            0 => page(
                serverTime: _t2,
                hasMore: true,
                nextToken: 'tok-1',
                customers: [_customer(1)],
              ),
            1 => page(
                serverTime: _t2,
                hasMore: true,
                nextToken: 'tok-2',
                customers: [_customer(2)],
              ),
            _ => page(serverTime: _t3, customers: [_customer(3)]),
          });
      await env.cursor.write(_t1);

      final report = ok(await env.pull.pull());

      expect(report.pages, 3);
      // P-5: `since` never moves mid-pull; only the token does.
      expect(env.queries.map((q) => q['since']).toList(), [_t1, _t1, _t1]);
      expect(env.queries.map((q) => q['page_token']).toList(), [null, 'tok-1', 'tok-2']);
      expect((await env.customers.read()).map((c) => c.id).toList(), [1, 2, 3]);
    });

    test('6. only the final page advances the cursor', () async {
      final env = wire((call) async => call == 0
          ? page(serverTime: _t2, hasMore: true, nextToken: 'tok-1')
          : page(serverTime: _t3));

      ok(await env.pull.pull());

      // D-M9.4-5: one write, after the last page is durably applied.
      expect(await env.cursor.read(), _t3);
    });

    test('the transient token is never persisted (P-7)', () async {
      final env = wire((call) async => call == 0
          ? page(serverTime: _t2, hasMore: true, nextToken: 'tok-1')
          : page(serverTime: _t3));

      ok(await env.pull.pull());

      final row = await env.db.select(env.db.syncCursors).getSingle();
      expect(row.serverTime, _t3);
      expect(row.serverTime, isNot(contains('tok')));
    });
  });

  group('failure on page two', () {
    Env failingOnSecondPage() => wire((call) async {
          if (call == 0) {
            return page(
              serverTime: _t2,
              hasMore: true,
              nextToken: 'tok-1',
              customers: [_customer(1), _customer(2)],
              deliveries: [_delivery(10)],
            );
          }
          throw DioException.connectionError(
            requestOptions: RequestOptions(path: PullService.path),
            reason: 'signal lost mid-pull',
          );
        });

    test('7. the previous cursor is left untouched', () async {
      final env = failingOnSecondPage();
      await env.cursor.write(_t1);

      final result = await env.pull.pull();

      expect(result, isA<Err<PullReport>>());
      expect(await env.cursor.read(), _t1, reason: 'a partial pull must not advance');
    });

    test('8. page one stays committed — the transaction boundary is per page', () async {
      // **The assertion this file exists for.** Per-page atomicity means page 1 is on disk
      // before page 2 is even requested; a whole-pull transaction would have rolled it back,
      // and would have held a SQLite write open across HTTP while doing so.
      final env = failingOnSecondPage();

      await env.pull.pull();

      expect((await env.customers.read()).map((c) => c.id).toList(), [1, 2]);
      expect((await env.deliveries.read()).map((d) => d.id).toList(), [10]);
    });

    test('9. a retry replays page one safely and completes', () async {
      var attempt = 0;
      final env = wire((call) async {
        if (call == 0 || call == 2) {
          return page(
            serverTime: _t2,
            hasMore: true,
            nextToken: 'tok-1',
            customers: [_customer(1)],
          );
        }
        if (call == 1 && attempt++ == 0) {
          throw DioException.connectionError(
            requestOptions: RequestOptions(path: PullService.path),
            reason: 'signal lost',
          );
        }
        return page(serverTime: _t3, customers: [_customer(2)]);
      });

      await env.pull.pull(); // fails on page 2
      expect(await env.cursor.read(), isNull);

      ok(await env.pull.pull()); // replays page 1, then finishes

      // Page 1 was applied twice and produced one row each: upsert on the server id.
      expect((await env.customers.read()).map((c) => c.id).toList(), [1, 2]);
      expect(await env.cursor.read(), _t3);
    });
  });

  group('idempotence and removal', () {
    test('10. a repeated pull upserts rather than duplicating', () async {
      final env = wire((_) async => page(
            serverTime: _t2,
            customers: [_customer(1)],
            deliveries: [_delivery(10)],
          ));

      ok(await env.pull.pull());
      ok(await env.pull.pull());

      expect(await env.customers.read(), hasLength(1));
      expect(await env.deliveries.read(), hasLength(1));
    });

    test('11. deactivated_ids remove exactly those ids', () async {
      final env = wire((call) async => call == 0
          ? page(serverTime: _t1, customers: [_customer(1), _customer(2), _customer(3)])
          : page(serverTime: _t2, deactivated: [2]));

      ok(await env.pull.pull());
      ok(await env.pull.pull());

      expect((await env.customers.read()).map((c) => c.id).toList(), [1, 3]);
    });

    test('12. absence from a pull deletes nothing', () async {
      // D-M9.4-3. Under P-5 a delta pull returns only what changed, so absence describes
      // almost every row the device holds — deleting on it would empty the cache.
      final env = wire((call) async => call == 0
          ? page(serverTime: _t1, customers: [_customer(1), _customer(2)])
          : page(serverTime: _t2, customers: [_customer(1)]));

      ok(await env.pull.pull());
      ok(await env.pull.pull());

      expect((await env.customers.read()).map((c) => c.id).toList(), [1, 2]);
    });

    test('13. a delivery is never removed, whatever the envelope carries', () async {
      // §11.1 gives deliveries `{updated}` and no `deactivated_ids`; `DeliveryCache` has no
      // removal method, so this is structural rather than a rule to remember.
      final env = wire((call) async => call == 0
          ? page(serverTime: _t1, deliveries: [_delivery(10), _delivery(11)])
          : page(serverTime: _t2, deactivated: [10, 11]));

      ok(await env.pull.pull());
      ok(await env.pull.pull());

      expect((await env.deliveries.read()).map((d) => d.id).toList(), [10, 11]);
    });

    test('a delivery status change is applied by upsert', () async {
      final env = wire((call) async => call == 0
          ? page(serverTime: _t1, deliveries: [_delivery(10)])
          : page(serverTime: _t2, deliveries: [_delivery(10, status: 'DELIVERED')]));

      ok(await env.pull.pull());
      ok(await env.pull.pull());

      final rows = await env.deliveries.read();
      expect(rows, hasLength(1));
      expect(rows.single.status, DeliveryStatus.delivered);
    });
  });

  group('structural guard', () {
    test('14. has_more without a token is refused and does not advance', () async {
      // The M9.2 drain defect arriving in the pull path: repeating the same request would
      // return the same page forever. Refusing leaves the cursor untouched, so the next
      // pull simply starts again.
      final env = wire((_) async => page(serverTime: _t2, hasMore: true));
      await env.cursor.write(_t1);

      final result = await env.pull.pull();

      expect((result as Err<PullReport>).failure, isA<MalformedResponse>());
      expect(await env.cursor.read(), _t1);
      expect(env.queries, hasLength(1), reason: 'it must not keep asking');
    });

    test('a customer row without shop_name is refused', () async {
      // **Relocated from T6 (M9.4).** `shop_name` is the one field a salesman navigates by;
      // a row without it is not a shop anyone can find. The rule did not change — the class
      // that enforces it did, from the customer repository to the parser behind the pull.
      final env = wire((_) async => jsonBody(200, {
            'server_time': _t1,
            'has_more': false,
            'customers': {
              'updated': [
                {'id': 1, 'code': 'C1'},
              ],
              'deactivated_ids': <dynamic>[],
            },
            'deliveries': {'updated': <dynamic>[]},
          }));

      final result = await env.pull.pull();

      expect((result as Err<PullReport>).failure, isA<MalformedResponse>());
      // A refused page must leave the device exactly as it was.
      expect(await env.customers.read(), isEmpty);
      expect(await env.cursor.read(), isNull);
    });

    test('a collection that is not a list is refused', () async {
      // **Relocated from T5/T6 (M9.4).** `05` §11.1 makes `updated` an array; anything else
      // is a contract break, and guessing at it would put unreadable data in the cache.
      final env = wire((_) async => jsonBody(200, {
            'server_time': _t1,
            'has_more': false,
            'customers': {'updated': 'not a list', 'deactivated_ids': <dynamic>[]},
            'deliveries': {'updated': <dynamic>[]},
          }));

      expect(await env.pull.pull(), isA<Err<PullReport>>());
      expect(await env.cursor.read(), isNull);
    });

    test('a response without server_time is refused', () async {
      // Without it the cursor cannot advance, and a pull that cannot advance repeats
      // forever. The one field whose absence is fatal.
      final env = wire((_) async => jsonBody(200, {
            'has_more': false,
            'customers': {'updated': <dynamic>[], 'deactivated_ids': <dynamic>[]},
            'deliveries': {'updated': <dynamic>[]},
          }));

      expect(await env.pull.pull(), isA<Err<PullReport>>());
      expect(await env.cursor.read(), isNull);
    });
  });
}
