import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/identity/authenticator.dart';

/// The sign-in port, **supplied by the composition root** (M5).
///
/// `features/` may import `domain/` and `core/` and nothing else, so this file cannot name
/// `AuthService` and cannot reach `app/providers.dart` either. It therefore declares what the
/// login feature needs and leaves the binding to `bootstrap`, which can see both sides —
/// the same shape as `tokenStoreProvider` and `apiClientProvider`, and for the same reason:
/// a scope that forgets to supply it fails immediately and by name.
///
/// The side effect is that every widget test overrides one small interface and never
/// constructs a `Dio`.
final authenticatorProvider = Provider<Authenticator>(
  (ref) => throw StateError('authenticatorProvider must be overridden at start-up'),
);
