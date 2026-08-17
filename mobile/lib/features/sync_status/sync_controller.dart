import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/failure.dart';
import '../../domain/outbox/outbox_operation.dart';
import 'sync_providers.dart';

final syncStatusProvider =
    NotifierProvider<SyncStatusController, SyncStatusState>(SyncStatusController.new);

/// How many of the oldest operations the detail list shows.
///
/// The headline count comes from `depth()` and is authoritative; this is a sample, labelled
/// as one. Loading the whole queue to build a per-type breakdown would be a table scan on a
/// device to produce a number nobody acts on.
const kOldestSample = 20;

@immutable
final class SyncStatusState {
  const SyncStatusState({
    this.loading = false,
    this.pending = 0,
    this.oldest = const [],
    this.asOf,
    this.message,
  });

  final bool loading;

  /// FR-SYN-008's *"count of pending transactions"*. From `depth()`, so it is the whole
  /// queue and not the sample below.
  final int pending;

  /// The oldest [kOldestSample] operations, sequence order (D-C2).
  final List<OutboxOperation> oldest;

  /// **P-8.** A count read ten minutes ago is fine; a count read ten minutes ago and
  /// presented as live is not.
  final DateTime? asOf;

  final String? message;

  bool get isEmpty => pending == 0;

  SyncStatusState copyWith({
    bool? loading,
    int? pending,
    List<OutboxOperation>? oldest,
    DateTime? asOf,
    String? message,
    bool clearMessage = false,
  }) =>
      SyncStatusState(
        loading: loading ?? this.loading,
        pending: pending ?? this.pending,
        oldest: oldest ?? this.oldest,
        asOf: asOf ?? this.asOf,
        message: clearMessage ? null : (message ?? this.message),
      );
}

/// What the device is still carrying (M8 §10 task 9, FR-SYN-008).
///
/// **Reads only, and never leaves the device.** M8 has no drain (§1.2), so nothing here can
/// retry, reorder or clear anything — a button that appeared to would be M9 logic wearing an
/// M8 label.
final class SyncStatusController extends Notifier<SyncStatusState> {
  @override
  SyncStatusState build() => const SyncStatusState();

  Future<void> load() async {
    if (state.loading) return;
    state = state.copyWith(loading: true, clearMessage: true);

    final outbox = ref.read(outboxPortProvider);
    final depth = await outbox.depth();
    final oldest = await outbox.pending(limit: kOldestSample);
    final now = ref.read(syncClockProvider).nowUtc();

    // Either read failing means the queue could not be inspected. Reporting zero would be
    // the worst possible answer — it is the one that says "nothing is waiting".
    final failure = depth.fold((_) => null, (f) => f) ?? oldest.fold((_) => null, (f) => f);
    if (failure != null) {
      state = state.copyWith(loading: false, message: _messageFor(failure));
      return;
    }

    state = state.copyWith(
      loading: false,
      pending: depth.fold((count) => count, (_) => 0),
      oldest: oldest.fold((operations) => operations, (_) => const []),
      asOf: now,
      clearMessage: true,
    );
  }

  String _messageFor(Failure failure) => switch (failure) {
        StorageFull() => 'Not enough storage to read the queue. Free some space.',
        Offline() ||
        Unauthenticated() ||
        MalformedResponse() ||
        Refused() ||
        ProblemFailure() =>
          // None of these can arise from a local read today. Named rather than defaulted,
          // because `Failure` is sealed and a new member should fan out here.
          'The pending queue could not be read.',
      };
}
