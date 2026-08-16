// M8 task 4 M6 — the offline window predicate, the claim reader, and the configuration.
//
// Everything here is pure: no database, no network, no widgets. That is the point of
// `OfflineWindow` being a domain type — the rule that decides whether a device unlocks can
// be read and falsified on its own.
import 'dart:convert';

import 'package:districore/app/config.dart';
import 'package:districore/data/identity/refresh_claims.dart';
import 'package:districore/domain/identity/offline_window.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/jwt.dart';

final _issued = DateTime.utc(2026, 8, 1, 9);

OfflineWindow _window({
  Duration credentialLife = const Duration(days: 30),
  Duration maxOffline = const Duration(days: 7),
}) =>
    OfflineWindow(
      issuedAt: _issued,
      expiresAt: _issued.add(credentialLife),
      maxOffline: maxOffline,
    );

void main() {
  group('the predicate', () {
    test('1. inside the window it permits', () {
      final window = _window();
      expect(window.permits(_issued), isTrue);
      expect(window.permits(_issued.add(const Duration(days: 6, hours: 23))), isTrue);
      expect(
        window.permits(_issued.add(const Duration(days: 7) - const Duration(seconds: 1))),
        isTrue,
      );
    });

    test('2. the exact boundary DENIES', () {
      // §14.12.2. A boundary that admits `==` is a boundary chosen by accident, and this
      // one is a security parameter.
      expect(_window().permits(_issued.add(const Duration(days: 7))), isFalse);
    });

    test('3. beyond the window it denies', () {
      expect(_window().permits(_issued.add(const Duration(days: 8))), isFalse);
      expect(_window().permits(_issued.add(const Duration(days: 400))), isFalse);
    });

    test('4. a credential shorter than the window becomes the ceiling', () {
      // `05` §7.2 — "bounded by refresh-token validity". Computed from the token rather than
      // assumed to be 30 days, so lowering DISTRICORE_REFRESH_TOKEN_DAYS cannot leave a
      // device unlocking against a credential the server has stopped honouring.
      final short = _window(credentialLife: const Duration(days: 2));

      expect(short.effective, const Duration(days: 2));
      expect(short.permits(_issued.add(const Duration(days: 1, hours: 23))), isTrue);
      expect(short.permits(_issued.add(const Duration(days: 2))), isFalse);
      expect(short.permits(_issued.add(const Duration(days: 3))), isFalse);
    });

    test('the configured window is the ceiling when the credential outlives it', () {
      expect(_window().effective, const Duration(days: 7));
      expect(_window().credentialLife, const Duration(days: 30));
    });

    test('13. a clock behind the server-issued anchor denies rather than permits', () {
      // Not a tamper-detection mechanism and not claimed as one — negative elapsed time is
      // simply not a state that can honestly occur, and `elapsed < effective` would
      // otherwise be trivially true for every backward date.
      expect(_window().permits(_issued.subtract(const Duration(seconds: 1))), isFalse);
      expect(_window().permits(DateTime.utc(1999)), isFalse);
    });

    test('13b. the anchor comes from the token, so the device clock cannot move it', () {
      // Two "devices" with wildly different clocks, one token. The anchor is identical; only
      // the answer differs, and it differs in the direction that locks people out.
      final window = _window();
      expect(window.issuedAt, _issued);
      expect(window.permits(_issued.add(const Duration(days: 1))), isTrue);
      expect(window.permits(_issued.add(const Duration(days: 30))), isFalse,
          reason: 'a clock jumped forward fails closed');
    });
  });

  group('RefreshClaims', () {
    test('reads iat and exp, and nothing about the user', () {
      final expires = _issued.add(const Duration(days: 30));
      final claims =
          RefreshClaims.tryParse(refreshTokenJwt(issuedAt: _issued, expiresAt: expires))!;

      expect(claims.issuedAt, _issued);
      expect(claims.expiresAt, expires);
      // The token carries `sub: 12`. Identity must never come from an unverified payload.
      expect(claims.toString(), isNot(contains('12')));
    });

    test('a non-JWT is null, not an exception — the caller falls back to the server', () {
      // This is exactly what keeps every M2 test behaving as it did: their fakes carry
      // `refresh-1`, which is not a JWT.
      expect(RefreshClaims.tryParse('refresh-1'), isNull);
      expect(RefreshClaims.tryParse(''), isNull);
      expect(RefreshClaims.tryParse('a.b'), isNull);
      expect(RefreshClaims.tryParse('a.b.c.d'), isNull);
      expect(RefreshClaims.tryParse('not.base64url!!.sig'), isNull);
    });

    test('a payload without integer iat/exp is null', () {
      expect(RefreshClaims.tryParse(_token(<String, Object?>{'exp': 1})), isNull);
      expect(RefreshClaims.tryParse(_token(<String, Object?>{'iat': 1})), isNull);
      expect(
        RefreshClaims.tryParse(_token(<String, Object?>{'iat': '1', 'exp': '2'})),
        isNull,
      );
    });

    test('a token that expires before it was issued is refused', () {
      // So `OfflineWindow` never has to consider a negative credentialLife.
      expect(RefreshClaims.tryParse(_token(<String, Object?>{'iat': 500, 'exp': 100})), isNull);
      expect(RefreshClaims.tryParse(_token(<String, Object?>{'iat': 500, 'exp': 500})), isNull);
    });

    test('the token itself never appears in toString', () {
      final token = refreshTokenJwt(
        issuedAt: _issued,
        expiresAt: _issued.add(const Duration(days: 30)),
      );
      expect(RefreshClaims.tryParse(token).toString(), isNot(contains(token)));
    });
  });

  group('DISTRICORE_OFFLINE_WINDOW_DAYS (D-D2)', () {
    AppConfig parse(String days) =>
        AppConfig.parse('https://api.example.com', rawOfflineWindowDays: days);

    test('absent means OI-5 seven days', () {
      expect(parse('').offlineWindow, const Duration(days: 7));
      expect(parse('   ').offlineWindow, const Duration(days: 7));
      expect(AppConfig.defaultOfflineWindowDays, 7);
    });

    test('an explicit value overrides it', () {
      expect(parse('1').offlineWindow, const Duration(days: 1));
      expect(parse(' 30 ').offlineWindow, const Duration(days: 30));
    });

    test('zero and negative are refused before runApp', () {
      // Zero asks for an app that locks out instantly; negative asks for one that never
      // locks out at all. Neither is what anyone meant.
      expect(() => parse('0'), throwsA(isA<ConfigurationException>()));
      expect(() => parse('-1'), throwsA(isA<ConfigurationException>()));
    });

    test('a non-numeric value is refused and names the define', () {
      expect(
        () => parse('seven'),
        throwsA(
          isA<ConfigurationException>()
              .having((e) => e.variable, 'variable', 'DISTRICORE_OFFLINE_WINDOW_DAYS')
              .having((e) => e.toString(), 'message', contains('--dart-define')),
        ),
      );
      expect(() => parse('7.5'), throwsA(isA<ConfigurationException>()));
    });

    test('the base URL is still validated alongside it', () {
      expect(
        () => AppConfig.parse('http://api.example.com', rawOfflineWindowDays: '7'),
        throwsA(isA<ConfigurationException>()),
      );
    });
  });
}

/// A JWT with an arbitrary payload, for the parser's rejection cases.
String _token(Map<String, Object?> payload) {
  String segment(Map<String, Object?> claims) =>
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');
  return '${segment(<String, Object?>{'alg': 'HS256'})}.${segment(payload)}.sig';
}
