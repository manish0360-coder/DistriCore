import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/companion/companion_repository.dart';

/// Owner Companion Mode's one port (M8 §3.4, task 8).
///
/// Same crossing every other feature makes: `features/` may name a `domain/` interface and
/// may not reach `app/providers.dart` for the binding, so the composition root overrides this
/// and the screen never learns that `ApiCompanionRepository` exists (§2.2).
///
/// Throws rather than defaulting, like `authenticatorProvider` and `syncStatusPortProvider`:
/// a `ProviderScope` that forgets to supply it fails immediately and by name, instead of
/// rendering four empty screens that look like a quiet morning.
final companionPortProvider = Provider<CompanionRepository>(
  (ref) => throw StateError('companionPortProvider must be overridden at start-up'),
);
