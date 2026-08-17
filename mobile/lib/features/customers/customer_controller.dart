import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/failure.dart';
import '../../domain/customer/customer.dart';
import '../../domain/visit/visit_outcome.dart';
import 'customer_providers.dart';

final customerListProvider =
    NotifierProvider<CustomerListController, CustomerListState>(CustomerListController.new);

@immutable
final class CustomerListState {
  const CustomerListState({
    this.loading = false,
    this.customers = const [],
    this.message,
    this.busyId,
  });

  final bool loading;
  final List<Customer> customers;

  /// Client-owned prose. Never a raw server `detail` — `05` §5 permits rewording those.
  final String? message;

  /// The shop whose visit is being written. **The duplicate-submission guard**, and an id
  /// rather than a flag so one slow write does not freeze the rest of the round.
  final int? busyId;

  CustomerListState copyWith({
    bool? loading,
    List<Customer>? customers,
    String? message,
    bool clearMessage = false,
    int? busyId,
    bool clearBusy = false,
  }) =>
      CustomerListState(
        loading: loading ?? this.loading,
        customers: customers ?? this.customers,
        message: clearMessage ? null : (message ?? this.message),
        busyId: clearBusy ? null : (busyId ?? this.busyId),
      );
}

final class CustomerListController extends Notifier<CustomerListState> {
  @override
  CustomerListState build() => const CustomerListState();

  Future<void> load() async {
    if (state.loading) return;
    state = state.copyWith(loading: true, clearMessage: true);

    final result = await ref.read(customerRepositoryProvider).customers();

    state = result.fold(
      (customers) =>
          state.copyWith(loading: false, customers: customers, clearMessage: true),
      (failure) => state.copyWith(loading: false, message: _messageFor(failure)),
    );
  }

  /// Log a call. **Returns as soon as the row is on disk** — nothing here awaits a network
  /// call (P-2), so it behaves identically in a market and in a basement.
  ///
  /// The `busyId` check is the real duplicate guard: a visit carries a fresh `client_uuid`
  /// by design (a shop may be called on twice), so two taps of one button would otherwise be
  /// two genuine visits rather than one replay.
  Future<void> recordVisit({
    required Customer customer,
    required VisitOutcome outcome,
    String notes = '',
  }) async {
    if (state.busyId != null) return;

    state = state.copyWith(busyId: customer.id, clearMessage: true);
    final result = await ref.read(customerRepositoryProvider).recordVisit(
          customer: customer,
          outcome: outcome,
          notes: notes.trim(),
        );

    state = result.fold(
      (visited) => state.copyWith(
        clearBusy: true,
        clearMessage: true,
        customers: [
          for (final row in state.customers)
            if (row.id == visited.id) visited else row,
        ],
      ),
      (failure) => state.copyWith(clearBusy: true, message: _messageFor(failure)),
    );
  }

  /// `Failure` is sealed, so this is exhaustive at compile time.
  String _messageFor(Failure failure) => switch (failure) {
        Offline() => 'No connection. Visits you record are saved and will sync.',
        Unauthenticated() => 'Your session has ended. Please sign in again.',
        StorageFull() => 'Not enough storage to save this. Free some space and try again.',
        MalformedResponse() => 'The server sent something we could not read.',
        Refused() || ProblemFailure() => 'That could not be saved. Try again.',
      };
}
