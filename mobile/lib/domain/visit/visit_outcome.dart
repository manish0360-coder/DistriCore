/// How a visit ended (`04` T-visit `ck_visit_outcome`).
///
/// **Exactly the three the CHECK constraint permits.** A fourth here would be rejected by the
/// database on sync, hours after the salesman walked away — so the enum is the constraint,
/// transcribed, and adding to it is a schema change rather than a UI decision.
enum VisitOutcome {
  orderTaken('ORDER_TAKEN', 'Order taken'),
  noOrder('NO_ORDER', 'No order'),
  shopClosed('SHOP_CLOSED', 'Shop closed');

  const VisitOutcome(this.code, this.label);

  /// The wire value. `05` §11.2 sends this string inside the `VISIT_CREATE` payload.
  final String code;

  /// What the salesman reads. Separate from [code] so a copy-edit is never a data change.
  final String label;

  static VisitOutcome? fromCode(String? code) {
    for (final outcome in values) {
      if (outcome.code == code) return outcome;
    }
    return null;
  }
}
