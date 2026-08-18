import '../../core/result.dart';
import 'server_sync_status.dart';

/// What the sync-status screen may ask of the server (`05` §11.5, M9.3).
///
/// **Read-only, and there is no second method.** M9.3 adds visibility and nothing else: no
/// send, no retry, no clear. A method here that changed server state would be M9.4 logic
/// wearing an M9.3 signature.
abstract interface class SyncStatusRepository {
  /// The server's view of **this** device.
  ///
  /// The device is identified by the JWT claim, so there is no parameter to pass and no way
  /// for one device to ask about another (D-M9.3-1, FR-SYN-011).
  Future<Result<ServerSyncStatus>> fetch();
}
