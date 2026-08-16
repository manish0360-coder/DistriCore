import 'dart:async';

import '../../core/result.dart';
import '../../domain/identity/session.dart';
import '../../domain/identity/session_repository.dart';
import '../api/tokens.dart';
import '../identity/session_restorer.dart';
import 'identity_cache.dart';

/// The real [SessionRepository]: session state owned here, restored from the keystore.
///
/// **Bound in M4.** `sessionRepositoryProvider` now delegates to this one instance, and
/// `bootstrap` holds the concrete type so it can call [restore] — which the read-only domain
/// interface deliberately does not expose.
final class TokenSessionRepository implements SessionRepository {
  TokenSessionRepository({
    required TokenStore tokens,
    required SessionRestorer restorer,
    required IdentityCache identity,
  })  : _tokens = tokens,
        _restorer = restorer,
        _identity = identity;

  final TokenStore _tokens;
  final SessionRestorer _restorer;
  final IdentityCache _identity;

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
  ///
  /// **Asynchronous since M6, and the order inside it is the point.** The identity is
  /// written to the encrypted database *before* the session is published, so the ordering
  /// `AuthService` already relied on — persist, then announce — now covers the cached
  /// identity too. Publishing first would leave a window in which the app is signed in and
  /// a cold start immediately afterwards would not be (§14.12 item 10).
  ///
  /// **No anchor is written here.** D-D1 makes the refresh token's `iat` the anchor, and
  /// `SecureTokenStore.save` has already stored the token this session came with.
  Future<void> adopt(Session session) async {
    await _identity.save(session);
    _session = session;
    _controller.add(session);
  }

  /// Sign out (C-7): drop the credentials, then tell the app.
  ///
  /// The order matters — emitting first would let a listener rebuild a screen that then
  /// makes a request with a token still in the store.
  ///
  /// **Three things deliberately survive**, and each for a reason that is not convenience:
  ///
  /// | Survives | Why |
  /// | --- | --- |
  /// | `device_id` | §8.4 / FR-IAM-009 — one physical device must present as one device |
  /// | The database key | It opens `outbox_operation`. Erasing it destroys unsent deliveries (§8.3) |
  /// | `outbox_operation` rows | §8.3 — a signed-out device still owes the business its work |
  ///
  /// The cached identity does **not** survive: it is the one thing here that names a person.
  Future<void> signOut() async {
    await _tokens.clear();
    await _identity.clear();
    _session = null;
    _controller.add(null);
  }

  void dispose() => unawaited(_controller.close());
}
