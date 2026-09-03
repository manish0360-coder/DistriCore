// M8 task 4 M4 — start-up configuration (`00` §9, `02A` §9.3, P-9).
//
// Every rule is exercised through `AppConfig.parse`, which is why the environment read was
// separated from the validation: `String.fromEnvironment` is fixed at compile time, so a
// suite that tested it directly could assert exactly one case per `flutter test` run.
//
// The last group is the exception, and it is deliberate — it is the only thing that can
// prove `make mobile-verify` actually supplies the define.
import 'dart:convert';

import 'package:districore/app/config.dart';
import 'package:flutter_test/flutter_test.dart';

/// Asserts the *specific* rule fired, not merely that something was refused.
///
/// A matcher that only checked the type would pass if every value were rejected for the
/// same wrong reason — and would still be green if `parse` threw on its first line.
Matcher _rejects(String reasonContains) => throwsA(
      isA<ConfigurationException>()
          .having((e) => e.variable, 'variable', AppConfig.baseUrlVariable)
          .having((e) => e.reason, 'reason', contains(reasonContains))
          .having((e) => e.toString(), 'message', contains('--dart-define')),
    );

void main() {
  group('the build supplied nothing', () {
    test('an absent define arrives as the empty string and is refused', () {
      // This is the real "missing" case: `String.fromEnvironment` has no null. If this ever
      // passed, an unconfigured release build would boot.
      expect(() => AppConfig.parse(''), _rejects('missing or blank'));
    });

    test('whitespace only is refused', () {
      expect(() => AppConfig.parse('   '), _rejects('missing or blank'));
      expect(() => AppConfig.parse('\n\t '), _rejects('missing or blank'));
    });
  });

  group('the build supplied something unusable', () {
    test('a bare hostname is refused — a base URL must be absolute', () {
      expect(() => AppConfig.parse('api.example.com'), _rejects('not absolute'));
      expect(() => AppConfig.parse('api.example.com/api/v1'), _rejects('not absolute'));
    });

    test('a scheme-relative URL is refused', () {
      expect(() => AppConfig.parse('//api.example.com'), _rejects('not absolute'));
    });

    test('http:// is refused', () {
      // The single most damaging value that would otherwise "work": every request succeeds,
      // in clear text, carrying a bearer token.
      expect(() => AppConfig.parse('http://api.example.com'), _rejects('only https://'));
    });

    test('a non-HTTP scheme is refused', () {
      expect(() => AppConfig.parse('ftp://api.example.com'), _rejects('only https://'));
      expect(() => AppConfig.parse('districore://api'), _rejects('only https://'));
    });

    test('a scheme with no host is refused', () {
      expect(() => AppConfig.parse('https://'), _rejects('no host'));
      expect(() => AppConfig.parse('https:///api/v1'), _rejects('no host'));
    });

    test('credentials in the URL are refused', () {
      // A secret in configuration. It would also be printed by any client that logs a
      // request line, which FR-IAM-015 forbids.
      expect(
        () => AppConfig.parse('https://user:pass@api.example.com'),
        _rejects('must not carry credentials'),
      );
    });

    test('a query string or fragment is refused', () {
      // Concatenating `/auth/login` onto these produces a URL with the query in the middle.
      expect(
        () => AppConfig.parse('https://api.example.com?v=1'),
        _rejects('query string or fragment'),
      );
      expect(
        () => AppConfig.parse('https://api.example.com#x'),
        _rejects('query string or fragment'),
      );
    });

    test('a string that is not a URL at all is refused', () {
      // Which rule catches it is not asserted — `Uri.parse` is lenient and the exact branch
      // is an implementation detail. That it never reaches `ApiClient` is the contract.
      expect(() => AppConfig.parse('not a url'), throwsA(isA<ConfigurationException>()));
      expect(() => AppConfig.parse('12345'), throwsA(isA<ConfigurationException>()));
    });

    test('the exception names the define, not the symptom', () {
      // The person reading this is holding a build that will not start. The message has to
      // tell them which flag to add, and that adding one is mandatory.
      expect(
        () => AppConfig.parse(''),
        throwsA(
          isA<ConfigurationException>().having(
            (e) => e.toString(),
            'message',
            allOf(contains('DISTRICORE_API_BASE_URL'), contains('no default')),
          ),
        ),
      );
    });
  });

  group('the build supplied a usable value', () {
    test('a plain https origin is accepted unchanged', () {
      expect(AppConfig.parse('https://api.example.com').baseUrl, 'https://api.example.com');
    });

    test('a path prefix is preserved — the API is mounted at /api/v1', () {
      // Not a nicety. `config/urls.py` mounts the API under `api/v1/` while the client
      // declares `/auth/login`, so a base URL that could not carry a path prefix could not
      // reach a single endpoint.
      expect(
        AppConfig.parse('https://api.example.com/api/v1').baseUrl,
        'https://api.example.com/api/v1',
      );
    });

    test('a trailing slash is trimmed so concatenation cannot double it', () {
      expect(AppConfig.parse('https://api.example.com/').baseUrl, 'https://api.example.com');
      expect(
        AppConfig.parse('https://api.example.com/api/v1/').baseUrl,
        'https://api.example.com/api/v1',
      );
      expect(
        AppConfig.parse('https://api.example.com/api/v1///').baseUrl,
        'https://api.example.com/api/v1',
      );
    });

    test('an explicit port survives normalisation', () {
      expect(
        AppConfig.parse('https://api.example.com:8443/api/v1/').baseUrl,
        'https://api.example.com:8443/api/v1',
      );
    });

    test('surrounding whitespace is tolerated', () {
      // A shell variable or CI value that picked up a newline is a build-system accident,
      // not an intent to point at a different host.
      expect(AppConfig.parse('  https://api.example.com \n').baseUrl,
          'https://api.example.com');
    });

    test('the result concatenates cleanly with the paths the API layer declares', () {
      final config = AppConfig.parse('https://api.example.com/api/v1/');
      expect('${config.baseUrl}/auth/login', 'https://api.example.com/api/v1/auth/login');
    });
  });

  group('the compile-time environment', () {
    // **This is the only test that can fail if the Makefile stops passing the define.**
    // It couples the suite to `make mobile-verify` on purpose: without it, item 12 of the
    // milestone would be unverifiable, and a bare `flutter test` would silently pass while
    // the gate's own wiring was broken.
    test('make mobile-verify supplies DISTRICORE_API_BASE_URL', () {
      expect(
        AppConfig.fromEnvironment().baseUrl,
        'https://api.test',
        reason: 'run this through `make mobile-verify`, which passes '
            '--dart-define=DISTRICORE_API_BASE_URL=https://api.test. That value is '
            'verification-only and is deliberately not a default in the application.',
      );
    });
  });

  // ---------------------------------------------------------------- the dev trust anchor
  group('the development trust anchor', () {
    /// A real, self-signed CA in PEM form. Bytes, not a URL: `_parseDevTrustAnchor` looks
    /// for the certificate header, so a fixture that only *looks* like one would pass for
    /// the wrong reason.
    const pem = '-----BEGIN CERTIFICATE-----\n'
        'MIIBkTCB+wIJAKHq0mzQ0aTPMA0GCSqGSIb3DQEBCwUAMBExDzANBgNVBAMMBnRl\n'
        'c3RjYTAeFw0yNjA4MjQwMDAwMDBaFw0zNjA4MjIwMDAwMDBaMBExDzANBgNVBAMM\n'
        'BnRlc3RjYTCBnzANBgkqhkiG9w0BAQEFAAOBjQAwgYkCgYEAx3Qm0Q0aTPtestca\n'
        '-----END CERTIFICATE-----\n';
    final encoded = base64.encode(ascii.encode(pem));

    Matcher rejectsAnchor(String reasonContains) => throwsA(
          isA<ConfigurationException>()
              .having((e) => e.variable, 'variable', AppConfig.devTrustAnchorVariable)
              .having((e) => e.reason, 'reason', contains(reasonContains)),
        );

    test('absent means null — the production path, and not an error', () {
      // The overwhelmingly common case. A release build supplies no CA and must behave
      // exactly as it did before this mechanism existed.
      expect(AppConfig.parse('https://api.example.com').devTrustAnchor, isNull);
      expect(
        AppConfig.parse('https://api.example.com', rawDevTrustAnchor: '   ').devTrustAnchor,
        isNull,
        reason: 'blank and unset must fail through one path, as they do for the base URL',
      );
    });

    test('a valid CA is decoded to its bytes', () {
      final config =
          AppConfig.parse('https://api.example.com', rawDevTrustAnchor: encoded);
      expect(config.devTrustAnchor, isNotNull);
      expect(ascii.decode(config.devTrustAnchor!), pem);
    });

    test('malformed base64 is refused before runApp', () {
      // Fails closed. Falling back to the default roots would present as the same generic
      // "no connection" the developer was already trying to diagnose.
      expect(
        () => AppConfig.parse('https://api.example.com', rawDevTrustAnchor: 'not base64!!'),
        rejectsAnchor('not valid base64'),
      );
    });

    test('base64 of something that is not a certificate is refused', () {
      // The two mistakes worth catching by name: handing over the private key, or handing
      // over the leaf instead of the CA. Both decode cleanly and neither is a trust anchor.
      expect(
        () => AppConfig.parse(
          'https://api.example.com',
          rawDevTrustAnchor: base64.encode(ascii.encode('-----BEGIN PRIVATE KEY-----')),
        ),
        rejectsAnchor('PEM certificate'),
      );
    });

    test('a CA does NOT make an http:// base URL acceptable', () {
      // **The rule this whole mechanism must never be able to bend.** Supplying a
      // certificate widens which issuers are trusted; it says nothing about whether TLS is
      // required. If these two rules ever became entangled, this is where it would show.
      expect(
        () => AppConfig.parse('http://api.example.com', rawDevTrustAnchor: encoded),
        throwsA(
          isA<ConfigurationException>()
              .having((e) => e.variable, 'variable', AppConfig.baseUrlVariable)
              .having((e) => e.reason, 'reason', contains('only https://')),
        ),
      );
    });
  });
}
