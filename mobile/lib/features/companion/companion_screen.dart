import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/as_of.dart';
import '../../domain/companion/companion.dart';
import 'companion_controller.dart';

/// **Owner Companion Mode** (M8 §10 task 8, §3.4 — ruled 2026-08-09).
///
/// > *"A distributor's owner is not at a desk — they are in the market, on a scooter, at a
/// > supplier. Companion Mode answers "is anything wrong right now?" without becoming a
/// > second admin UI."*
///
/// **Four read-only sections and no action anywhere.** §3.4's boundary table is the spec:
/// read, show today, drill from a number to the list behind it, and **link out to the web
/// admin for action** — never approve, cancel, adjust, price or invoice. There is deliberately
/// no button on this screen that changes anything, and `CompanionRepository` offers nothing
/// one could be wired to. `02A` §9.3 is why that is not the control: CORE refuses the write.
///
/// **Online-only** (ruled 2026-09-06): no cache, so nothing here is stale in the P-8 sense.
/// `is_live` still labels the two figures `05` §9.11.1 marks as describing *today* and
/// therefore not reproducible.
class CompanionScreen extends ConsumerStatefulWidget {
  const CompanionScreen({super.key});

  @override
  ConsumerState<CompanionScreen> createState() => _CompanionScreenState();
}

class _CompanionScreenState extends ConsumerState<CompanionScreen> {
  @override
  void initState() {
    super.initState();
    // After the first frame, like every other screen: `ref.read` during `initState` runs
    // before the widget is mounted into the container's lifecycle.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(ref.read(companionProvider.notifier).show(CompanionSection.today));
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(companionProvider);
    final controller = ref.read(companionProvider.notifier);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Companion')),
      body: Column(
        children: [
          _SectionBar(
            selected: state.section,
            onSelected: (section) => unawaited(controller.show(section)),
          ),
          if (state.message case final message?)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Text(
                message,
                key: const Key('companion.message'),
                style: TextStyle(color: theme.colorScheme.error),
              ),
            ),
          if (state.isLoading(state.section))
            const Padding(
              padding: EdgeInsets.all(16),
              child: CircularProgressIndicator(key: Key('companion.loading')),
            ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: controller.refresh,
              child: switch (state.section) {
                CompanionSection.today => _TodayView(dashboard: state.dashboard),
                CompanionSection.pending => _PendingView(deliveries: state.pending),
                CompanionSection.receivables =>
                  _ReceivablesView(summary: state.receivables),
                CompanionSection.attention => _AttentionView(board: state.attention),
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// The four sections, as a row of filter chips.
///
/// **Not a second navigation architecture.** `RoleShell` owns the app's tab bar and this is
/// one destination inside it; a nested `ShellRoute` would put two routers in the tree for
/// four views that share one state object.
class _SectionBar extends StatelessWidget {
  const _SectionBar({required this.selected, required this.onSelected});

  final CompanionSection selected;
  final void Function(CompanionSection) onSelected;

  static const _labels = {
    CompanionSection.today: 'Today',
    CompanionSection.pending: 'Deliveries',
    CompanionSection.receivables: 'Receivables',
    CompanionSection.attention: 'Needs attention',
  };

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: [
            for (final entry in _labels.entries)
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: ChoiceChip(
                  key: Key('companion.section.${entry.key.name}'),
                  label: Text(entry.value),
                  selected: selected == entry.key,
                  onSelected: (_) => onSelected(entry.key),
                ),
              ),
          ],
        ),
      );
}

// ------------------------------------------------------------------------- 1. Today
class _TodayView extends StatelessWidget {
  const _TodayView({required this.dashboard});

  final Dashboard? dashboard;

  @override
  Widget build(BuildContext context) {
    final board = dashboard;
    if (board == null) return const _Placeholder(key: Key('companion.today.empty'));

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(12),
      children: [
        for (final metric in board.metrics) _MetricCard(metric: metric),
        if (board.asOf case final asOf?)
          Padding(
            padding: const EdgeInsets.all(12),
            child: Text(
              // The **server's** date (P-4: the device clock never labels a server figure).
              'As at ${asOfLabel(asOf).split(' ').first}',
              key: const Key('companion.today.asOf'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
      ],
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.metric});

  final DashboardMetric metric;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      key: Key('companion.metric.${metric.key}'),
      child: ListTile(
        title: Text(metric.label),
        subtitle: Text(metric.caption),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              metric.isMoney ? '₹${metric.value}' : metric.value,
              key: Key('companion.metric.${metric.key}.value'),
              style: theme.textTheme.titleLarge,
            ),
            // `05` §9.11.1: two of the four describe *today* and are **not reproducible**.
            // The label is the whole reason `is_live` crosses the wire — a figure presented
            // without it acquires an authority M7 §8.2 deliberately withholds.
            if (metric.isLive)
              Text(
                'live',
                key: Key('companion.metric.${metric.key}.live'),
                style: theme.textTheme.labelSmall,
              ),
          ],
        ),
      ),
    );
  }
}

// -------------------------------------------------------------- 2. Pending deliveries
class _PendingView extends StatelessWidget {
  const _PendingView({required this.deliveries});

  final List<CompanionDelivery> deliveries;

  @override
  Widget build(BuildContext context) {
    if (deliveries.isEmpty) {
      return const _Empty(
        key: Key('companion.pending.empty'),
        text: 'Nothing waiting to go out.',
      );
    }

    return ListView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      itemCount: deliveries.length,
      itemBuilder: (context, index) {
        final delivery = deliveries[index];
        return Card(
          key: Key('companion.pending.${delivery.id}'),
          margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: ListTile(
            title: Text(delivery.customerName),
            // `05` §9.4.1 — the name, not the id. The whole reason that field was added.
            subtitle: Text(
              delivery.assignedUserName.isEmpty
                  ? '${delivery.orderNumber} · Unassigned'
                  : '${delivery.orderNumber} · ${delivery.assignedUserName}',
            ),
            // **No trailing action.** The driver's screen completes a delivery; this one
            // watches it. §3.4: link out to the web admin for action.
          ),
        );
      },
    );
  }
}

// -------------------------------------------------------------------- 3. Receivables
class _ReceivablesView extends StatelessWidget {
  const _ReceivablesView({required this.summary});

  final ReceivablesSummary? summary;

  @override
  Widget build(BuildContext context) {
    final value = summary;
    if (value == null) return const _Placeholder(key: Key('companion.receivables.empty'));
    final theme = Theme.of(context);

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(12),
      children: [
        Card(
          child: ListTile(
            title: const Text('Total outstanding'),
            // The report's own total row, not a sum of the ten rows below it.
            trailing: Text(
              '₹${value.totalOutstanding.toJson()}',
              key: const Key('companion.receivables.total'),
              style: theme.textTheme.titleLarge,
            ),
          ),
        ),
        const Padding(
          padding: EdgeInsets.fromLTRB(4, 16, 4, 8),
          child: Text('Worst $kWorstCustomers'),
        ),
        if (value.worst.isEmpty)
          const _Empty(
            key: Key('companion.receivables.none'),
            text: 'Nothing outstanding.',
          ),
        for (final row in value.worst)
          Card(
            key: Key('companion.receivable.${row.code}'),
            child: ListTile(
              title: Text(row.customerName),
              subtitle: Text(
                // **Age, not overdue.** No overdue rule exists in the corpus and V1 does not
                // invent one; the bucket and the day count are what the server sends.
                row.oldestDays == null
                    ? row.bucket
                    : '${row.bucket} · oldest ${row.oldestDays} days',
              ),
              trailing: Text('₹${row.outstanding.toJson()}'),
            ),
          ),
      ],
    );
  }
}

// ----------------------------------------------------------------- 4. Needs attention
class _AttentionView extends StatelessWidget {
  const _AttentionView({required this.board});

  final AttentionBoard? board;

  static const _headings = {
    AttentionKind.undispatchedOrder: 'Confirmed, not dispatched',
    AttentionKind.failedDelivery: 'Failed deliveries',
  };

  @override
  Widget build(BuildContext context) {
    final value = board;
    if (value == null) return const _Placeholder(key: Key('companion.attention.empty'));
    if (value.isEmpty) {
      return const _Empty(
        key: Key('companion.attention.none'),
        text: 'Nothing needs you right now.',
      );
    }

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(12),
      children: [
        for (final kind in AttentionKind.values)
          ...() {
            final items = value.items.where((item) => item.kind == kind).toList();
            if (items.isEmpty) return <Widget>[];
            return <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 12, 4, 8),
                child: Text(
                  '${_headings[kind]} (${items.length})',
                  key: Key('companion.attention.${kind.name}'),
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              for (final item in items)
                Card(
                  child: ListTile(
                    title: Text(item.customerName),
                    subtitle: Text(
                      item.detail.isEmpty
                          ? item.reference
                          : '${item.reference} · ${item.detail}',
                    ),
                  ),
                ),
            ];
          }(),
      ],
    );
  }
}

// ----------------------------------------------------------------------- shared bits
/// Before the first load. **Not the same as "nothing to show"** — a screen that has not
/// loaded must not claim a quiet morning.
class _Placeholder extends StatelessWidget {
  const _Placeholder({super.key});

  @override
  Widget build(BuildContext context) => ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: const [SizedBox(height: 240)],
      );
}

class _Empty extends StatelessWidget {
  const _Empty({required this.text, super.key});

  final String text;

  @override
  Widget build(BuildContext context) => ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [Padding(padding: const EdgeInsets.all(48), child: Center(child: Text(text)))],
      );
}
