import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:districore/data/api/tokens.dart';

/// An immutable snapshot of one request as it reached the wire.
///
/// **Storing the live `RequestOptions` is a trap.** D-B3 replays the *same* object on
/// retry, and `AuthInterceptor` rewrites its `Authorization` header in place — so a list of
/// references shows every attempt carrying the *last* token, and an assertion comparing the
/// first attempt's body with the last one is comparing an object with itself. That is a
/// test that cannot fail, which is worse than one that does.
final class RecordedRequest {
  RecordedRequest(RequestOptions options)
      : method = options.method,
        path = options.path,
        headers = Map<String, dynamic>.of(options.headers),
        data = options.data is Map<String, dynamic>
            ? Map<String, dynamic>.of(options.data as Map<String, dynamic>)
            : options.data;

  final String method;
  final String path;
  final Map<String, dynamic> headers;
  final Object? data;

  Map<String, dynamic> get body => data! as Map<String, dynamic>;
}

/// A scriptable `HttpClientAdapter`. Hand-written rather than a mock package: it is ~30
/// lines, and it keeps the dependency list to what ships in the binary.
final class FakeAdapter implements HttpClientAdapter {
  FakeAdapter(this.handler);

  /// Every request that reached the wire, in order, **snapshotted**.
  final List<RecordedRequest> requests = [];
  final FutureOr<ResponseBody> Function(RequestOptions options, int callIndex) handler;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final index = requests.length;
    requests.add(RecordedRequest(options));
    return handler(options, index);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody jsonBody(int status, Map<String, dynamic> body) => ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );

ResponseBody tokenExpired() => jsonBody(401, {
      'code': 'TOKEN_EXPIRED',
      'status': 401,
      'title': 'Token expired',
      'detail': 'Access token expired',
      'errors': <dynamic>[],
    });

/// An in-memory [TokenStore]. Records every save so a test can prove the rotated refresh
/// token replaced the old one.
final class FakeTokens implements TokenStore {
  FakeTokens({this.accessToken = 'access-1', this.refreshToken = 'refresh-1'});

  @override
  String? accessToken;
  @override
  String? refreshToken;
  @override
  String? deviceId = 'device-abc';

  int saves = 0;
  int clears = 0;

  @override
  Future<void> save({required String accessToken, required String refreshToken}) async {
    saves += 1;
    this.accessToken = accessToken;
    this.refreshToken = refreshToken;
  }

  @override
  Future<void> clear() async {
    clears += 1;
    accessToken = null;
    refreshToken = null;
  }
}
