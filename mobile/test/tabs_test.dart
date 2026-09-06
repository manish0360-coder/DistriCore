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

  test('an owner sees Companion and status, and no field tab', () {
    // **Task 8 arrived.** This expectation read `['/status']` and carried the note *"An owner
    // has no field tabs in M8; Companion Mode arrives at task 8"* — so the test predicted its
    // own change and this is that change, not a weakening. What it asserts is unchanged in
    // substance: an owner still gets no `/deliveries` and no `/customers`, because those are
    // the field roles' screens and Companion Mode reads rather than works a round.
    expect(_visiblePaths({Role.owner}), ['/companion', '/status']);
  });

  test('no tab is reachable without a role that grants it', () {
    // **The assertion this name always described, and never made.** The previous version
    // passed `{Role.owner}` — a role — so the genuine no-role case went untested from M8 task
    // 1 until Companion Mode made the name's claim false as well as unproven. Split rather
    // than deleted: the owner expectation above is a different property from this one.
    //
    // Only the unrestricted tabs may appear. `/status` is deliberately among them — `TabSpec`
    // reads *"empty means every signed-in user"*, and a `Session` exists only once signed in.
    final unrestricted = [
      for (final tab in tabs)
        if (tab.roles.isEmpty) tab.path,
    ];
    expect(unrestricted, isNotEmpty, reason: 'no unrestricted tab — this would be vacuous');

    expect(_visiblePaths(const <Role>{}), unrestricted);
  });

  test('Companion is drawn for the owner alone', () {
    // P-9: presentation only — every figure behind it is authorised again in CORE. What this
    // holds is that the app does not *offer* the owner's view to a field role.
    for (final role in Role.values) {
      expect(
        _visiblePaths({role}).contains('/companion'),
        role == Role.owner,
        reason: '$role',
      );
    }
  });
}
