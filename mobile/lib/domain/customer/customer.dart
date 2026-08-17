import '../visit/visit_outcome.dart';

/// A shop on the salesman's round (`04` T-customer, `05` §9.2).
///
/// **Carries no money, deliberately.** `CustomerSerializer` returns `credit_limit_amount` as
/// a decimal string, and P-3 is kept most cheaply by not giving this type a field a `double`
/// could occupy. Credit arrives with the screen that needs it, through the `Money` codec.
final class Customer {
  const Customer({
    required this.id,
    required this.code,
    required this.shopName,
    this.ownerName = '',
    this.phone = '',
    this.zoneName = '',
    this.lastOutcome,
    this.visitedAt,
  });

  final int id;
  final String code;
  final String shopName;
  final String ownerName;
  final String phone;
  final String zoneName;

  /// Set once a visit for this customer is sitting in the outbox. `null` means "not visited
  /// on this round yet" — it is **not** a history: M8 has no visit list, and inventing one
  /// from the queue would present unsent work as a record.
  final VisitOutcome? lastOutcome;

  /// Device time of that queued visit (`04` T-visit `visited_at`). A label, never an
  /// ordering key (P-4).
  final DateTime? visitedAt;

  bool get visitedThisRound => lastOutcome != null;

  /// The optimistic view after a visit is queued but not yet synced.
  ///
  /// A new value rather than a mutation: the fetched row is the server's fact and the visit
  /// is the device's.
  Customer visitedLocally({required VisitOutcome outcome, required DateTime at}) => Customer(
        id: id,
        code: code,
        shopName: shopName,
        ownerName: ownerName,
        phone: phone,
        zoneName: zoneName,
        lastOutcome: outcome,
        visitedAt: at,
      );
}
