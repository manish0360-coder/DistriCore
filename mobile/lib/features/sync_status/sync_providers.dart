import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/clock.dart';
import '../../domain/outbox/outbox_repository.dart';
import '../../domain/sync/sync_status_repository.dart';

/// The outbox, **supplied by the composition root**.
///
/// Same crossing as the other feature ports. `OutboxRepository` already lives in `domain/`,
/// so this file may name the type — what it may not do is reach `app/providers.dart` for the
/// binding.
final outboxPortProvider = Provider<OutboxRepository>(
  (ref) => throw StateError('outboxPortProvider must be overridden at start-up'),
);

/// P-8 needs an `as_of`, and P-4 needs that clock to be injectable rather than reached for.
///
/// Defaulted rather than override-required, because unlike a keystore or a base URL a clock
/// can be constructed anywhere. `bootstrap` still overrides it so the app runs on one clock.
final syncClockProvider = Provider<Clock>((ref) => const SystemClock());

/// The server's view of this device (`05` §11.5, M9.3). Supplied by the composition root,
/// like every other feature port.
final syncStatusPortProvider = Provider<SyncStatusRepository>(
  (ref) => throw StateError('syncStatusPortProvider must be overridden at start-up'),
);
