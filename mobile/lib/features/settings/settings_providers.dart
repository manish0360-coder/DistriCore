import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/identity/session_repository.dart';

/// Settings' one port (`M8_Design_Review` §2.2).
///
/// Same crossing every other feature makes: `features/` may name a `domain/` interface and
/// may not reach `app/providers.dart` for the binding, so the composition root overrides
/// this and the screen never learns that a `TokenSessionRepository` exists.
///
/// Throws rather than defaulting, like `companionPortProvider` and `syncStatusPortProvider`:
/// a `ProviderScope` that forgets to supply it fails immediately and by name, instead of
/// rendering a Sign out button that quietly does nothing.
final settingsPortProvider = Provider<SessionRepository>(
  (ref) => throw StateError('settingsPortProvider must be overridden at start-up'),
);
