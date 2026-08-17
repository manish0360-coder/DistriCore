import '../../core/failure.dart';
import '../../core/result.dart';
import '../../domain/outbox/outbox_operation.dart';
import '../../domain/outbox/outbox_repository.dart';
import '../../domain/outbox/outbox_status.dart';
import '../api/api_client.dart';
import '../api/tokens.dart';

/// **The drain** (M9.2, `05` §11.2). One push at a time, in sequence order.
///
/// Lives in `data/` because it needs both `ApiClient` and the outbox; it depends on the
/// **domain** `OutboxRepository`, so no screen ever learns Drift exists.
///
/// It owns no business rule. Every verdict comes from the server and is written back
/// verbatim — the engine decides *when* to send and *what becomes of the row*, never
/// whether an operation was valid.
final class SyncEngine {
  SyncEngine({
    required ApiClient api,
    required OutboxRepository outbox,
    required TokenStore tokens,
  })  : _api = api,
        _outbox = outbox,
        _tokens = tokens;

  static const path = '/sync/push';

  /// `05` §13. The server refuses more, so this is the largest legal batch and therefore
  /// the fewest round trips.
  static const maxBatch = 200;

  final ApiClient _api;
  final OutboxRepository _outbox;
  final TokenStore _tokens;

  /// **Single-flight**, the shape `RefreshInterceptor` uses for D-B1. Two overlapping syncs
  /// would corrupt nothing — `claimBatch` is transactional and `client_uuid` dedupes
  /// server-side — but they would double the requests against a 60/hour limit and halve an
  /// already thin connection.
  Future<Result<SyncReport>>? _running;

  Future<Result<SyncReport>> sync() =>
      _running ??= _run().whenComplete(() => _running = null);

  Future<Result<SyncReport>> _run() async {
    // **Recover before sending.** A push killed mid-flight leaves rows `IN_FLIGHT`; they are
    // unsent work, and resending is safe because a replay is `DUPLICATE` (I-4). Leaving them
    // stranded is the loss FR-SYN-004 forbids.
    final reclaimed = await _outbox.reclaimInFlight();
    if (reclaimed is Err<int>) return Err(reclaimed.failure);

    final deviceId = _tokens.deviceId;
    if (deviceId == null || deviceId.isEmpty) {
      // §8.4 mints it at first launch, so this is unreachable in a booted app — and an
      // unattributed batch (C-10) is worse than an unsent one.
      return const Err(Unauthenticated());
    }

    var report = const SyncReport();
    while (true) {
      final claimed = await _outbox.claimBatch(limit: maxBatch);
      if (claimed is Err<List<OutboxOperation>>) return Err(claimed.failure);

      final batch = (claimed as Ok<List<OutboxOperation>>).value;
      if (batch.isEmpty) return Ok(report);

      final pushed = await _push(deviceId: deviceId, batch: batch);
      if (pushed is Err<Map<String, OutboxStatus>>) {
        // **Nothing lost, nothing guessed.** These rows return to `PENDING` for the next
        // attempt; batches already settled in this run keep their verdicts, which is
        // FR-SYN-017's "never restarted from the beginning".
        await _outbox.reclaimInFlight();
        return Err(pushed.failure);
      }

      final verdicts = (pushed as Ok<Map<String, OutboxStatus>>).value;
      // Anything the server did not mention returns to `PENDING` rather than being assumed
      // accepted — the one assumption that would lose a delivery.
      final settled = <String, OutboxStatus>{
        for (final operation in batch)
          operation.clientUuid: verdicts[operation.clientUuid] ?? OutboxStatus.pending,
      };
      final applied = await _outbox.settle(settled);
      if (applied is Err<int>) return Err(applied.failure);

      report = report.plus(settled.values);

      // **A full batch is not on its own a reason to fetch another one.**
      //
      // `DEFERRED` and any operation the server did not mention both return to `PENDING`
      // (rulings B and C) — so a batch of exactly `maxBatch` that produced no terminal
      // verdict leaves the queue byte-identical, and the next `claimBatch` returns the very
      // same rows. `batch.length < maxBatch` alone therefore never becomes true, and the
      // engine loops forever against a server that allows 60 pushes an hour, on a phone.
      //
      // That is `05` C-7's *"never loop"* reached through the drain instead of through
      // refresh. Requiring progress bounds the passes by queue depth: each continuing pass
      // removes at least one row from `PENDING`.
      final progressed = settled.values.any(
        (status) =>
            status == OutboxStatus.acknowledged || status == OutboxStatus.rejected,
      );
      if (batch.length < maxBatch || !progressed) return Ok(report);
    }
  }

  /// One `POST /sync/push`. Authentication and the single `TOKEN_EXPIRED` refresh are the
  /// interceptors' job (C-7, D-B1); there is no second auth path here.
  Future<Result<Map<String, OutboxStatus>>> _push({
    required String deviceId,
    required List<OutboxOperation> batch,
  }) =>
      _api.post<Map<String, OutboxStatus>>(
        path,
        body: <String, dynamic>{
          // **PU-4: once per batch, never inside a payload.**
          'device_id': deviceId,
          'operations': [
            for (final operation in batch)
              <String, dynamic>{
                'client_uuid': operation.clientUuid,
                'operation_type': operation.operationType,
                // PU-3: metadata. The array position is the order.
                'client_created_at': operation.clientCreatedAt.toUtc().toIso8601String(),
                'payload': operation.payload,
              },
          ],
        },
        decode: _decodeResults,
      );

  /// Matched by `client_uuid`, **not by position** — the server echoes the key, and matching
  /// by index would silently mis-assign every verdict after a dropped element.
  static Map<String, OutboxStatus> _decodeResults(Object? body) {
    if (body is! Map) throw const SyncPayloadException('not an object');
    final results = body['results'];
    if (results is! List) throw const SyncPayloadException('results missing');

    final verdicts = <String, OutboxStatus>{};
    for (final entry in results) {
      if (entry is! Map) continue;
      final clientUuid = entry['client_uuid'];
      final status = entry['status'];
      if (clientUuid is! String || status is! String) continue;
      final local = _localStatus(status);
      if (local != null) verdicts[clientUuid] = local;
    }
    return verdicts;
  }

  /// The wire vocabulary is five values; the local machine has four. This mapping is frozen
  /// (M9.2 rulings A–C) and is the whole of this engine's interpretation:
  ///
  /// | Server | Local | Why |
  /// | --- | --- | --- |
  /// | `ACCEPTED` | `ACKNOWLEDGED` | Applied. Removed later by the retention purge |
  /// | `DUPLICATE` | `ACKNOWLEDGED` | A replay is **success** (BR-012), not an error |
  /// | `DEFERRED` | `PENDING` | Retaining the row *is* the retry; no local state exists |
  /// | `REJECTED` | `REJECTED` | Kept. The reason is the server's (BR-014) |
  /// | `RECEIVED` | *unmapped* | Not a verdict — the row stays `PENDING` |
  static OutboxStatus? _localStatus(String wire) => switch (wire) {
        'ACCEPTED' || 'DUPLICATE' => OutboxStatus.acknowledged,
        'DEFERRED' => OutboxStatus.pending,
        'REJECTED' => OutboxStatus.rejected,
        _ => null,
      };
}

/// What one run did. Counts only — the rows stay in the outbox.
final class SyncReport {
  const SyncReport({this.acknowledged = 0, this.deferred = 0, this.rejected = 0});

  final int acknowledged;
  final int deferred;
  final int rejected;

  int get total => acknowledged + deferred + rejected;

  SyncReport plus(Iterable<OutboxStatus> statuses) {
    var ack = acknowledged;
    var defer = deferred;
    var reject = rejected;
    for (final status in statuses) {
      switch (status) {
        case OutboxStatus.acknowledged:
          ack += 1;
        case OutboxStatus.pending:
          defer += 1;
        case OutboxStatus.rejected:
          reject += 1;
        case OutboxStatus.inFlight:
          break;
      }
    }
    return SyncReport(acknowledged: ack, deferred: defer, rejected: reject);
  }

  @override
  String toString() =>
      'SyncReport(acknowledged: $acknowledged, deferred: $deferred, rejected: $rejected)';
}

/// The push response did not match `05` §11.2. Carries a reason, never a value.
final class SyncPayloadException implements Exception {
  const SyncPayloadException(this.reason);

  final String reason;

  @override
  String toString() => 'SyncPayloadException: $reason';
}
