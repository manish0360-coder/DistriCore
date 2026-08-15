import 'dart:convert';

import 'package:drift/drift.dart';

import '../../core/result.dart';
import '../../domain/outbox/outbox_operation.dart';
import '../../domain/outbox/outbox_repository.dart';
import '../../domain/outbox/outbox_status.dart';
import '../db/app_database.dart';
import '../outbox/storage_failure.dart';

/// The outbox, on SQLite (M8 §5.3, §9).
final class DriftOutboxRepository implements OutboxRepository {
  DriftOutboxRepository(this._db);

  final AppDatabase _db;

  @override
  Future<Result<OutboxOperation>> append({
    required String clientUuid,
    required String operationType,
    required DateTime clientCreatedAt,
    required Map<String, Object?> payload,
  }) async {
    try {
      // One transaction. `Ok` is returned only after it commits, which is what makes
      // §5.3's "the user is never told 'saved' before it is" true rather than intended.
      final row = await _db.transaction(() async {
        final existing = await (_db.select(_db.outboxOperations)
              ..where((row) => row.clientUuid.equals(clientUuid)))
            .getSingleOrNull();
        // I-4: a replay returns the original operation. The lookup is a fast path, not the
        // guarantee — the UNIQUE constraint below is, and it is what survives a race.
        if (existing != null) return existing;

        final sequence = await _db.into(_db.outboxOperations).insert(
              OutboxOperationsCompanion.insert(
                clientUuid: clientUuid,
                operationType: operationType,
                // Metadata (D-C2), stored in the wire's own form so it round-trips.
                clientCreatedAt: clientCreatedAt.toUtc().toIso8601String(),
                // Verbatim. The device captures facts; it does not edit them (P-1).
                payload: jsonEncode(payload),
                // **M8 writes PENDING and nothing else** (§5.3). M9 owns every transition.
                status: OutboxStatus.pending.code,
              ),
            );
        return (_db.select(_db.outboxOperations)
              ..where((row) => row.sequence.equals(sequence)))
            .getSingle();
      });
      return Ok(_toDomain(row));
    } catch (error) {
      final failure = storageFailureFor(error);
      if (failure != null) return Err(failure);
      rethrow; // D-C3: only storage exhaustion is StorageFull. Everything else is itself.
    }
  }

  @override
  Future<Result<List<OutboxOperation>>> pending({int limit = 100}) async {
    try {
      final rows = await (_db.select(_db.outboxOperations)
            ..where((row) => row.status.equals(OutboxStatus.pending.code))
            // **D-C2.** Sequence, never `client_created_at`: a clock adjustment reorders
            // timestamps within one device, and P-4 keeps the clock off this path.
            ..orderBy([(row) => OrderingTerm.asc(row.sequence)])
            ..limit(limit))
          .get();
      return Ok(rows.map(_toDomain).toList());
    } catch (error) {
      final failure = storageFailureFor(error);
      if (failure != null) return Err(failure);
      rethrow;
    }
  }

  @override
  Future<Result<int>> depth() async {
    final count = _db.outboxOperations.sequence.count();
    final query = _db.selectOnly(_db.outboxOperations)
      ..addColumns([count])
      ..where(_db.outboxOperations.status.equals(OutboxStatus.pending.code));
    final row = await query.getSingle();
    return Ok(row.read(count) ?? 0);
  }

  @override
  Future<Result<int>> purgeAcknowledgedBefore(DateTime before) async {
    // **Only ACKNOWLEDGED.** `REJECTED` has no delete path at all (C-3, FR-SYN-006, P-5)
    // and `PENDING` is unsent work. Deleting rows is safe for ordering only because D-C1
    // chose `AUTOINCREMENT`: without it, removing the highest row would let SQLite reissue
    // its rowid.
    final deleted = await (_db.delete(_db.outboxOperations)
          ..where((row) =>
              row.status.equals(OutboxStatus.acknowledged.code) &
              row.clientCreatedAt.isSmallerThanValue(before.toUtc().toIso8601String())))
        .go();
    return Ok(deleted);
  }

  OutboxOperation _toDomain(OutboxRow row) => OutboxOperation(
        sequence: row.sequence,
        clientUuid: row.clientUuid,
        operationType: row.operationType,
        clientCreatedAt: DateTime.parse(row.clientCreatedAt),
        payload: jsonDecode(row.payload) as Map<String, Object?>,
        status: OutboxStatus.fromCode(row.status),
      );
}
