import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/clock.dart';
import '../data/repositories/in_memory_session_repository.dart';
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
final sessionProvider = StreamProvider<Session?>((ref) async* {
  final repository = ref.watch(sessionRepositoryProvider);
  yield repository.current().fold((session) => session, (_) => null);
  yield* repository.changes();
});
