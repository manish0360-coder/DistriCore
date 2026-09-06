import '../../core/failure.dart';
import '../../core/result.dart';
import '../../domain/companion/companion.dart';
import '../../domain/companion/companion_repository.dart';
import '../api/api_client.dart';
import 'companion_dto.dart';

/// Owner Companion Mode over the existing client (M8 §3.4, task 8).
///
/// **Four `GET`s and nothing else.** Every path below already existed before this milestone;
/// task 8 is *"read-only over endpoints that already exist"* (§10.1), and the only backend
/// change it needed was one additive field (`05` §9.4.1).
///
/// **Online-only for V1** (ruled 2026-09-06). No cache is consulted and none is written, so
/// there is no `as_of` to label: what the screen shows is what this request returned. That is
/// a deliberate narrowing of P-8 rather than an omission of it — the owner is on a scooter
/// with a signal, not in a warehouse without one, and adding a cache would mean adding a
/// second source of truth for figures the web admin already owns.
final class ApiCompanionRepository implements CompanionRepository {
  const ApiCompanionRepository(this._api);

  static const dashboardPath = '/reports/dashboard';
  static const deliveriesPath = '/deliveries';
  static const receivablesPath = '/reports/receivables';
  static const ordersPath = '/orders';

  /// `Delivery.Status` — `PENDING | DELIVERED | FAILED`. "Not yet completed" is one value.
  static const pendingStatus = 'PENDING';
  static const failedStatus = 'FAILED';

  /// `SalesOrder.Status.CONFIRMED` — confirmed and not yet dispatched, which is exactly
  /// `02A` §13's *"unactioned orders"*.
  static const confirmedStatus = 'CONFIRMED';

  /// `StandardPagination` defaults to 25 and caps at 100.
  ///
  /// **One page, on purpose.** These are attention lists, not registers: an owner who has
  /// more than a hundred undispatched orders has a different problem from the one this screen
  /// solves, and paging a phone through hundreds of rows over 2G to render a card the user
  /// scrolls past would spend the connection on the wrong thing. The web admin is where the
  /// full list lives — §3.4: *"Link out to the web admin for action."*
  static const pageSize = 100;

  final ApiClient _api;

  @override
  Future<Result<Dashboard>> dashboard() =>
      _guard(() => _api.get<Dashboard>(dashboardPath, decode: CompanionDto.dashboardFromJson));

  @override
  Future<Result<List<CompanionDelivery>>> pendingDeliveries() => _guard(
        () => _api.get<List<CompanionDelivery>>(
          deliveriesPath,
          query: {'status': pendingStatus, 'page_size': pageSize},
          decode: CompanionDto.deliveriesFromJson,
        ),
      );

  @override
  Future<Result<ReceivablesSummary>> receivables() => _guard(
        () => _api.get<ReceivablesSummary>(
          receivablesPath,
          // **No period parameter.** §3.4's boundary: Companion Mode does not *"run reports
          // over arbitrary periods"*. The ageing report is a balance and defaults to today.
          decode: CompanionDto.receivablesFromJson,
        ),
      );

  @override
  Future<Result<AttentionBoard>> needsAttention() async {
    final orders = await _guard(
      () => _api.get<List<AttentionItem>>(
        ordersPath,
        query: {'status': confirmedStatus, 'page_size': pageSize},
        decode: CompanionDto.undispatchedFromJson,
      ),
    );
    if (orders case Err(:final failure)) return Err(failure);

    final failed = await _guard(
      () => _api.get<List<AttentionItem>>(
        deliveriesPath,
        query: {'status': failedStatus, 'page_size': pageSize},
        decode: CompanionDto.failedFromJson,
      ),
    );
    if (failed case Err(:final failure)) return Err(failure);

    // **Either read failing fails the board.** A short list and a list that could not be
    // built look identical on screen, and the second one silently tells the owner there is
    // nothing to do — the one wrong answer this screen must never give. Same reasoning as
    // `SyncStatusController` refusing to report zero when the queue could not be read.
    return Ok(
      AttentionBoard(
        items: [
          ...orders.fold((items) => items, (_) => const []),
          ...failed.fold((items) => items, (_) => const []),
        ],
      ),
    );
  }

  /// Turns a decode refusal into a [Failure], the way [ApiSyncStatusRepository] does.
  ///
  /// `ApiClient` already converts `DioException` and [MoneyFormatException]; what it cannot
  /// know about is this file's own payload contract. Catching here rather than inside each
  /// decoder keeps the decoders pure functions that a test can call directly.
  Future<Result<T>> _guard<T>(Future<Result<T>> Function() call) async {
    try {
      return await call();
    } on CompanionPayloadException catch (error) {
      return Err(MalformedResponse(error.reason));
    }
  }
}
