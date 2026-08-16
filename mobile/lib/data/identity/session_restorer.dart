import '../../core/clock.dart';
import '../../core/failure.dart';
import '../../core/result.dart';
import '../../domain/identity/offline_window.dart';
import '../../domain/identity/session.dart';
import '../api/api_client.dart';
import '../api/tokens.dart';
import '../repositories/identity_cache.dart';
import 'refresh_claims.dart';
import 'user_dto.dart';

/// Cold-start session restoration (M8 §8.2, §8.3; offline window frozen at §14.12).
///
/// **`/auth/refresh` returns no user.** Verified against `RefreshView`: its response is
/// `access_token`, `refresh_token`, `expires_in` — and nothing else. A refresh token alone
/// therefore cannot rebuild a [Session]; the identity has to come from `GET /auth/me` or,
/// since M6, from the cached identity row.
///
/// **Which is why this never calls `/auth/refresh` itself.** The access token is memory-only
/// and gone after a restart, so the first `/auth/me` will meet `401 TOKEN_EXPIRED` — and
/// `RefreshInterceptor` already refreshes exactly once and replays the original request
/// (D-B1, D-B3). Refreshing here as well would be a second, unsynchronised refresh path
/// against a server that **rotates and blacklists** refresh tokens, which is the precise
/// failure D-B1 exists to prevent.
///
/// **M6 adds one branch in front of all of that**: if the window is open and an identity is
/// cached, restoration answers from disk and **makes no request at all**. That is
/// FR-IAM-016, and it is also the only way a van with no signal reaches a delivery list
/// before the 30-second receive timeout.
final class SessionRestorer {
  const SessionRestorer({
    required TokenStore tokens,
    required ApiClient api,
    required IdentityCache identity,
    required Clock clock,
    required Duration offlineWindow,
  })  : _tokens = tokens,
        _api = api,
        _identity = identity,
        _clock = clock,
        _offlineWindow = offlineWindow;

  static const path = '/auth/me';

  final TokenStore _tokens;
  final ApiClient _api;
  final IdentityCache _identity;
  final Clock _clock;
  final Duration _offlineWindow;

  /// `Ok(null)` — signed out. `Ok(session)` — restored. `Err` — see the mapping below.
  Future<Result<Session?>> restore() async {
    final refreshToken = _tokens.refreshToken;
    if (refreshToken == null || refreshToken.isEmpty) {
      // No credentials is not a failure; it is the state a fresh install is in. **No network
      // call is made** — an offline first launch must not wait on a timeout to show a login
      // screen.
      return const Ok(null);
    }

    // **D-D1: the anchor is the token the server issued, never anything this device wrote.**
    // `null` means "not a JWT we can read", which is not the same as "invalid" — the caller
    // falls through to the server and lets it decide.
    final claims = RefreshClaims.tryParse(refreshToken);
    final window = claims == null
        ? null
        : OfflineWindow(
            issuedAt: claims.issuedAt,
            expiresAt: claims.expiresAt,
            maxOffline: _offlineWindow,
          );
    final windowOpen = window != null && window.permits(_clock.nowUtc());

    if (windowOpen) {
      final cached = await _identity.read();
      // **All three of D-D6's conditions, and no fourth.** Refresh token present (checked
      // above), identity cached and readable, window unexpired. A missing or unreadable row
      // falls through to the server rather than unlocking — fail closed.
      if (cached != null) return Ok(cached);
    }

    final Result<UserDto> result;
    try {
      result = await _api.get<UserDto>(path, decode: UserDto.fromJson);
    } on UserPayloadException catch (error) {
      // `ApiClient` converts transport failures; a body that parses to nothing sensible is
      // not a transport failure, so it surfaces here.
      return Err(MalformedResponse(error.reason));
    }

    if (result is Ok<UserDto>) {
      final session = result.value.toSession();
      // **The round trip that D-D4/D-D5 require, and its consequence.** Reaching here means
      // `RefreshInterceptor` rotated the token, so `_tokens.refreshToken` now carries a
      // fresh `iat` — the window is re-anchored with nothing written to record it. Caching
      // the identity is what makes the *next* cold start work offline.
      await _identity.save(session);
      return Ok(session);
    }

    final failure = (result as Err<UserDto>).failure;

    if (failure is Unauthenticated) {
      // The request itself was refused as unauthenticated — `TOKEN_INVALID` or
      // `REFRESH_EXPIRED` on `/auth/me`. Keeping a credential the server has already
      // rejected only produces the same 401 next launch. `clear()` leaves `device_id` in
      // place (§8.4), and the database key is untouched (`PlatformDatabaseKey`).
      await _tokens.clear();
      await _identity.clear();
      return Err(failure);
    }

    // **The refresh chain ended the session, and the surfaced code does not say so.**
    //
    // `RefreshInterceptor` propagates the *original* error when a refresh fails, so a
    // `/auth/me` that met `401 TOKEN_EXPIRED` still reports `TOKEN_EXPIRED` even after
    // `/auth/refresh` came back `REFRESH_EXPIRED`. Taken at face value that tells the
    // caller to *"refresh, retry once"* (`05` §5.1) — which is precisely what has just
    // failed, and would loop.
    //
    // The interceptor clears the store **only** when `/auth/refresh` itself returns 401,
    // never on `Offline`. So a refresh token that was present on entry and is gone now is
    // an unambiguous signal that the credential is finished: `05` §5.1's *"full re-login"*,
    // which is [Unauthenticated].
    if (_tokens.refreshToken == null) {
      await _identity.clear();
      return const Err<Session?>(Unauthenticated());
    }

    // **The window is over and the server could not be reached.** `Offline` would tell the
    // user to wait for signal, which is true but incomplete: the local unlock has ended and
    // signing in is the remedy that works either way. §14.12 D-D4/D-D5 puts this at
    // `Unauthenticated`.
    //
    // **The credentials are kept.** The window expiring is not the server revoking anything
    // — §17: clearing here *"would end FR-IAM-016's offline window at the first tunnel"* —
    // so a refresh that succeeds later still re-anchors and signs the user straight back in.
    if (window != null && !windowOpen) return const Err<Session?>(Unauthenticated());

    // **`Offline` inside the window falls through with the tokens intact.** No signal is not
    // a revoked session, and wiping the keystore because a tunnel was in the way would force
    // a re-login on a device that was never actually signed out.
    return Err(failure);
  }
}
