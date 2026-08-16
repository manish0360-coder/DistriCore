import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/failure.dart';
import '../../domain/delivery/delivery.dart';
import 'delivery_providers.dart';

final deliveryListProvider =
    NotifierProvider<DeliveryListController, DeliveryListState>(DeliveryListController.new);

/// What the deliveries screen draws itself from.
@immutable
final class DeliveryListState {
  const DeliveryListState({
    this.loading = false,
    this.deliveries = const [],
    this.message,
    this.busyId,
  });

  final bool loading;
  final List<Delivery> deliveries;

  /// User-visible, client-owned prose. Never a raw server `detail` — `05` §5 says `title`
  /// and `detail` may be reworded, so a screen that rendered them is a screen a copy-edit
  /// can break.
  final String? message;

  /// The delivery whose completion is in flight. **The duplicate-submission guard**, and the
  /// reason it is an id rather than a bool: one slow handover must not freeze the buttons on
  /// every other drop in the round.
  final int? busyId;

  DeliveryListState copyWith({
    bool? loading,
    List<Delivery>? deliveries,
    String? message,
    bool clearMessage = false,
    int? busyId,
    bool clearBusy = false,
  }) =>
      DeliveryListState(
        loading: loading ?? this.loading,
        deliveries: deliveries ?? this.deliveries,
        message: clearMessage ? null : (message ?? this.message),
        busyId: clearBusy ? null : (busyId ?? this.busyId),
      );
}

/// The deliveries screen's decisions, with no widget in them.
final class DeliveryListController extends Notifier<DeliveryListState> {
  @override
  DeliveryListState build() => const DeliveryListState();

  Future<void> load() async {
    if (state.loading) return;
    state = state.copyWith(loading: true, clearMessage: true);

    final result = await ref.read(deliveryRepositoryProvider).assignedToMe();

    state = result.fold(
      (deliveries) => state.copyWith(
        loading: false,
        deliveries: deliveries,
        clearMessage: true,
      ),
      (failure) => state.copyWith(loading: false, message: _messageFor(failure)),
    );
  }

  /// Hand over a parcel.
  ///
  /// **Returns as soon as the row is on disk**, because that is when the promise is kept
  /// (§5.3). Nothing here awaits a network call — P-2 — so this completes at the same speed
  /// in a warehouse and in a dead spot.
  Future<void> complete({required Delivery delivery, required String recipientName}) async {
    // The guard, not the disabled button. A second tap can land between the tap and the
    // rebuild, and the repository's `client_uuid` reuse is the second line of defence rather
    // than the first.
    if (state.busyId != null) return;

    final recipient = recipientName.trim();
    if (recipient.isEmpty) {
      state = state.copyWith(message: 'Enter who received the delivery.');
      return;
    }

    state = state.copyWith(busyId: delivery.id, clearMessage: true);
    final result = await ref
        .read(deliveryRepositoryProvider)
        .complete(delivery: delivery, recipientName: recipient);

    state = result.fold(
      (completed) => state.copyWith(
        clearBusy: true,
        clearMessage: true,
        // The list is rebuilt rather than mutated: the fetched rows are the server's facts
        // and this one is the device's.
        deliveries: [
          for (final row in state.deliveries)
            if (row.id == completed.id) completed else row,
        ],
      ),
      (failure) => state.copyWith(clearBusy: true, message: _messageFor(failure)),
    );
  }

  /// `Failure` is sealed, so this is exhaustive at compile time.
  String _messageFor(Failure failure) => switch (failure) {
        Offline() => 'No connection. Your completed deliveries are saved and will sync.',
        Unauthenticated() => 'Your session has ended. Please sign in again.',
        // D-C3. Retrying changes nothing until space is freed, so the message says so
        // rather than implying the app is merely waiting for signal.
        StorageFull() => 'Not enough storage to save this. Free some space and try again.',
        MalformedResponse() => 'The server sent something we could not read.',
        Refused() || ProblemFailure() => 'That could not be saved. Try again.',
      };
}
