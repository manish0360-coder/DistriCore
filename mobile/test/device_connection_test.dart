/// **The database key is read on the main isolate, before the executor exists.**
///
/// This test exists because 314 green tests did not catch a defect that hung the app on
/// every device. Every other test builds `AppDatabase` over `NativeDatabase.memory()` with
/// no `setup` and no key provider; **nothing called `openDeviceDatabase` at all**, so the
/// one function that only runs on a phone was the one function never executed.
///
/// **What went wrong.** `setup:` was an `async` closure that awaited
/// `DatabaseKeyProvider.key()` — a `MethodChannel` call into the platform keystore. But
/// `createInBackground` runs `setup` in a **spawned isolate**, which has no binary messenger
/// bound to the platform thread, so that await never completed. The first Drift query on a
/// device is `IdentityCache.save` during sign-in, which is why the symptom was a login
/// screen spinning forever *after* the server had already answered `200`.
///
/// **Why an isolate makes this testable at all.** Isolates do not share memory: a closure
/// sent to one operates on a **copy**. So if the key provider below observes its own call
/// count increase, the call must have happened on this isolate — the test's own object could
/// not have been reached otherwise. That single fact is the assertion.
///
/// Against the previous implementation this test fails for two independent reasons, and
/// either alone is enough: `setup` is not invoked during `openDeviceDatabase` (the executor
/// connects lazily, on first query), and even when it did run the increment would land in a
/// copy. Both leave the counter at zero.
library;

import 'dart:io';

import 'package:districore/data/db/connection.dart';
import 'package:districore/data/db/database_key.dart';
import 'package:drift/drift.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Counts its own invocations. **Deliberately not a mock**: the point is object identity
/// across an isolate boundary, and a mocking framework would obscure exactly that.
final class _RecordingKeyProvider implements DatabaseKeyProvider {
  int calls = 0;

  @override
  Future<String?> key() async {
    calls += 1;
    // `null` on purpose — this test is about *when and where* the key is read, not about
    // what it is. A value would drag SQLCipher into a test that is not about encryption.
    return null;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory temporary;

  setUp(() {
    temporary = Directory.systemTemp.createTempSync('districore-connection');
    // `openDeviceDatabase` asks path_provider for the documents directory. On a device that
    // is a platform channel; here it is answered with a real directory, so the function
    // under test runs unmodified rather than being restructured for testability.
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => temporary.path,
    );
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (temporary.existsSync()) temporary.deleteSync(recursive: true);
  });

  test('the key is read on the calling isolate, before the executor is built', () async {
    final keys = _RecordingKeyProvider();

    final executor = await openDeviceDatabase(keys);

    expect(
      keys.calls,
      1,
      reason: 'the key was not read on this isolate. Reading it inside '
          "`createInBackground`'s setup callback means reading it in a spawned isolate, "
          'where a MethodChannel to the keystore never completes — the app hangs on its '
          'first database query, which on a device is the sign-in that has just succeeded',
    );
    expect(executor, isA<QueryExecutor>());

    await executor.close();
  });

  test('the key is read exactly once per open, not once per query', () async {
    // Cheapness is not the point; a keystore read per statement would put a platform
    // channel on the hot path of every outbox append (P-2 — a user action must not wait
    // on anything it does not have to).
    final keys = _RecordingKeyProvider();

    final executor = await openDeviceDatabase(keys);
    await executor.close();

    expect(keys.calls, 1);
  });
}
