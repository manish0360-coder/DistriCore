import '../../core/result.dart';
import 'delivery.dart';

/// What a delivery screen may ask for (M8 §2.2, §10 task 5).
///
/// **There is no `send` here, and that is P-2.** [complete] records a fact durably and
/// returns; the network is a background consequence that M9 owns. A method on this interface
/// that awaited an HTTP call would put a spinner between a salesman and the next drop.
abstract interface class DeliveryRepository {
  /// The rounds assigned to the signed-in user.
  ///
  /// **Reads need the network in V1.** There is no cached delivery table — M6 added an
  /// identity row and nothing else, and §5.2 is explicit that the read cache *"is disposable
  /// and arrives with the screens that need it"*. A failed fetch is an [Err] the screen shows,
  /// not an empty list pretending to be an answer.
  ///
  /// Locally completed deliveries are already overlaid on the result, so a caller never sees
  /// a delivery it has queued as still awaiting handover.
  Future<Result<List<Delivery>>> assignedToMe();

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
