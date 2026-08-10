/// Failures are values, not exceptions (M8 §7.3).
///
/// A field app spends its life failing: no signal, a 401, a full disk. If those arrive
/// as exceptions, every call site either catches or forgets to, and the ones that forget
/// are discovered by a salesman in a market. As values they are in the type.
sealed class Failure {
  const Failure(this.message);
  final String message;
}

/// The device could not reach the server. **Not an error the user caused.**
final class Offline extends Failure {
  const Offline() : super('No connection.');
}

/// The server refused. [code] is the server's own problem+json code (`05` §5).
final class Refused extends Failure {
  const Refused(this.code, super.message);
  final String code;
}

/// The session is gone and cannot be refreshed (C-7: refresh once, then re-authenticate).
final class Unauthenticated extends Failure {
  const Unauthenticated() : super('Sign in again.');
}
