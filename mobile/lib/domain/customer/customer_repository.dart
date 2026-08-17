import '../../core/result.dart';
import '../visit/visit_outcome.dart';
import 'customer.dart';

/// The salesman's round (M8 §10 task 7, `05` §9.2 and §9.7).
///
/// Same shape as `DeliveryRepository`, and for the same reasons: **read from the network,
/// write to the outbox** (P-2). A visit recorded in a shop doorway must not depend on signal.
abstract interface class CustomerRepository {
  /// The shops this user may call on.
  ///
  /// **Reads need the network in V1.** There is no cached customer table — §5.2 keeps the
  /// read cache disposable and says it *"arrives with the screens that need it"*. A failed
  /// fetch is an [Err] the screen shows, not an empty round pretending to be an answer.
  ///
  /// Visits already queued are overlaid, so a salesman never sees a shop they have just
  /// logged as still outstanding.
  Future<Result<List<Customer>>> customers();

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
