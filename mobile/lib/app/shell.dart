import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'providers.dart';
import 'tabs.dart';

/// The tab bar, composed from the session's roles (P-7).
class RoleShell extends ConsumerWidget {
  const RoleShell({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider).valueOrNull;
    if (session == null) return child;

    final visible = tabs.where((tab) => tab.visibleTo(session)).toList();
    // A single-tab user gets no bar: one destination is not a choice, and the bar would
    // cost a delivery-only user a row of screen on a phone held in one hand.
    if (visible.length < 2) return child;

    final location = GoRouterState.of(context).matchedLocation;
    final selected = visible.indexWhere((tab) => tab.path == location);
    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: selected < 0 ? 0 : selected,
        onDestinationSelected: (index) => context.go(visible[index].path),
        destinations: [
          for (final tab in visible)
            NavigationDestination(icon: Icon(tab.icon), label: tab.label),
        ],
      ),
    );
  }
}
