import '../../core/result.dart';
import '../sync/cached_round.dart';
import 'delivery.dart';

/// What a delivery screen may ask for (M8 §2.2, §10 task 5).
///
/// **There is no `send` here, and that is P-2.** [complete] records a fact durably and
/// returns; the network is a background consequence that M9 owns. A method on this interface
/// that awaited an HTTP call would put a spinner between a salesman and the next drop.
abstract interface class DeliveryRepository {
  /// The rounds assigned to the signed-in user.
  ///
  /// **Cache-first since M9.4** — this reads only what the last pull left on the device, so
  /// a driver starting the day in a depot with no signal still has their round. That was the
  /// largest gap in the app from T5 until now. The network belongs to `PullService`.
  ///
  /// The result carries `asOf` (P-8). `null` means no pull has ever completed.
  ///
  /// Locally completed deliveries are already overlaid on the result, so a caller never sees
  /// a delivery it has queued as still awaiting handover.
  Future<Result<CachedRound<Delivery>>> assignedToMe();

  /// Record a handover. **Durable before it returns** (§5.3).
  ///
  /// `Ok` means one `DELIVERY_COMPLETE` row is committed to disk — the difference between a
  /// confirmation and a lie. Calling it twice for the same delivery yields the *same*
  /// operation, never a second one (I-4).
  Future<Result<Delivery>> complete({
    required Delivery delivery,
    required String recipientName,
  });
}
