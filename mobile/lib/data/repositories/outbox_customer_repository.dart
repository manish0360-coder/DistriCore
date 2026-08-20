import '../../core/clock.dart';
import '../../core/result.dart';
import '../../core/uuid.dart';
import '../../domain/customer/customer.dart';
import '../../domain/customer/customer_repository.dart';
import '../../domain/outbox/outbox_operation.dart';
import '../../domain/outbox/outbox_repository.dart';
import '../../domain/sync/cached_round.dart';
import '../../domain/visit/visit_outcome.dart';
import 'customer_cache.dart';
import 'sync_cursor_store.dart';

/// Customers: **read from the local cache, visits written to the outbox** (M9.4, P-2).
///
/// **This class no longer knows the network exists.** Until M9.4 it fetched over HTTP and
/// overlaid the queue; `PullService` now owns the fetch, and what is left here is the
/// asymmetry that always mattered — a read comes from disk and may be stale, a write is a
/// promise that goes to the outbox.
final class OutboxCustomerRepository implements CustomerRepository {
  const OutboxCustomerRepository({
    required CustomerCache cache,
    required OutboxRepository outbox,
    required SyncCursorStore cursor,
    required Clock clock,
  })  : _cache = cache,
        _outbox = outbox,
        _cursor = cursor,
        _clock = clock;

  /// `04` T-26's vocabulary, and one of the three `05` §11.2 spells out in its own example.
  static const operationType = 'VISIT_CREATE';

  final CustomerCache _cache;
  final OutboxRepository _outbox;
  final SyncCursorStore _cursor;
  final Clock _clock;

  @override
  Future<Result<CachedRound<Customer>>> customers() async {
    final cached = await _cache.read();
    final queued = await _queuedVisits();

    return Ok(CachedRound<Customer>(
      rows: [
        for (final customer in cached)
          if (queued[customer.id] case final visit?)
            customer.visitedLocally(outcome: visit.outcome, at: visit.at)
          else
            customer,
      ],
      // P-8. `null` until a pull has completed, which a screen must render differently from
      // a round taken this morning.
      asOf: await _asOf(),
    ));
  }

  @override
  Future<Result<Customer>> recordVisit({
    required Customer customer,
    required VisitOutcome outcome,
    String notes = '',
  }) async {
    final at = _clock.nowUtc();

    // **A fresh `client_uuid` every time, and the difference from a delivery is the point.**
    // P-6 says the key is minted before the first attempt and never regenerated *for that
    // attempt* — a delivery reuses one because a parcel is handed over once. `04` T-visit has
    // no per-customer uniqueness, so a shop called on twice in a day is two visits, and
    // reusing a key here would silently discard the second. The double-tap guard lives in
    // the controller, where the two taps are one intent.
    final appended = await _outbox.append(
      clientUuid: newClientUuid(),
      operationType: operationType,
      clientCreatedAt: at,
      payload: <String, Object?>{
        // `customer_id`, not `05` §11.2's `customer_client_uuid`: that form is for a shop
        // created offline in the same batch, which is Edition 2's field capture (DV-1).
        'customer_id': customer.id,
        'visited_at': at.toIso8601String(),
        'outcome': outcome.code,
        if (notes.isNotEmpty) 'notes': notes,
        // **No coordinates and no photo** — GPS is task 6, and an absent field is honest
        // where a zeroed one is a false fix. **No `device_id`** — D-C4 carries it per batch.
      },
    );

    return appended.fold(
      (_) => Ok(customer.visitedLocally(outcome: outcome, at: at)),
      Err.new,
    );
  }

  /// The server's snapshot instant, or `null` if no pull has ever completed.
  Future<DateTime?> _asOf() async {
    final serverTime = await _cursor.read();
    return serverTime == null ? null : DateTime.tryParse(serverTime)?.toUtc();
  }

  /// Queued visits, keyed by `customer_id`, **latest wins**.
  ///
  /// Unchanged by M9.4. Reads the outbox rather than a second index — the queue is already
  /// the authority on what is unsent.
  Future<Map<int, ({VisitOutcome outcome, DateTime at})>> _queuedVisits() async {
    final pending = await _outbox.pending();
    return pending.fold(
      (operations) {
        final byCustomer = <int, ({VisitOutcome outcome, DateTime at})>{};
        // `pending()` is sequence-ordered oldest first (D-C2), so a later call on the same
        // shop overwrites an earlier one — which is what the salesman last recorded.
        for (final operation in operations) {
          if (operation.operationType != operationType) continue;
          final id = operation.payload['customer_id'];
          final outcome = VisitOutcome.fromCode(_codeOf(operation));
          if (id is int && outcome != null) {
            byCustomer[id] = (outcome: outcome, at: operation.clientCreatedAt);
          }
        }
        return byCustomer;
      },
      (_) => const <int, ({VisitOutcome outcome, DateTime at})>{},
    );
  }

  static String? _codeOf(OutboxOperation operation) =>
      operation.payload['outcome'] is String ? operation.payload['outcome']! as String : null;
}
