import '../../core/failure.dart';
import '../../core/result.dart';
import '../../domain/identity/session.dart';
import '../api/api_client.dart';
import '../api/tokens.dart';
import 'user_dto.dart';

/// Cold-start session restoration (M8 §8.2).
///
/// **`/auth/refresh` returns no user.** Verified against `RefreshView`: its response is
/// `access_token`, `refresh_token`, `expires_in` — and nothing else. A refresh token alone
/// therefore cannot rebuild a [Session]; the identity has to come from `GET /auth/me`.
///
/// **Which is why this never calls `/auth/refresh` itself.** The access token is memory-only
/// and gone after a restart, so the first `/auth/me` will meet `401 TOKEN_EXPIRED` — and
/// `RefreshInterceptor` already refreshes exactly once and replays the original request
/// (D-B1, D-B3). Refreshing here as well would be a second, unsynchronised refresh path
/// against a server that **rotates and blacklists** refresh tokens, which is the precise
/// failure D-B1 exists to prevent.
final class SessionRestorer {
  const SessionRestorer({required TokenStore tokens, required ApiClient api})
      : _tokens = tokens,
        _api = api;

  static const path = '/auth/me';

  final TokenStore _tokens;
  final ApiClient _api;

  /// `Ok(null)` — signed out. `Ok(session)` — restored. `Err` — see the mapping below.
  Future<Result<Session?>> restore() async {
    final refreshToken = _tokens.refreshToken;
    if (refreshToken == null || refreshToken.isEmpty) {
      // No credentials is not a failure; it is the state a fresh install is in. **No network
      // call is made** — an offline first launch must not wait on a timeout to show a login
      // screen.
      return const Ok(null);
    }

    final Result<UserDto> result;
    try {
      result = await _api.get<UserDto>(path, decode: UserDto.fromJson);
    } on UserPayloadException catch (error) {
      // `ApiClient` converts transport failures; a body that parses to nothing sensible is
      // not a transport failure, so it surfaces here.
      return Err(MalformedResponse(error.reason));
    }

    if (result is Ok<UserDto>) return Ok(result.value.toSession());

    final failure = (result as Err<UserDto>).failure;

    if (failure is Unauthenticated) {
      // The request itself was refused as unauthenticated — `TOKEN_INVALID` or
      // `REFRESH_EXPIRED` on `/auth/me`. Keeping a credential the server has already
      // rejected only produces the same 401 next launch. `clear()` leaves `device_id` in
      // place (§8.4).
      await _tokens.clear();
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
    if (_tokens.refreshToken == null) return const Err<Session?>(Unauthenticated());

    // **`Offline` falls through with the tokens intact.** No signal is not a revoked
    // session, and wiping the keystore because a tunnel was in the way would force a
    // re-login on a device that was never actually signed out.
    return Err(failure);
  }
}
