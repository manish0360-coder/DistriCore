import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/result.dart';
import '../../domain/identity/session.dart';
import 'settings_providers.dart';

/// Settings, and the only place a signed-in user can sign out.
///
/// **`M8_Design_Review` §3.1 specifies this screen as "Version, device id, sign out".**
/// `TokenSessionRepository.signOut()` has existed and been covered since M8 —
/// `session_restoration_test.dart` proves it emits `null`, clears the tokens and keeps the
/// device id — and until now **nothing in `lib/` ever called it**. The mechanism was
/// complete, tested and unreachable: the route existed, the screen behind it rendered the
/// word "Settings", and `SessionRepository` did not even declare the method, so `features/`
/// had no way to name it.
///
/// **Version and device id are still not built.** They are the other two items on that line
/// and neither is what made the screen unreachable; adding them here would be scope this
/// defect fix has not earned. Recorded rather than silently dropped.
///
/// **No navigation after signing out, deliberately.** `signOut()` emits `null` on the
/// session stream, `app/router.dart`'s `refreshListenable` hears it, and the single
/// redirect guard sends any sessionless location to `/login`. Pushing a route here as well
/// would be a second authority over one decision — the shape M8 §4 exists to prevent.
class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  /// Guards a second tap while the first is clearing the stores. Not cosmetic: two
  /// concurrent `signOut()` calls would race the token store against the identity store.
  bool _signingOut = false;

  Future<void> _signOut() async {
    if (_signingOut) return;
    setState(() => _signingOut = true);
    await ref.read(settingsPortProvider).signOut();
    // No `setState` and no navigation afterwards: the redirect guard has already taken this
    // route away, and touching state on a disposed element is how that becomes a crash.
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final session = switch (ref.read(settingsPortProvider).current()) {
      Ok<Session?>(value: final value) => value,
      _ => null,
    };

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (session != null)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(session.fullName),
              subtitle: const Text('Signed in'),
            ),
          const Divider(height: 32),
          FilledButton.tonalIcon(
            onPressed: _signingOut ? null : () => unawaited(_signOut()),
            icon: const Icon(Icons.logout),
            label: Text(_signingOut ? 'Signing out…' : 'Sign out'),
          ),
          const SizedBox(height: 12),
          // Stating what `signOut()` already does, so a driver with undelivered work knows
          // this is not the button that loses it (§8.3: a signed-out device still owes the
          // business its work).
          Text(
            'Deliveries and visits you have recorded but not yet synced stay on this '
            'device and will send once someone signs in again.',
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
