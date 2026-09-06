import '../../core/result.dart';
import 'companion.dart';

/// What Owner Companion Mode may ask of the server (M8 §3.4).
///
/// **Four reads, and there is deliberately no fifth method.** §3.4's boundary table is the
/// specification:
///
/// | Companion Mode does | does not |
/// | --- | --- |
/// | Read | Write **anything** |
/// | Show today's operational state | Run reports over arbitrary periods |
/// | Drill from a number to the list behind it | Export CSV |
/// | Link out to the web admin for action | Approve, cancel, adjust, price, invoice |
///
/// So this interface has no `confirm`, no `dispatch`, no `cancel` and no period parameter —
/// the same discipline `SyncStatusRepository` applies for the same reason: *"a method here
/// that changed server state would be M9.4 logic wearing an M9.3 signature."*
///
/// **That is not the security control.** `02A` §9.3/DV-4 assume the binary is decompiled, so
/// read-only is enforced by CORE refusing writes, not by this file omitting them. What the
/// omission buys is that no future screen can reach for one by accident.
abstract interface class CompanionRepository {
  /// The four D-4 numbers (`05` §9.11.1). No period: the endpoint resolves *today*
  /// server-side, which is the one place in `/reports/` that does.
  Future<Result<Dashboard>> dashboard();

  /// Assigned and not yet completed — `GET /deliveries?status=PENDING`.
  ///
  /// `Delivery.Status` is `PENDING | DELIVERED | FAILED`, so *"not yet completed"* is
  /// exactly one value rather than a set the client has to assemble.
  Future<Result<List<CompanionDelivery>>> pendingDeliveries();

  /// The ageing report's total and its worst [kWorstCustomers] rows (`05` §9.11).
  Future<Result<ReceivablesSummary>> receivables();

  /// Undispatched orders and failed deliveries, in one board (M8 §3.4, `02A` §13).
  Future<Result<AttentionBoard>> needsAttention();
}
