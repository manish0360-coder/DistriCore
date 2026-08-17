import '../../core/clock.dart';
import '../../core/failure.dart';
import '../../core/result.dart';
import '../../core/uuid.dart';
import '../../domain/customer/customer.dart';
import '../../domain/customer/customer_repository.dart';
import '../../domain/outbox/outbox_operation.dart';
import '../../domain/outbox/outbox_repository.dart';
import '../../domain/visit/visit_outcome.dart';
import '../api/api_client.dart';
import '../customer/customer_dto.dart';

/// Customers: **read from the API, visits written to the outbox** (M8 §5.1, P-2).
///
/// The same asymmetry `OutboxDeliveryRepository` uses, applied to the other field role. A
/// salesman standing in a shop with no signal must be able to log the call and walk out.
final class OutboxCustomerRepository implements CustomerRepository {
  const OutboxCustomerRepository({
    required ApiClient api,
    required OutboxRepository outbox,
    required Clock clock,
  })  : _api = api,
        _outbox = outbox,
        _clock = clock;

  static const listPath = '/customers';

  /// `04` T-26's vocabulary, and one of the three `05` §11.2 spells out in its own example.
  static const operationType = 'VISIT_CREATE';

  final ApiClient _api;
  final OutboxRepository _outbox;
  final Clock _clock;

  @override
  Future<Result<List<Customer>>> customers() async {
    final Result<List<Customer>> fetched;
    try {
      fetched = await _api.get<List<Customer>>(
        listPath,
        // Active shops only. A deactivated customer is not somewhere anyone should be sent.
        query: <String, dynamic>{'is_active': true},
        decode: CustomerDto.listFromJson,
      );
    } on CustomerPayloadException catch (error) {
      return Err(MalformedResponse(error.reason));
    }

    if (fetched is Err<List<Customer>>) return Err(fetched.failure);

    final queued = await _queuedVisits();
    return Ok([
      for (final customer in (fetched as Ok<List<Customer>>).value)
        if (queued[customer.id] case final visit?)
          customer.visitedLocally(outcome: visit.outcome, at: visit.at)
        else
          customer,
    ]);
  }

  @override
  Future<Result<Customer>> recordVisit({
    required Customer customer,
    required VisitOutcome outcome,
    String notes = '',
  }) async {
    final at = _clock.nowUtc();

    // **A fresh `client_uuid` every time, and the difference from a delivery is the point.**
    // P-6 says the key is minted before the first attempt and never regenerated *for that
    // attempt* — a delivery reuses one because a parcel is handed over once. `04` T-visit has
    // no per-customer uniqueness, so a shop called on twice in a day is two visits, and
    // reusing a key here would silently discard the second. The double-tap guard lives in
    // the controller, where the two taps are one intent.
    final appended = await _outbox.append(
      clientUuid: newClientUuid(),
      operationType: operationType,
      clientCreatedAt: at,
      payload: <String, Object?>{
        // `customer_id`, not `05` §11.2's `customer_client_uuid`: that form is for a shop
        // created offline in the same batch, which is Edition 2's field capture (DV-1).
        // `04` T-visit's FK is what an existing customer is referenced by.
        'customer_id': customer.id,
        'visited_at': at.toIso8601String(),
        'outcome': outcome.code,
        if (notes.isNotEmpty) 'notes': notes,
        // **No coordinates and no photo.** `ck_visit_coords` makes them nullable together,
        // and GPS is task 6 — an absent field is honest, a zeroed one is a false fix.
        // **No `device_id`** — D-C4 carries it once per batch.
      },
    );

    return appended.fold(
      (_) => Ok(customer.visitedLocally(outcome: outcome, at: at)),
      Err.new,
    );
  }

  /// Queued visits, keyed by `customer_id`, **latest wins**.
  ///
  /// Reads the outbox rather than a second index — the queue is already the authority on
  /// what is unsent, and a parallel store would be the duplicate persistence layer this
  /// milestone is told not to build.
  Future<Map<int, ({VisitOutcome outcome, DateTime at})>> _queuedVisits() async {
    final pending = await _outbox.pending();
    return pending.fold(
      (operations) {
        final byCustomer = <int, ({VisitOutcome outcome, DateTime at})>{};
        // `pending()` is sequence-ordered oldest first (D-C2), so a later call on the same
        // shop overwrites an earlier one — which is what the salesman last recorded.
        for (final operation in operations) {
          if (operation.operationType != operationType) continue;
          final id = operation.payload['customer_id'];
          final outcome = VisitOutcome.fromCode(_codeOf(operation));
          if (id is int && outcome != null) {
            byCustomer[id] = (outcome: outcome, at: operation.clientCreatedAt);
          }
        }
        return byCustomer;
      },
      (_) => const <int, ({VisitOutcome outcome, DateTime at})>{},
    );
  }

  static String? _codeOf(OutboxOperation operation) =>
      operation.payload['outcome'] is String ? operation.payload['outcome']! as String : null;
}
