import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/clock.dart';
import '../data/api/api_client.dart';
import '../data/api/tokens.dart';
import '../data/identity/auth_service.dart';
import '../data/identity/session_restorer.dart';
import '../data/repositories/token_session_repository.dart';
import '../domain/identity/session.dart';
import '../domain/identity/session_repository.dart';

/// **The composition root.** The only place an interface is bound to an implementation.
///
/// This is why `features/` may import `domain/` and never `data/` (M8 §2.2): a screen asks
/// for a `SessionRepository` and receives whatever is wired here. M4 swapped the stub for
/// the real one by changing one binding in this file and nothing else — no screen, no
/// feature, no domain type moved — which is what the seam was for and the reason the
/// layering test forbids the shortcut.
final clockProvider = Provider<Clock>((ref) => const SystemClock());

/// **The real repository, bound (M4).**
///
/// It delegates rather than constructing, so [tokenSessionRepositoryProvider] and this
/// provider are the *same object*. Constructing a second `TokenSessionRepository` here would
/// compile, pass every existing test, and produce an app in which `bootstrap` restores one
/// repository while the UI watches another — a session that is never seen.
///
/// `InMemorySessionRepository` is no longer wired, and is kept as a test double: a fake in
/// `lib/` that the app also runs is how a stub survives into production.
final sessionRepositoryProvider = Provider<SessionRepository>(
  (ref) => ref.watch(tokenSessionRepositoryProvider),
);

/// Supplied at start-up, not constructed here.
///
/// `SecureTokenStore.open()` is asynchronous and `ApiClient` needs the validated base URL
/// from `AppConfig`, which only exists once the process has read its compile-time
/// environment. Rather than let this file guess, both are declared as overrides: a
/// `ProviderScope` that forgets to supply them fails immediately and by name, instead of
/// reaching a device with a plausible wrong host.
final tokenStoreProvider = Provider<TokenStore>(
  (ref) => throw StateError('tokenStoreProvider must be overridden at start-up'),
);

final apiClientProvider = Provider<ApiClient>(
  (ref) => throw StateError('apiClientProvider must be overridden at start-up'),
);

final sessionRestorerProvider = Provider<SessionRestorer>(
  (ref) => SessionRestorer(
    tokens: ref.watch(tokenStoreProvider),
    api: ref.watch(apiClientProvider),
  ),
);

/// The owner of the session. [sessionRepositoryProvider] is a view onto this one instance,
/// and `bootstrap` reads it directly to call `restore()` — which the read-only domain
/// interface deliberately does not expose.
final tokenSessionRepositoryProvider = Provider<TokenSessionRepository>((ref) {
  final repository = TokenSessionRepository(
    tokens: ref.watch(tokenStoreProvider),
    restorer: ref.watch(sessionRestorerProvider),
  );
  ref.onDispose(repository.dispose);
  return repository;
});

/// The two sign-in paths (§8.1). Depends on the concrete [TokenSessionRepository], because
/// publishing a session is implementation-level: the domain interface stays read-only.
final authServiceProvider = Provider<AuthService>(
  (ref) => AuthService(
    api: ref.watch(apiClientProvider),
    tokens: ref.watch(tokenStoreProvider),
    sessions: ref.watch(tokenSessionRepositoryProvider),
  ),
);

/// The session as the UI sees it: a value that changes, not a thing to be polled.
///
/// **Subscribed synchronously, and that is the whole reason this is not an `async*` body.**
/// `changes()` is a broadcast stream with no replay, and M4 moved restoration to *after*
/// `runApp` so the shell can render offline. An `async*` generator only reaches
/// `yield* changes()` a microtask or two after the provider is created, so any emission in
/// that window is dropped — and the observable symptom is a device sitting on the login
/// screen while holding a perfectly valid refresh token. `onListen` runs inside
/// `container.read`, which closes the window rather than relying on restoration always
/// being slower than the event loop.
///
/// The current value is delivered **first**. On a cold start after a night offline there may
/// never be a stream event at all, and a shell that waited for one would show a spinner to a
/// user who is already signed in.
final sessionProvider = StreamProvider<Session?>((ref) {
  final repository = ref.watch(sessionRepositoryProvider);

  late final StreamController<Session?> controller;
  StreamSubscription<Session?>? subscription;

  controller = StreamController<Session?>(
    onListen: () {
      controller.add(repository.current().fold((session) => session, (_) => null));
      subscription = repository.changes().listen(
            controller.add,
            onError: controller.addError,
          );
    },
    onCancel: () async {
      await subscription?.cancel();
      subscription = null;
    },
  );

  ref.onDispose(controller.close);
  return controller.stream;
});
