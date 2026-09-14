import 'dart:async';

import '../../core/result.dart';
import '../../domain/identity/session.dart';
import '../../domain/identity/session_repository.dart';

/// A `SessionRepository` that holds one session in memory and starts signed out.
///
/// **No longer wired.** M4 bound `sessionRepositoryProvider` to `TokenSessionRepository`;
/// this survives as a test double for suites that need a session without a keystore, a
/// network or a `--dart-define`.
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

  /// Sign out, in memory. Emits `null` exactly as the real one does, so a suite that
  /// exercises the redirect does not need a keystore.
  @override
  Future<void> signOut() async => set(null);

  /// Used by task 4's sign-in flow and by tests. Not part of the domain interface —
  /// the presentation layer may read a session, never install one.
  void set(Session? session) {
    _session = session;
    _controller.add(session);
  }

  void dispose() => unawaited(_controller.close());
}
