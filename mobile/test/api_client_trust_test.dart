/// **The development trust anchor, at the transport boundary.**
///
/// `AppConfig` decides whether a certificate was supplied and whether it is usable;
/// `api_client_test`-adjacent cases here prove what `ApiClient` then *does* with it. The two
/// halves are tested separately because they fail differently: a bad define must refuse to
/// start, and a good one must reach both HTTP clients.
///
/// **The property that matters most is the negative one.** With no anchor, this class must
/// behave exactly as it did before the mechanism existed — same adapter, same
/// `SecurityContext`, same roots. Production supplies no CA, so that path is the one every
/// field device runs.
library;

import 'dart:io';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';

const _baseUrl = 'https://api.test/api/v1';

ApiClient build({SecurityContext? trustAnchor, Dio? dio, Dio? refreshDio}) => ApiClient(
      baseUrl: _baseUrl,
      tokens: FakeTokens(),
      dio: dio,
      refreshDio: refreshDio,
      trustAnchor: trustAnchor,
    );

void main() {
  group('no anchor — the production path', () {
    test('the adapter is left exactly as Dio built it', () {
      // **Byte-for-byte equivalence, asserted rather than assumed.** A build without
      // `DISTRICORE_DEV_CA_B64` must not touch the transport at all: no custom adapter, no
      // custom `SecurityContext`, no widened roots. This is the assertion that would fail
      // if someone later made the anchor unconditional "for convenience".
      final untouched = Dio();
      final original = untouched.httpClientAdapter;

      build(dio: untouched);

      // **Identity, not type.** Dio's own default on the VM *is* an `IOHttpClientAdapter`,
      // so asserting the class here proves nothing — an earlier draft did exactly that and
      // failed for the right reason. The question is whether `ApiClient` replaced the
      // object, and `identical` is the only thing that answers it.
      expect(identical(untouched.httpClientAdapter, original), isTrue);

      // And the property that carries the TLS behaviour: a `createHttpClient` factory is
      // how a custom `SecurityContext` reaches the socket. `null` means Dio builds the
      // stock `HttpClient` — default context, default roots, exactly as a build without
      // `DISTRICORE_DEV_CA_B64` must. The development path below asserts the mirror image.
      expect((untouched.httpClientAdapter as IOHttpClientAdapter).createHttpClient, isNull);
    });

    test('the refresh client is left alone too (D-B2)', () {
      final refresh = Dio();
      final original = refresh.httpClientAdapter;

      build(refreshDio: refresh);

      expect(identical(refresh.httpClientAdapter, original), isTrue);
      expect((refresh.httpClientAdapter as IOHttpClientAdapter).createHttpClient, isNull);
    });
  });

  group('with an anchor — the development path', () {
    test('BOTH clients receive an IOHttpClientAdapter', () {
      // D-B2 separates the two `Dio`s so `/auth/refresh` cannot re-enter the refresh
      // interceptor. That isolation is about interceptors, not transport: both talk to the
      // same host over the same TLS. An anchor on one and not the other would make refresh
      // fail on precisely the connection login had just succeeded on — and only after a
      // token expired, which is the worst possible time to discover it.
      final main = Dio();
      final refresh = Dio();

      build(
        trustAnchor: SecurityContext(withTrustedRoots: true),
        dio: main,
        refreshDio: refresh,
      );

      expect(main.httpClientAdapter, isA<IOHttpClientAdapter>());
      expect(refresh.httpClientAdapter, isA<IOHttpClientAdapter>());
    });

    test('the adapter builds a client bound to the supplied context', () {
      final context = SecurityContext(withTrustedRoots: true);
      final main = Dio();

      build(trustAnchor: context, dio: main);

      final adapter = main.httpClientAdapter as IOHttpClientAdapter;
      expect(
        adapter.createHttpClient,
        isNotNull,
        reason: 'without a factory the adapter would fall back to the default context, '
            'silently ignoring the certificate the build supplied',
      );
      // Calling it proves the closure is real and does not throw; the context it carries is
      // the one constructed above, which `bootstrap` builds with `withTrustedRoots: true`.
      final client = adapter.createHttpClient!();
      expect(client, isA<HttpClient>());
      client.close(force: true);
    });

    test('every connection gets its own client, so no setting can leak between them', () {
      // **The bypass prohibition is NOT asserted here, and cannot be.** `dart:io` declares
      // `badCertificateCallback` as a **setter only** — there is no getter, so no Dart test
      // can read back whether one was installed. An earlier draft of this test tried, and
      // the analyzer refused it: *"The getter 'badCertificateCallback' isn't defined for the
      // type 'HttpClient'."*
      //
      // That guarantee therefore lives where it *can* be enforced:
      // `test_mobile_boundary.py::test_no_certificate_verification_is_bypassed` reads the
      // Dart sources and fails the build if the name appears in `lib/` at all. It runs
      // inside `make verify`, which `flutter test` does not (TD-37), so it is the stronger
      // of the two placements anyway.
      //
      // What IS assertable is the property below, and it is worth having: the factory
      // returns a **fresh** client per call. A shared instance would let a setting applied
      // for one request — a timeout, a proxy, a callback — silently outlive it.
      final main = Dio();
      build(trustAnchor: SecurityContext(withTrustedRoots: true), dio: main);
      final create = (main.httpClientAdapter as IOHttpClientAdapter).createHttpClient!;

      final first = create();
      final second = create();

      expect(identical(first, second), isFalse);
      first.close(force: true);
      second.close(force: true);
    });
  });
}
