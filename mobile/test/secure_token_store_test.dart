// M8 task 4 M1 — the secure token store (§8.2, §8.4).
//
// Every assertion is against a real in-memory `SecureStorage`, so "the access token is never
// persisted" is checked by looking at what was stored rather than by trusting a call count.
import 'package:districore/data/api/tokens.dart';
import 'package:districore/data/identity/secure_token_store.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_secure_storage.dart';

const _access = 'access-token-1';
const _refresh = 'refresh-token-1';

/// The keystore entry names, restated here so the test fails if the implementation renames
/// them silently — a rename would orphan every already-installed device's credentials.
const _refreshKey = 'districore.refresh';
const _deviceKey = 'districore.device';

void main() {
  late FakeSecureStorage storage;

  setUp(() => storage = FakeSecureStorage());

  group('first run', () {
    test('access and refresh start null; a device id is minted', () async {
      final store = await SecureTokenStore.open(storage);

      expect(store.accessToken, isNull);
      expect(store.refreshToken, isNull, reason: 'nothing stored yet');
      expect(store.deviceId, isNotNull);
      expect(store.deviceId, isNotEmpty);
    });

    test('the minted device id is persisted through the seam', () async {
      final store = await SecureTokenStore.open(storage);
      expect(storage.entries[_deviceKey], store.deviceId);
    });

    test('the device id fits `04` T-26 device_id VARCHAR(64)', () async {
      final store = await SecureTokenStore.open(storage);
      expect(store.deviceId!.length, lessThanOrEqualTo(64));
      expect(store.deviceId, matches(RegExp(r'^[0-9a-f]+$')));
    });

    test('two independent installs do not share a device id', () async {
      final a = await SecureTokenStore.open(FakeSecureStorage());
      final b = await SecureTokenStore.open(FakeSecureStorage());
      expect(a.deviceId, isNot(b.deviceId), reason: 'Random.secure(), not a fixed seed');
    });
  });

  group('reconstruction', () {
    test('the same storage yields the same device id — generated once (§8.4)', () async {
      final first = await SecureTokenStore.open(storage);
      final second = await SecureTokenStore.open(storage);

      expect(second.deviceId, first.deviceId);
      expect(storage.writes, 1, reason: 'the second open must not mint a new identity');
    });

    test('a new store restores the refresh token', () async {
      final first = await SecureTokenStore.open(storage);
      await first.save(accessToken: _access, refreshToken: _refresh);

      final second = await SecureTokenStore.open(storage);
      expect(second.refreshToken, _refresh);
    });

    test('a new store does NOT restore the access token', () async {
      // §8.2: "Access token — memory. Re-derived from refresh on cold start."
      final first = await SecureTokenStore.open(storage);
      await first.save(accessToken: _access, refreshToken: _refresh);

      final second = await SecureTokenStore.open(storage);
      expect(second.accessToken, isNull);
    });
  });

  group('save', () {
    test('persists the refresh token and keeps the access token in memory', () async {
      final store = await SecureTokenStore.open(storage);
      await store.save(accessToken: _access, refreshToken: _refresh);

      expect(store.accessToken, _access);
      expect(store.refreshToken, _refresh);
      expect(storage.entries[_refreshKey], _refresh);
    });

    test('the access token NEVER reaches storage', () async {
      // The invariant this whole class exists for. Asserted over every stored value, so a
      // future extra write cannot smuggle it in under a different key.
      final store = await SecureTokenStore.open(storage);
      await store.save(accessToken: _access, refreshToken: _refresh);

      expect(storage.entries.values, isNot(contains(_access)));
      expect(storage.entries.keys, unorderedEquals([_deviceKey, _refreshKey]));
    });

    test('rotation replaces the previous refresh token', () async {
      final store = await SecureTokenStore.open(storage);
      await store.save(accessToken: _access, refreshToken: _refresh);
      await store.save(accessToken: 'access-2', refreshToken: 'refresh-2');

      expect(store.refreshToken, 'refresh-2');
      expect(storage.entries[_refreshKey], 'refresh-2');
      expect(storage.entries.values, isNot(contains(_refresh)),
          reason: 'the server rotates and blacklists; keeping the old one is a lockout');
    });

    test('a failed persist leaves the access token unchanged', () async {
      // Ordering, stated as behaviour: the access token becomes visible only after the
      // refresh token is stored. Advertising a session we could not persist produces a
      // device that works until expiry and then cannot recover.
      final store = await SecureTokenStore.open(storage);
      storage.failNextWrite = StateError('keystore unavailable');

      await expectLater(
        store.save(accessToken: _access, refreshToken: _refresh),
        throwsA(isA<StateError>()),
      );
      expect(store.accessToken, isNull);
      expect(store.refreshToken, isNull);
      expect(storage.entries.containsKey(_refreshKey), isFalse);
    });
  });

  group('clear', () {
    test('drops both tokens', () async {
      final store = await SecureTokenStore.open(storage);
      await store.save(accessToken: _access, refreshToken: _refresh);

      await store.clear();

      expect(store.accessToken, isNull);
      expect(store.refreshToken, isNull);
      expect(storage.entries.containsKey(_refreshKey), isFalse);
    });

    test('KEEPS the device id — sign-out is not revocation (§8.4, FR-IAM-009)', () async {
      final store = await SecureTokenStore.open(storage);
      final identity = store.deviceId;
      await store.save(accessToken: _access, refreshToken: _refresh);

      await store.clear();

      expect(store.deviceId, identity);
      expect(storage.entries[_deviceKey], identity,
          reason: 'a fresh id per sign-out makes one device present as several');
    });

    test('a store reopened after sign-out keeps the same device id', () async {
      final first = await SecureTokenStore.open(storage);
      final identity = first.deviceId;
      await first.clear();

      final second = await SecureTokenStore.open(storage);
      expect(second.deviceId, identity);
      expect(second.refreshToken, isNull);
    });
  });

  group('FR-IAM-015 — credentials never surface', () {
    test('toString reports presence, never values', () async {
      final store = await SecureTokenStore.open(storage);
      await store.save(accessToken: _access, refreshToken: _refresh);

      final text = store.toString();
      expect(text, isNot(contains(_access)));
      expect(text, isNot(contains(_refresh)));
      expect(text, contains('true'), reason: 'presence is still useful for diagnosis');
    });

    test('the device id is not treated as a credential and may be shown', () async {
      // It is attribution, not a secret: `05` §11.2 sends it in a request body.
      final store = await SecureTokenStore.open(storage);
      expect(store.deviceId, isNotNull);
    });

    test('the store satisfies the frozen TokenStore contract', () async {
      final TokenStore store = await SecureTokenStore.open(storage);
      expect(store.accessToken, isNull);
      expect(store.deviceId, isNotNull);
    });
  });
}
