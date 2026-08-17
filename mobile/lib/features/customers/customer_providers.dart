import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/customer/customer_repository.dart';

/// The customer/visit port, **supplied by the composition root**.
///
/// Same shape and same reason as `authenticatorProvider` and `deliveryRepositoryProvider`:
/// `features/` sees `domain/` and `core/` and nothing else, so the binding happens in
/// `bootstrap`, where both sides are visible.
final customerRepositoryProvider = Provider<CustomerRepository>(
  (ref) => throw StateError('customerRepositoryProvider must be overridden at start-up'),
);
