/// A snapshot read from the local cache, with the moment the server produced it (D-M9.4-6).
///
/// **P-8: *"a cached figure is always displayed with its `as_of`. Stale is acceptable;
/// silently stale is not."*** Returning a bare list would make it impossible for a screen to
/// honour that — the rows carry no timestamp and should not, because `as_of` is one fact
/// about the whole snapshot rather than a field repeated on every row.
///
/// That is also why `asOf` is here and not on `Customer` or `Delivery`: those are entities,
/// and this is provenance.
final class CachedRound<T> {
  const CachedRound({required this.rows, this.asOf});

  /// Empty is a legitimate answer — a device that has never pulled has an empty round, and
  /// saying so is honest where an error would not be.
  final List<T> rows;

  /// The server's `server_time` from the last completed pull, or `null` if none has ever
  /// finished. **`null` means "never synced", not "synced at the epoch"**, and a screen must
  /// render the two differently.
  final DateTime? asOf;

  bool get isEmpty => rows.isEmpty;

  /// The same snapshot with different rows — used when an outbox overlay rewrites one.
  /// `asOf` travels with it, because overlaying a local write does not change when the
  /// server's copy was taken.
  CachedRound<T> withRows(List<T> replacement) =>
      CachedRound<T>(rows: replacement, asOf: asOf);
}
