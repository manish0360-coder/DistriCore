// P-7 / `05` C-12: the tab bar is *composed* from the roles array, never switched on a
// single "primary role". This is the smallest test that fails if anyone reintroduces one.
import 'package:districore/app/tabs.dart';
import 'package:districore/domain/identity/role.dart';
import 'package:districore/domain/identity/session.dart';
import 'package:flutter_test/flutter_test.dart';

Session _session(Set<Role> roles) =>
    Session(userId: 1, fullName: 'Test', roles: roles);

List<String> _visiblePaths(Set<Role> roles) => tabs
    .where((tab) => tab.visibleTo(_session(roles)))
    .map((tab) => tab.path)
    .toList();

void main() {
  test('a delivery-only user sees deliveries and status', () {
    expect(_visiblePaths({Role.delivery}), ['/deliveries', '/status']);
  });

  test('a salesman-only user sees customers and status', () {
    expect(_visiblePaths({Role.salesman}), ['/customers', '/status']);
  });

  test('a salesman who also delivers sees BOTH — the client normal case', () {
    // The bug this prevents is invisible until that person holds the phone: collapse
    // `roles` to one value and their delivery tab disappears.
    expect(_visiblePaths({Role.salesman, Role.delivery}),
        ['/deliveries', '/customers', '/status']);
  });

  test('status is visible to every signed-in user', () {
    for (final role in Role.values) {
      expect(_visiblePaths({role}), contains('/status'));
    }
  });

  test('no tab is reachable without a role that grants it', () {
    // An owner has no field tabs in M8; Companion Mode arrives at task 8.
    expect(_visiblePaths({Role.owner}), ['/status']);
  });
}
