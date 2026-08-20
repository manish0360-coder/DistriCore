import '../../core/result.dart';
import '../sync/cached_round.dart';
import '../visit/visit_outcome.dart';
import 'customer.dart';

/// The salesman's round (M8 §10 task 7, `05` §9.2 and §9.7).
///
/// Same shape as `DeliveryRepository`, and for the same reasons: **read from the network,
/// write to the outbox** (P-2). A visit recorded in a shop doorway must not depend on signal.
abstract interface class CustomerRepository {
  /// The shops this user may call on.
  ///
  /// **Cache-first since M9.4** — this reads only what the last pull left on the device, so
  /// a salesman with no signal still has their round. The network belongs to `PullService`;
  /// nothing on this path touches it.
  ///
  /// The result carries `asOf` (P-8): stale is acceptable, silently stale is not. `null`
  /// means no pull has ever completed, which a screen must render differently from an empty
  /// round taken this morning.
  ///
  /// Visits already queued are overlaid, so a salesman never sees a shop they have just
  /// logged as still outstanding.
  Future<Result<CachedRound<Customer>>> customers();

  /// Record a call. **Durable before it returns** (§5.3).
  ///
  /// **Not idempotent per customer, and that is the contract rather than an omission.**
  /// `04` T-visit's only uniqueness is on `client_uuid`; a shop can legitimately be visited
  /// twice in a day, so collapsing two calls into one — which is right for a delivery, where
  /// one parcel is handed over once — would silently discard a real visit here.
  Future<Result<Customer>> recordVisit({
    required Customer customer,
    required VisitOutcome outcome,
    String notes,
  });
}
