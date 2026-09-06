// M8 task 8 — Owner Companion Mode, against a real `ApiClient` over a scripted adapter.
//
// **Nothing below the HTTP boundary is faked**, for the same reason `pull_slice_test` does
// not fake it: the properties under test are decode rules and request shapes, and a fake
// repository would agree with whatever the code did. What is asserted is the JSON that
// arrives and the query that reaches the wire.
//
// The four screens are §3.4's, and each has its own group. The last group is the one that
// would be easy to leave out and hardest to add later: **that nothing here can write.**
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:districore/app/tabs.dart';
import 'package:districore/core/failure.dart';
import 'package:districore/core/money.dart';
import 'package:districore/core/result.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:districore/data/companion/api_companion_repository.dart';
import 'package:districore/data/companion/companion_dto.dart';
import 'package:districore/domain/companion/companion.dart';
import 'package:districore/domain/companion/companion_repository.dart';
import 'package:districore/domain/identity/role.dart';
import 'package:districore/domain/identity/session.dart';
import 'package:districore/features/companion/companion_controller.dart';
import 'package:districore/features/companion/companion_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';

const _baseUrl = 'https://api.test/api/v1';

/// `05` §9.11.1's own example, verbatim — including `awaiting_dispatch` as a JSON **integer**
/// while the other three are strings. The mixed encoding is the point of the fixture.
Map<String, dynamic> get _dashboardBody => {
      'as_of': '2026-08-10',
      'metrics': [
        {
          'key': 'sales_today',
          'label': 'Sales today',
          'value': '11800.00',
          'caption': 'Taxable value, net of credit notes',
          'is_live': true,
          'is_money': true,
        },
        {
          'key': 'awaiting_dispatch',
          'label': 'Orders awaiting dispatch',
          'value': 3,
          'caption': 'Confirmed, not yet gone',
          'is_live': false,
          'is_money': false,
        },
      ],
    };

Map<String, dynamic> _list(List<Map<String, dynamic>> results) =>
    {'count': results.length, 'next': null, 'previous': null, 'results': results};

/// A receivables report as `_as_json` renders it **since TD-36**: money as a canonical
/// string, `oldest_days` as an integer, and `null` in the total where nothing was measured.
Map<String, dynamic> _receivablesBody({int rows = 3}) => {
      'key': 'receivables',
      'title': 'Receivables ageing',
      'columns': [
        {'key': 'code', 'label': 'Code', 'numeric': false, 'kind': 'TEXT'},
        {'key': 'outstanding', 'label': 'Outstanding', 'numeric': true, 'kind': 'MONEY'},
        {'key': 'oldest_days', 'label': 'Oldest (days)', 'numeric': true, 'kind': 'COUNT'},
      ],
      'rows': [
        for (var i = 0; i < rows; i++)
          {
            'code': 'C-${i.toString().padLeft(4, '0')}',
            'label': 'Shop $i',
            'outstanding': '${1000 - i}.00',
            'on_account': '0.00',
            'balance': '${1000 - i}.00',
            'oldest_days': 90 - i,
            'bucket': '61-90',
            'oldest_document': 'INV-$i',
          },
      ],
      'total': {
        'code': '',
        'label': 'Total',
        'outstanding': '9999.00',
        'on_account': '0.00',
        'balance': '9999.00',
        'oldest_days': null,
        'bucket': '',
        'oldest_document': '',
      },
    };

typedef Env = ({
  ApiCompanionRepository repository,
  FakeAdapter adapter,
  List<Map<String, dynamic>> queries,
});

Env _wire(FutureOr<ResponseBody> Function(RequestOptions options, int call) script) {
  final queries = <Map<String, dynamic>>[];
  final adapter = FakeAdapter((options, call) {
    // `RecordedRequest` does not carry query parameters, so what actually reached the wire is
    // captured here rather than inferred — the same reason `pull_slice_test` does it.
    queries.add(Map<String, dynamic>.of(options.queryParameters));
    return script(options, call);
  });

  final api = ApiClient(
    baseUrl: _baseUrl,
    tokens: FakeTokens(),
    dio: Dio()..httpClientAdapter = adapter,
    refreshDio: Dio()..httpClientAdapter = adapter,
  );
  return (repository: ApiCompanionRepository(api), adapter: adapter, queries: queries);
}

/// A container with the port bound to [repository] and nothing else wired.
ProviderContainer _container(CompanionRepositoryStub repository) {
  final container = ProviderContainer(
    overrides: [companionPortProvider.overrideWithValue(repository)],
  );
  addTearDown(container.dispose);
  return container;
}

void main() {
  // -------------------------------------------------------------- 1. Today
  group('Today — the four D-4 numbers (05 §9.11.1)', () {
    test('money arrives as a string and a count arrives as an integer', () async {
      final env = _wire((_, __) async => jsonBody(200, _dashboardBody));

      final result = await env.repository.dashboard();
      final board = result.fold((value) => value, (f) => throw StateError('$f'));

      final sales = board.metrics.firstWhere((m) => m.key == 'sales_today');
      final orders = board.metrics.firstWhere((m) => m.key == 'awaiting_dispatch');

      // AD-02, at the scale it arrived with — `Money` carries the scale so `"11800.00"`
      // does not normalise to `"11800"`.
      expect(sales.value, '11800.00');
      expect(sales.isMoney, isTrue);
      expect(sales.isLive, isTrue, reason: '05 §9.11.1 marks sales_today not reproducible');

      // §9.11.1 departure 3: a count is not money and must not be stringified into "3.00".
      expect(orders.value, '3');
      expect(orders.isMoney, isFalse);
      expect(orders.isLive, isFalse);
    });

    test('the encoding is chosen by is_money, not by the metric key', () {
      // The property that stops the decoder rotting when a fifth metric appears: a key this
      // app has never seen, declared as money, is parsed as money.
      final board = CompanionDto.dashboardFromJson({
        'as_of': '2026-08-10',
        'metrics': [
          {'key': 'collected_tomorrow', 'value': '42.50', 'is_money': true, 'is_live': false},
        ],
      });

      expect(board.metrics.single.value, '42.50');
    });

    test('a money metric sent as a JSON number is refused, not rounded', () async {
      // **P-3 / TD-36's client half.** The server was fixed at 5e22614; this is the guard
      // that made the defect visible rather than silent, and it stays either way.
      final env = _wire(
        (_, __) async => jsonBody(200, {
          'as_of': '2026-08-10',
          'metrics': [
            {'key': 'sales_today', 'value': 11800.0, 'is_money': true, 'is_live': true},
          ],
        }),
      );

      final result = await env.repository.dashboard();

      expect(result.isOk, isFalse);
      expect(
        result.fold((_) => null, (f) => f),
        isA<MalformedResponse>(),
        reason: 'a double has already lost the paisa; accepting it would store a known-wrong '
            'figure rather than refuse an unreadable one',
      );
    });

    test('a non-money metric that is not an integer is refused', () {
      expect(
        () => CompanionDto.dashboardFromJson({
          'metrics': [
            {'key': 'awaiting_dispatch', 'value': '3', 'is_money': false},
          ],
        }),
        throwsA(isA<CompanionPayloadException>()),
      );
    });

    test('a missing metrics array is a broken contract, not an empty dashboard', () {
      expect(
        () => CompanionDto.dashboardFromJson({'as_of': '2026-08-10'}),
        throwsA(isA<CompanionPayloadException>()),
        reason: 'rendering zero numbers would read as "nothing happened today"',
      );
    });
  });

  // --------------------------------------------------- 2. Pending deliveries
  group('Pending deliveries (05 §9.4, §9.4.1)', () {
    test('asks for PENDING and reads the salesman name', () async {
      final env = _wire(
        (_, __) async => jsonBody(
          200,
          _list([
            {
              'id': 41,
              'order_number': 'SO-41',
              'customer_name': 'Sharma Stores',
              'assigned_user_id': 7,
              'assigned_user_name': 'Ravi Kumar',
              'status': 'PENDING',
            },
          ]),
        ),
      );

      final result = await env.repository.pendingDeliveries();
      final rows = result.fold((value) => value, (f) => throw StateError('$f'));

      expect(env.queries.single['status'], 'PENDING');
      expect(rows.single.assignedUserName, 'Ravi Kumar');
      expect(rows.single.orderNumber, 'SO-41');
    });

    test('an unassigned delivery is a state, not a decode failure', () {
      final rows = CompanionDto.deliveriesFromJson(
        _list([
          {'id': 42, 'order_number': 'SO-42', 'customer_name': 'X', 'status': 'PENDING'},
        ]),
      );

      expect(rows.single.assignedUserName, isEmpty);
    });

    test('a row with no id is refused — the list is keyed by it', () {
      expect(
        () => CompanionDto.deliveriesFromJson(_list([
          {'order_number': 'SO-43'},
        ])),
        throwsA(isA<CompanionPayloadException>()),
      );
    });
  });

  // ------------------------------------------------------------ 3. Receivables
  group('Receivables summary (05 §9.11)', () {
    test('takes the first ten of a server-ordered list and does not reorder it', () async {
      final env = _wire((_, __) async => jsonBody(200, _receivablesBody(rows: 25)));

      final result = await env.repository.receivables();
      final summary = result.fold((value) => value, (f) => throw StateError('$f'));

      expect(summary.worst, hasLength(kWorstCustomers));
      // **The server's order, untouched.** §2.3 forbids the device deriving a credit
      // decision; re-sorting here would be a second implementation of an ordering the
      // report already owns (D-3). The fixture descends, so a sort would be invisible —
      // which is why the codes are asserted in the order they arrived.
      expect(
        [for (final row in summary.worst) row.code],
        [for (var i = 0; i < kWorstCustomers; i++) 'C-${i.toString().padLeft(4, '0')}'],
      );
    });

    test('the total is the report total, not a sum of the visible rows', () async {
      final env = _wire((_, __) async => jsonBody(200, _receivablesBody(rows: 25)));

      final result = await env.repository.receivables();
      final summary = result.fold((value) => value, (f) => throw StateError('$f'));

      expect(summary.totalOutstanding.toJson(), '9999.00');
      final visible = summary.worst.fold(Money.zero, (sum, row) => sum + row.outstanding);
      expect(
        summary.totalOutstanding.toJson(),
        isNot(visible.toJson()),
        reason: 'the fixture is not exercising the distinction the label depends on',
      );
    });

    test('sends no period parameter', () async {
      final env = _wire((_, __) async => jsonBody(200, _receivablesBody()));

      await env.repository.receivables();

      // §3.4's boundary: Companion Mode does not run reports over arbitrary periods.
      expect(env.queries.single.containsKey('date_from'), isFalse);
      expect(env.queries.single.containsKey('date_to'), isFalse);
    });

    test('a null oldest_days stays null and is never read as zero', () {
      // TD-36: a blank COUNT is `null` on the wire. Zero would claim "nothing is aged".
      final summary = CompanionDto.receivablesFromJson({
        'rows': [
          {'code': 'C-1', 'label': 'Shop', 'outstanding': '10.00', 'oldest_days': null},
        ],
        'total': {'outstanding': '10.00'},
      });

      expect(summary.worst.single.oldestDays, isNull);
    });

    test('an empty report is a valid answer with a zero total', () {
      final summary = CompanionDto.receivablesFromJson({'rows': <dynamic>[], 'total': null});

      expect(summary.worst, isEmpty);
      expect(summary.totalOutstanding.toJson(), '0');
    });
  });

  // -------------------------------------------------------- 4. Needs attention
  group('Needs attention (02A §13, ruled 2026-09-06)', () {
    test('reads confirmed orders and failed deliveries, and nothing else', () async {
      final env = _wire((options, call) async {
        if (options.path.contains('/orders')) {
          return jsonBody(
            200,
            _list([
              {'order_number': 'SO-9', 'customer_name': 'Shop A', 'total_amount': '500.00'},
            ]),
          );
        }
        return jsonBody(
          200,
          _list([
            {
              'id': 3,
              'order_number': 'SO-3',
              'customer_name': 'Shop B',
              'failure_reason': 'Shop closed',
            },
          ]),
        );
      });

      final result = await env.repository.needsAttention();
      final board = result.fold((value) => value, (f) => throw StateError('$f'));

      expect(env.queries[0]['status'], 'CONFIRMED');
      expect(env.queries[1]['status'], 'FAILED');
      expect(env.queries, hasLength(2), reason: 'no third source — overdue is excluded in V1');

      expect(board.items.map((i) => i.kind), [
        AttentionKind.undispatchedOrder,
        AttentionKind.failedDelivery,
      ]);
      expect(board.items.last.detail, 'Shop closed');
    });

    test('either read failing fails the board rather than shortening it', () async {
      // A short list and a list that could not be built look identical on screen, and the
      // second one silently says "nothing needs you" — the one wrong answer here.
      final env = _wire((options, call) async {
        if (options.path.contains('/orders')) return jsonBody(200, _list([]));
        return jsonBody(503, {
          'code': 'SERVICE_UNAVAILABLE',
          'status': 503,
          'title': 'x',
          'detail': 'x',
          'errors': <dynamic>[],
        });
      });

      final result = await env.repository.needsAttention();

      expect(result.isOk, isFalse);
    });

    test('an unparseable order value loses the label, never the row', () {
      final items = CompanionDto.undispatchedFromJson(
        _list([
          {'order_number': 'SO-9', 'customer_name': 'Shop A', 'total_amount': 500.0},
        ]),
      );

      expect(items.single.reference, 'SO-9');
      expect(items.single.detail, isEmpty);
    });
  });

  // -------------------------------------------------------- controller states
  group('CompanionController — loading, success, failure', () {
    test('a section moves loading -> loaded and keeps the data', () async {
      final stub = CompanionRepositoryStub();
      final container = _container(stub);
      final controller = container.read(companionProvider.notifier);

      final pending = controller.load(CompanionSection.today);
      expect(container.read(companionProvider).isLoading(CompanionSection.today), isTrue);

      stub.dashboardResult = const Ok(Dashboard(asOf: null, metrics: []));
      await pending;

      final state = container.read(companionProvider);
      expect(state.isLoading(CompanionSection.today), isFalse);
      expect(state.dashboard, isNotNull);
      expect(state.message, isNull);
    });

    test('a failure sets prose and leaves the previous data in place', () async {
      final stub = CompanionRepositoryStub()
        ..dashboardResult = const Ok(Dashboard(asOf: null, metrics: []));
      final container = _container(stub);
      final controller = container.read(companionProvider.notifier);
      await controller.load(CompanionSection.today);

      stub.dashboardResult = const Err<Dashboard>(Offline());
      await controller.load(CompanionSection.today);

      final state = container.read(companionProvider);
      expect(state.message, contains('No connection'));
      expect(
        state.dashboard,
        isNotNull,
        reason: 'blanking a figure that was true a minute ago is worse than labelling it',
      );
    });

    test('show() loads once and does not refetch a loaded section', () async {
      final stub = CompanionRepositoryStub()
        ..dashboardResult = const Ok(Dashboard(asOf: null, metrics: []));
      final container = _container(stub);
      final controller = container.read(companionProvider.notifier);

      await controller.show(CompanionSection.today);
      await controller.show(CompanionSection.today);

      expect(stub.dashboardCalls, 1, reason: 'four round trips on 2G is the cost being saved');
    });

    test('refresh reloads the section on screen', () async {
      final stub = CompanionRepositoryStub()
        ..dashboardResult = const Ok(Dashboard(asOf: null, metrics: []));
      final container = _container(stub);
      final controller = container.read(companionProvider.notifier);

      await controller.show(CompanionSection.today);
      await controller.refresh();

      expect(stub.dashboardCalls, 2);
    });

    test('a concurrent load of the same section is dropped, not queued', () async {
      final stub = CompanionRepositoryStub();
      final container = _container(stub);
      final controller = container.read(companionProvider.notifier);

      final first = controller.load(CompanionSection.today);
      final second = controller.load(CompanionSection.today);
      stub.dashboardResult = const Ok(Dashboard(asOf: null, metrics: []));
      await Future.wait([first, second]);

      expect(stub.dashboardCalls, 1);
    });
  });

  // ------------------------------------------------------------- role gating
  group('The Companion tab is the owner only', () {
    Session session(Set<Role> roles) => Session(userId: 1, fullName: 'X', roles: roles);
    TabSpec companion() => tabs.firstWhere((tab) => tab.path == '/companion');

    test('an owner sees it', () {
      expect(companion().visibleTo(session({Role.owner})), isTrue);
    });

    test('a salesman, a driver and a retailer do not', () {
      for (final role in [Role.salesman, Role.delivery, Role.retailer]) {
        expect(companion().visibleTo(session({role})), isFalse, reason: '$role');
      }
    });

    test('a user who is both owner and salesman sees both tabs', () {
      // `05` C-12 / P-7: roles are a set and are never collapsed to a primary one.
      final both = session({Role.owner, Role.salesman});
      final visible = [for (final tab in tabs) if (tab.visibleTo(both)) tab.path];

      expect(visible, containsAll(<String>['/companion', '/customers']));
    });

    test('it is first, so an owner lands on it', () {
      // `router._landingFor` takes the first visible tab. An owner opening the app to check
      // the day should not arrive on a delivery list they will never work.
      expect(tabs.first.path, '/companion');
    });
  });

  // --------------------------------------------------------- the boundary itself
  group('§3.4 — Companion Mode writes nothing', () {
    test('every request it makes is a GET', () async {
      final env = _wire((options, call) async {
        if (options.path.contains('dashboard')) return jsonBody(200, _dashboardBody);
        if (options.path.contains('receivables')) return jsonBody(200, _receivablesBody());
        return jsonBody(200, _list([]));
      });

      await env.repository.dashboard();
      await env.repository.pendingDeliveries();
      await env.repository.receivables();
      await env.repository.needsAttention();

      expect(env.adapter.requests, hasLength(5));
      expect(
        {for (final request in env.adapter.requests) request.method},
        {'GET'},
        reason: '§3.4: Companion Mode reads. A write here would be admin logic wearing a '
            'Companion label — and `02A` §9.3 means hiding the button would not be a control',
      );
    });
  });
}

/// A hand-written stub, like `FakeAdapter`: the controller's collaborators are four futures,
/// and a mock package would be a dependency for less than this file already spends.
final class CompanionRepositoryStub implements CompanionRepository {
  Result<Dashboard>? dashboardResult;
  int dashboardCalls = 0;

  @override
  Future<Result<Dashboard>> dashboard() async {
    dashboardCalls++;
    // Yield, so a test can observe the loading state before this completes.
    await Future<void>.delayed(Duration.zero);
    return dashboardResult ?? const Ok(Dashboard(asOf: null, metrics: []));
  }

  @override
  Future<Result<List<CompanionDelivery>>> pendingDeliveries() async => const Ok([]);

  @override
  Future<Result<ReceivablesSummary>> receivables() async =>
      Ok(ReceivablesSummary(totalOutstanding: Money.zero, worst: const []));

  @override
  Future<Result<AttentionBoard>> needsAttention() async => const Ok(AttentionBoard());
}
