import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/clock.dart';
import '../data/api/api_client.dart';
import '../data/api/tokens.dart';
import '../data/identity/session_restorer.dart';
import '../data/repositories/in_memory_session_repository.dart';
import '../data/repositories/token_session_repository.dart';
import '../domain/identity/session.dart';
import '../domain/identity/session_repository.dart';

/// **The composition root.** The only place an interface is bound to an implementation.
///
/// This is why `features/` may import `domain/` and never `data/` (M8 §2.2): a screen asks
/// for a `SessionRepository` and receives whatever is wired here. Task 4 swaps the stub for
/// the real one by changing one line in this file and nothing else — which is the entire
/// point of the seam, and the reason the layering test forbids the shortcut.
final clockProvider = Provider<Clock>((ref) => const SystemClock());

final sessionRepositoryProvider = Provider<SessionRepository>((ref) {
  final repository = InMemorySessionRepository();
  ref.onDispose(repository.dispose);
  return repository;
});

/// The session as the UI sees it: a value that changes, not a thing to be polled.
///
/// The current value is yielded **before** subscribing. On a cold start after a night
/// offline there may never be a stream event, and a shell that waits for one would show a
/// spinner to a user who is already signed in.
/// Supplied at start-up, not constructed here.
///
/// `SecureTokenStore.open()` is asynchronous and `ApiClient` needs a base URL that **no
/// configuration source in this repository provides yet**. Rather than invent one, these
/// two are declared as overrides: a `ProviderScope` that forgets to supply them fails
/// immediately and by name, instead of reaching a device with a plausible wrong host.
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

/// The real repository, **declared but not yet bound** to [sessionRepositoryProvider].
///
/// Binding it needs the two overrides above, which need start-up configuration that does
/// not exist. Until then `InMemorySessionRepository` remains the seam, exactly as task 1
/// left it — a provider swapped before the values behind it exist would fail at the first
/// frame rather than at the wiring.
final tokenSessionRepositoryProvider = Provider<TokenSessionRepository>((ref) {
  final repository = TokenSessionRepository(
    tokens: ref.watch(tokenStoreProvider),
    restorer: ref.watch(sessionRestorerProvider),
  );
  ref.onDispose(repository.dispose);
  return repository;
});

final sessionProvider = StreamProvider<Session?>((ref) async* {
  final repository = ref.watch(sessionRepositoryProvider);
  yield repository.current().fold((session) => session, (_) => null);
  yield* repository.changes();
});
