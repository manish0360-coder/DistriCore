import 'package:districore/data/identity/secure_storage.dart';

/// An in-memory [SecureStorage].
///
/// **A real map, not a mock.** The invariants under test are about what ends up *in
/// storage* — that the access token never does, that the device id survives a sign-out — so
/// the test has to be able to look. A mock could only confirm which methods were called,
/// which is the question nobody is asking.
final class FakeSecureStorage implements SecureStorage {
  FakeSecureStorage([Map<String, String>? initial])
      : entries = {...?initial};

  /// Inspectable on purpose: the security assertions read this directly.
  final Map<String, String> entries;

  int writes = 0;
  int deletes = 0;

  /// Set to make the next [write] throw, so the failed-rotation ordering can be asserted.
  Object? failNextWrite;

  @override
  Future<String?> read(String key) async => entries[key];

  @override
  Future<void> write(String key, String value) async {
    final failure = failNextWrite;
    if (failure != null) {
      failNextWrite = null;
      throw failure;
    }
    writes += 1;
    entries[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    deletes += 1;
    entries.remove(key);
  }
}
