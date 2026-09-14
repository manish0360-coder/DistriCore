import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// The one way into `/settings`, and therefore the one way to sign out.
///
/// **Why a shared widget rather than four `IconButton`s, and why not the tab bar.** Every
/// feature screen builds its own `Scaffold` and `AppBar`, so `RoleShell` cannot inject an
/// action into them — and the tab bar is not an option either: `RoleShell` returns the bare
/// child when a session sees fewer than two tabs, so a delivery-only user has no bar at
/// all. Putting sign-out there would hide it from exactly the person most likely to be
/// handed a shared phone.
///
/// `push`, not `go`: `/settings` sits outside the `ShellRoute` (`app/router.dart`), so
/// pushing gives it the automatic back affordance and returns the user where they were.
class SettingsAction extends StatelessWidget {
  const SettingsAction({super.key});

  @override
  Widget build(BuildContext context) => IconButton(
        icon: const Icon(Icons.settings_outlined),
        tooltip: 'Settings',
        onPressed: () => context.push('/settings'),
      );
}
