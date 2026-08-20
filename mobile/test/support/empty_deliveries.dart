import 'package:districore/core/result.dart';
import 'package:districore/domain/delivery/delivery.dart';
import 'package:districore/domain/delivery/delivery_repository.dart';
import 'package:districore/domain/sync/cached_round.dart';

/// A [DeliveryRepository] for tests that are **not about deliveries**.
///
/// `deliveryRepositoryProvider` is override-required by design (T5), so any test that drives
/// the real router far enough to land on `/deliveries` must supply one — otherwise
/// `DeliveriesScreen.initState` throws `StateError` during a frame and the failure surfaces
/// much later as a `pumpAndSettle` timeout, naming the wrong thing.
///
/// **Deliberately not the recording fake `delivery_slice_test.dart` uses.** That one exists to
/// observe what a delivery test asked for; this one exists so a *different* test can reach
/// the shell without accidentally becoming a delivery test. [complete] therefore **throws**
/// rather than returning a plausible value: if a test that installed this ever completes a
/// delivery, it has drifted from what it was written to prove, and it should say so loudly.
final class EmptyDeliveryRepository implements DeliveryRepository {
  const EmptyDeliveryRepository();

  @override
  Future<Result<CachedRound<Delivery>>> assignedToMe() async =>
      // `asOf: null` — a stand-in has never pulled, and that is the honest value.
      const Ok<CachedRound<Delivery>>(CachedRound<Delivery>(rows: []));

  @override
  Future<Result<Delivery>> complete({
    required Delivery delivery,
    required String recipientName,
  }) =>
      throw UnsupportedError(
        'EmptyDeliveryRepository is a stand-in for tests that are not about deliveries. '
        'Use the recording fake in delivery_slice_test.dart to assert on a completion.',
      );
}
