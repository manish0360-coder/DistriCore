import 'dart:async';

import '../../core/result.dart';
import '../../domain/identity/session.dart';
import '../../domain/identity/session_repository.dart';

/// A `SessionRepository` that holds one session in memory and starts signed out.
///
/// **This is the DI seam, not the feature.** Task 4 replaces it with the real
/// implementation over secure storage and the token endpoints; task 1 needs exactly one
/// implementation so the composition root has something to wire and the layering test is
/// not asserting a rule against an empty folder.
///
/// It deliberately persists nothing: a stub that half-remembered a session would be worse
/// than one that plainly does not, because it would look like it worked.
final class InMemorySessionRepository implements SessionRepository {
  final _controller = StreamController<Session?>.broadcast();
  Session? _session;

  @override
  Result<Session?> current() => Ok(_session);

  @override
  Stream<Session?> changes() => _controller.stream;

  /// Used by task 4's sign-in flow and by tests. Not part of the domain interface —
  /// the presentation layer may read a session, never install one.
  void set(Session? session) {
    _session = session;
    _controller.add(session);
  }

  void dispose() => unawaited(_controller.close());
}
