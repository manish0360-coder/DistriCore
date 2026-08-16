import 'dart:async';

import '../../core/result.dart';
import '../../domain/identity/session.dart';
import '../../domain/identity/session_repository.dart';
import '../api/tokens.dart';
import '../identity/session_restorer.dart';

/// The real [SessionRepository]: session state owned here, restored from the keystore.
///
/// **Bound in M4.** `sessionRepositoryProvider` now delegates to this one instance, and
/// `bootstrap` holds the concrete type so it can call [restore] — which the read-only domain
/// interface deliberately does not expose.
final class TokenSessionRepository implements SessionRepository {
  TokenSessionRepository({
    required TokenStore tokens,
    required SessionRestorer restorer,
  })  : _tokens = tokens,
        _restorer = restorer;

  final TokenStore _tokens;
  final SessionRestorer _restorer;

  final _controller = StreamController<Session?>.broadcast();
  Session? _session;

  /// **Synchronous, and callable before [restore] has run** — the domain contract offers no
  /// way to refuse, and `providers.dart` reads it to seed the first frame before it
  /// subscribes. It answers `Ok(null)`: *not signed in yet*, which is true both before
  /// restoration and after a failed one.
  @override
  Result<Session?> current() => Ok(_session);

  @override
  Stream<Session?> changes() => _controller.stream;

  /// Restore once, then publish once — **whatever the outcome**.
  ///
  /// A listener that only heard about success would wait forever on a device with no
  /// signal. Emitting `null` on failure is what moves the shell to the login screen.
  Future<Result<Session?>> restore() async {
    final result = await _restorer.restore();
    _session = result.fold((session) => session, (_) => null);
    _controller.add(_session);
    return result;
  }

  /// Publish a freshly authenticated session (M3).
  ///
  /// **Implementation-level on purpose.** The domain `SessionRepository` stays read-only —
  /// `current()` and `changes()` and nothing else — so no screen can install a session, and
  /// there is still exactly one source of truth for who is signed in. Only `AuthService`,
  /// which holds the concrete type, can call this.
  ///
  /// The caller must have persisted the credentials **before** calling: a listener rebuilds
  /// on this emission and will immediately make requests.
  void adopt(Session session) {
    _session = session;
    _controller.add(session);
  }

  /// Sign out (C-7): drop the credentials, then tell the app.
  ///
  /// The order matters — emitting first would let a listener rebuild a screen that then
  /// makes a request with a token still in the store.
  Future<void> signOut() async {
    await _tokens.clear();
    _session = null;
    _controller.add(null);
  }

  void dispose() => unawaited(_controller.close());
}
