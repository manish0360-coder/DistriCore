import 'dart:math';

/// An RFC 4122 version 4 UUID, from a cryptographic source.
///
/// **Hand-rolled rather than a package**, for the reason M1 gives for `device_id`: this is
/// twenty lines and one dependency less in a binary that `02A` §9.3 assumes is fully
/// decompiled. `Random.secure()` rather than `Random()` because `client_uuid` is the
/// idempotency key on financial rows (AD-09) — a value an attacker could predict is a value
/// they could collide.
String newClientUuid() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));

  // Version 4 in the high nibble of byte 6, variant 10xx in the top bits of byte 8. The
  // server stores this in a `UUIDField`, which validates the form.
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  String hex(int start, int end) =>
      bytes.sublist(start, end).map((b) => b.toRadixString(16).padLeft(2, '0')).join();

  return '${hex(0, 4)}-${hex(4, 6)}-${hex(6, 8)}-${hex(8, 10)}-${hex(10, 16)}';
}
