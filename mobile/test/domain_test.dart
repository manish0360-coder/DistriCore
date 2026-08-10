// Pure-domain tests: no widget, no binding, no emulator, no network. That is the property
// `domain/ imports nothing` buys, and this file is what proves it was bought.
//
// `flutter_test` is imported rather than `package:test` only because it is what a Flutter
// package resolves without a version conflict. Nothing here calls `testWidgets` or
// `ensureInitialized`, so no binding is started — the claim is about what runs, and it
// holds.
import 'package:districore/core/clock.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/core/result.dart';
import 'package:districore/domain/identity/role.dart';
import 'package:districore/domain/identity/session.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Role', () {
    test('parses the wire codes `05` sends', () {
      expect(Role.fromCodes(['OWNER', 'DELIVERY']), {Role.owner, Role.delivery});
    });

    test('drops an unknown code instead of throwing', () {
      // A server that adds a role must not brick an app that has not been updated.
      expect(Role.fromCodes(['SALESMAN', 'WAREHOUSE']), {Role.salesman});
    });
  });

  group('Session', () {
    test('a dual-role user matches on either role (C-12, P-7)', () {
      // The client's normal case: a salesman who also delivers. Collapsing `roles` to a
      // single "primary role" is how the delivery tab disappears for exactly this person.
      const session = Session(
        userId: 1,
        fullName: 'Ravi',
        roles: {Role.salesman, Role.delivery},
      );
      expect(session.hasAny({Role.delivery}), isTrue);
      expect(session.hasAny({Role.salesman}), isTrue);
      expect(session.hasAny({Role.owner}), isFalse);
    });
  });

  group('Result', () {
    test('fold is the only way in, on both branches', () {
      const Result<int> ok = Ok(3);
      const Result<int> err = Err(Offline());
      expect(ok.fold((v) => v, (_) => -1), 3);
      expect(err.fold((v) => v, (_) => -1), -1);
      expect(err.isOk, isFalse);
    });
  });

  group('Clock', () {
    test('FixedClock lets a test pin the instant (P-4)', () {
      // Not `const`: `instant` is a runtime local, so the constructor call cannot be a
      // constant expression even though `FixedClock` declares one.
      final instant = DateTime.utc(2026, 8, 10, 6, 30);
      expect(FixedClock(instant).nowUtc(), instant);
    });
  });
}
