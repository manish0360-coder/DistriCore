import '../../core/money.dart';
import '../../domain/companion/companion.dart';

/// Decoding for Companion Mode's four payloads (M8 §3.4).
///
/// **Strict about what a screen cannot render without, forgiving about the rest** — the same
/// split `DeliveryDto` and `ApiSyncStatusRepository` make. A missing metric `key` is a broken
/// contract; a missing `caption` is a label.
///
/// **Money is never read as a number.** `05` AD-02 sends it as a decimal string and
/// `Money.fromJson` throws on a `num`, so a server that regressed to floats fails loudly at
/// this boundary rather than rounding quietly for months. TD-36 fixed the server side of that
/// contract at `5e22614`; this is the client half, and it stays whether or not the server
/// behaves.
final class CompanionDto {
  const CompanionDto._();

  // ------------------------------------------------------------------ 1. Today
  /// `GET /reports/dashboard` → [Dashboard] (`05` §9.11.1).
  static Dashboard dashboardFromJson(Object? body) {
    if (body is! Map) throw const CompanionPayloadException('dashboard: not an object');

    final metrics = body['metrics'];
    if (metrics is! List) {
      throw const CompanionPayloadException('dashboard: metrics missing or not a list');
    }

    return Dashboard(
      asOf: _date(body['as_of']),
      metrics: [for (final metric in metrics) _metric(metric)],
    );
  }

  /// One metric, branching on the server's own `is_money` rather than on the metric's key.
  ///
  /// `05` §9.11.1 departure 3: *"`awaiting_dispatch` is a JSON number, not a string. AD-02
  /// governs money and quantity. A count is neither… `is_money` says which encoding applies,
  /// per metric."* Hard-coding which keys are money would work today and break on the fifth
  /// metric, which is exactly the kind of drift a per-metric flag exists to prevent.
  static DashboardMetric _metric(Object? raw) {
    if (raw is! Map) throw const CompanionPayloadException('metric: not an object');

    final key = raw['key'];
    if (key is! String || key.isEmpty) {
      throw const CompanionPayloadException('metric: key missing');
    }

    final isMoney = raw['is_money'] == true;
    final value = raw['value'];

    return DashboardMetric(
      key: key,
      label: _text(raw['label']),
      // `Money.fromJson` is the guard, not a formatter: it refuses a `num` outright. Its
      // `toJson` gives the value back at the scale it arrived with, so `"11800.00"` stays
      // two-place rather than normalising to `"11800"`.
      value: isMoney ? Money.fromJson(value).toJson() : _count(value, key),
      caption: _text(raw['caption']),
      isLive: raw['is_live'] == true,
      isMoney: isMoney,
    );
  }

  /// A non-money metric. An integer stays an integer — stringifying it here would undo the
  /// distinction §9.11.1 item 3 draws.
  static String _count(Object? value, String key) {
    if (value is int) return value.toString();
    throw CompanionPayloadException('metric $key: is_money is false but value is not an int');
  }

  // ------------------------------------------------------- 2. Pending deliveries
  /// `GET /deliveries?status=…` → [CompanionDelivery] (`05` §9.4, §9.4.1).
  ///
  /// **AD-05's `{results: [...]}` envelope**, because this reads the list endpoint directly
  /// rather than through `PullService`. `DeliveryDto` takes the bare list for the opposite
  /// reason, and the two are separate decoders precisely so neither has to guess.
  static List<CompanionDelivery> deliveriesFromJson(Object? body) =>
      [for (final row in _results(body, 'deliveries')) _delivery(row)];

  static CompanionDelivery _delivery(Object? raw) {
    if (raw is! Map) throw const CompanionPayloadException('delivery: not an object');

    final id = raw['id'];
    if (id is! int) throw const CompanionPayloadException('delivery: id missing');

    final reason = _text(raw['failure_reason']);
    return CompanionDelivery(
      id: id,
      orderNumber: _text(raw['order_number']),
      customerName: _text(raw['customer_name']),
      // `05` §9.4.1. Empty when nobody is assigned, which is a state and not a defect.
      assignedUserName: _text(raw['assigned_user_name']),
      status: _text(raw['status']),
      failureReason: reason.isEmpty ? null : reason,
    );
  }

  // ------------------------------------------------------------- 3. Receivables
  /// `GET /reports/receivables` → [ReceivablesSummary] (`05` §9.11).
  ///
  /// **A prefix of a server-ordered list.** `reporting.receivables_ageing` sorts by age
  /// descending before returning, so "worst ten" is `take(10)` and nothing else — §2.3
  /// forbids the device deriving a credit decision, and re-sorting here would be a second
  /// implementation of an ordering the server owns (D-3).
  static ReceivablesSummary receivablesFromJson(Object? body) {
    if (body is! Map) throw const CompanionPayloadException('receivables: not an object');

    final rows = body['rows'];
    if (rows is! List) {
      throw const CompanionPayloadException('receivables: rows missing or not a list');
    }

    // **The report's own total, not a fold over the visible rows.** Ten rows sum to a
    // different number from the whole fleet, and a label that says "total outstanding" over
    // the first answer would be quietly wrong. Absent only when the report is empty.
    final total = body['total'];
    final outstanding = total is Map ? total['outstanding'] : null;

    return ReceivablesSummary(
      totalOutstanding: outstanding == null ? Money.zero : Money.fromJson(outstanding),
      worst: [for (final row in rows.take(kWorstCustomers)) _receivable(row)],
    );
  }

  static ReceivableRow _receivable(Object? raw) {
    if (raw is! Map) throw const CompanionPayloadException('receivable: not an object');

    final outstanding = raw['outstanding'];
    if (outstanding == null) {
      throw const CompanionPayloadException('receivable: outstanding missing');
    }

    final days = raw['oldest_days'];
    return ReceivableRow(
      code: _text(raw['code']),
      customerName: _text(raw['label']),
      outstanding: Money.fromJson(outstanding),
      bucket: _text(raw['bucket']),
      // TD-36: a `COUNT` column is a JSON integer, and `null` where nothing was measured.
      // Anything else is a contract change, so it is not coerced into a plausible zero.
      oldestDays: days is int ? days : null,
    );
  }

  // ---------------------------------------------------------- 4. Needs attention
  /// `GET /orders?status=CONFIRMED` → the undispatched half of the board.
  static List<AttentionItem> undispatchedFromJson(Object? body) => [
        for (final row in _results(body, 'orders'))
          if (row is Map)
            AttentionItem(
              kind: AttentionKind.undispatchedOrder,
              reference: _text(row['order_number']),
              customerName: _text(row['customer_name']),
              detail: _amount(row['total_amount']),
            ),
      ];

  /// `GET /deliveries?status=FAILED` → the failed half.
  static List<AttentionItem> failedFromJson(Object? body) => [
        for (final row in _results(body, 'deliveries'))
          if (row is Map)
            AttentionItem(
              kind: AttentionKind.failedDelivery,
              reference: _text(row['order_number']),
              customerName: _text(row['customer_name']),
              // `ck_delivery_failed_reason` makes this mandatory on a FAILED row, so an
              // empty one is a server defect rather than a missing optional.
              detail: _text(row['failure_reason']),
            ),
      ];

  /// Prose for a card, so an unreadable amount must not lose the row.
  ///
  /// The reference and the customer are what the owner acts on; refusing the whole item
  /// because a label would not parse would hide work that needs them.
  static String _amount(Object? value) {
    if (value == null) return '';
    try {
      return Money.fromJson(value).toJson();
    } on MoneyFormatException {
      return '';
    }
  }

  // ----------------------------------------------------------------- primitives
  /// AD-05's list envelope: `{"count": n, "results": [...]}`.
  ///
  /// Returns the raw list rather than a typed one: `strict-casts` forbids the implicit
  /// `List<dynamic>` → `List<Object?>` narrowing, and every caller iterates anyway — which
  /// is the shape `DeliveryDto` and `ApiSyncStatusRepository` already use.
  static List<dynamic> _results(Object? body, String what) {
    if (body is! Map) throw CompanionPayloadException('$what: not an object');
    final results = body['results'];
    if (results is! List) {
      throw CompanionPayloadException('$what: results missing or not a list');
    }
    return results;
  }

  static String _text(Object? value) => value is String ? value : '';

  /// `as_of` is a date, not an instant. `null` for anything unparseable — a dashboard with
  /// an unreadable label is still four usable numbers.
  static DateTime? _date(Object? value) =>
      value is String ? DateTime.tryParse(value)?.toUtc() : null;
}

/// A Companion payload did not match `05`. Carries a reason, never a value.
final class CompanionPayloadException implements Exception {
  const CompanionPayloadException(this.reason);

  final String reason;

  @override
  String toString() => 'CompanionPayloadException: $reason';
}
