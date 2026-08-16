import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/delivery/delivery.dart';
import 'delivery_controller.dart';

/// The round (M8 §10 task 5, `05` §9.4).
///
/// **Nothing here touches the network to save.** "Mark delivered" writes to the outbox and
/// returns; the row is on disk before the button stops spinning, and M9 delivers it whenever
/// signal returns (P-2). That is why the same tap behaves identically in a warehouse and in
/// a dead spot — which is the property the whole milestone exists for.
class DeliveriesScreen extends ConsumerStatefulWidget {
  const DeliveriesScreen({super.key});

  @override
  ConsumerState<DeliveriesScreen> createState() => _DeliveriesScreenState();
}

class _DeliveriesScreenState extends ConsumerState<DeliveriesScreen> {
  @override
  void initState() {
    super.initState();
    // After the first frame: `ref.read` during `initState` would run before the widget is
    // mounted into the container's lifecycle.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(ref.read(deliveryListProvider.notifier).load());
    });
  }

  Future<void> _confirm(Delivery delivery) async {
    final controller = ref.read(deliveryListProvider.notifier);
    final recipient = await showDialog<String>(
      context: context,
      builder: (context) => _RecipientDialog(delivery: delivery),
    );
    if (recipient == null) return;
    await controller.complete(delivery: delivery, recipientName: recipient);
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(deliveryListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Deliveries')),
      body: RefreshIndicator(
        onRefresh: ref.read(deliveryListProvider.notifier).load,
        child: Column(
          children: [
            if (state.message case final message?)
              Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  message,
                  key: const Key('deliveries.message'),
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            if (state.loading)
              const Padding(
                padding: EdgeInsets.all(24),
                child: CircularProgressIndicator(key: Key('deliveries.loading')),
              ),
            Expanded(
              child: state.deliveries.isEmpty && !state.loading
                  ? const _Empty()
                  : ListView.builder(
                      // Always scrollable, so pull-to-refresh works on a short round.
                      physics: const AlwaysScrollableScrollPhysics(),
                      itemCount: state.deliveries.length,
                      itemBuilder: (context, index) => _DeliveryTile(
                        delivery: state.deliveries[index],
                        busy: state.busyId == state.deliveries[index].id,
                        onComplete: _confirm,
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  const _Empty();

  @override
  Widget build(BuildContext context) => const Center(
        child: Text('Nothing to deliver right now.', key: Key('deliveries.empty')),
      );
}

class _DeliveryTile extends StatelessWidget {
  const _DeliveryTile({
    required this.delivery,
    required this.busy,
    required this.onComplete,
  });

  final Delivery delivery;
  final bool busy;
  final Future<void> Function(Delivery) onComplete;

  @override
  Widget build(BuildContext context) {
    final delivered = delivery.status == DeliveryStatus.delivered;

    return Card(
      key: Key('delivery.${delivery.id}'),
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: ListTile(
        title: Text(delivery.customerName),
        subtitle: Text(
          delivered && delivery.recipientName != null
              // §5.3 / C-8's spirit: a locally saved handover is shown as saved, not as sent.
              ? '${delivery.orderNumber} · Received by ${delivery.recipientName}'
              : '${delivery.orderNumber} · ${delivery.status.code}',
        ),
        trailing: switch ((delivered, busy)) {
          (_, true) => const SizedBox(
              key: Key('deliveries.saving'),
              height: 22,
              width: 22,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          (true, _) => const Icon(Icons.check_circle_outline, key: Key('delivery.done')),
          _ => FilledButton(
              key: Key('delivery.complete.${delivery.id}'),
              onPressed: delivery.canComplete ? () => unawaited(onComplete(delivery)) : null,
              child: const Text('Delivered'),
            ),
        },
      ),
    );
  }
}

/// Who took the parcel. The one field `05` §10.3 needs that only the driver knows.
///
/// GPS, the photo and the failure path are **task 6 and later** — deliberately absent rather
/// than stubbed, because a disabled control is a promise the milestone has not made.
class _RecipientDialog extends StatefulWidget {
  const _RecipientDialog({required this.delivery});

  final Delivery delivery;

  @override
  State<_RecipientDialog> createState() => _RecipientDialogState();
}

class _RecipientDialogState extends State<_RecipientDialog> {
  final _recipient = TextEditingController();

  @override
  void dispose() {
    _recipient.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.delivery.customerName),
        content: TextField(
          key: const Key('deliveries.recipient'),
          controller: _recipient,
          autofocus: true,
          textCapitalization: TextCapitalization.words,
          decoration: const InputDecoration(
            labelText: 'Received by',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
            key: const Key('deliveries.cancel'),
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const Key('deliveries.confirm'),
            onPressed: () => Navigator.of(context).pop(_recipient.text),
            child: const Text('Save'),
          ),
        ],
      );
}
