import '../../core/clock.dart';
import '../../core/result.dart';
import '../../core/uuid.dart';
import '../../domain/delivery/delivery.dart';
import '../../domain/delivery/delivery_repository.dart';
import '../../domain/outbox/outbox_operation.dart';
import '../../domain/outbox/outbox_repository.dart';
import '../../domain/sync/cached_round.dart';
import 'delivery_cache.dart';
import 'sync_cursor_store.dart';

/// Deliveries: **read from the local cache, written to the outbox** (M9.4, P-2).
///
/// **The network is gone from this class.** T5 fetched over HTTP and overlaid the queue,
/// which meant a driver opening the app in a depot with no signal saw an empty round — the
/// largest gap in the app between T5 and now. `PullService` owns the fetch; this reads disk.
final class OutboxDeliveryRepository implements DeliveryRepository {
  const OutboxDeliveryRepository({
    required DeliveryCache cache,
    required OutboxRepository outbox,
    required SyncCursorStore cursor,
    required Clock clock,
  })  : _cache = cache,
        _outbox = outbox,
        _cursor = cursor,
        _clock = clock;

  /// `04` T-26's vocabulary, quoted from `05` §11.2's own example.
  static const operationType = 'DELIVERY_COMPLETE';

  final DeliveryCache _cache;
  final OutboxRepository _outbox;
  final SyncCursorStore _cursor;
  final Clock _clock;

  @override
  Future<Result<CachedRound<Delivery>>> assignedToMe() async {
    final cached = await _cache.read();
    final queued = await _pendingCompletions();

    // **The overlay, unchanged by M9.4.** A delivery completed ten minutes ago is still
    // `DISPATCHED` in the cache until the next pull. Showing that verbatim would tell a
    // driver to deliver a parcel they have already handed over.
    return Ok(CachedRound<Delivery>(
      rows: [
        for (final delivery in cached)
          if (queued[delivery.id] case final operation?)
            delivery.completedLocally(
              recipientName: _recipientOf(operation),
              at: operation.clientCreatedAt,
            )
          else
            delivery,
      ],
      asOf: await _asOf(),
    ));
  }

  @override
  Future<Result<Delivery>> complete({
    required Delivery delivery,
    required String recipientName,
  }) async {
    // **P-6, and the reason this is a lookup rather than a fresh mint.** `client_uuid` is
    // *"generated before the first attempt and never regenerated"* — a second tap, or a
    // relaunch after the app was killed mid-tap, is the same attempt. Re-appending the
    // existing key returns the original row through the outbox's UNIQUE constraint (I-4).
    final existing = (await _pendingCompletions())[delivery.id];
    final clientUuid = existing?.clientUuid ?? newClientUuid();
    final at = existing?.clientCreatedAt ?? _clock.nowUtc();
    final recipient = existing == null ? recipientName : _recipientOf(existing);

    final appended = await _outbox.append(
      clientUuid: clientUuid,
      operationType: operationType,
      // Metadata and audit only (D-C2) — the array's order is the order, not this.
      clientCreatedAt: at,
      payload: <String, Object?>{
        'delivery_id': delivery.id,
        'recipient_name': recipient,
        'delivered_at': at.toIso8601String(),
        // **No `device_id`** — D-C4: `05` §11.2 carries it once per batch, from the keystore,
        // when M9 builds the request. **No `client_uuid`** — it is the operation's identity,
        // not part of its payload.
      },
    );

    return appended.fold(
      (_) => Ok(delivery.completedLocally(recipientName: recipient, at: at)),
      // `StorageFull` and friends surface unchanged (D-C3).
      Err.new,
    );
  }

  /// The server's snapshot instant, or `null` if no pull has ever completed.
  Future<DateTime?> _asOf() async {
    final serverTime = await _cursor.read();
    return serverTime == null ? null : DateTime.tryParse(serverTime)?.toUtc();
  }

  /// Queued completions, keyed by `delivery_id`. Unchanged by M9.4.
  Future<Map<int, OutboxOperation>> _pendingCompletions() async {
    final pending = await _outbox.pending();
    return pending.fold(
      (operations) => <int, OutboxOperation>{
        for (final operation in operations)
          if (operation.operationType == operationType)
            if (operation.payload['delivery_id'] case final int id) id: operation,
      },
      // A queue that cannot be read is not a queue with nothing in it. Returning empty here
      // would let `complete` mint a second `client_uuid`, so the caller sees the append's own
      // failure instead — one error, from one place.
      (_) => const <int, OutboxOperation>{},
    );
  }

  static String _recipientOf(OutboxOperation operation) =>
      operation.payload['recipient_name'] is String
          ? operation.payload['recipient_name']! as String
          : '';
}
