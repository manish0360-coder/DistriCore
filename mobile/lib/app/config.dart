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
  const AppConfig._(this.baseUrl);

  /// Absolute, `https`, no trailing slash. Safe to concatenate with the leading-slash paths
  /// the API layer declares (`/auth/login`, `/auth/me`, …).
  final String baseUrl;

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

  /// Reads the value baked in at compile time. Throws [ConfigurationException] if the build
  /// did not supply a usable one.
  factory AppConfig.fromEnvironment() => AppConfig.parse(_rawBaseUrl);

  /// The validation, separated from the environment read so that every rule below is
  /// testable without recompiling the suite once per case.
  factory AppConfig.parse(String raw) {
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
    return AppConfig._(uri.replace(path: path).toString());
  }

  @override
  String toString() => 'AppConfig(baseUrl: $baseUrl)';
}
