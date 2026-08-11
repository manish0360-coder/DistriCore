import 'package:dio/dio.dart';

import '../../core/failure.dart';
import '../../core/money.dart';
import '../../core/result.dart';
import 'interceptors/auth_interceptor.dart';
import 'interceptors/device_interceptor.dart';
import 'interceptors/refresh_interceptor.dart';
import 'problem.dart';
import 'tokens.dart';

/// The one way this app speaks HTTP (M8 §7.2).
///
/// Two `Dio` instances, and the second one is the point:
///
/// * [_dio] carries auth, refresh and device-id.
/// * [_refreshDio] carries **none of them** — **D-B2**. A refresh call that could itself
///   trigger the refresh interceptor is an infinite loop reachable from one expired token,
///   and structural isolation cannot be undone by a later edit the way a re-entrancy flag
///   can. The same reasoning as `DashboardView` declaring only `JSONRenderer`.
final class ApiClient {
  ApiClient({
    required String baseUrl,
    required TokenStore tokens,
    Dio? dio,
    Dio? refreshDio,
    Duration connectTimeout = const Duration(seconds: 15),
    Duration receiveTimeout = const Duration(seconds: 30),
  })  : _dio = dio ?? Dio(),
        _refreshDio = refreshDio ?? Dio() {
    final options = BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: connectTimeout,
      receiveTimeout: receiveTimeout,
      contentType: Headers.jsonContentType,
      // **Dio's default `validateStatus` is deliberately kept.** A permissive one looks
      // tidier — every response becomes a value, nothing throws — but it also means Dio
      // never enters its error path, and `RefreshInterceptor.onError` becomes dead code
      // that no 401 can reach. The failures-as-values conversion happens in [_send]
      // instead, one layer up, where it costs nothing.
    );
    _dio.options = options;
    _refreshDio.options = options;

    _dio.interceptors.addAll([
      AuthInterceptor(tokens),
      DeviceInterceptor(tokens),
      RefreshInterceptor(
        tokens: tokens,
        refreshClient: _refreshDio,
        retryClient: () => _dio,
      ),
    ]);
  }

  final Dio _dio;
  final Dio _refreshDio;

  /// Exposed for the repositories that task 5 onwards will add, and for tests to install a
  /// fake adapter. Not for screens: §2.2 says a screen sees a repository, never transport.
  Dio get raw => _dio;

  Future<Result<T>> get<T>(
    String path, {
    Map<String, dynamic>? query,
    required T Function(Object? body) decode,
  }) =>
      _send(() => _dio.get<dynamic>(path, queryParameters: query), decode);

  Future<Result<T>> post<T>(
    String path, {
    Object? body,
    required T Function(Object? body) decode,
  }) =>
      _send(() => _dio.post<dynamic>(path, data: body), decode);

  /// One place where a response becomes a [Result].
  ///
  /// Non-2xx arrives as a `DioException` carrying the response, so the problem+json body is
  /// still intact when [failureFromDioException] reads it — and the interceptor chain has
  /// already had its chance to refresh and retry before we get here.
  Future<Result<T>> _send<T>(
    Future<Response<dynamic>> Function() call,
    T Function(Object? body) decode,
  ) async {
    try {
      final response = await call();
      return Ok(decode(response.data));
    } on DioException catch (error) {
      return Err(failureFromDioException(error));
    } on MoneyFormatException catch (error) {
      // P-3: a money field arrived as a JSON number. Surfaced as a failure rather than an
      // unhandled throw, because TD-36 means this is currently reachable on the report
      // endpoints and a crash is a worse answer than a refusal.
      return Err(MalformedResponse(error.message));
    }
  }
}
