import '../../core/result.dart';
import 'outbox_operation.dart';

/// What the app may ask of the outbox (M8 §5.3, §9).
///
/// An interface in `domain`, implemented in `data` — so the queue's rules can be reasoned
/// about, and tested, without Drift, Flutter or a device (P-10).
///
/// **There is no send, no drain and no state transition here.** M8 writes the outbox and M9
/// drains it (§1.2); a method that moved an operation out of `PENDING` would be M9 logic
/// wearing an M8 signature.
abstract interface class OutboxRepository {
  /// Append a new operation in [OutboxStatus.pending] and return it with its assigned
  /// sequence.
  ///
  /// **Durable before it returns.** `Ok` means the row is committed to disk; §5.3 —
  /// *"the user is never told 'saved' before it is"* — makes that the difference between a
  /// confirmation and a lie. A failure to persist is [Err], never a silent success (D-C3).
  ///
  /// **Idempotent on [clientUuid].** Re-appending a key already present returns the
  /// existing operation rather than creating a second: the retry a flaky connection
  /// produces is the *correct* client behaviour (I-4), and the uniqueness is a database
  /// constraint rather than a check, because a check loses the race it exists for (I-6).
  Future<Result<OutboxOperation>> append({
    required String clientUuid,
    required String operationType,
    required DateTime clientCreatedAt,
    required Map<String, Object?> payload,
  });

  /// Operations awaiting transmission, **in sequence order** (D-C2), oldest first.
  ///
  /// M8 has no drain, so this exists for the task 9 sync-status screen and for the tests
  /// that prove ordering. It reads; it changes nothing.
  Future<Result<List<OutboxOperation>>> pending({int limit});

  /// How many operations are waiting — FR-SYN-008's depth, without loading them.
  Future<Result<int>> depth();

  /// Delete acknowledged operations older than [before], and **only** those.
  ///
  /// §5.3 permits purging `ACKNOWLEDGED` after a retention window. It permits nothing else:
  /// `REJECTED` has no delete path at all (C-3, FR-SYN-006, P-5), and `PENDING` is unsent
  /// work. This is also the reason D-C1 requires `AUTOINCREMENT` — purging the highest row
  /// would otherwise let SQLite reissue its rowid and break the ordering guarantee.
  Future<Result<int>> purgeAcknowledgedBefore(DateTime before);
}
