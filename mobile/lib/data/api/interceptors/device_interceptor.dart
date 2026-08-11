import 'package:dio/dio.dart';

import '../tokens.dart';

/// `05` C-10 / FR-IAM-009 — `device_id` on **every write**.
///
/// **It goes in the body, not in a header.** Every example in `05` §9 carries `device_id`
/// inside the JSON object, and the DRF serializers read it from `request.data`
/// (`billing_serializers.py`). A header would be accepted by the transport, ignored by the
/// server, and lose the audit attribution silently — which is exactly the failure C-10
/// names. The interceptor diagram in M8 §7.2 does not say where it goes; the contract does.
///
/// Reads only: a `device_id` already present is left alone, because a queued outbox
/// operation records the device that **captured** it, which may not be the device that
/// eventually sends it.
final class DeviceInterceptor extends Interceptor {
  DeviceInterceptor(this._tokens);

  static const _writeMethods = {'POST', 'PUT', 'PATCH'};

  final TokenStore _tokens;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final deviceId = _tokens.deviceId;
    final method = options.method.toUpperCase();
    final data = options.data;

    if (deviceId != null &&
        deviceId.isNotEmpty &&
        _writeMethods.contains(method) &&
        // `Map<String, dynamic>`, not bare `Map`: a bare `Map` narrows to
        // `Map<dynamic, dynamic>`, whose keys cannot be spread into a `<String, dynamic>`
        // literal. Widening the literal to `<dynamic, dynamic>` or casting the keys would
        // both compile — and both would let a non-string key reach `jsonEncode`, which is
        // a runtime failure on a delivery confirmation instead of a compile error here.
        //
        // Dart's generics are covariant, so this still admits a `Map<String, String>` body.
        data is Map<String, dynamic> &&
        !data.containsKey('device_id')) {
      // A new map rather than a mutation: `RequestOptions` is replayed verbatim on retry
      // (D-B3), and mutating a caller's map would edit the outbox row it came from.
      options.data = <String, dynamic>{...data, 'device_id': deviceId};
    }
    handler.next(options);
  }
}
