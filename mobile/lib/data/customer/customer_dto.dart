import '../../domain/customer/customer.dart';

/// `GET /customers` → [Customer] (`05` §9.2, `master_serializers.CustomerSerializer`).
///
/// **`credit_limit_amount` is deliberately not read.** It is a money string (AD-02) and this
/// slice has no use for it; parsing it here would put a decimal on a path that does not need
/// one, which is how P-3 gets broken by accident rather than on purpose.
final class CustomerDto {
  const CustomerDto._();

  /// **A bare list — `05` §11.1's `customers.updated`.**
  ///
  /// This once also accepted AD-05's `{results: [...]}` envelope, because T6 read
  /// `GET /customers` directly. Since M9.4 the only caller is `PullService`, which always
  /// hands over `collection['updated']`; the envelope branch became unreachable from
  /// production, and a branch nothing can call is a branch nothing can test.
  static List<Customer> listFromJson(Object? body) {
    if (body is! List) throw const CustomerPayloadException('not a list');
    return [for (final item in body) fromJson(item)];
  }

  static Customer fromJson(Object? body) {
    if (body is! Map) throw const CustomerPayloadException('not an object');

    final id = body['id'];
    if (id is! int) throw const CustomerPayloadException('id missing or not an integer');

    final shopName = body['shop_name'];
    if (shopName is! String || shopName.isEmpty) {
      // The one field a salesman navigates by. A row without it is not a shop they can find.
      throw const CustomerPayloadException('shop_name missing');
    }

    return Customer(
      id: id,
      code: _text(body['code']),
      shopName: shopName,
      ownerName: _text(body['owner_name']),
      phone: _text(body['phone']),
      zoneName: body['zone'] is Map ? _text((body['zone']! as Map)['name']) : '',
    );
  }

  static String _text(Object? value) => value is String ? value : '';
}

/// The customer payload did not match `05` §9.2. Carries a reason, never a value.
final class CustomerPayloadException implements Exception {
  const CustomerPayloadException(this.reason);

  final String reason;

  @override
  String toString() => 'CustomerPayloadException: $reason';
}
