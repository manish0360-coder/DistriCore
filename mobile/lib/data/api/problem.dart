import 'package:dio/dio.dart';

import '../../core/failure.dart';

/// RFC 9457 problem+json → a typed [Failure] (`05` §5, M8 §7.3).
///
/// **Failures are values here, not exceptions.** A field app has no "unexpected" network
/// error: no signal is the normal state, and an app that throws on it throws all day.
///
/// The envelope is fixed by `api/v1/exception_handler.py`:
/// `{type, title, status, detail, instance, code, request_id, errors[]}`.
Failure failureFromDioException(DioException error) {
  switch (error.type) {
    case DioExceptionType.connectionError:
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
      return const Offline();
    case DioExceptionType.cancel:
      return const Offline();
    case DioExceptionType.transformTimeout:
      // **Not `Offline`.** The request reached the server and the server answered; what
      // timed out is Dio's own transformer converting the payload — a slow device or an
      // oversized body, on a working connection.
      //
      // Calling it `Offline` would tell a salesman standing in signal that they have none,
      // and would put the operation back on a queue whose next attempt fails identically.
      // `MalformedResponse` carries the honest meaning: the server replied, we could not
      // make sense of it, retrying later is the only safe move.
      return const MalformedResponse('The response could not be decoded in time.');
    case DioExceptionType.badCertificate:
      return const MalformedResponse('The server certificate was rejected.');
    case DioExceptionType.badResponse:
    case DioExceptionType.unknown:
      break;
  }

  final response = error.response;
  if (response == null) return const Offline();
  return failureFromResponse(response);
}

Failure failureFromResponse(Response<dynamic> response) {
  final body = response.data;
  final status = response.statusCode ?? 0;

  // A proxy 502 or an HTML error page has no `code` to branch on. Naming that case is the
  // difference between "retry later" and a client that reports `null` to the user.
  if (body is! Map) {
    return MalformedResponse(
      'The server did not return problem+json (status $status).',
      status: status,
    );
  }
  final code = body['code'];
  if (code is! String || code.isEmpty) {
    return MalformedResponse('Response carried no error code.', status: status);
  }

  if (code == 'TOKEN_INVALID' || code == 'REFRESH_EXPIRED') return const Unauthenticated();

  return ProblemFailure(
    code: code,
    status: status,
    detail: body['detail'] is String ? body['detail'] as String : '',
    errors: _fieldErrors(body['errors']),
    requestId: body['request_id'] is String ? body['request_id'] as String : null,
  );
}

List<FieldError> _fieldErrors(Object? raw) {
  if (raw is! List) return const [];
  return [
    for (final entry in raw)
      if (entry is Map)
        FieldError(
          field: entry['field']?.toString() ?? '',
          message: entry['message']?.toString() ?? '',
        ),
  ];
}

/// `05` §5.1: the one code that means "refresh, retry once". Every other 401 is terminal.
bool isAccessTokenExpired(DioException error) {
  final response = error.response;
  if (response?.statusCode != 401) return false;
  final body = response?.data;
  return body is Map && body['code'] == 'TOKEN_EXPIRED';
}
