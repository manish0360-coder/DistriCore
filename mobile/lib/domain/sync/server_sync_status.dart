/// The **server's** view of what this device has sent (`05` §11.5).
///
/// Deliberately a different type from anything the outbox produces. §11.5 exists so a
/// disagreement between the two views is *visible*: the local queue counts work that has
/// never left the phone, and this counts work the server has and has not finished. Folding
/// them into one number would delete the only information the endpoint carries.
final class ServerSyncStatus {
  const ServerSyncStatus({
    required this.deviceId,
    this.lastSyncAt,
    this.pending = 0,
    this.deferred = 0,
    this.rejected = 0,
    this.rejections = const [],
  });

  final String deviceId;

  /// `MAX(received_at)`. `null` means this device has never pushed anything.
  final DateTime? lastSyncAt;

  /// **An alarm, not a queue depth** (`05` §11.5, D-M9.3-1). The receiver records and
  /// completes an operation in one request, so this survives only if processing was
  /// interrupted after receipt. Normally zero.
  final int pending;

  /// Held for a dependency the server has not yet accepted. Unreachable in V1 — local
  /// reference resolution is Edition 2 — but part of the frozen contract.
  final int deferred;

  final int rejected;

  /// The refused operations themselves, oldest first. Four fields and no more (D-M9.3-2).
  final List<RejectedOperation> rejections;

  bool get isHealthy => pending == 0 && rejected == 0;
}

/// One refusal, as the owner's exception list shows it.
///
/// **No payload and no detail.** The payload is business data the device already holds, and
/// `detail` is prose `05` §5 permits rewording — so a client that branched on it would be a
/// client a copy-edit can break.
final class RejectedOperation {
  const RejectedOperation({
    required this.clientUuid,
    required this.operationType,
    required this.errorCode,
    required this.clientCreatedAt,
  });

  final String clientUuid;
  final String operationType;
  final String errorCode;
  final DateTime clientCreatedAt;
}
