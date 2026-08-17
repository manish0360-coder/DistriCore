import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/outbox/outbox_operation.dart';
import 'sync_controller.dart';

/// What this device is still carrying (M8 §10 task 9, FR-SYN-008).
///
/// **The screen that makes the outbox believable.** T5 and T6 let two roles record work into
/// a queue nothing drains yet; without this, a driver who completed five drops has no way to
/// tell whether any of it survived closing the app — and the natural response to that doubt
/// is to enter it again.
///
/// **Deliberately read-only.** M8 has no drain (§1.2). There is no retry button, no clear
/// button and no "sync now": each would be M9 logic wearing an M8 label, and a button that
/// appears to send something and does not is worse than no button.
class SyncStatusScreen extends ConsumerStatefulWidget {
  const SyncStatusScreen({super.key});

  @override
  ConsumerState<SyncStatusScreen> createState() => _SyncStatusScreenState();
}

class _SyncStatusScreenState extends ConsumerState<SyncStatusScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(ref.read(syncStatusProvider.notifier).load());
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(syncStatusProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Sync status')),
      body: RefreshIndicator(
        onRefresh: ref.read(syncStatusProvider.notifier).load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            if (state.message case final message?)
              Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: Text(
                  message,
                  key: const Key('sync.message'),
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ),
            if (state.loading)
              const Padding(
                padding: EdgeInsets.only(bottom: 16),
                child: Center(child: CircularProgressIndicator(key: Key('sync.loading'))),
              ),

            // FR-SYN-008 — count of pending transactions.
            Card(
              child: ListTile(
                leading: const Icon(Icons.inventory_2_outlined),
                title: Text(
                  state.isEmpty ? 'Nothing waiting' : '${state.pending} waiting to sync',
                  key: const Key('sync.pending'),
                  style: theme.textTheme.titleLarge,
                ),
                subtitle: Text(
                  state.isEmpty
                      ? 'Everything you have recorded is saved on this device.'
                      : 'Saved on this device. It will be sent when syncing arrives.',
                ),
              ),
            ),

            // FR-SYN-008 — last successful sync. **There has never been one, and saying so
            // is the honest answer**: §10 records task 9 as *"necessarily partial until M9"*,
            // and a blank field would read as "unknown" rather than as "not built".
            Card(
              child: ListTile(
                leading: const Icon(Icons.cloud_off_outlined),
                title: const Text('Not synced yet', key: Key('sync.lastSync')),
                subtitle: const Text(
                  'Sending to the server is not part of this version. Nothing you record is '
                  'lost — it stays on the device until then.',
                ),
              ),
            ),

            // FR-SYN-008 — count of unresolved conflicts. Zero **by construction**, not by
            // measurement: §5.3 has M8 write `PENDING` and nothing else, so no operation on
            // this device has ever been in a state the server could reject.
            Card(
              child: ListTile(
                leading: const Icon(Icons.rule_outlined),
                title: const Text('No conflicts', key: Key('sync.conflicts')),
                subtitle: const Text('Nothing here has been sent, so nothing can be refused.'),
              ),
            ),

            if (state.asOf case final asOf?)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Text(
                  // P-8: stale is acceptable, silently stale is not.
                  'Counted at ${_time(asOf)} UTC',
                  key: const Key('sync.asOf'),
                  style: theme.textTheme.bodySmall,
                ),
              ),

            if (state.oldest.isNotEmpty) ...[
              const Divider(),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Text(
                  state.pending > state.oldest.length
                      ? 'Oldest ${state.oldest.length} of ${state.pending}'
                      : 'Oldest first',
                  key: const Key('sync.sampleLabel'),
                  style: theme.textTheme.labelLarge,
                ),
              ),
              for (final operation in state.oldest) _OperationTile(operation: operation),
            ],
          ],
        ),
      ),
    );
  }

  static String _time(DateTime instant) =>
      '${instant.hour.toString().padLeft(2, '0')}:${instant.minute.toString().padLeft(2, '0')}';
}

class _OperationTile extends StatelessWidget {
  const _OperationTile({required this.operation});

  final OutboxOperation operation;

  @override
  Widget build(BuildContext context) => ListTile(
        key: Key('sync.operation.${operation.sequence}'),
        dense: true,
        leading: Text('#${operation.sequence}'),
        title: Text(_label(operation.operationType)),
        subtitle: Text('Recorded ${operation.clientCreatedAt.toIso8601String()}'),
        trailing: Text(operation.status.code),
      );

  /// Field vocabulary, not `04` T-26's.
  ///
  /// An unknown type falls back to its own code rather than to "Unknown": a driver reading
  /// `PAYMENT_CREATE` learns something; a driver reading "Unknown" learns that the app is
  /// confused.
  static String _label(String operationType) => switch (operationType) {
        'DELIVERY_COMPLETE' => 'Delivery completed',
        'VISIT_CREATE' => 'Customer visit',
        _ => operationType,
      };
}
