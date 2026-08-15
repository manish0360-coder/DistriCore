/// The four states of an outbox operation (M8 §5.3).
///
/// **All four exist in the schema from the first migration, and M8 writes only
/// [pending].** That is not speculative: the M8 gate is *"outbox survives kill, restart and
/// storage exhaustion"*, and a schema that has to grow states at M9 is a migration on a
/// device already carrying a week of unsent work (AR-3).
///
/// The wire codes match `04` T-26's `sync_operation.status` vocabulary so that M9's mapping
/// is a lookup rather than a translation.
enum OutboxStatus {
  /// Written locally, never transmitted. **The only state M8 creates.**
  pending('PENDING'),

  /// Handed to the network, no result yet. M9 writes this.
  inFlight('IN_FLIGHT'),

  /// The server accepted it. Purgeable after the retention window (§5.3).
  acknowledged('ACKNOWLEDGED'),

  /// The server refused it. **Never deleted by code** — C-3, FR-SYN-006, P-5.
  rejected('REJECTED');

  const OutboxStatus(this.code);

  /// The stored and transmitted form. Persisted as text rather than as an ordinal so a
  /// reordering of this enum cannot silently reinterpret rows already on a device.
  final String code;

  static OutboxStatus fromCode(String code) => OutboxStatus.values.firstWhere(
        (status) => status.code == code,
        orElse: () => throw ArgumentError('Unknown outbox status: $code'),
      );

  /// C-3 / P-5. Asked as a question of the state itself, so no caller has to remember it.
  bool get isPurgeable => this == OutboxStatus.acknowledged;
}
