import 'package:decimal/decimal.dart';

/// **P-3 / `05` AD-02 / C-1 — the client half of "money is never a `double`".**
///
/// `05` AD-02 sends every monetary and quantity value as a **string** for one reason: JSON
/// numbers are IEEE-754 doubles in essentially every parser, Dart's included. `jsonDecode`
/// turns `1180.00` into a `double` before any of our code sees it, and the error is baked
/// in by then — there is no later point at which it can be detected.
///
/// So this type refuses to be built from a number at all. **That refusal is the mechanism.**
/// A DTO that reaches for `Money.fromJson(json['amount'])` on a field the server sent
/// unquoted throws at the boundary, loudly, instead of rounding quietly for months.
///
/// **TD-36 is the server side of this exact defect** — the seven report endpoints emit money
/// as JSON floats today. When that is fixed the client needs no change; until it is, this
/// type turns a silent corruption into a visible failure.
///
/// A plain class rather than an extension type: this must be obvious to read and impossible
/// to bypass, and an extension type erases to its representation at run time.
final class Money implements Comparable<Money> {
  const Money._(this.value, this.scale);

  /// Parse a wire value. **Strings only**, per AD-02.
  ///
  /// A numeric input throws rather than converting: by the time a `double` exists the
  /// precision is already gone, so accepting it would mean storing a value we know is wrong.
  factory Money.fromJson(Object? raw) {
    if (raw is String) {
      final parsed = Decimal.tryParse(raw);
      if (parsed == null) throw MoneyFormatException.unparseable(raw);
      return Money._(parsed, _scaleOf(raw));
    }
    if (raw is num) throw MoneyFormatException.notAString(raw);
    throw MoneyFormatException.unparseable(raw);
  }

  /// For values this app constructs itself — a quantity typed by the user, a zero total.
  factory Money.parse(String value) => Money.fromJson(value);

  static final Money zero = Money._(Decimal.zero, 0);

  /// Digits after the decimal point **as received**, so the wire form round-trips.
  ///
  /// `package:decimal` normalises: `Decimal.parse('11800.00').toString()` is `'11800'`.
  /// That is correct arithmetic and wrong transport. `05` sends money at 14,2 and quantity
  /// at 14,3, and an app that answers `"11800"` to a server that said `"11800.00"` has
  /// quietly changed the field's declared scale — the kind of difference that is invisible
  /// until a reconciliation report disagrees by nothing at all.
  static int _scaleOf(String raw) {
    final dot = raw.indexOf('.');
    return dot < 0 ? 0 : raw.length - dot - 1;
  }

  /// Combining two values keeps the wider scale — standard decimal semantics, and it means
  /// `zero + "0.01"` is `"0.01"` rather than `"0"`.
  static int _widest(Money a, Money b) => a.scale > b.scale ? a.scale : b.scale;

  final Decimal value;

  /// The scale this value arrived with. Carried so [toJson] can give it back unchanged.
  final int scale;

  /// The wire form. A string, always — the same discipline outbound as inbound, **at the
  /// scale it was received**, so a value read from the API and sent back is byte-identical.
  String toJson() => value.toStringAsFixed(scale);

  /// Fixed-scale display. `05` uses 14,2 for money and 14,3 for quantity; the caller says
  /// which, because this type does not know what it is measuring.
  String toStringAsScale(int scale) => value.toStringAsFixed(scale);

  Money operator +(Money other) => Money._(value + other.value, _widest(this, other));
  Money operator -(Money other) => Money._(value - other.value, _widest(this, other));
  bool operator <(Money other) => value < other.value;
  bool operator >(Money other) => value > other.value;

  bool get isZero => value == Decimal.zero;
  bool get isNegative => value < Decimal.zero;

  @override
  int compareTo(Money other) => value.compareTo(other.value);

  @override
  bool operator ==(Object other) => other is Money && other.value == value;

  @override
  int get hashCode => value.hashCode;

  @override
  String toString() => toJson();
}

/// Thrown at the wire boundary, never swallowed.
final class MoneyFormatException implements Exception {
  const MoneyFormatException(this.message);

  factory MoneyFormatException.notAString(num raw) => MoneyFormatException(
        'Money arrived as a JSON number ($raw). `05` AD-02 requires a decimal string; a '
        'number has already lost precision by the time it reaches Dart (P-3, C-1).',
      );

  factory MoneyFormatException.unparseable(Object? raw) =>
      MoneyFormatException('Not a decimal string: ${raw.runtimeType} $raw');

  final String message;

  @override
  String toString() => 'MoneyFormatException: $message';
}
