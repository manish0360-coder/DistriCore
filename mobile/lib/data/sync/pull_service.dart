import '../../core/failure.dart';
import '../../core/result.dart';
import '../../domain/customer/customer.dart';
import '../../domain/delivery/delivery.dart';
import '../api/api_client.dart';
import '../customer/customer_dto.dart';
import '../db/app_database.dart';
import '../delivery/delivery_dto.dart';
import '../repositories/customer_cache.dart';
import '../repositories/delivery_cache.dart';
import '../repositories/sync_cursor_store.dart';

/// **The pull half of sync** (M9.4, `05` §11.1).
///
/// Reads the server's view into the local cache, page by page, and advances the persisted
/// cursor exactly once — after the last page is on disk.
final class PullService {
  const PullService({
    required ApiClient api,
    required AppDatabase db,
    required CustomerCache customers,
    required DeliveryCache deliveries,
    required SyncCursorStore cursor,
  })  : _api = api,
        _db = db,
        _customers = customers,
        _deliveries = deliveries,
        _cursor = cursor;

  static const path = '/sync/pull';

  final ApiClient _api;
  final AppDatabase _db;
  final CustomerCache _customers;
  final DeliveryCache _deliveries;
  final SyncCursorStore _cursor;

  Future<Result<PullReport>> pull() async {
    // `null` means no pull has ever completed: the request omits `since` entirely and P-1
    // makes it a full bootstrap. Not an empty string, not an epoch.
    final since = await _cursor.read();

    String? token;
    String? serverTime;
    var pages = 0;
    var customers = 0;
    var deliveries = 0;
    var removed = 0;

    while (true) {
      final fetched = await _fetch(since: since, pageToken: token);
      if (fetched is Err<_PullPage>) return Err(fetched.failure);
      final page = (fetched as Ok<_PullPage>).value;

      // **One transaction per page, and never across a request.** Holding a SQLite write
      // transaction open over HTTP would block every outbox append for the duration — and an
      // outbox append is a user action (P-2). A driver completing a delivery mid-pull would
      // wait on the network.
      await _db.transaction(() async {
        await _customers.save(page.customers);
        // **The only removal path** (D-M9.4-3). Absence from a page deletes nothing.
        await _customers.remove(page.deactivatedCustomerIds);
        // §11.1 gives deliveries `{updated}` and no `deactivated_ids`; `DeliveryCache` has
        // no removal method at all, so there is nothing here that could delete one.
        await _deliveries.save(page.deliveries);
      });

      serverTime = page.serverTime;
      pages += 1;
      customers += page.customers.length;
      deliveries += page.deliveries.length;
      removed += page.deactivatedCustomerIds.length;

      if (!page.hasMore) break;

      if (page.nextPageToken == null || page.nextPageToken!.isEmpty) {
        // **`has_more` without a token is an unterminating loop**, and repeating the same
        // request would return the same page forever — the M9.2 drain defect, arriving here.
        // Refusing leaves the cursor untouched, so the next pull simply starts again.
        return const Err(MalformedResponse('has_more was set without a continuation token.'));
      }
      // P-5: the **same** `since` travels with every page. Only the token moves, and it is
      // never persisted (P-7).
      token = page.nextPageToken;
    }

    // **The one write, after the last page is durably applied** (D-M9.4-5). Advancing per
    // page would let a crash mid-sequence skip every page not yet fetched, permanently.
    //
    // **Unguarded, and it has to be.** The loop is `while (true)`; its only non-`return`
    // exit is the `break` above, which is reached after `serverTime` has been assigned from
    // a page whose own `server_time` is non-null by construction (`_PullPage.fromJson`
    // throws without it). A `!= null` guard here therefore never evaluates false — it read
    // as though a completed pull might have no cursor to write, and would silently return
    // `Ok` while leaving the cursor un-advanced if that ever became reachable.
    await _cursor.write(serverTime);

    return Ok(PullReport(
      pages: pages,
      customers: customers,
      deliveries: deliveries,
      removed: removed,
    ));
  }

  Future<Result<_PullPage>> _fetch({String? since, String? pageToken}) async {
    try {
      return await _api.get<_PullPage>(
        path,
        query: <String, dynamic>{
          if (since != null) 'since': since,
          if (pageToken != null) 'page_token': pageToken,
        },
        decode: _PullPage.fromJson,
      );
    } on CustomerPayloadException catch (error) {
      return Err(MalformedResponse(error.reason));
    } on DeliveryPayloadException catch (error) {
      return Err(MalformedResponse(error.reason));
    } on PullPayloadException catch (error) {
      return Err(MalformedResponse(error.reason));
    }
  }
}

/// One page of `05` §11.1, as this client reads it.
///
/// Only the two collections M9.4 implements are parsed. The others are **absent from an
/// M9.4 server**, and a client that required them would refuse a valid response.
final class _PullPage {
  const _PullPage({
    required this.serverTime,
    required this.hasMore,
    required this.customers,
    required this.deliveries,
    required this.deactivatedCustomerIds,
    this.nextPageToken,
  });

  factory _PullPage.fromJson(Object? body) {
    if (body is! Map) throw const PullPayloadException('not an object');

    final serverTime = body['server_time'];
    if (serverTime is! String || serverTime.isEmpty) {
      // Without it the cursor cannot advance, and a pull that cannot advance repeats
      // forever. This is the one field whose absence is fatal.
      throw const PullPayloadException('server_time missing');
    }

    final hasMore = body['has_more'];
    if (hasMore is! bool) throw const PullPayloadException('has_more missing');

    final customers = body['customers'];
    final deliveries = body['deliveries'];

    return _PullPage(
      // **Verbatim.** The string that arrived is the string that goes back out as the next
      // `since`; parsing and re-rendering is how a cursor drifts and silently skips records.
      serverTime: serverTime,
      hasMore: hasMore,
      nextPageToken:
          body['next_page_token'] is String ? body['next_page_token'] as String : null,
      customers: customers is Map
          ? CustomerDto.listFromJson(customers['updated'] ?? const [])
          : const [],
      deliveries: deliveries is Map
          ? DeliveryDto.listFromJson(deliveries['updated'] ?? const [])
          : const [],
      deactivatedCustomerIds: customers is Map
          ? [
              for (final id in (customers['deactivated_ids'] as List<dynamic>? ?? const []))
                if (id is int) id,
            ]
          : const [],
    );
  }

  final String serverTime;
  final bool hasMore;
  final String? nextPageToken;
  final List<Customer> customers;
  final List<Delivery> deliveries;
  final List<int> deactivatedCustomerIds;
}

/// What one pull did. Counts only — the rows are in the cache.
final class PullReport {
  const PullReport({
    this.pages = 0,
    this.customers = 0,
    this.deliveries = 0,
    this.removed = 0,
  });

  final int pages;
  final int customers;
  final int deliveries;
  final int removed;

  @override
  String toString() =>
      'PullReport(pages: $pages, customers: $customers, deliveries: $deliveries, '
      'removed: $removed)';
}

/// The pull envelope did not match `05` §11.1. Carries a reason, never a value.
final class PullPayloadException implements Exception {
  const PullPayloadException(this.reason);

  final String reason;

  @override
  String toString() => 'PullPayloadException: $reason';
}
