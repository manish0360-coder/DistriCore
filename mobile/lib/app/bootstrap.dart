import 'dart:async';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/failure.dart';
import '../core/result.dart';
import '../data/api/api_client.dart';
import '../data/api/tokens.dart';
import '../data/db/app_database.dart';
import '../data/db/connection.dart';
import '../data/db/platform_database_key.dart';
import '../data/identity/platform_secure_storage.dart';
import '../data/identity/secure_token_store.dart';
import '../domain/identity/session.dart';
import '../features/auth/auth_providers.dart';
import '../features/customers/customer_providers.dart';
import '../features/deliveries/delivery_providers.dart';
import '../features/sync_status/sync_providers.dart';
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
/// 5. *Then* start the background chain: restore → push → pull.
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

  // **The retry cadence's only tie to the platform** (TD-41). Bound here, after
  // `ensureInitialized` and `runApp`, because `AppLifecycleListener` needs a live binding.
  // Constructing the scheduler does not arm it; only `startBackgroundSync` does, and only
  // once there is a session.
  bindSyncToAppLifecycle(container);

  // **One call, one order.** M9.2 and M9.4 each added a start-up task; started
  // independently they raced, and a pull that won could overwrite the cache describing
  // writes the push had not yet delivered.
  unawaited(startBackgroundSync(container));
}

/// **Flutter's lifecycle, bound to the retry cadence** (TD-41).
///
/// **The callbacks that are absent decide as much as the two that are present.** There is no
/// `onPause` and no `onInactive`, deliberately: whether a Dart timer survives backgrounding is
/// Android's decision — Doze and App Standby — and stopping the cadence here as well would add
/// a *second, self-inflicted* reason to miss FR-SYN-010's 120-second bound on top of the one
/// the OS already imposes. The cadence therefore runs through `paused` and `inactive`, and
/// stops only at `detached`. Please do not add a pause handler as a battery optimisation
/// without a measurement (B2) showing one is needed.
///
/// `onResume` fires an attempt immediately rather than waiting out the remaining cadence: if
/// the OS *did* suspend the timer while the app was away, this is the moment that becomes
/// visible, and the worst time to be patient is when the user is already looking at the screen.
///
/// The listener registers itself with `WidgetsBinding`, which holds it, so the return value is
/// returned for testability rather than because a caller must retain it.
AppLifecycleListener bindSyncToAppLifecycle(ProviderContainer container) {
  final scheduler = container.read(syncSchedulerProvider);
  return AppLifecycleListener(
    onResume: scheduler.resumed,
    onDetach: scheduler.dispose,
  );
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
///
/// **[overrides] is appended after the bindings below, never substituted for them**, so a
/// caller replaces one binding without silently losing the rest — and, because it comes last,
/// a caller that names a provider this function also binds wins rather than being ignored. It
/// exists for the dependencies a test cannot wait for or reach; `syncTickerProvider` is the
/// first. It defaults to empty, which is every production build.
ProviderContainer buildRootContainer({
  required AppConfig config,
  required TokenStore tokens,
  required AppDatabase database,
  List<Override> overrides = const [],
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
            trustAnchor: _devTrustContext(config),
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
        customerRepositoryProvider
            .overrideWith((ref) => ref.watch(customerRepositoryImplProvider)),
        // The sync-status screen reads the same queue everything else writes to (T7).
        outboxPortProvider.overrideWith((ref) => ref.watch(outboxRepositoryProvider)),
        // One clock in the running app, even though the feature can default its own.
        syncClockProvider.overrideWith((ref) => ref.watch(clockProvider)),
        // `05` §11.5 — the server's view of this device, beside the local queue (M9.3).
        syncStatusPortProvider
            .overrideWith((ref) => ref.watch(syncStatusRepositoryProvider)),
        // Last, so a caller's binding wins over anything above it.
        ...overrides,
      ],
    );

/// The development trust anchor, or `null` — which is every production build.
///
/// **`withTrustedRoots: true` is the whole design.** The supplied certificate is *added* to
/// the platform roots, never substituted for them: a build carrying a development CA still
/// verifies every public certificate exactly as one without it does. Widening the set of
/// acceptable issuers is a different act from disabling verification, and only the first
/// happens here.
///
/// **What is deliberately absent:** no `badCertificateCallback`, no `HttpClient` returning
/// `true` for a rejected chain, no `allowLegacyUnsafeRenegotiation`, no cleartext fallback.
/// `test_mobile_boundary.py::test_no_certificate_verification_is_bypassed` runs inside
/// `make verify` and fails the build if any of them ever appears.
SecurityContext? _devTrustContext(AppConfig config) {
  final anchor = config.devTrustAnchor;
  if (anchor == null) return null;

  final context = SecurityContext(withTrustedRoots: true)
    ..setTrustedCertificatesBytes(anchor);
  return context;
}

/// Cold-start restoration. **The `read` of [sessionProvider] happens synchronously**, before
/// anything is awaited — see [bootstrap].
///
/// That read is not a stray expression: it forces the provider to exist, and therefore to
/// subscribe to the repository, *before* `restore()` can emit. That ordering is the reason
/// `sessionProvider` builds its stream synchronously; without one of the two, a restoration
/// that completes without real I/O publishes into a stream nobody is listening to yet and
/// the event is gone.
///
/// Returns the outcome rather than swallowing it, because M9.4's orchestration has to know
/// whether there is a session before it tries to sync one.
Future<Result<Session?>> startSessionRestoration(ProviderContainer container) {
  container.read(sessionProvider);
  return container.read(tokenSessionRepositoryProvider).restore();
}

/// **The one background chain, in one order** (M9.4, D-M9.4-7):
///
/// ```
/// restore session → push the outbox → pull server state
/// ```
///
/// **Ordered, not concurrent, and the order is the design.** Local durable writes must reach
/// the server *before* a pull overwrites the cache they describe; running the two together
/// would let a pull land the server's stale view over work the device has already recorded.
/// The outbox overlay would still mask it on screen, but the ordering should be deliberate
/// rather than whatever the event loop chose.
///
/// **Returns immediately.** A device with no signal must reach its delivery list without
/// waiting on requests that will time out — which is also why `runApp` precedes this.
///
/// **The launch round is no longer the only round (TD-41).** A repeating trigger now exists —
/// `SyncScheduler` — and it is armed at the end of this chain. The earlier note here claimed a
/// trigger could simply *"call this function"*; that was wrong, and the correction is the
/// reason [SyncRound] exists. This function restores a session, which is a **launch** concern:
/// a trigger calling it would re-authenticate against `/auth/me` on every attempt. The
/// scheduler calls [SyncRound] instead, and the two share the ordering rather than restating
/// it.
///
/// **This still does not discharge FR-SYN-010.** The requirement is that sync *completes*
/// within two minutes of reconnection; the cadence bounds when an attempt *starts*. Completion
/// at the DR-8 envelope over a real network is a timed device measurement (B1) that does not
/// exist yet, and the background case remains an open specification gap (**TD-47**).
/// **Returns the chain's future; `bootstrap` still does not await it.**
///
/// Production behaviour is unchanged — the call below is `unawaited`, so `runApp` is never
/// blocked, which is the whole point of this function. What changes is that the work is no
/// longer *unobservable*: a caller that needs to know when the chain finished can await it.
///
/// That is not a convenience. Hiding the future made every test of this function guess how
/// many event-loop turns the chain needs, and a guess that is one round trip short lets the
/// chain outlive the test — which closes the database under an in-flight `reclaimInFlight`
/// and reports a `Bad state` from a test that had already passed. A signal beats a guess.
Future<void> startBackgroundSync(ProviderContainer container) =>
    _restoreThenSync(container);

Future<void> _restoreThenSync(ProviderContainer container) async {
  // Runs synchronously up to this first `await`, so the `sessionProvider` read inside
  // `startSessionRestoration` still happens before anything can emit.
  final restored = await startSessionRestoration(container);

  // **No session, no sync — and there are two ways to arrive at no session.**
  //
  // `Err` is restoration *failing*. `Ok(null)` is restoration *succeeding* and finding no
  // credential — a fresh install, or a device signed out. They are different events and the
  // distinction matters elsewhere (§8.2: `Ok(null)` is what lets the shell render a login
  // screen without waiting on a timeout), but neither produces an authenticated session, so
  // both stop here. Pushing would meet a guaranteed 401 and pulling would return someone
  // else's nothing; both would look like work and be neither.
  final Session? session = restored.fold((value) => value, (_) => null);
  if (session == null) return;

  // **The launch round, through the same object every later attempt uses.** Push before pull,
  // `Unauthenticated` stopping before the pull, a transient failure still pulling — all of it
  // now lives in `SyncRound` rather than being restated here. Two callers stating one ordering
  // is how the two drift apart.
  final failure = (await container.read(syncRoundProvider).run())
      .fold<Failure?>((_) => null, (value) => value);

  // **A dead credential arms nothing.** Every tick would meet the same 401 and stop the
  // scheduler on its first attempt; starting it would buy one wasted round and nothing else.
  // Any other failure is exactly what the cadence exists for — `Offline` and `StorageFull`
  // both leave the rows `PENDING` and both resolve without a relaunch.
  if (failure is Unauthenticated) return;

  // **FR-SYN-017's retry, armed** — and only now, with a session in hand (D-M9.4-7 carried
  // forward to the trigger).
  container.read(syncSchedulerProvider).start();
}
