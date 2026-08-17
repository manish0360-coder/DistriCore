import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/customer/customer.dart';
import '../../domain/visit/visit_outcome.dart';
import 'customer_controller.dart';

/// The round (M8 §10 task 7, `05` §9.2).
///
/// **Nothing here touches the network to save.** Logging a call writes a `VISIT_CREATE` row
/// to the outbox and returns; M9 delivers it whenever signal comes back (P-2). The salesman
/// gets the same behaviour inside a shop with thick walls as outside it, which is the whole
/// reason the outbox exists.
class CustomersScreen extends ConsumerStatefulWidget {
  const CustomersScreen({super.key});

  @override
  ConsumerState<CustomersScreen> createState() => _CustomersScreenState();
}

class _CustomersScreenState extends ConsumerState<CustomersScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(ref.read(customerListProvider.notifier).load());
    });
  }

  Future<void> _log(Customer customer) async {
    final controller = ref.read(customerListProvider.notifier);
    final outcome = await showModalBottomSheet<VisitOutcome>(
      context: context,
      builder: (context) => _OutcomeSheet(customer: customer),
    );
    if (outcome == null) return;
    await controller.recordVisit(customer: customer, outcome: outcome);
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(customerListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Customers')),
      body: RefreshIndicator(
        onRefresh: ref.read(customerListProvider.notifier).load,
        child: Column(
          children: [
            if (state.message case final message?)
              Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  message,
                  key: const Key('customers.message'),
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            if (state.loading)
              const Padding(
                padding: EdgeInsets.all(24),
                child: CircularProgressIndicator(key: Key('customers.loading')),
              ),
            Expanded(
              child: state.customers.isEmpty && !state.loading
                  ? const Center(
                      child: Text('No customers on this round.', key: Key('customers.empty')),
                    )
                  : ListView.builder(
                      physics: const AlwaysScrollableScrollPhysics(),
                      itemCount: state.customers.length,
                      itemBuilder: (context, index) => _CustomerTile(
                        customer: state.customers[index],
                        busy: state.busyId == state.customers[index].id,
                        onLog: _log,
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CustomerTile extends StatelessWidget {
  const _CustomerTile({
    required this.customer,
    required this.busy,
    required this.onLog,
  });

  final Customer customer;
  final bool busy;
  final Future<void> Function(Customer) onLog;

  @override
  Widget build(BuildContext context) => Card(
        key: Key('customer.${customer.id}'),
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        child: ListTile(
          title: Text(customer.shopName),
          subtitle: Text(_subtitle(customer)),
          trailing: switch ((customer.visitedThisRound, busy)) {
            (_, true) => const SizedBox(
                key: Key('customers.saving'),
                height: 22,
                width: 22,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            (true, _) => const Icon(Icons.check_circle_outline, key: Key('customer.visited')),
            _ => FilledButton(
                key: Key('customer.visit.${customer.id}'),
                onPressed: () => unawaited(onLog(customer)),
                child: const Text('Log visit'),
              ),
          },
        ),
      );

  /// A visited shop shows what was recorded; an unvisited one shows how to find it.
  ///
  /// **"Recorded", not "sent"** — the row is on disk and M9 has not seen it yet, and §5.3 is
  /// clear that the user is never told more than is true.
  static String _subtitle(Customer customer) {
    final outcome = customer.lastOutcome;
    if (outcome != null) return '${customer.code} · ${outcome.label}';
    return [customer.code, customer.zoneName, customer.phone]
        .where((part) => part.isNotEmpty)
        .join(' · ');
  }
}

/// The three outcomes `ck_visit_outcome` permits, and nothing else.
///
/// A sheet rather than a dialog: one thumb, three large targets, no typing. Notes, GPS and
/// the photo are **task 6 and later** — absent rather than disabled, because a greyed-out
/// control is a promise this milestone has not made.
class _OutcomeSheet extends StatelessWidget {
  const _OutcomeSheet({required this.customer});

  final Customer customer;

  @override
  Widget build(BuildContext context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              title: Text(customer.shopName, style: Theme.of(context).textTheme.titleMedium),
              subtitle: const Text('How did the visit go?'),
            ),
            const Divider(height: 1),
            for (final outcome in VisitOutcome.values)
              ListTile(
                key: Key('customers.outcome.${outcome.code}'),
                title: Text(outcome.label),
                onTap: () => Navigator.of(context).pop(outcome),
              ),
            TextButton(
              key: const Key('customers.cancel'),
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancel'),
            ),
          ],
        ),
      );
}
