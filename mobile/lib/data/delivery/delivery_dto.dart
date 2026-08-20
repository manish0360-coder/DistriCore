import '../../domain/delivery/delivery.dart';

/// `GET /deliveries` → [Delivery] (`05` §9.4, `billing_serializers.DeliverySerializer`).
///
/// Strict about the three fields a screen cannot render without and forgiving about the
/// rest, which is the same split `UserDto` makes: a missing `id` is a broken contract, a
/// missing `recipient_name` is an undelivered parcel.
final class DeliveryDto {
  const DeliveryDto._();

  /// **A bare list — `05` §11.1's `deliveries.updated`.**
  ///
  /// This once also accepted AD-05's `{results: [...]}` envelope, because T5 read
  /// `GET /deliveries` directly. Since M9.4 the only caller is `PullService`, which always
  /// hands over `collection['updated']`; the envelope branch became unreachable from
  /// production, and a branch nothing can call is a branch nothing can test.
  static List<Delivery> listFromJson(Object? body) {
    if (body is! List) throw const DeliveryPayloadException('not a list');
    return [for (final item in body) fromJson(item)];
  }

  static Delivery fromJson(Object? body) {
    if (body is! Map) throw const DeliveryPayloadException('not an object');

    final id = body['id'];
    if (id is! int) throw const DeliveryPayloadException('id missing or not an integer');

    final status = body['status'];
    if (status is! String || status.isEmpty) {
      throw const DeliveryPayloadException('status missing');
    }

    return Delivery(
      id: id,
      orderNumber: _text(body['order_number']),
      customerName: _text(body['customer_name']),
      status: DeliveryStatus.fromCode(status),
      recipientName: body['recipient_name'] is String && (body['recipient_name'] as String).isNotEmpty
          ? body['recipient_name'] as String
          : null,
      deliveredAt: _instant(body['delivered_at']),
    );
  }

  static String _text(Object? value) => value is String ? value : '';

  /// `null` for anything unparseable. A delivery whose timestamp is malformed is still a
  /// delivery the driver has to make; refusing the whole row over a label would be worse.
  static DateTime? _instant(Object? value) =>
      value is String ? DateTime.tryParse(value)?.toUtc() : null;
}

/// The delivery payload did not match `05` §9.4. Carries a reason, never a value.
final class DeliveryPayloadException implements Exception {
  const DeliveryPayloadException(this.reason);

  final String reason;

  @override
  String toString() => 'DeliveryPayloadException: $reason';
}
