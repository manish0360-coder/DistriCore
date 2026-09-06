import 'dart:async';

import 'package:dio/dio.dart';

import '../problem.dart';
import '../tokens.dart';

/// **D-B1, D-B2, D-B3 — refresh once, exactly once, without losing operation identity.**
///
/// `05` C-7 says *"refresh once on `401 TOKEN_EXPIRED`, then re-authenticate. Never loop."*
/// Under concurrency that sentence is not enough, and the gap is not theoretical: the server
/// sets `ROTATE_REFRESH_TOKENS: True` **and** `BLACKLIST_AFTER_ROTATION: True`. Three
/// requests failing together would fire three refreshes; the first rotates and blacklists
/// the token, and the other two present a blacklisted one — which reuse detection treats as
/// an attack. A working session is signed out by nothing but its own concurrency.
///
/// So: **concurrent 401s share one refresh operation, waiters share its result, and each
/// original request retries exactly once.** A second 401 after that retry is terminal.
final class RefreshInterceptor extends Interceptor {
  RefreshInterceptor({
    required TokenStore tokens,
    required Dio refreshClient,
    required Dio Function() retryClient,
    this.refreshPath = '/auth/refresh',
  })  : _tokens = tokens,
        _refreshClient = refreshClient,
        _retryClient = retryClient;

  /// Marks a request that has already been retried once. Lives in `extra`, which Dio
  /// carries on the `RequestOptions` — so it survives the replay and makes the second 401
  /// terminal by construction rather than by counting attempts somewhere else.
  static const retriedKey = 'districore.refresh.retried';

  final TokenStore _tokens;

  /// **D-B2.** A separate `Dio` that carries neither `AuthInterceptor` nor this
  /// interceptor. Isolation is structural: an absent interceptor cannot be re-entered, and
  /// there is no flag for a later edit to get wrong.
  final Dio _refreshClient;

  /// The main client, resolved lazily because it owns *this* interceptor — a constructor
  /// argument would be a cycle.
  final Dio Function() _retryClient;

  final String refreshPath;

  Future<bool>? _inFlight;

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    if (!_isRecoverable(err)) return handler.next(err);

    if (err.requestOptions.extra[retriedKey] == true) {
      // Refreshed, retried, still expired. C-7: stop. Looping here is how a flat battery
      // and a lockout are produced from one stale token.
      await _tokens.clear();
      return handler.next(err);
    }

    final refreshed = await _sharedRefresh();
    if (!refreshed) return handler.next(err);

    // **D-B3.** Replay the ORIGINAL RequestOptions — method, path, query, headers and body,
    // including any `client_uuid`. Rebuilding the request here is the most plausible place
    // in the whole client for a second operation identity to appear, because the code that
    // retries is not the code that created the operation (P-6, C-2).
    final options = err.requestOptions..extra[retriedKey] = true;
    try {
      handler.resolve(await _retryClient().fetch<dynamic>(options));
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }

  /// **Which 401s a refresh can repair.** `TOKEN_EXPIRED` always — that is C-7. And one more:
  /// a `TOKEN_INVALID` on a request that carried **no `Authorization` header at all**.
  ///
  /// **Those two codes mean different things, and the header is what tells them apart.** The
  /// server raises `NotAuthenticated` when no credential was supplied and `AuthenticationFailed`
  /// when one was supplied and rejected, and `api/v1/exception_handler.py` maps the first to
  /// `TOKEN_INVALID` — the same code it uses for a genuinely dead credential. So `TOKEN_INVALID`
  /// on a request that *did* present a token still means *"this credential is finished"* and
  /// stays terminal, exactly as before. On a request that presented nothing it means *"you sent
  /// nothing"*, which a refresh fixes.
  ///
  /// **Why this case exists at all.** The access token is memory-only (§8.2), so a restart
  /// loses it. Restoration normally recovers one because `/auth/me` presents the *expired*
  /// token and meets `TOKEN_EXPIRED` — but inside the offline window with a cached identity,
  /// `SessionRestorer` answers from disk and *"makes no request at all"* (FR-IAM-016). The
  /// process is then left holding a live refresh token and no access token, and every request
  /// it sends goes out bare.
  ///
  /// Before this, such a request was refused `TOKEN_INVALID`, no refresh was attempted, and
  /// `problem.dart` mapped it to `Unauthenticated` — terminal for `SyncRound`, and terminal for
  /// `SyncScheduler`, which stops for good. **B1 measured exactly that**: a device that
  /// cold-started offline and then reconnected never synced again until it was relaunched,
  /// which is the launch-only behaviour TD-41 exists to remove.
  ///
  /// **Deliberately here and not in `AuthInterceptor`.** Refreshing *before* the request looks
  /// tidier and was tried first; it breaks D-B1's contract, because
  /// `startup_refresh_race_test.dart` requires both concurrent callers to be refused a 401 and
  /// to share **one** refresh. A pre-emptive refresh removes the push's 401 entirely, so the
  /// two callers refresh in sequence rather than together — two flights against a server that
  /// blacklists on rotation. Reacting to the 401 keeps every caller on the one shared flight.
  bool _isRecoverable(DioException err) {
    if (isAccessTokenExpired(err)) return true;

    // A header present means a credential was offered and refused: not this case.
    if (err.requestOptions.headers.containsKey('Authorization')) return false;

    final response = err.response;
    if (response?.statusCode != 401) return false;
    final body = response?.data;
    return body is Map && body['code'] == 'TOKEN_INVALID';
  }

  /// One flight, shared. Assigned before the first `await` inside [_performRefresh], so a
  /// concurrent caller arriving mid-flight sees the same `Future` and never starts a second.
  Future<bool> _sharedRefresh() {
    final existing = _inFlight;
    if (existing != null) return existing;

    final flight = _performRefresh();
    _inFlight = flight;
    // `identical` so a flight that finishes after a newer one began cannot clear it.
    unawaited(flight.whenComplete(() {
      if (identical(_inFlight, flight)) _inFlight = null;
    }));
    return flight;
  }

  Future<bool> _performRefresh() async {
    final refreshToken = _tokens.refreshToken;
    if (refreshToken == null || refreshToken.isEmpty) {
      await _tokens.clear();
      return false;
    }

    try {
      final response = await _refreshClient.post<dynamic>(
        refreshPath,
        data: <String, dynamic>{'refresh_token': refreshToken},
      );
      final body = response.data;
      final access = body is Map ? body['access_token'] : null;
      final rotated = body is Map ? body['refresh_token'] : null;
      if (access is! String || rotated is! String) {
        // A 200 that is not the documented shape is a contract break, not a credential
        // problem. Do not destroy a session over it.
        return false;
      }
      // The server rotates: keeping the old token guarantees a lockout on next use.
      await _tokens.save(accessToken: access, refreshToken: rotated);
      return true;
    } on DioException catch (error) {
      // **Offline must not sign anyone out.** FR-IAM-016 gives the app a configured window
      // of local use; wiping the keystore because the refresh could not reach the server
      // would end that window at the first tunnel. Only the server saying "this credential
      // is finished" ends a session.
      if (error.response?.statusCode == 401) await _tokens.clear();
      return false;
    }
  }
}
