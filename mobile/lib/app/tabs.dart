import 'package:flutter/material.dart';

import '../domain/identity/role.dart';
import '../domain/identity/session.dart';
import '../features/customers/customers_screen.dart';
import '../features/deliveries/deliveries_screen.dart';
import '../features/sync_status/sync_status_screen.dart';

/// One tab, and the roles that make it appear.
///
/// **Tabs are composed from the roles array, never switched on a "primary role"**
/// (`05` C-12, P-7). A user holding both `SALESMAN` and `DELIVERY` sees both tabs, because
/// that person is the client's normal case and the bug this prevents is invisible until
/// they hold the phone.
@immutable
final class TabSpec {
  const TabSpec({
    required this.path,
    required this.label,
    required this.icon,
    required this.roles,
    required this.builder,
  });

  final String path;
  final String label;
  final IconData icon;

  /// Empty means "every signed-in user".
  final Set<Role> roles;
  final Widget Function() builder;

  bool visibleTo(Session session) => roles.isEmpty || session.hasAny(roles);
}

/// The tab inventory (M8 §4). The owner's "Today" tab arrives with Companion Mode at
/// task 8; it is absent rather than hidden, because a tab with no screen behind it is a
/// dead route someone will wire up by accident.
final tabs = <TabSpec>[
  TabSpec(
    path: '/deliveries',
    label: 'Deliveries',
    icon: Icons.local_shipping_outlined,
    roles: {Role.delivery},
    builder: DeliveriesScreen.new,
  ),
  TabSpec(
    path: '/customers',
    label: 'Customers',
    icon: Icons.store_outlined,
    roles: {Role.salesman},
    builder: CustomersScreen.new,
  ),
  TabSpec(
    path: '/status',
    label: 'Status',
    icon: Icons.sync_outlined,
    roles: const {},
    builder: SyncStatusScreen.new,
  ),
];
