import 'failure.dart';

/// Success or [Failure], in the type rather than in a `try`.
///
/// Deliberately minimal: `fold` is the only way to read it, so a caller cannot reach the
/// value without having said what happens when there isn't one.
sealed class Result<T> {
  const Result();

  R fold<R>(R Function(T value) onOk, R Function(Failure failure) onErr);

  bool get isOk => fold((_) => true, (_) => false);
}

final class Ok<T> extends Result<T> {
  const Ok(this.value);
  final T value;

  @override
  R fold<R>(R Function(T value) onOk, R Function(Failure failure) onErr) => onOk(value);
}

final class Err<T> extends Result<T> {
  const Err(this.failure);
  final Failure failure;

  @override
  R fold<R>(R Function(T value) onOk, R Function(Failure failure) onErr) => onErr(failure);
}
