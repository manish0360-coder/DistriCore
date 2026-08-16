import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/delivery/delivery_repository.dart';

/// The delivery port, **supplied by the composition root**.
///
/// Same shape and same reason as `authenticatorProvider`: `features/` may see `domain/` and
/// `core/` and nothing else, so this file cannot name `OutboxDeliveryRepository` and cannot
/// reach `app/providers.dart`. It declares what the screen needs; `bootstrap` binds it.
///
/// The dividend is the test file: a delivery screen is exercised against one small interface,
/// with no Dio, no Drift and no keystore anywhere in the fixture.
final deliveryRepositoryProvider = Provider<DeliveryRepository>(
  (ref) => throw StateError('deliveryRepositoryProvider must be overridden at start-up'),
);
