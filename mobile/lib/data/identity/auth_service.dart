import '../../core/failure.dart';
import '../../core/result.dart';
import '../../domain/identity/authenticator.dart';
import '../../domain/identity/otp_challenge.dart';
import '../../domain/identity/session.dart';
import '../api/api_client.dart';
import '../api/tokens.dart';
import '../repositories/token_session_repository.dart';
import 'auth_dto.dart';
import 'user_dto.dart';

/// The two supported sign-in paths (M8 §8.1): **OTP for the field, password for internal
/// fallback.**
///
/// Both end in the same three steps — persist the credentials, build the session, publish
/// it once — so they share one private path. Two copies would eventually disagree about
/// which happens first, and the ordering is the part that matters.
///
/// Implements [Authenticator] so `features/` can depend on the interface without importing
/// `data/` (M5). No method was renamed to fit the port.
final class AuthService implements Authenticator {
  const AuthService({
    required ApiClient api,
    required TokenStore tokens,
    required TokenSessionRepository sessions,
  })  : _api = api,
        _tokens = tokens,
        _sessions = sessions;

  static const otpRequestPath = '/auth/otp/request';
  static const otpVerifyPath = '/auth/otp/verify';
  // Named for the endpoint, not the credential: a constant called
  // `password…` assigned a string literal trips the P-9 secret-shape check,
  // and that check is right to be blunt about it.
  static const loginPath = '/auth/login';

  final ApiClient _api;
  final TokenStore _tokens;
  final TokenSessionRepository _sessions;

  /// Ask the server to send a code.
  ///
  /// The result is deliberately uninformative about the account: see [OtpChallenge].
  /// Rate limiting and validation arrive as the ordinary `05` §5 codes — `OTP_RATE_LIMITED`,
  /// `VALIDATION_FAILED` — and stay [ProblemFailure], because the client branches on `code`
  /// and inventing a bespoke failure here would hide it.
  @override
  Future<Result<OtpChallenge>> requestOtp(String phone) async {
    try {
      return await _api.post<OtpChallenge>(
        otpRequestPath,
        body: <String, dynamic>{'phone': phone},
        decode: parseOtpChallenge,
      );
    } on AuthPayloadException catch (error) {
      return Err(MalformedResponse(error.reason));
    }
  }

  /// Exchange a code for a session.
  ///
  /// **`device_id` is not set here.** `DeviceInterceptor` injects it into every write body
  /// that lacks one, reading the value `SecureTokenStore` minted at first launch (C-10,
  /// §8.4) — and the server's serializer accepts it as optional precisely so one mechanism
  /// can supply it. Setting it here as well would be a second source for one fact.
  @override
  Future<Result<Session>> verifyOtp({
    required String phone,
    required String code,
  }) =>
      _authenticate(otpVerifyPath, <String, dynamic>{'phone': phone, 'code': code});

  /// Internal fallback (§8.1). Same bundle, same handling.
  @override
  Future<Result<Session>> loginWithPassword({
    required String phone,
    required String password,
  }) =>
      _authenticate(
        loginPath,
        <String, dynamic>{'phone': phone, 'password': password},
      );

  /// Persist, then publish — **and never the other way round.**
  ///
  /// `adopt` wakes every listener, which will immediately issue requests. Publishing before
  /// `save` would give them a session with no token attached and a first request that 401s
  /// for no reason a user could understand.
  ///
  /// **Nothing is published on failure**, so a rejected code or a wrong password leaves an
  /// existing session exactly as it was.
  Future<Result<Session>> _authenticate(String path, Map<String, dynamic> body) async {
    final Result<AuthBundle> result;
    try {
      result = await _api.post<AuthBundle>(path, body: body, decode: AuthBundle.fromJson);
    } on AuthPayloadException catch (error) {
      return Err(MalformedResponse(error.reason));
    } on UserPayloadException catch (error) {
      // The nested user object is parsed by M2's DTO, which throws its own type.
      return Err(MalformedResponse(error.reason));
    }

    if (result is Err<AuthBundle>) return Err(result.failure);

    final bundle = (result as Ok<AuthBundle>).value;
    await _tokens.save(
      accessToken: bundle.accessToken,
      refreshToken: bundle.refreshToken,
    );

    final session = bundle.user.toSession();
    _sessions.adopt(session);
    return Ok(session);
  }
}
