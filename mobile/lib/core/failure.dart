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

/// A field-level validation error from `05` §5.4's `errors[]`.
final class FieldError {
  const FieldError({required this.field, required this.message});
  final String field;
  final String message;
}

/// The server answered with RFC 9457 problem+json (`05` §5).
///
/// **Carries `code`, and callers branch on `code` alone.** `05` says `title` and `detail`
/// may be reworded without breaking a client, so any code that matches on prose is a client
/// that a copy-edit can break.
final class ProblemFailure extends Failure {
  const ProblemFailure({
    required this.code,
    required this.status,
    required String detail,
    this.errors = const [],
    this.requestId,
  }) : super(detail);

  final String code;
  final int status;
  final List<FieldError> errors;
  final String? requestId;

  /// `DUPLICATE_CLIENT_UUID` is **not an error** — `05` §5.3 lists it at status 200 and C-4
  /// requires the client to treat it as success. A retry after a timeout is correct client
  /// behaviour; answering it as a failure is how a delivery gets recorded twice by a person
  /// who was told the first attempt failed.
  bool get isReplay => code == 'DUPLICATE_CLIENT_UUID';
}

/// The server replied, but not in a shape `05` describes — a proxy error page, an HTML 502,
/// a truncated body. Distinct from [ProblemFailure] because there is no `code` to branch on
/// and the only safe action is to retry later.
final class MalformedResponse extends Failure {
  const MalformedResponse(super.message, {this.status});
  final int? status;
}

/// **D-C3 — the durable write could not be made, because there is no room for it.**
///
/// Deliberately **not** [Offline], and the distinction is behavioural rather than tidy:
/// `Offline` means *retry later and it will work*; this means *retrying changes nothing
/// until space is freed*. Folding the two together produces an app that retries forever
/// against a full disk and tells the user it is merely waiting for signal.
///
/// Also deliberately not an unhandled exception. §5.3 — *"the user is never told 'saved'
/// before it is"* — and NFR-OFF-005 make a failed outbox write a **failed user action**,
/// which is a value the UI must handle, not a crash.
///
/// `Failure` is sealed, so adding this member fans out at compile time across every
/// `fold` in the app. That is the point of the sealed hierarchy, and the reason this is one
/// new class rather than a flag on an existing one.
final class StorageFull extends Failure {
  const StorageFull([super.message = 'Not enough storage to save this.']);
}
