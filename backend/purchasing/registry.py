"""R-2 registration: ``GoodsReceipt`` is a permitted source document in **both** registries.

**This is the first model registered in both, and the reason is what a receipt is.** A goods
receipt is the one document that moves stock and raises money in the same act, so it must be
resolvable from either fact table:

    inventory.services.SOURCE_DOCUMENT_REGISTRY   governs  stock_movement   (T-13)
    ledger.services.SOURCE_DOCUMENT_REGISTRY      governs  supplier_ledger_entry (T-34)
                                                  and     customer_ledger_entry (T-22)

**They are two separate dictionaries that happen to share a name**, and conflating them is a
live hazard: `Delivery` is registered only in the first, `Invoice`/`CreditNote`/`Payment` only
in the second. Registering `GoodsReceipt` in one would leave the other refusing it at
``_resolve_source`` — at runtime, on the first real receipt, not in a test.

Registration lives here rather than in `inventory` or `ledger` so the dependency points the
right way: `purchasing` sits above both and may import them; neither may import `purchasing`.
That is the same pattern `billing`, `receivables` and `fulfilment` follow.
"""

from __future__ import annotations

from inventory.services import SOURCE_DOCUMENT_REGISTRY as STOCK_SOURCE_REGISTRY
from ledger.services import SOURCE_DOCUMENT_REGISTRY as LEDGER_SOURCE_REGISTRY
from purchasing.models import GoodsReceipt, SupplierPayment

#: The single spelling of the type code, so the two registrations cannot drift apart.
GOODS_RECEIPT_SOURCE_TYPE = "GOODS_RECEIPT"

STOCK_SOURCE_REGISTRY[GoodsReceipt] = GOODS_RECEIPT_SOURCE_TYPE
LEDGER_SOURCE_REGISTRY[GoodsReceipt] = GOODS_RECEIPT_SOURCE_TYPE

# --------------------------------------------------------------------------------
# `SupplierPayment` — **`"PAYMENT"`, and the name is load-bearing** (S4.3 ruling U-1).
#
# `ledger.walk.annulled_entry_ids` finds an annullable target with this predicate:
#
#     entry.entry_type == entry.source_document_type
#
# A supplier payment's ledger entry has `entry_type = SupplierLedgerEntry.Type.PAYMENT`,
# the literal `"PAYMENT"`. Registering this model as `"SUPPLIER_PAYMENT"` — the tidier
# name — would break that equality, so the payment entry would never enter the walk's
# `unclaimed` map, the reversal `ADJUSTMENT` would find no target, and **no annulment
# would happen**.
#
# That failure is silent. The reversal would become an ordinary positive debit dated the
# day of the reversal, resurrecting settled receipts as *new* debt instead of restoring
# them at their original ages — the exact defect M6 §5A was written to prevent, on the
# payables side. `GoodsReceipt` above satisfies the same equality by coincidence of
# naming, which is why Stage 3 never surfaced this.
#
# **Two models therefore map to `"PAYMENT"`** in this registry: `receivables.Payment` and
# `SupplierPayment`. That is safe because the registry is read **forward only**
# (`REGISTRY[model] -> str`); no reverse lookup exists anywhere in the codebase. It is
# unambiguous in practice because `customer_ledger_entry` only ever references `Payment`
# and `supplier_ledger_entry` only ever references `SupplierPayment` — resolution is
# per-ledger, never global. **Ruling U-2: any future reverse lookup MUST be scoped by
# ledger.** It is not registered in the stock registry: a payment moves no stock.
# --------------------------------------------------------------------------------
SUPPLIER_PAYMENT_SOURCE_TYPE = "PAYMENT"

LEDGER_SOURCE_REGISTRY[SupplierPayment] = SUPPLIER_PAYMENT_SOURCE_TYPE
