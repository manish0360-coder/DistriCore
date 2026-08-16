import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/api/api_client.dart';
import '../data/api/tokens.dart';
import '../data/db/app_database.dart';
import '../data/db/connection.dart';
import '../data/db/platform_database_key.dart';
import '../data/identity/platform_secure_storage.dart';
import '../data/identity/secure_token_store.dart';
import '../features/auth/auth_providers.dart';
import '../features/deliveries/delivery_providers.dart';
import 'app.dart';
import 'config.dart';
import 'providers.dart';

/// Start-up, in one place (M8 task 4 M4).
///
/// **The order is the design:**
///
/// 1. Read and validate configuration. A build with no `--dart-define` **must not render** —
///    it has no server to talk to, and a login screen that fails every attempt is a worse
///    diagnosis than a refusal that names the missing define.
/// 2. Open the keystore. `SecureTokenStore`'s getters are synchronous, so hydration has to
///    finish before anything can hold the store (§8.2).
/// 3. Wire the container.
/// 4. `runApp` — **before** any network call.
/// 5. *Then* start restoration.
///
/// Step 4 before step 5 is the correction M4 makes to task 1's comment, which claimed
/// restoration should precede the first frame. `SessionRestorer` calls `/auth/me`, and on a
/// van with no signal that call runs to a 30-second timeout. Awaiting it here would show a
/// blank window for half a minute on exactly the device this app is built for. The shell
/// renders signed-out — which `current()` truthfully reports (D-C, §8.2) — and the single
/// emission from `restore()` moves it.
Future<void> bootstrap() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Fails closed, before anything is constructed and long before anything is rendered.
  final config = AppConfig.fromEnvironment();

  const storage = PlatformSecureStorage();
  final tokens = await SecureTokenStore.open(storage);

  // **The database is opened here, before the first frame, and keyed from the keystore.**
  // Task 3 built the schema and left `DatabaseKeyProvider` unimplemented on purpose — *"a
  // placeholder key compiled into the binary would satisfy the type system and violate
  // P-9"*. M6 is the first milestone that reads local data at start-up, so it is the one
  // that pays that deferral.
  final database = AppDatabase(
    await openDeviceDatabase(const PlatformDatabaseKey(storage)),
  );

  final container = buildRootContainer(
    config: config,
    tokens: tokens,
    database: database,
  );

  runApp(
    UncontrolledProviderScope(
      container: container,
      child: const DistriCoreApp(),
    ),
  );

  startSessionRestoration(container);
}

/// The composition root's two runtime values, bound.
///
/// Split out of [bootstrap] because everything above it — `ensureInitialized`, the platform
/// keystore, `runApp` — needs a device, and the wiring itself does not. This function is
/// what the tests can actually execute.
///
/// `apiClientProvider` is overridden with a *factory* rather than a value so the client
/// reads its store from [tokenStoreProvider]. Passing `tokens` to both by hand would make it
/// possible for the two to disagree, which is the kind of defect that only shows up as a
/// request carrying no `Authorization` header.
ProviderContainer buildRootContainer({
  required AppConfig config,
  required TokenStore tokens,
  required AppDatabase database,
}) =>
    ProviderContainer(
      overrides: [
        tokenStoreProvider.overrideWithValue(tokens),
        appDatabaseProvider.overrideWithValue(database),
        // `data/` may not import `app/`, so the window crosses the boundary as a plain
        // `Duration` rather than as an `AppConfig` the restorer would have to know about.
        offlineWindowProvider.overrideWithValue(config.offlineWindow),
        apiClientProvider.overrideWith(
          (ref) => ApiClient(
            baseUrl: config.baseUrl,
            tokens: ref.watch(tokenStoreProvider),
          ),
        ),
        // **The only place the login feature meets its implementation** (M5).
        // `features/` cannot import `data/` or `app/`, so `authenticatorProvider` is
        // declared beside the screen that needs it and bound here, where both sides are
        // visible. `AuthService` already implements the port; nothing is adapted.
        authenticatorProvider.overrideWith((ref) => ref.watch(authServiceProvider)),
        // Same crossing as `authenticatorProvider`, same reason: the delivery feature
        // declares the port it needs and the composition root is the only place that knows
        // which implementation satisfies it (T5).
        deliveryRepositoryProvider
            .overrideWith((ref) => ref.watch(deliveryRepositoryImplProvider)),
      ],
    );

/// Kick off cold-start restoration. **Returns immediately, by design** — see [bootstrap].
///
/// The `read` of [sessionProvider] is not a stray expression: it forces the provider to
/// exist, and therefore to subscribe to the repository, *before* [restore] can emit. That
/// ordering is the reason `sessionProvider` builds its stream synchronously; without one of
/// the two, a restoration that completes without real I/O publishes into a stream nobody is
/// listening to yet and the event is gone.
void startSessionRestoration(ProviderContainer container) {
  container.read(sessionProvider);
  unawaited(container.read(tokenSessionRepositoryProvider).restore());
}
