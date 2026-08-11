import 'package:dio/dio.dart';

import '../tokens.dart';

/// Attaches the access token. Nothing else.
///
/// Deliberately re-read from the [TokenStore] on **every** request rather than captured
/// once: after a refresh the token has changed, and a retry that replays a captured header
/// would present the token that just failed.
final class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._tokens);

  final TokenStore _tokens;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final token = _tokens.accessToken;
    if (token != null && token.isNotEmpty) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }
}
