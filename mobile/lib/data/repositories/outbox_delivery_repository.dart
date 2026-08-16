import '../../core/clock.dart';
import '../../core/failure.dart';
import '../../core/result.dart';
import '../../core/uuid.dart';
import '../../domain/delivery/delivery.dart';
import '../../domain/delivery/delivery_repository.dart';
import '../../domain/outbox/outbox_operation.dart';
import '../../domain/outbox/outbox_repository.dart';
import '../api/api_client.dart';
import '../delivery/delivery_dto.dart';

/// Deliveries: **read from the API, write to the outbox** (M8 §5.1, P-2).
///
/// The asymmetry is the whole design. A read is a convenience and may fail — the screen
/// says so. A write is a promise, so it goes to a durable local queue and M9 delivers it.
/// A repository that posted the completion here would put the network between a salesman and
/// the next drop, and would lose the handover entirely when the van has no signal.
final class OutboxDeliveryRepository implements DeliveryRepository {
  const OutboxDeliveryRepository({
    required ApiClient api,
    required OutboxRepository outbox,
    required Clock clock,
  })  : _api = api,
        _outbox = outbox,
        _clock = clock;

  static const listPath = '/deliveries';

  /// `04` T-26's vocabulary, quoted from `05` §11.2's own example. Not an enum: M8 task 3
  /// owns the queue, not the operations that fill it.
  static const operationType = 'DELIVERY_COMPLETE';

  final ApiClient _api;
  final OutboxRepository _outbox;
  final Clock _clock;

  @override
  Future<Result<List<Delivery>>> assignedToMe() async {
    final Result<List<Delivery>> fetched;
    try {
      fetched = await _api.get<List<Delivery>>(
        listPath,
        // `05` §9.4. `assigned_to=me` keeps the scoping decision on the server, where
        // N-06 re-authorises it — the client asking for "mine" is not the client deciding
        // what "mine" means.
        query: <String, dynamic>{'assigned_to': 'me'},
        decode: DeliveryDto.listFromJson,
      );
    } on DeliveryPayloadException catch (error) {
      return Err(MalformedResponse(error.reason));
    }

    if (fetched is Err<List<Delivery>>) return Err(fetched.failure);

    // **The overlay, and why it is here rather than in the screen.** A delivery completed
    // ten minutes ago is still `DISPATCHED` on the server until M9 syncs. Showing the server's
    // answer verbatim would tell a driver to deliver a parcel they have already handed over.
    // Merging is a repository concern because the outbox is a repository concern.
    final queued = await _pendingCompletions();
    return Ok([
      for (final delivery in (fetched as Ok<List<Delivery>>).value)
        if (queued[delivery.id] case final operation?)
          delivery.completedLocally(
            recipientName: _recipientOf(operation),
            at: operation.clientCreatedAt,
          )
        else
          delivery,
    ]);
  }

  @override
  Future<Result<Delivery>> complete({
    required Delivery delivery,
    required String recipientName,
  }) async {
    // **P-6, and the reason this is a lookup rather than a fresh mint.** `client_uuid` is
    // *"generated before the first attempt and never regenerated"* — a second tap, or a
    // relaunch after the app was killed mid-tap, is the same attempt. Re-appending the
    // existing key returns the original row through the outbox's UNIQUE constraint (I-4, I-6)
    // rather than queueing a second handover for one parcel.
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
        // when M9 builds the request. A column here would duplicate it.
        // **No `client_uuid`** — it is the operation's identity, not part of its payload.
      },
    );

    return appended.fold(
      (_) => Ok(delivery.completedLocally(recipientName: recipient, at: at)),
      // `StorageFull` and friends surface unchanged (D-C3). §5.3: the user is never told
      // "saved" before it is.
      Err.new,
    );
  }

  /// Queued completions, keyed by `delivery_id`.
  ///
  /// Reads the outbox rather than a second index. Introducing one would be the "second
  /// persistence layer" that has to be kept in step with the first, and the outbox is
  /// already the authority on what is unsent.
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
