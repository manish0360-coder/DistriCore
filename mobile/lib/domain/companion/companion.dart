/// **Owner Companion Mode's four read models** (M8 §3.4, ruled 2026-08-09).
///
/// > *"Lightweight read-only operational visibility. All administration and reporting stay
/// > on the web."*
///
/// **Nothing here can write, and that is structural rather than a convention.** These are
/// values; `CompanionRepository` exposes four fetches and no command. Read-only is enforced
/// server-side — `02A` §9.3 and P-9: the binary is public, so *"the absence of a button is
/// not a control"* — and this layer simply has nothing to offer a button that wanted one.
///
/// **Online-only for V1** (ruled 2026-09-06). No cache, no `as_of` label: every figure on
/// these screens was fetched in the request that drew it, so P-8's *"stale is acceptable,
/// silently stale is not"* is satisfied by there being nothing stale to show. The one
/// exception is [DashboardMetric.isLive], which the server itself sends.
library;

import '../../core/money.dart';

/// One of the four D-4 numbers (`05` §9.11.1).
///
/// **`value` is a `String`, not a `Money`, and that is the contract rather than laziness.**
/// §9.11.1 sends `awaiting_dispatch` as a JSON *integer* — *"AD-02 governs money and
/// quantity. A count is neither"* — and the other three as decimal strings. `isMoney` is the
/// server saying which encoding it used, so the decode branches on the server's own answer
/// instead of on a hard-coded list of keys that would rot the day a fifth metric appears.
final class DashboardMetric {
  const DashboardMetric({
    required this.key,
    required this.label,
    required this.value,
    required this.caption,
    required this.isLive,
    required this.isMoney,
  });

  final String key;
  final String label;

  /// Already formatted for display: a canonical decimal string for money, the digits of the
  /// count otherwise. The device does no arithmetic on it — §2.3.
  final String value;

  final String caption;

  /// `05` §9.11.1: marks a figure that describes *today* and is therefore **not
  /// reproducible**. The screen labels it rather than presenting it as a record.
  final bool isLive;

  final bool isMoney;
}

/// The Today screen's payload: four metrics and the day the server resolved.
final class Dashboard {
  const Dashboard({required this.asOf, required this.metrics});

  /// The server's date, never the device's (P-4). `null` only if the server omitted it.
  final DateTime? asOf;
  final List<DashboardMetric> metrics;
}

/// A delivery the owner is watching, not one they are performing.
///
/// Deliberately **not** `domain/delivery/Delivery`: that type carries `canComplete`,
/// `recipientName` and a status the driver's screen acts on, and reusing it here would put a
/// completable object behind a read-only screen. The overlap is three strings.
final class CompanionDelivery {
  const CompanionDelivery({
    required this.id,
    required this.orderNumber,
    required this.customerName,
    required this.assignedUserName,
    required this.status,
    this.failureReason,
  });

  final int id;
  final String orderNumber;
  final String customerName;

  /// `05` §9.4.1, added for this screen. `''` when nobody is assigned — which is a real
  /// state, not a decode failure.
  final String assignedUserName;

  final String status;

  /// Only ever populated for a failed delivery (`ck_delivery_failed_reason` makes it
  /// mandatory there). `null` on the pending list.
  final String? failureReason;
}

/// One row of the receivables ageing report (`05` §9.11), as the summary shows it.
///
/// **The ranking is the server's.** `reporting.receivables_ageing` sorts by age descending
/// before it returns, and §2.3 forbids the device deriving a credit decision — so the screen
/// takes a prefix of a list it did not order. Sorting here would be a second implementation
/// of an ordering the server already owns (D-3).
final class ReceivableRow {
  const ReceivableRow({
    required this.code,
    required this.customerName,
    required this.outstanding,
    required this.bucket,
    required this.oldestDays,
  });

  final String code;
  final String customerName;

  /// AD-02: a decimal string on the wire, a [Money] here. Since TD-36 the report endpoints
  /// send it as a string, so this parses rather than throws.
  final Money outstanding;

  /// `0-30`, `31-60`, `90+` … — a display bucket the server computes (M6 C-2). Empty when
  /// the customer has nothing outstanding.
  final String bucket;

  /// **Age, not overdue.** No overdue rule exists in the corpus — `Customer.credit_days` is
  /// stored and consumed by nothing — and V1 deliberately does not invent one (ruled
  /// 2026-09-06). This is days since the oldest unpaid document, which is what the server
  /// sends. `null` on the fleet total, which has no oldest document.
  final int? oldestDays;
}

/// The receivables summary: the whole-fleet total plus the worst few.
final class ReceivablesSummary {
  const ReceivablesSummary({required this.totalOutstanding, required this.worst});

  /// The report's own total row — **the server's sum, not a fold over [worst]**. Adding up
  /// ten rows would silently answer a different question from the one the label asks.
  final Money totalOutstanding;

  /// The first [kWorstCustomers] rows of a server-ordered list.
  final List<ReceivableRow> worst;
}

/// How many rows the receivables summary shows.
///
/// `M8_Design_Review` §3.4: *"Total outstanding, oldest bucket, **worst ten customers**"*.
/// A constant rather than a parameter because it is a specification, not a preference.
const int kWorstCustomers = 10;

/// One thing waiting on the owner (M8 §3.4, `02A` §13).
///
/// **Two kinds, and no third.** `02A` §13 cut in-app notifications entirely and named its own
/// replacement — *"an 'unactioned orders' filter on the order list achieves the same thing for
/// nothing"* — and V1 adopts that plus failed deliveries (ruled 2026-09-06). **"Overdue
/// balances" is excluded**: it would need an overdue rule the corpus does not define, and that
/// belongs in `receivables` rather than arriving inside a mobile screen.
enum AttentionKind {
  /// Confirmed and not yet dispatched. `GET /orders?status=CONFIRMED`.
  undispatchedOrder,

  /// A delivery attempt that failed, with its mandatory reason.
  /// `GET /deliveries?status=FAILED`.
  failedDelivery,
}

final class AttentionItem {
  const AttentionItem({
    required this.kind,
    required this.reference,
    required this.customerName,
    this.detail = '',
  });

  final AttentionKind kind;

  /// The order number or the delivery's order number — what the owner would quote on the
  /// phone, and what they would search for in the web admin to act on it.
  final String reference;

  final String customerName;

  /// The failure reason, or the order's value. Prose for the eye, never parsed.
  final String detail;
}

/// Everything the "Needs attention" screen shows, in one value.
///
/// Both lists are fetched; **an empty screen and a screen that could not load are different
/// claims**, so a failure of either read is a failure of the load rather than a silently
/// short list.
final class AttentionBoard {
  const AttentionBoard({this.items = const []});

  final List<AttentionItem> items;

  bool get isEmpty => items.isEmpty;
}
