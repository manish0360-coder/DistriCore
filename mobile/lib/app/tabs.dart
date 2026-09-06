import 'package:flutter/material.dart';

import '../domain/identity/role.dart';
import '../domain/identity/session.dart';
import '../features/companion/companion_screen.dart';
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

/// The tab inventory (M8 §4).
///
/// **Companion Mode arrived at task 8**, which is what the previous note here promised: the
/// owner's tab was *"absent rather than hidden, because a tab with no screen behind it is a
/// dead route someone will wire up by accident."* There is a screen behind it now.
///
/// **First, so the owner lands on it.** `_landingFor` takes the first tab the session can
/// see, and an owner opening the app to check the day should not arrive on a delivery list
/// they will never work. A user holding both `OWNER` and `SALESMAN` sees both tabs — the roles
/// are a set and are never collapsed to a primary one (`05` C-12, P-7).
final tabs = <TabSpec>[
  TabSpec(
    path: '/companion',
    label: 'Today',
    icon: Icons.insights_outlined,
    // **Presentation only** (P-9, `02A` §9.3). This decides which tab is drawn; every figure
    // behind it is authorised again in CORE, and a patched APK that adds `Role.owner` here
    // gains a tab showing whatever its own token is allowed to see — which for a salesman is
    // what `/reports/*` already permits, and for a retailer is a 403.
    roles: {Role.owner},
    builder: CompanionScreen.new,
  ),
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
