// `05` §5. The client branches on `code`; `title` and `detail` may be reworded freely.
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/data/api/problem.dart';
import 'package:flutter_test/flutter_test.dart';

Response<dynamic> _response(int status, Object? body) => Response<dynamic>(
      requestOptions: RequestOptions(path: '/x'),
      statusCode: status,
      data: body,
    );

void main() {
  test('maps a problem+json body to a typed failure carrying the code', () {
    final failure = failureFromResponse(_response(409, {
      'code': 'CREDIT_LIMIT_EXCEEDED',
      'detail': 'Order exceeds available credit',
      'request_id': 'req-1',
      'errors': <dynamic>[],
    }));
    expect(failure, isA<ProblemFailure>());
    final problem = failure as ProblemFailure;
    expect(problem.code, 'CREDIT_LIMIT_EXCEEDED');
    expect(problem.status, 409);
    expect(problem.requestId, 'req-1');
  });

  test('branches on code alone — a reworded detail changes nothing', () {
    Failure map(String detail) => failureFromResponse(
          _response(409, {'code': 'CUSTOMER_INACTIVE', 'detail': detail}),
        );
    expect((map('Customer deactivated') as ProblemFailure).code,
        (map('This shop is no longer active') as ProblemFailure).code);
  });

  test('flattens errors[] into fields (05 §5.4)', () {
    final problem = failureFromResponse(_response(422, {
      'code': 'VALIDATION_FAILED',
      'detail': 'Invalid',
      'errors': [
        {'field': 'lines.0.quantity', 'message': 'must be positive'},
      ],
    })) as ProblemFailure;
    expect(problem.errors.single.field, 'lines.0.quantity');
    expect(problem.errors.single.message, 'must be positive');
  });

  test('TOKEN_INVALID and REFRESH_EXPIRED end the session, not the request', () {
    for (final code in ['TOKEN_INVALID', 'REFRESH_EXPIRED']) {
      expect(failureFromResponse(_response(401, {'code': code})), isA<Unauthenticated>());
    }
  });

  test('DUPLICATE_CLIENT_UUID is flagged as a replay, not a failure to show (C-4)', () {
    final problem =
        failureFromResponse(_response(200, {'code': 'DUPLICATE_CLIENT_UUID'})) as ProblemFailure;
    expect(problem.isReplay, isTrue);
  });

  test('an HTML error page is MalformedResponse, not a null code', () {
    expect(failureFromResponse(_response(502, '<html>bad gateway</html>')),
        isA<MalformedResponse>());
    expect(failureFromResponse(_response(500, {'oops': true})), isA<MalformedResponse>());
  });

  test('a connection error is Offline — the normal state, not an exception', () {
    final failure = failureFromDioException(DioException(
      requestOptions: RequestOptions(path: '/x'),
      type: DioExceptionType.connectionError,
    ));
    expect(failure, isA<Offline>());
  });

  group('isAccessTokenExpired', () {
    test('only TOKEN_EXPIRED triggers a refresh', () {
      DioException err(int status, String code) => DioException(
            requestOptions: RequestOptions(path: '/x'),
            response: _response(status, {'code': code}),
          );
      expect(isAccessTokenExpired(err(401, 'TOKEN_EXPIRED')), isTrue);
      expect(isAccessTokenExpired(err(401, 'TOKEN_INVALID')), isFalse);
      expect(isAccessTokenExpired(err(401, 'INVALID_CREDENTIALS')), isFalse);
      expect(isAccessTokenExpired(err(403, 'TOKEN_EXPIRED')), isFalse);
    });
  });

  test('a rejected certificate is NOT reported as "no connection"', () {
    // **The defect: a working connection described as a missing one.**
    //
    // Dio raises `badCertificate` only when a `badCertificateCallback` returns false, and
    // this codebase deliberately has none — `test_no_certificate_verification_is_bypassed`
    // fails the build if one appears. A failed TLS handshake therefore arrives as `unknown`
    // wrapping a `HandshakeException`, with no response, and fell through to `Offline`.
    //
    // On the emulator the app said "No connection. Check your signal and try again." after
    // the TCP handshake had already succeeded, which points the developer at networking
    // when the fault is the trust anchor. In the field it tells a salesman standing in full
    // signal that they have none.
    final failure = failureFromDioException(
      DioException(
        requestOptions: RequestOptions(path: '/auth/otp/request'),
        type: DioExceptionType.unknown,
        error: const HandshakeException('CERTIFICATE_VERIFY_FAILED'),
      ),
    );
    expect(failure, isA<CertificateRejected>());
    expect(failure, isNot(isA<Offline>()));
  });

  // **The defect found 2026-09-14: a working connection described as an unreadable one.**
  //
  // The line above proved a rejected certificate is not `Offline`. It used to land on
  // `MalformedResponse` instead — a type shared with an HTML error page, a truncated body
  // and a slow decode, all four rendered by `login_messages.dart` as the identical "The
  // server sent something we could not read." A developer holding that screen cannot tell
  // "your dev CA is stale" from "the server sent junk" from it, and neither could the person
  // reading this repository trying to diagnose it — which is exactly what happened.
  test('a rejected certificate is its own type, not a MalformedResponse', () {
    final failure = failureFromDioException(
      DioException(
        requestOptions: RequestOptions(path: '/auth/login'),
        type: DioExceptionType.unknown,
        error: const HandshakeException('CERTIFICATE_VERIFY_FAILED'),
      ),
    );
    expect(failure, isA<CertificateRejected>());
    // `Failure` is sealed and the two are siblings, not a subtype relationship — a case
    // written as `MalformedResponse()` cannot silently reabsorb this one.
    expect(failure, isNot(isA<MalformedResponse>()));
  });

  test('the verdict matches badCertificate — the cause is the same', () {
    // Two routes to one fact: the chain did not verify. A client that called one of them
    // "no signal" and the other "certificate rejected" would be reporting the transport
    // rather than the problem.
    String messageOf(DioException error) =>
        (failureFromDioException(error) as CertificateRejected).message;

    expect(
      messageOf(DioException(
        requestOptions: RequestOptions(path: '/x'),
        type: DioExceptionType.unknown,
        error: const HandshakeException('CERTIFICATE_VERIFY_FAILED'),
      )),
      messageOf(DioException(
        requestOptions: RequestOptions(path: '/x'),
        type: DioExceptionType.badCertificate,
      )),
    );
  });

  test('a genuine transport failure is still Offline', () {
    // Anti-vacuity. The fix must not turn every errorless exception into a certificate
    // problem: no signal remains the normal state of a field device.
    final failure = failureFromDioException(
      DioException(
        requestOptions: RequestOptions(path: '/x'),
        type: DioExceptionType.unknown,
        error: const SocketException('Network is unreachable'),
      ),
    );
    expect(failure, isA<Offline>());
  });
}
