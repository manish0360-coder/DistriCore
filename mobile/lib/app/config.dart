/// **Start-up configuration, read from the build — never written into the source.**
///
/// `02A` §9.3 assumes the APK is downloadable and fully decompiled, and P-9 forbids an
/// internal surface in the binary. The server address is therefore supplied by the release
/// command as `--dart-define=DISTRICORE_API_BASE_URL=…` and read here exactly once. A
/// literal in `lib/` would also mean the address could only be changed by changing code.
///
/// **There is deliberately no default.** `00` §9 states the rule for the backend —
/// *"secrets and production endpoints have no default and must fail"* — and this is the same
/// rule applied to the second toolchain, in the same spirit as `mobile-pin`: *"It is the
/// pin; refusing to guess."* An unconfigured build must not reach a device pointing at a
/// plausible wrong host, so [AppConfig.fromEnvironment] throws **before `runApp`**.
///
/// The production hostname does not exist yet: `00` §6 A-04 buys the domain *before M11*.
/// Nothing in this file invents one. `make mobile-verify` supplies a verification-only
/// value, which is why that value lives in the Makefile and not here.
library;

import 'dart:convert';
import 'dart:typed_data';

/// Compiled once rather than per call. Trailing slashes only: a base URL is normalised, not
/// rewritten.
final _trailingSlashes = RegExp(r'/+$');

/// A build that cannot be trusted to reach the right server.
///
/// Not a `Failure`: `core/failure.dart` models things the *user* can be told about and the
/// app can recover from. This is a defect in how the binary was produced, and the only
/// correct response is to refuse to start.
final class ConfigurationException implements Exception {
  const ConfigurationException(this.variable, this.reason);

  /// The `--dart-define` name, so the message names the fix rather than the symptom.
  final String variable;
  final String reason;

  @override
  String toString() =>
      'Build misconfigured: --dart-define=$variable $reason. It has no default; '
      'the build command must supply it.';
}

/// Everything start-up needs to know that is not in the source tree.
///
/// One field today. It is a class rather than a bare `String` so that the *validation* has
/// somewhere to live and the second setting does not arrive as a second parameter threaded
/// through `bootstrap`.
final class AppConfig {
  const AppConfig._(this.baseUrl, this.offlineWindow, this.devTrustAnchor);

  /// Absolute, `https`, no trailing slash. Safe to concatenate with the leading-slash paths
  /// the API layer declares (`/auth/login`, `/auth/me`, …).
  final String baseUrl;

  /// **D-D2.** The FR-IAM-016 offline window.
  ///
  /// Unlike [baseUrl] this one **has a default**, and the difference is not inconsistency:
  /// a base URL is a deployment fact nobody can guess, while 7 days is a frozen product
  /// requirement (OI-5). A build that omits it is correct; a build that omits the host is a
  /// defect.
  final Duration offlineWindow;

  /// **A development certificate authority, and nothing else.** `null` in every build that
  /// does not supply one — which is every production build.
  ///
  /// **Why this exists.** `00` §7.3 puts the emulator on `10.0.2.2`, and [baseUrl] refuses
  /// `http://`, so the development stack terminates TLS at Caddy with a locally-issued
  /// certificate. Dio speaks through `dart:io`'s `HttpClient`, which verifies against
  /// **BoringSSL's** roots inside the Dart VM — it does not read Android's
  /// `network_security_config.xml` and it does not read the device's user CA store. A CA
  /// installed on the device is therefore invisible to this app, which is why the
  /// certificate has to arrive through the build instead.
  ///
  /// **This widens trust; it does not weaken verification.** The bytes are *added* to the
  /// normal roots (`withTrustedRoots: true`). Chain building, expiry, hostname matching and
  /// every other check behave exactly as they do in production. There is no
  /// `badCertificateCallback` anywhere in this codebase, and
  /// `test_mobile_boundary.py::test_no_certificate_verification_is_bypassed` fails the build
  /// if one appears.
  ///
  /// **P-9 is satisfied because nothing is compiled in.** The certificate is supplied by the
  /// build command, exactly as [baseUrl] is; `lib/` contains no key material and no host.
  final Uint8List? devTrustAnchor;

  /// The `--dart-define` name, stated once. `00` §9's convention: `DISTRICORE_` prefix,
  /// `SCREAMING_SNAKE_CASE`.
  static const baseUrlVariable = 'DISTRICORE_API_BASE_URL';

  /// **No `defaultValue:` argument, on purpose.** `String.fromEnvironment` falls back to the
  /// empty string when the define is absent, and [parse] rejects that — so "unset" and
  /// "blank" fail through one path instead of two.
  ///
  /// Read in a `const` context because that is the only context in which
  /// `String.fromEnvironment` is guaranteed to see the compile-time environment.
  static const _rawBaseUrl = String.fromEnvironment(baseUrlVariable);

  /// **D-D2.** `00` §9's convention again: `DISTRICORE_` prefix, `SCREAMING_SNAKE_CASE`.
  static const offlineWindowVariable = 'DISTRICORE_OFFLINE_WINDOW_DAYS';

  /// OI-5. Stated once, here, and nowhere else in the codebase.
  static const defaultOfflineWindowDays = 7;

  static const _rawOfflineWindowDays = String.fromEnvironment(offlineWindowVariable);

  /// **Base64, not raw PEM.** A certificate is multi-line; `--dart-define` values that
  /// contain newlines are quoted differently by every shell and are silently truncated by
  /// some. One base64 line survives PowerShell, `sh` and a Makefile unchanged.
  static const devTrustAnchorVariable = 'DISTRICORE_DEV_CA_B64';

  static const _rawDevTrustAnchor = String.fromEnvironment(devTrustAnchorVariable);

  /// Reads the values baked in at compile time. Throws [ConfigurationException] if the build
  /// did not supply usable ones.
  factory AppConfig.fromEnvironment() => AppConfig.parse(
        _rawBaseUrl,
        rawOfflineWindowDays: _rawOfflineWindowDays,
        rawDevTrustAnchor: _rawDevTrustAnchor,
      );

  /// The validation, separated from the environment read so that every rule below is
  /// testable without recompiling the suite once per case.
  factory AppConfig.parse(
    String raw, {
    String rawOfflineWindowDays = '',
    String rawDevTrustAnchor = '',
  }) {
    final value = raw.trim();

    if (value.isEmpty) {
      throw const ConfigurationException(baseUrlVariable, 'is missing or blank');
    }

    // Defensive, and labelled as such: `Uri.parse` is lenient, so most malformed input
    // reaches one of the checks below instead of arriving here. `tryParse` rather than
    // `parse` so that whatever *does* reach it becomes a named configuration error rather
    // than a `FormatException` thrown out of `main`.
    final uri = Uri.tryParse(value);
    if (uri == null) {
      throw const ConfigurationException(baseUrlVariable, 'is not a URL');
    }

    if (uri.scheme.isEmpty) {
      throw const ConfigurationException(
        baseUrlVariable,
        'is not absolute — it must begin with https://',
      );
    }

    // **Not a stylistic preference.** `00` §9's TLS termination and `02A` §9.3 both assume
    // the field device talks HTTPS; an `http://` base URL would silently disable the
    // transport security the whole auth design rests on, and would do so on a phone on a
    // shared network.
    if (uri.scheme != 'https') {
      throw ConfigurationException(
        baseUrlVariable,
        'uses ${uri.scheme}:// — only https:// is accepted',
      );
    }

    if (uri.host.isEmpty) {
      throw const ConfigurationException(baseUrlVariable, 'has no host');
    }

    // Credentials in a URL are a secret in configuration, which P-9 and `00` §9 both
    // exclude — and they would be logged by every HTTP client that prints a request line.
    if (uri.userInfo.isNotEmpty) {
      throw const ConfigurationException(
        baseUrlVariable,
        'must not carry credentials',
      );
    }

    // A query or fragment on a *base* URL cannot survive path concatenation: it would end up
    // in the middle of every request URL. Rejecting is honest; silently dropping is not.
    if (uri.hasQuery || uri.hasFragment) {
      throw const ConfigurationException(
        baseUrlVariable,
        'must not carry a query string or fragment',
      );
    }

    // A path prefix is **required**, not merely tolerated: the API is mounted at `/api/v1/`
    // (`config/urls.py`) while the client declares paths as `/auth/login`. Trailing slashes
    // are trimmed so that concatenation cannot produce `…/api/v1//auth/login`.
    final path = uri.path.replaceAll(_trailingSlashes, '');
    return AppConfig._(
      uri.replace(path: path).toString(),
      _parseOfflineWindow(rawOfflineWindowDays),
      // **After the scheme check, deliberately.** A build that supplies a certificate and an
      // `http://` base URL has already been refused above. Supplying a CA can never make a
      // rejected URL acceptable — the two rules are independent and the order makes that
      // impossible to get wrong by editing one of them.
      _parseDevTrustAnchor(rawDevTrustAnchor),
    );
  }

  /// **Absent is the normal case and is not an error.** Present-but-broken is.
  ///
  /// A build that supplies an unusable certificate must refuse to start rather than fall
  /// back to the default roots: the fallback would connect to nothing and present as the
  /// same generic "no connection" the developer was already trying to fix. Fail closed,
  /// before `runApp`, naming the define — the same rule [parse] applies to the host.
  static Uint8List? _parseDevTrustAnchor(String raw) {
    final value = raw.trim();
    if (value.isEmpty) return null;

    final Uint8List bytes;
    try {
      bytes = base64.decode(value);
    } on FormatException {
      throw const ConfigurationException(
        devTrustAnchorVariable,
        'is not valid base64 — supply `base64 -w0 build/districore-dev-ca.crt`',
      );
    }

    // Catches the two mistakes that would otherwise reach BoringSSL as an opaque failure:
    // handing over the private key, or handing over the leaf instead of the CA.
    if (!ascii.decode(bytes, allowInvalid: true).contains(_pemCertificateHeader)) {
      throw const ConfigurationException(
        devTrustAnchorVariable,
        'does not decode to a PEM certificate — expected a `$_pemCertificateHeader` block',
      );
    }
    return bytes;
  }

  static const _pemCertificateHeader = '-----BEGIN CERTIFICATE-----';

  /// **D-D2.** Absent means OI-5's 7 days. Present means it must be a usable number of days.
  ///
  /// Rejected **before `runApp`**, like every other configuration error here: a build that
  /// says `0` has asked for an app that locks out instantly, and a build that says `-1` has
  /// asked for one that never locks out at all. Neither is what anyone meant, and both would
  /// otherwise be discovered by a salesman rather than by a build.
  static Duration _parseOfflineWindow(String raw) {
    final value = raw.trim();
    if (value.isEmpty) return const Duration(days: defaultOfflineWindowDays);

    final days = int.tryParse(value);
    if (days == null) {
      throw const ConfigurationException(
        offlineWindowVariable,
        'is not a whole number of days',
      );
    }
    if (days <= 0) {
      throw ConfigurationException(
        offlineWindowVariable,
        'is $days — it must be a positive number of days',
      );
    }
    return Duration(days: days);
  }

  @override
  String toString() =>
      'AppConfig(baseUrl: $baseUrl, offlineWindow: ${offlineWindow.inDays}d)';
}
