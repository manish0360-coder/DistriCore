import 'outbox_status.dart';

/// One durable local write, waiting for M9 to drain it (M8 §5.3).
///
/// **Fields are the frozen row and nothing else** — `04` T-26 and `05` §11.2 between them
/// fix the shape, and D-C4 keeps `device_id` out: `05` §11.2 carries it **once per batch**,
/// sourced from the keystore when M9 constructs the batch, so a column here would duplicate
/// a value the contract already places elsewhere.
class OutboxOperation {
  const OutboxOperation({
    required this.sequence,
    required this.clientUuid,
    required this.operationType,
    required this.clientCreatedAt,
    required this.payload,
    required this.status,
  });

  /// **D-C1.** The `INTEGER PRIMARY KEY AUTOINCREMENT` value: row identity *and* queue
  /// order in one column. Never renumbered, never reused — `AUTOINCREMENT` is what makes
  /// the second half true across the purge §5.3 permits.
  ///
  /// **D-C2.** This, not [clientCreatedAt], is the ordering key. A device clock is not
  /// monotonic: a timezone change or an NTP correction reorders timestamps *within one
  /// device*, which is exactly what P-4 keeps off the correctness path.
  final int sequence;

  /// **P-6 / C-2 / AD-09.** Minted before the first attempt and never regenerated.
  final String clientUuid;

  /// `04` T-26's vocabulary — `DELIVERY_COMPLETE`, `VISIT_CREATE`, … The domain does not
  /// enumerate them: M8 task 3 owns the queue, not the operations that will fill it.
  final String operationType;

  /// **Metadata, audit and display only (D-C2).** Carried because `05` §11.2 puts it on the
  /// wire, never consulted to decide order.
  final DateTime clientCreatedAt;

  /// The request body M9 will send, stored verbatim. Not interpreted here — P-1: the device
  /// captures facts, it does not decide them.
  final Map<String, Object?> payload;

  final OutboxStatus status;
}
