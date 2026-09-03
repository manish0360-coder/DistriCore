/// Host-side driver for `flutter drive` (M8 → M9 device gate).
///
/// The standard three-line driver. It exists because `flutter drive` requires one; the
/// device gate's phases are orchestrated by the `mobile-device-*` targets in the Makefile,
/// not from here.
///
/// **No `timeout:` argument, and that is a finding rather than an omission.** A bounded
/// driver wait was added on 2026-09-01 on the theory that kill-gate phase 1 — which SIGKILLs
/// its own process before the binding can report — would leave the driver awaiting a result
/// that could never arrive, and so sit out the package default of about twenty minutes. The
/// first real run of `make mobile-device-kill` refuted it: the moment the process dies the
/// VM service connection drops and `requestData` fails immediately with
///
///     DriverError: Failed to fulfill RequestData due to remote error
///     Original error: ext.flutter.driver: (112) Service has disappeared
///
/// The Makefile's inverted check reads that as *"phase 1 terminated abnormally, as
/// designed"* and proceeds to phase 2, which passed. The timeout never engaged and was
/// reverted rather than kept as an unexercised guard against a failure mode nobody has seen.
library;

import 'package:integration_test/integration_test_driver.dart';

Future<void> main() => integrationDriver();
