import '../../core/failure.dart';
import '../../core/result.dart';
import '../../domain/sync/server_sync_status.dart';
import '../../domain/sync/sync_status_repository.dart';
import '../api/api_client.dart';

/// `GET /sync/status` through the existing client (`05` §11.5, M9.3).
///
/// No auth code, no device parameter: the token carries the identity and the interceptors
/// carry the token.
final class ApiSyncStatusRepository implements SyncStatusRepository {
  const ApiSyncStatusRepository(this._api);

  static const path = '/sync/status';

  final ApiClient _api;

  @override
  Future<Result<ServerSyncStatus>> fetch() async {
    try {
      return await _api.get<ServerSyncStatus>(path, decode: _decode);
    } on SyncStatusPayloadException catch (error) {
      return Err(MalformedResponse(error.reason));
    }
  }

  /// Strict about the counts, forgiving about the rest.
  ///
  /// A missing count would render as a plausible zero — *"nothing is waiting"* — which is
  /// the one wrong answer this screen must never give. A malformed rejection entry is
  /// dropped instead, because losing one row off an advisory list is better than refusing to
  /// show the counts at all.
  static ServerSyncStatus _decode(Object? body) {
    if (body is! Map) throw const SyncStatusPayloadException('not an object');

    return ServerSyncStatus(
      deviceId: body['device_id'] is String ? body['device_id']! as String : '',
      lastSyncAt: _instant(body['last_sync_at']),
      pending: _count(body, 'pending_count'),
      deferred: _count(body, 'deferred_count'),
      rejected: _count(body, 'rejected_count'),
      rejections: _rejections(body['rejected']),
    );
  }

  static int _count(Map<dynamic, dynamic> body, String key) {
    final value = body[key];
    if (value is! int) throw SyncStatusPayloadException('$key missing or not an integer');
    return value;
  }

  static List<RejectedOperation> _rejections(Object? raw) {
    if (raw is! List) return const [];
    return [
      for (final entry in raw)
        if (entry is Map &&
            entry['client_uuid'] is String &&
            entry['operation_type'] is String)
          RejectedOperation(
            clientUuid: entry['client_uuid']! as String,
            operationType: entry['operation_type']! as String,
            errorCode: entry['error_code'] is String ? entry['error_code']! as String : '',
            clientCreatedAt: _instant(entry['client_created_at']) ?? DateTime.utc(1970),
          ),
    ];
  }

  static DateTime? _instant(Object? value) =>
      value is String ? DateTime.tryParse(value)?.toUtc() : null;
}

/// The status payload did not match `05` §11.5. Carries a reason, never a value.
final class SyncStatusPayloadException implements Exception {
  const SyncStatusPayloadException(this.reason);

  final String reason;

  @override
  String toString() => 'SyncStatusPayloadException: $reason';
}
