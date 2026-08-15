/// Where the SQLCipher key comes from.
///
/// The §5.6 ADR is Drift **with SQLCipher** — FR-SYN-016 and NFR-SEC-008 require the outbox
/// encrypted at rest. The key belongs in the platform keystore, and the keystore arrives at
/// **task 4**.
///
/// So task 3 defines the seam and nothing behind it. That is deliberate: a placeholder key
/// compiled into the binary would satisfy the type system and violate P-9 — *"the binary
/// holds no secret"* — which is worse than an obvious gap.
abstract interface class DatabaseKeyProvider {
  /// The SQLCipher passphrase, or `null` for an unencrypted database.
  ///
  /// `null` is legitimate only where there is nothing to protect: the in-memory databases
  /// the unit tests build. **The application must supply a key** (task 4).
  Future<String?> key();
}
