import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../domain/identity/session.dart';
import '../features/auth/login_screen.dart';
import '../features/settings/settings_screen.dart';
import 'providers.dart';
import 'shell.dart';
import 'tabs.dart';

/// Declarative routing with **one** redirect guard (M8 §4).
///
/// Route-level role checks are presentation only. Deep links are not supported in M8:
/// nothing external links into the app, and a route reachable without the guard is a route
/// reachable without a session.
final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/deliveries',
    refreshListenable: _SessionRefresh(ref),
    redirect: (context, state) {
      final session = ref.read(sessionProvider).valueOrNull;
      final atLogin = state.matchedLocation == '/login';
      if (session == null) return atLogin ? null : '/login';
      if (atLogin) return _landingFor(session);
      return null;
    },
    routes: [
      // Outside the shell: neither has a tab bar, and login must not render one before
      // there is a session to compose it from.
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      GoRoute(path: '/settings', builder: (_, __) => const SettingsScreen()),
      ShellRoute(
        builder: (_, __, child) => RoleShell(child: child),
        routes: [
          for (final tab in tabs)
            GoRoute(path: tab.path, builder: (_, __) => tab.builder()),
        ],
      ),
    ],
  );
});

/// The first tab this user can actually see. A fixed landing route would strand a
/// delivery-only user on a salesman screen.
String _landingFor(Session session) =>
    tabs.firstWhere((tab) => tab.visibleTo(session), orElse: () => tabs.last).path;

/// Bridges Riverpod's session stream to go_router's imperative refresh.
class _SessionRefresh extends ChangeNotifier {
  _SessionRefresh(Ref ref) {
    ref.listen(sessionProvider, (_, __) => notifyListeners());
  }
}
