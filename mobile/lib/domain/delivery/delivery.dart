/// Where a delivery is in its life (`04` T-16).
///
/// Unknown codes become [unknown] rather than throwing, for the reason `Role.fromCodes`
/// drops them: a server that adds a state must not brick an installed app. **[unknown] is
/// not actionable** — the UI offers no button for it — so a new state degrades to "visible
/// but read-only" instead of to a crash or to a wrong action.
enum DeliveryStatus {
  pending('PENDING'),
  dispatched('DISPATCHED'),
  delivered('DELIVERED'),
  failed('FAILED'),
  unknown('');

  const DeliveryStatus(this.code);

  final String code;

  static DeliveryStatus fromCode(String code) => DeliveryStatus.values.firstWhere(
        (status) => status.code == code,
        orElse: () => DeliveryStatus.unknown,
      );
}

/// One delivery, as a field device needs to see it.
///
/// **Carries no money.** `DeliverySerializer` returns none, and P-3 is easiest to keep by
/// not having a field a `double` could occupy.
final class Delivery {
  const Delivery({
    required this.id,
    required this.orderNumber,
    required this.customerName,
    required this.status,
    this.recipientName,
    this.deliveredAt,
  });

  final int id;
  final String orderNumber;
  final String customerName;
  final DeliveryStatus status;
  final String? recipientName;

  /// **Device time** (`05` §10.3: *"DEVICE time — may be hours before receipt"*). A label,
  /// never an ordering key (P-4).
  final DateTime? deliveredAt;

  /// Only a dispatched delivery can be handed over. `PENDING` has not left the warehouse and
  /// `DELIVERED`/`FAILED` are terminal — the server owns the machine (AD-08), and this is the
  /// client's read of it so a screen does not offer an action the server would refuse.
  bool get canComplete =>
      status == DeliveryStatus.dispatched || status == DeliveryStatus.pending;

  /// The optimistic view after a local completion is queued but not yet synced.
  ///
  /// A **new value**, not a mutation: the fetched list is a fact from the server and the
  /// pending operation is a fact from the device. Overlaying produces a third thing rather
  /// than editing either.
  Delivery completedLocally({required String recipientName, required DateTime at}) => Delivery(
        id: id,
        orderNumber: orderNumber,
        customerName: customerName,
        status: DeliveryStatus.delivered,
        recipientName: recipientName,
        deliveredAt: at,
      );
}
