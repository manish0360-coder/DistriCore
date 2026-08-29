# D5 — Purchase & Supplier Management: Design Review

| Field | Value |
| --- | --- |
| Document ID | `D5_Design_Review` |
| Version | **0.8.0 — design of record** |
| Status | **Design of record. Stages 1 and 2 (FR-PUR-001, 002, 003, 005) CLOSED and verified. Stage 3 (FR-PUR-006, 007, 008, 009, 010, 011, 013) designed, approved and UNBLOCKED — BD-2 closed 2026-08-27 as Option C.** Ten rulings applied (D-PUR-1…D-PUR-10); **CD-1, CD-2 and BD-2 resolved**; four business decisions (BD-1, BD-3, BD-4, BD-5) and one interface contract (DR-10) remain open, **none of which blocks Stage 3** |
| Date | 2026-08-25 |
| Scope | D5 Purchase & Supplier Management — FR-PUR-001…015 |
| Release | **v1.0**, confirmed 2026-08-25 (`01` §7.2, §7.4) |
| Depends on | `00` v1.0.0 · `01` · `02` v0.4.0 · **`02A` v0.3.0** · **`04` v0.2.0** · `05` · `M8_Design_Review` v1.8.0 · `M9_Design_Review` v1.3.0 |
| Independent review | Gemini, 2026-08-18 — **corroboration, not authority** (`M9_Design_Review` §6 precedent) |

### Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1.0 | 2026-08-25 | Initial architecture and staging proposal, following the V1.0 acceptance audit's Tranche 1 finding that D5 has no implementation |
| **0.2.0** | **2026-08-25** | **Independent review reconciled.** §5.1 re-opened with both allocation models specified and **neither chosen**; §5.2 promoted from *"parked"* to a **required DR-10 interface contract** (§6); the ledger sign convention converted from an instruction into a **stated, testable invariant**; over-receipt re-opened with three policy options and **no default**; FR-PUR-004 gains the fulfilment/revenue/demand distinction with a marked recommendation. **Two deliberate divergences from the independent review recorded in §4.** No code, no migration, no schema, no requirement change |
| **0.3.0** | **2026-08-25** | **CD-1 and CD-2 resolved.** **D-PUR-6** returns D5 to v1.0 and supersedes DV-6's verdict **for D5 only**, applied in `02A` §14 (v0.3.0) and followed consequentially by `04` (v0.2.0). **D-PUR-7** rules that goods receipt reuses `StockMovement.Type.RECEIPT` with `source_document_type='GOODS_RECEIPT'` and creates **no** new movement type, superseding `04`'s future-evolution note. **`R-D5-1…5` renamed `D-PUR-1…5`** — `R-` was an invented prefix, and `D-D5-n` would collide with `M8_Design_Review` §14.12's existing `D-D5`. **§1 re-toned:** the reason-coded stock-in path is described as deliberate DV-6 behaviour, which it was, and not as an implementation mistake. **Minor, not patch: two decisions added.** No code, no migration, no schema, no requirement change |
| **0.4.0** | **2026-08-26** | **Two Stage-1 clarifications, ruled before coding. Neither reopens architecture.** **§3.4 audit vocabulary corrected** — `AuditLog.Action` is a fixed enum and the corpus distinguishes entities by `entity_type`; the earlier `SUPPLIER_CREATED`-style names were descriptive shorthand and are replaced by a mapping onto `CREATE`/`UPDATE`/`DEACTIVATE`/`ISSUE`/`CANCEL`/`PAYMENT_REVERSE`. **D5 adds no action codes and no `audit_log` migration.** **§3.1 `Supplier` field list made explicit** — *"mirror `Customer` field-for-field"* was not literally applicable (`Customer` carries `shop_name`, `zone`, `credit_limit_amount`, coordinates); the conventions are mirrored, the field list is not. `email` recorded as new; `state_code` recorded as carried with no v1.0 consumer. **Purchasing placed at `"orders \| purchasing"` in the layers contract.** Stage 1 = FR-PUR-001 + FR-PUR-002 only |
| **0.5.0** | **2026-08-26** | **Stage 1 CLOSED** — `make verify` VERIFIED, 875 passed, 94.56%, migrations clean, 3/3 contracts kept. **Stage 2 approved** (FR-PUR-003, FR-PUR-005). **D-PUR-8 added: `po_number` is allocated at creation, not at issue** — the product owner reversed the engineering proposal, and the reasoning is stronger: a draft is already a business document, needs a human-readable reference for support and audit, and a PO number is an internal reference where gaps cost nothing. **The nullable column and the partial-unique-on-null mechanism are therefore not built.** §3.1 gains the full `PurchaseOrder`/`PurchaseOrderLine` field lists, `is_editable = status == DRAFT` (narrower than `SalesOrder`, and why), and the snapshot rationale; §3.5's migration order puts the sequence **before** the table because `po_number` is `NOT NULL` from the first row; §6 gains the exact `issue_purchase_order` call graph and the point at which BD-4 becomes required. **Minor, not patch: a decision was added.** No code changed by this revision |
| **0.6.0** | **2026-08-27** | **Stage 2 CLOSED** — `make verify` VERIFIED, 947 passed, 94.52%, migrations clean, 3/3 contracts. **Stage 3 designed.** **D-PUR-9: FR-PUR-010 and FR-PUR-011 move from Stage 4 into Stage 3** — `record_goods_receipt` cannot be written twice, and splitting it would create a period in which stock increases with no liability recorded. The staging table, not the atomic boundary, was wrong; nothing newly blocking is pulled forward, because BD-1 governs payment *allocation* and the supplier ledger is identical under either option. **D-PUR-10: `inventory.services.receive_stock` is widened to `reason_code: ReasonCode \| None = None`** — a narrow enabling seam correction, not a new inventory feature: `record_movement` beneath it already implements BR-007 as *"source document **or** reason code"*, and the wrapper was narrower than the thing it wrapped. Bypassing `receive_stock`, calling `record_movement` from `purchasing`, inventing a `GOODS_RECEIPT` reason code and adding a `GOODS_RECEIPT` movement type are all **explicitly forbidden**. §3.1 gains the full `GoodsReceipt`/`GoodsReceiptLine` field lists and the `stock_movement` back-pointer; **the GRN immutability rationale no longer claims a correction mechanism exists** — *"Posted goods receipts are immutable; correction mechanisms are outside Stage 3 and require a separately approved design."* **BD-2 remains open**, with the three predicates modelled and the duplicate-submission consequence of option B recorded for revisit. **Minor, not patch: two decisions added.** No code changed by this revision |
| **0.7.0** | **2026-08-27** | **BD-2 CLOSED — Option C, a configurable per-line over-receipt tolerance.** D-PUR-4 rewritten from an open question into a ruling. The predicate is **cumulative and per purchase-order line**: `Σ received <= ordered × (1 + tolerance/100)`, with `tolerance` read from **`BusinessProfile.over_receipt_tolerance_percent`**, **default `0`**, nothing hard-coded, and **no supplier- or product-specific tolerance modelled**. Cumulative rather than per-receipt because three receipts of 40% would otherwise each pass and overshoot together; per line rather than per order because a shortfall on one line must not finance an overage on another. **Rejection is whole-document and atomic** — no GRN, no `StockMovement`, no ledger entry, no status change, no audit row. Under-receipt is unchanged and still yields `PARTIALLY_RECEIVED`. **Duplicate-safety analysed rather than assumed:** the predicate covers every duplicate that would exceed tolerance — at the default `0` that is every duplicate of a completing receipt — but **cannot** catch a duplicated *partial* that fits within tolerance, because such a receipt is arithmetically indistinguishable from the second delivery FR-PUR-013 permits; **no idempotency mechanism is added**, the confirm screen is the mitigation, and only contrary implementation evidence reopens it. **"Receiving Intelligence / Supplier Reliability" recorded as a NON-IMPLEMENTED future capability** — must be derived from `purchase_order_line` and `goods_receipt_line`, and must never become a second source of truth (N-03/E-01). §3.3, §7, §8 and §9 updated; A and B retained as the historical record. **Minor, not patch: a decision changed.** No code changed by this revision |
| **0.8.0** | **2026-08-28** | **Two design-record errors corrected, both found while verifying the real signatures before Stage 3 coding. Neither changes a decision.** **(1) The supplier ledger writes no audit row.** §3.4 previously listed *"payable posted → `CREATE` → `supplier_ledger_entry`"*; `ledger/services.py` states the governing rule — *"Under **R-3** a ledger entry writes no audit row: it is immutable and already carries actor, timestamp, amount, narration and its source document"* — and D5 must not make its ledger behave differently from the ledger it ports. **The goods receipt's own `CREATE` row is the audit record for the whole atomic transaction**, and the payable remains reachable from it by `source_document_id`. Still **no new `AuditLog.Action` value**. **(2) There are two source-document registries, not one.** `inventory.services.SOURCE_DOCUMENT_REGISTRY` governs `stock_movement` and holds only `Delivery`; `ledger.services.SOURCE_DOCUMENT_REGISTRY` governs `customer_ledger_entry` and holds `Invoice`, `CreditNote` and `Payment`. `04` T-13 had conflated them and is corrected in the same pass. **`GoodsReceipt` is the first document registered in both**, because a receipt moves stock *and* raises a liability, so `purchasing/registry.py` makes two registrations. **Patch-level in substance but recorded as minor**, because §3.1 and §3.4 both changed. No code changed by this revision |

> **Why this document exists.** The V1.0 acceptance audit (2026-08-25, Tranche 1) established that D5 — fifteen requirements, thirteen of them `MUST` — has **no implementation of any kind**: no supplier model, no purchase order, no goods receipt, no supplier ledger, no route, no template, no test. `01` §7.2 places Purchase & Supplier Management in v1.0 and the business confirmed that placement on 2026-08-25. This is the design that closes it.
>
> **No code is authorised by this document.** It is the architecture that Stage 1 may be built against once §7's blockers are cleared.

---

## 1. The problem, stated once

**Stock currently has no document-backed inbound path, and that is by design.** The only way on-hand increases today is `inventory.services.receive_stock()` with a **reason code and no source document**. `StockMovement`'s CHECK permits *either* a source document *or* a reason code, so reason-coded receipts are legal by construction.

**This is DV-6 working exactly as specified, not an implementation mistake.** `02A` DV-6 recorded the deviation, weighed it and accepted it: *"Stock must still enter the system. Without purchase orders, inbound stock is recorded as a reason-coded receipt — which the Owner 'Stock' feature already provides."* It was a deliberate, priced, documented judgement, and `04` §2.2 carried it faithfully.

What has changed is not the quality of that decision but its consequence, now that D5 has returned to v1.0 (`02A` §14, D-PUR-6): **every unit of stock the business has bought entered the ledger with no purchase order, no supplier and no unit cost behind it.** FR-PUR-007 and BR-007 exist to close that gap, and the fields to do it are already present and constraint-enforced.

**Reason-coded stock-in survives D5 unchanged** (`02A` §14.1 clause 4). It remains the correct path for inbound stock with no purchase behind it — opening stock, found stock, corrections. D5 adds a second, document-backed path; it does not replace the first.

**There are also no payables at all.** `ledger/` is customer-only by name and by foreign key. The business can see what it is owed and nothing about what it owes.

**Order-to-cash is unaffected.** Order → invoice → delivery → receivable is complete and tested. D5 is **procure-to-pay**, the other half of the cycle, and the two meet only at `StockMovement`.

---

## 2. Patterns adopted, and the files they come from

The greatest risk in a new domain is a parallel subsystem. Every row below is a decision **not** to invent one.

| Concern | Existing pattern | Source | D5 decision |
| --- | --- | --- | --- |
| Base model | `TimeStampedModel` | `core/models.py:21` | adopt for masters and PO |
| Money / quantity | `MoneyField(14,2)`, `QuantityField(14,3)` | `core/fields.py:58,71` | adopt; never a raw `DecimalField` |
| Master identity | `code = CharField(32, unique=True)` | `catalogue/Product:21` | adopt for `Supplier.code` |
| Status machine | `TextChoices` + module-level `ALLOWED_TRANSITIONS` + one `_transition()` **in services** | `orders/services.py:36,289` | adopt exactly. **No state logic on the model** |
| Line snapshots | `product_code`, `product_name`, `unit_name`, `pack_size_snapshot` frozen on the line | `orders/SalesOrderLine:155` | adopt — a cost history must not move when a product is renamed |
| Issued-document immutability | `_ImmutableDocument` abstract, `_mutable_fields` escape | `billing/models.py:94` | adopt for **GoodsReceipt** and **SupplierPayment** only |
| Ledger | derived balance `SUM(amount)`, immutable rows, `source_document_type/id`, one `OPENING` per party via partial unique index | `ledger/models.py:45,155` | **port** into `ledger`, not a new app |
| Payment | `_ImmutableDocument`, `nextval` reference number, reversal by flag + reason | `receivables/` | port |
| Numbering | two kinds — **statutory gapless** with a row lock (`billing.allocate_number`) vs **reference, gaps permitted** (`receivables/services.py:45`) | | PO / GRN / supplier payment are **references**. None is statutory |
| Stock in | `receive_stock()` → `StockMovement.Type.RECEIPT`, sign-enforced positive | `inventory/services.py:199` | **call it. Never write `StockMovement` directly** |
| Provenance | `source_document_type` + `source_document_id`, CHECK forbidding half a reference | `inventory/models.py:130,187` | the FR-PUR-007 hook. **Nothing new required** |
| Authorization | `require_roles(actor, Role.OWNER)` **in services, not views** (N-01) | `core/permissions.py:49` | adopt |
| Audit | `record_audit(...)` **inside the same transaction** as the change | `core/services.py:65` | adopt |
| Web surface | `@login_required` function views + Django templates | `webadmin/master_views.py` | adopt. **Not an SPA, not DRF** |

### 2.1 Deliberately **not** adopted

- **No `client_uuid` anywhere in D5.** Every FR-PUR surface is `S1` or `CORE`; no offline device originates a purchase. `SalesOrder.client_uuid` is nullable precisely because web orders leave it null. Adding it here would be cargo-cult idempotency.
- **No REST API.** No FR-PUR carries an `S2` surface, and `05_API_Contracts` contracts no purchase endpoint. Building `/api/v1/purchase-orders/` would invent a surface no requirement asks for. If a later surface needs one, it is added then, against a requirement.
- **No second allocation model, no second payment model, no second ledger, no second status-machine style, no second stock-receipt mechanism.**
- **`PurchaseOrder` is *not* an `_ImmutableDocument`.** That base is for *issued financial documents*; a PO has a legitimate `DRAFT` phase and must be editable there. Editability is enforced in services by status, not by the ORM.

---

## 3. The design

### 3.1 Entities

**New app `purchasing`.** `SupplierLedgerEntry` goes in the existing `ledger` app instead — BR-005 says *"on the same terms as the customer ledger"*, and `ledger` already owns immutability, the derived-balance rule and the opening-balance constraint.

| Entity | App | Base | Requirement |
| --- | --- | --- | --- |
| `Supplier` | `purchasing` | `TimeStampedModel` | FR-PUR-001 |
| `ProductSupplier` | `purchasing` | — | FR-PUR-002 |
| `PurchaseOrder` | `purchasing` | `TimeStampedModel` | FR-PUR-003, 005 |
| `PurchaseOrderLine` | `purchasing` | — | FR-PUR-003 |
| `GoodsReceipt` | `purchasing` | `_ImmutableDocument` | FR-PUR-006, 013 |
| `GoodsReceiptLine` | `purchasing` | — | FR-PUR-006 |
| `SupplierLedgerEntry` | **`ledger`** | immutable | FR-PUR-011 |
| `SupplierPayment` | `purchasing` | `_ImmutableDocument` | FR-PUR-012 — **shape pending BD-1** |
| `SupplierPaymentAllocation` | `purchasing` | — | **only if BD-1 = Option B** |

**`Supplier`** — `code` (32, unique) · `name` (200) · `contact_name` · `phone` · `alt_phone` · `email` · `billing_address` (required) · `dispatch_address` (blank = same as billing) · `gstin` (15) · `state_code` (2) · `payment_terms_days` · `is_active` · `created_by` · `TimeStampedModel`

> **Fixed in v0.4.0.** The 0.2.0 draft said the fields *"must mirror `customers.Customer` field-for-field"*. That instruction cannot be taken literally and would have been wrong: `Customer` carries `shop_name`, `zone`, `delivery_address`, `credit_limit_amount`, `opening_balance_amount` and `latitude`/`longitude` — retailer-specific fields a supplier has no use for. **What is mirrored is the field *conventions*, not the field *list*:** `code` as `CharField(32, unique=True)`, addresses as `TextField` with the second blank meaning *"same as the first"*, `gstin` at 15 and `state_code` at 2, a non-negative `SmallIntegerField` for terms guarded by a `CHECK` exactly as `ck_customer_credit_days` guards `credit_days`.
>
> `email` has **no** `Customer` analogue and is new. `state_code` is carried to satisfy FR-PUR-001's *"tax identifiers"* (plural) and **has no consumer in v1.0** — D5 computes no purchase tax; it is one blank-able column, retained by ruling on 2026-08-26.

**`ProductSupplier`** — `product` FK PROTECT · `supplier` FK PROTECT · `supplier_sku` · `is_preferred` · unique(`product`,`supplier`) · **partial unique index: at most one `is_preferred` per product**

**`PurchaseOrder`** — `po_number` (`CharField(32)`, **unique, NOT NULL, allocated at creation** — D-PUR-8) · `supplier` FK PROTECT · `status` (default `DRAFT`) · `order_date` · `expected_date` · `subtotal_amount`/`tax_amount`/`total_amount` (`MoneyField`) · `notes` · `issued_at`/`issued_by` · `cancelled_reason`/`_at`/`_by` · `created_by` · `TimeStampedModel`

> **`is_editable` is `status == DRAFT`** — narrower than `SalesOrder.is_editable`, which also permits `CONFIRMED`. A `CONFIRMED` sales order is still ours to amend; an **`ISSUED` purchase order has been sent to a supplier**, and amending it silently would leave the two parties holding different documents.
>
> **Not an `_ImmutableDocument`** (§2.1): a `DRAFT` PO must be editable, so immutability begins at `ISSUED` and is enforced in services through `is_editable`, exactly as `orders.services.amend_order` does.

**`PurchaseOrderLine`** — `purchase_order` FK CASCADE · `line_number` (1-based) · `product` FK PROTECT · **snapshots** `product_code`/`product_name`/`unit_name`/`pack_size_snapshot`/`tax_rate_percent` · `quantity_ordered` (`QuantityField`) · `unit_cost` (`MoneyField`) · `taxable_amount`/`tax_amount`/`line_total` · unique(`purchase_order`,`line_number`)

> **The snapshots freeze the commercial agreement.** `SalesOrderLine` snapshots the sale; this snapshots the purchase. A product renamed or repriced after issue must not retroactively change what was ordered. **`unit_cost` is a purchase price and is unrelated to `product.selling_price`** — there is no cost field on `Product`, and D5 does not add one; the cost is entered per line, which is also what makes FR-PUR-008's variance measurable.

**`GoodsReceipt`** — `grn_number` (`CharField(32)`, unique, `GRN-00000001`, `nextval`) · `purchase_order` FK PROTECT · `receipt_date` (**caller-supplied**) · `supplier_reference` · `subtotal_amount`/`tax_amount`/`total_amount` (`MoneyField`) · `notes` · `received_by` · `created_at` · **`_ImmutableDocument`**

> **Immutable once created, unlike `PurchaseOrder`.** A GRN has no draft phase: the moment it exists it has moved stock and created a liability.
>
> **Posted goods receipts are immutable; correction mechanisms are outside Stage 3 and require a separately approved design.** No such mechanism exists today, and nothing in Stage 3 may be read as providing one. `SupplierLedgerEntry.entry_type` includes `DEBIT_NOTE` as a *vocabulary* item; **no service writes it and no workflow produces it.**

**`GoodsReceiptLine`** — `goods_receipt` FK CASCADE · `purchase_order_line` FK PROTECT · `quantity_received` · `unit_cost`/`tax_rate_percent`/`taxable_amount`/`tax_amount`/`line_total` **snapshotted from the PO line** · **`stock_movement` FK PROTECT, `NOT NULL`** · unique(`goods_receipt`, `purchase_order_line`)

> **`stock_movement` as a real foreign key is the strongest available form of FR-PUR-007.** `source_document_type`/`_id` points forward from the movement to the receipt; this points back. Both directions must resolve, and `NOT NULL` makes a receipt line without a movement unrepresentable rather than merely discouraged.

**`GoodsReceiptLine`** — `goods_receipt` FK CASCADE · `purchase_order_line` FK PROTECT · `quantity_received` · `unit_cost` snapshot · unique(`goods_receipt`,`purchase_order_line`)

**`SupplierLedgerEntry`** — `supplier` FK PROTECT · `entry_date` · `entry_type` ∈ {`GOODS_RECEIPT`, `PAYMENT`, `OPENING`, `ADJUSTMENT`, `DEBIT_NOTE`} · `amount` · `source_document_type`/`source_document_id` · `narration` · `created_by` · `created_at` · immutable · one `OPENING` per supplier

> **Ports `CustomerLedgerEntry` field-for-field**, including the `_SIGN_RULES` map that
> `ledger/services.py:70` uses to refuse an entry whose sign disagrees with its type. Written
> through a new `ledger.services.record_supplier_entry`, mirroring `record_entry` — the same
> "single write path", the same no-lock append, the same `_resolve_source` validation, and
> **the same R-3 rule that it writes no audit row** (§3.4).
>
> **Its `source_document` is validated against `ledger.services.SOURCE_DOCUMENT_REGISTRY`** —
> a **different dictionary** from `inventory.services.SOURCE_DOCUMENT_REGISTRY`, which governs
> `stock_movement`. `GoodsReceipt` is the first document registered in **both**, because a
> receipt moves stock *and* raises a liability; `purchasing/registry.py` therefore makes two
> registrations, one into each module.
>
> **`DEBIT_NOTE` is vocabulary, not capability.** It is listed so the enum need not be
> migrated when a correction mechanism is designed. **Stage 3 writes only `GOODS_RECEIPT`;
> Stage 4 adds `PAYMENT`.** Nothing writes `ADJUSTMENT` or `DEBIT_NOTE`.

**`SupplierPayment`** — `payment_number` (unique, `SPY-00000001`) · `supplier` FK PROTECT · `method` · `reference_number` · `payment_date` · `amount` · `paid_by` · `notes` · `is_reversed`/`reversed_reason`/`_at`/`_by`

### 3.2 Purchase order lifecycle — FR-PUR-005

| From | To |
| --- | --- |
| `DRAFT` | `ISSUED`, `CANCELLED` |
| `ISSUED` | `PARTIALLY_RECEIVED`, `RECEIVED`, `CANCELLED` |
| `PARTIALLY_RECEIVED` | `PARTIALLY_RECEIVED`, `RECEIVED`, `CLOSED` |
| `RECEIVED` | `CLOSED` |
| `CLOSED` | *(terminal)* |
| `CANCELLED` | *(terminal)* |

`PARTIALLY_RECEIVED → PARTIALLY_RECEIVED` is what makes FR-PUR-013 work. **`CANCELLED` is reachable from `DRAFT` and `ISSUED` only**, exactly as FR-PUR-005 states — a PO with stock against it can be short-closed, never cancelled. Status is **recomputed from received-versus-ordered totals after each receipt**, then moved through the same `_transition()` guard.

### 3.3 Invariants

| Constraint | Requirement |
| --- | --- |
| `quantity_ordered > 0`, `unit_cost >= 0` | FR-PUR-003 |
| `quantity_received > 0` — a zero receipt is not a receipt | FR-PUR-006 |
| unique(`purchase_order`,`line_number`); unique(`goods_receipt`,`purchase_order_line`) | FR-PUR-013 |
| one `OPENING` per supplier (partial unique index) | FR-PUR-011 |
| receipt rejected unless the PO is `ISSUED` or `PARTIALLY_RECEIVED` — **in the service** | FR-PUR-009 |
| **cumulative per-line acceptance** — `Σ received <= ordered × (1 + tolerance/100)`, tolerance from `BusinessProfile.over_receipt_tolerance_percent`, default `0` | FR-PUR-008 — **D-PUR-4, decided** |
| stock provenance | **no new constraint** — the existing CHECK already forbids half a reference |

**Idempotency.** None by `client_uuid` (§2.1). Double-submit protection on the web is the `DRAFT → ISSUED` transition guard plus `GoodsReceipt`'s immutability. Re-issuing an `ISSUED` PO raises; re-posting a receipt creates a second, distinct GRN — legitimate under FR-PUR-013, which is why the confirm screen must show what has already been received.

### 3.4 Transaction boundaries

`record_goods_receipt` is the critical one. **One atomic block, all or nothing:**

1. allocate the GRN number (`nextval`)
2. insert `GoodsReceipt` + lines
3. per line: `receive_stock(actor, product, qty, source_document_type='GOODS_RECEIPT', source_document_id=grn.pk)`
4. insert `SupplierLedgerEntry` (`GOODS_RECEIPT`, **positive**)
5. recompute and `_transition()` the PO status
6. `record_audit('GOODS_RECEIPT_RECORDED', …)`

> A receipt that moved stock without creating the payable, or a payable without the stock, is the defect this boundary exists to prevent — the same reasoning `receivables.record_payment` already follows.

`issue_purchase_order` and `record_supplier_payment` are likewise atomic with their audit rows.

**Audit events — corrected in v0.4.0.** `AuditLog.Action` is a **fixed `TextChoices` enum** and the corpus distinguishes entities by `entity_type`, not by inventing action codes (`customers.services.create_zone` writes `Action.CREATE` with `entity_type="zone"`). Earlier drafts of this section listed `SUPPLIER_CREATED`, `PURCHASE_ORDER_ISSUED` and similar; **those were descriptive shorthand, never proposed enum values.** D5 adds **no** action codes and therefore no migration to `audit_log`.

| Event | `action` | `entity_type` |
| --- | --- | --- |
| supplier created / changed / deactivated | `CREATE` · `UPDATE` · `DEACTIVATE` | `supplier` |
| product↔supplier linked / changed / unlinked | `CREATE` · `UPDATE` · `DEACTIVATE` | `product_supplier` |
| purchase order created / issued / cancelled | `CREATE` · `ISSUE` · `CANCEL` | `purchase_order` |
| goods receipt recorded | `CREATE` | `goods_receipt` |
| supplier payment recorded / reversed | `CREATE` · `PAYMENT_REVERSE` | `supplier_payment` |
| **supplier ledger entry** | **none — see R-3 below** | — |

> **A supplier ledger entry writes no audit row. Corrected in v0.8.0.**
>
> `ledger/services.py` states the rule for the customer side and it applies unchanged here:
>
> > *"Under **R-3** a ledger entry writes **no audit row**: it is immutable and already carries
> > actor, timestamp, amount, narration and its source document. An audit row would duplicate
> > a record that cannot change."*
>
> An earlier draft of this section listed *"payable posted → `CREATE` → `supplier_ledger_entry`"*.
> **That was wrong** — it would have made D5's ledger behave differently from the ledger it
> ports, and duplicated an immutable record.
>
> **The goods receipt's own `CREATE` row is the audit record for the whole transaction.** It is
> written inside the same atomic block as the movements, the ledger entry and the purchase-order
> transition, so nothing is lost: the payable is reachable from the GRN by
> `source_document_id`, and the GRN is reachable from the audit row by `entity_id`.
>
> **No new `AuditLog.Action` value is added by Stage 3**, or by D5 at all.

> **Payload keys must avoid `code`.** `core.services._scrub` redacts audit values by **key
> name** against `_SENSITIVE`, which contains `code` and `code_hash` because an OTP is a
> credential (`04` §T-05, SEC-3, FR-AUD-006), and the match is exact. A business identifier
> written under the key `code` becomes `[redacted]` — as `customers` and `catalogue` have
> been doing since M1, unnoticed because no test asserted it. **D5 writes `supplier_code`**,
> which survives the scrubber. The redaction policy is correct and is not modified; only the
> key is chosen to sit outside it. `tests/unit/test_audit.py` continues to assert that a raw
> `code` key *is* redacted.

### 3.5 Surfaces and migrations

**Web (S1) only** — `webadmin/purchasing_views.py` plus templates: `supplier_list`/`_form`, `purchase_order_list`/`_form`/`_detail`, `goods_receipt_form`, `supplier_payment_list`, `supplier_outstanding`. Function views, `@login_required`, **all rules in services**.

**Migration sequence**

1. `purchasing/0001` — `Supplier`, `ProductSupplier` **(Stage 1, shipped)**
2. `purchasing/0002` — `CREATE SEQUENCE purchase_order_number_seq` · `purchasing/0003` — `PurchaseOrder`, `PurchaseOrderLine`. **The sequence migrates before the table**, because `po_number` is `NOT NULL` from the first row (D-PUR-8) and the service that allocates it must have a sequence to read
3. `purchasing/0004` — `GoodsReceipt`, `GoodsReceiptLine` + GRN sequence
4. `ledger/0004` — `SupplierLedgerEntry`
5. `purchasing/0005` — `SupplierPayment` + SPY sequence *(+ `SupplierPaymentAllocation` iff BD-1 = B)*

---

## 4. Rulings

### D-PUR-1 — FR-PUR-012 remains **undecided**. Neither model is designed in.

Both are specified. **Neither is built.**

| | Model | Shape |
| --- | --- | --- |
| **A** | Deterministic derived settlement | No allocation table. Outstanding is `SUM(SupplierLedgerEntry.amount)`; settlement is computed **oldest-outstanding-first**. Mirrors `receivables`, which states outright: *"no allocation table and no allocation column"* |
| **B** | Explicit allocation | `purchasing.SupplierPaymentAllocation` — `payment` FK, `goods_receipt` FK, `amount`. A payment records **which** receipts it settles, by user intent |

**The unresolved business question, in the exact form it must be put — BD-1:**

> **Must a supplier payment be explicitly allocated by a user to specific outstanding receipt(s), or is deterministic oldest-outstanding-first settlement acceptable?**

**No inference is drawn from the word "allocatable."** The requirement's verb is not evidence of the workflow behind it.

**Blocked until answered:** `SupplierPayment`'s final shape, supplier-outstanding reporting (FR-PUR-015), and the FR-PUR-012 acceptance test. **`SupplierLedgerEntry` is not blocked** — it is identical under both models.

### D-PUR-2 — The DR-10 approval interface contract is part of this design

See §6. `issue_purchase_order` is **not implementable** until that contract is signed. **No purchase-specific approval logic will be written under any circumstances.**

### D-PUR-3 — Supplier ledger sign convention, stated as an invariant

Replacing *"mirror `CustomerLedgerEntry`"*, which was an instruction and not a testable contract:

> **A positive `amount` increases the distributor's liability to the supplier.**
>
> - `GOODS_RECEIPT` → **positive**
> - `PAYMENT` → **negative**
> - `OPENING` → signed as the opening position requires
> - **Balance ≡ `SUM(amount)`.** Never stored, never cached.
> - **Rows are immutable.** No `UPDATE`, no `DELETE`, enforced exactly as `CustomerLedgerEntry` enforces it.

Testable as written: a receipt of 1,000 followed by a payment of 400 leaves a balance of exactly 600.

### D-PUR-4 — Over-receipt: **Option C, a configurable per-line tolerance. BD-2 CLOSED.**

**Ruled 2026-08-27.** BD-2 is decided and is no longer an open business decision.

| | Policy | |
| --- | --- | :-: |
| **A** | Reject any receipt exceeding `quantity_ordered − quantity_already_received` | not adopted |
| **B** | Permit, record the variance, report it | not adopted |
| **C** | Permit within a configurable tolerance; reject beyond | **ADOPTED** |

A and B are retained only as the record of what was weighed. The comparison below is likewise
historical — it is why the ruling needed no schema change.

**How each option would have changed exactly one predicate**, where `remaining = quantity_ordered − Σ already received`:

| | Acceptance predicate | Transaction behaviour |
| --- | --- | --- |
| **A** | `qty <= remaining`, else `ValidationFailed` | the whole transaction rolls back — no stock, no payable, no status change |
| **B** | `qty > 0` only | commits in full; stock and payable reflect what actually arrived |
| **C** | `qty <= remaining × (1 + tolerance)`, tolerance on `BusinessProfile` | commits within tolerance, rolls back beyond it |

**Nothing else in the design differs between them** — same models, same boundary, same audit, same PO transition. That was deliberate: it kept BD-2 a business decision rather than an architectural one, and it is why the ruling below required no schema change.

#### The ruling — Option C

**The acceptance predicate**, evaluated **independently for every purchase-order line**:

```
Σ received_for_this_po_line (including this receipt)
    <= po_line.quantity_ordered × (1 + tolerance_percent / 100)
```

- **Cumulative, not per-receipt.** The sum spans every `goods_receipt_line` already posted against that PO line plus the quantity now being received. A per-receipt test would let three receipts of 40% each pass individually and overshoot together.
- **Per line, never per order.** A shortfall on one line must not finance an overage on another; that would let a receipt pass while both lines were wrong.
- **`tolerance_percent` is read from `BusinessProfile`**, alongside the other configurable values, as **`over_receipt_tolerance_percent`** (`PercentField`).
- **The default is `0`.** An unconfigured system rejects every over-receipt — the safest commercial position, and the one that can be relaxed later without a migration. **No figure is hard-coded**; 5% is not a default and appears nowhere.
- **Supplier-specific and product-specific tolerances are deliberately not modelled.** One system-wide value until a real need argues otherwise — see *Future differentiation*.

| Case | Result |
| --- | --- |
| `Σ received < ordered` | **valid.** PO moves to `PARTIALLY_RECEIVED` — FR-PUR-013, unchanged |
| `Σ received == ordered` | valid. PO moves to `RECEIVED` |
| `ordered < Σ received <= ordered × (1 + t/100)` | valid, within tolerance. PO moves to `RECEIVED` |
| `Σ received > ordered × (1 + t/100)` | **`ValidationFailed`. The entire receipt is rejected** |

> **Rejection is whole-document, not per-line.** One line beyond tolerance fails the receipt: **no GRN, no `StockMovement`, no supplier ledger entry, no PO status change, no audit row.** `transaction.atomic` is the entire mechanism — there is no compensation and no partial post. A delivery is accepted as it stands or not at all, which is also how it works on a loading bay.

**Variance is derived, never stored** — `quantity_ordered − Σ quantity_received` per PO line. A stored variance would be a second source of truth for a subtraction, which N-03/E-01 forbid for the same reason they forbid a cached balance. **Under-receipt needed no ruling and is built regardless**: it is `PARTIALLY_RECEIVED`, and FR-PUR-013 already requires it.

#### Duplicate submission — what the predicate does and does not cover

D5 has no `client_uuid` (§2.1) because no offline surface originates a purchase, so a repeated
POST creates a **second** goods receipt. **The cumulative per-line predicate is the guard, and
no idempotency mechanism is added in Stage 3.** Its coverage is asymmetric, and stating that
precisely is better than assuming it is total:

- **Covered.** Any duplicate that would push a line past `ordered × (1 + t/100)` is refused —
  at the default `t = 0` that is *every* duplicate of a completing receipt, and at any
  tolerance below 100% it is every duplicate of a full-quantity receipt.
- **Not covered, and cannot be.** A duplicated **partial** receipt that still fits inside the
  tolerance is accepted, because it is **arithmetically indistinguishable from the second
  delivery FR-PUR-013 explicitly permits.** No predicate over quantities can separate the two;
  only an identity could, and D5 deliberately has none.

**Mitigation is the confirm screen**, which shows *ordered / already received / remaining* per
line before the receipt is posted. That residual is accepted for Stage 3 and recorded here so
it is a known limit rather than a later discovery. **Only implementation evidence that the
predicate fails a case it was expected to cover reopens this; nothing else does.**

#### Future differentiation — **NOT IMPLEMENTED**

Receiving history per supplier and per product could later feed a derived **"Receiving
Intelligence / Supplier Reliability"** layer — habitual short-shippers, chronic over-shippers,
lines that never arrive complete.

**This is a non-implemented future capability. Nothing in v1.0 provides it**, and nothing in
Stage 3 may be read as a step toward it. Two constraints bind whoever builds it:

1. It **must be derived from transaction history** — `purchase_order_line` and
   `goods_receipt_line` already hold everything required.
2. It **must not become a second source of truth.** No reliability score column, no cached
   fulfilment rate, no per-supplier tolerance written back onto `supplier`. The rule that
   forbids `outstanding_balance` and a stored variance (N-03 / E-01) applies unchanged, and it
   is precisely why supplier-specific tolerance is excluded above.

### D-PUR-5 — FR-PUR-004, with the semantics named

| | Measure | The question it answers | Source |
| --- | --- | --- | --- |
| **V1** | **Fulfilment velocity** | *"How fast are we physically moving this product?"* | `StockMovement` ISSUE, source `DELIVERY` |
| **V2** | **Revenue velocity** | *"How fast are we earning from this product?"* | invoice lines |
| **V3** | **Demand velocity** | *"How fast are customers asking for it?"* — **includes sales lost to stockouts** | `SalesOrderLine` |

**Recommendation: V3 — BUSINESS CONFIRMATION REQUIRED.** You reorder against what customers want, not against what you happened to be able to ship; a stockout suppresses V1 and V2 precisely when reordering matters most.

Four dimensions remain open regardless of basis: **trailing window** (30/60/90 days) · **units or packs** · **cancellation and return handling** · **zero-sales display** (`0`, blank, or *"no data"*).

**If confirmation is delayed, build the screen without the velocity column.** The stock-position half is a single call to `inventory.selectors.on_hand_for()` and is not blocked.

### D-PUR-6 — D5 is v1.0 scope. DV-6's verdict is superseded **for D5 only**.

**Ruled 2026-08-25.** Authorises the amendment applied in `02A` §14; `04` follows consequentially. Resolves **CD-1**.

1. **D5 Purchase & Supplier Management is v1.0 product scope.** `01` §7.2 lists it among the v1.0 functional domains and §7.4 places it in the v1.0 release; the business confirmed that placement on 2026-08-25.
2. **DV-6's verdict is superseded as it applies to D5.** DV-6's row is **not** edited — it is a dated recommendation and remains readable as one, exactly as `02A` §13 leaves §6.1 in place. Its reasoning is not repudiated; `02A` §14.3 records what changed.
3. **`02A` is where membership changes.** A design review may authorise an amendment but may not make one — the rule D-M9-1 established for `02`, applied to `02A`.
4. **`04` is amended consequentially**, its Scope line citing `02A` §14.
5. **The remainder of DV-6 is preserved.** Reason-coded stock-in is neither removed nor deprecated (§1).
6. **DV-9 is untouched** — *"No approval workflow in Edition 1"* stands, which is why FR-PUR-014 remains deferred pending DR-10 and BD-4. **DV-8 is untouched** — `purchase_return` stays Edition 2 and is outside D5's v1.0 scope.
7. **Effort is acknowledged:** `02A` §8 prices purchasing and the supplier ledger at **4.5 units, 16%** of the Edition-1 estimate. That returns to the v1.0 budget in full.

### D-PUR-7 — D5 reuses `StockMovement.Type.RECEIPT`. No `GOODS_RECEIPT` movement type is created.

**Ruled 2026-08-25.** Supersedes `04`'s *"Future evolution"* note at `stock_movement`. Resolves **CD-2**.

Goods receipt writes a movement of the **existing** `Type.RECEIPT`, carrying `source_document_type = 'GOODS_RECEIPT'` and `source_document_id = <GoodsReceipt.pk>`. **No new movement type, no CHECK migration, no schema change to `stock_movement`.**

**Why this does not weaken provenance, and does not invent a second stock-in mechanism:**

- **There is exactly one inbound service** — `inventory.services.receive_stock()` — and D5 calls it. D5 writing `StockMovement` directly is forbidden and enforced by an adversarial AST test (§9, FR-PUR-007). A distinct `GOODS_RECEIPT` *type* is what would create a second mechanism: two movement types for one physical event, *"goods came in"*.
- **It uses the field the corpus designated for it.** `02A` §11 EP-8: *"Stock movement `sourceDocumentType` — Enumerated, extensible — **Purchase orders**, transfers, structured returns"*. Purchase orders are the first example that extension point names.
- **The guarantee is stronger after D5.** Today every receipt is reason-coded and unsourced. After D5, purchase-borne stock carries a document reference that is indexed (`ix_stock_mv_source`), constrained against half-references, and asserted by test: every `GOODS_RECEIPT`-sourced movement references a real GRN.
- **A second type is the riskier change.** It needs a CHECK migration on what `04` calls *"the least reversible artefact in the project"* and splits every query filtering `movement_type='RECEIPT'`. Two types for one event is how a sign convention or a balance query drifts silently.

### D-PUR-8 — `po_number` is allocated at **creation**, not at issue.

**Ruled 2026-08-26**, on the product owner's decision, reversing the engineering proposal.

The Stage 2 design proposed allocating at issue so that an abandoned draft consumed no
document number, leaving `po_number` nullable with a partial unique index. **That was
refused, and the reasoning given is stronger than the reasoning it replaced:**

1. **A draft PO is already a business document** and needs a stable reference.
2. **Users need a human-readable identifier for drafts** — `#pk` is not one.
3. **Audit, support and debugging benefit from identity before issue.** A PO that is
   discussed on the phone before it is issued must be nameable.
4. **PO numbers are internal references, not a statutory series** — so gaps are permitted and
   an abandoned draft costing a number costs nothing.

**Consequences, all simplifications:**

- `po_number` is `NOT NULL, unique` from the first row. **No partial-unique-on-null
  mechanism is needed** and none is built.
- Allocation happens inside `create_purchase_order`'s existing atomic block, using the
  project's reference-numbering pattern — `SELECT nextval('purchase_order_number_seq')`,
  lock-free, gaps permitted, exactly as `receivables.services._next_payment_number` does and
  explicitly **not** as `billing.services.allocate_number` does. `receivables/services.py:52`
  draws that line: a row lock is for a gapless statutory series, and a PO is not one.
- **The number survives amendment and issue unchanged.** `issue_purchase_order` never
  allocates — the only thing that could produce a second number is a second *creation*.
- **Re-issue is still guarded by the lifecycle, not by the number.** `DRAFT → ISSUED` is the
  only edge into `ISSUED`; a second attempt raises `INVALID_TRANSITION` from
  `ALLOWED_TRANSITIONS`. That guard is unchanged by this ruling and remains the double-submit
  protection.

### D-PUR-9 — FR-PUR-010 and FR-PUR-011 move into Stage 3. The receipt transaction cannot be split.

**Ruled 2026-08-27.**

Stage 3's central invariant is **one** atomic transaction:

```
GoodsReceipt → GoodsReceiptLine → inventory receipt → supplier payable
             → PurchaseOrder status transition → audit
```

`record_goods_receipt` cannot be written twice. Shipping it at Stage 3 without the payable
and retrofitting one at Stage 4 would create a period in which **stock increases and no
liability is recorded** — the precise stock/payable mismatch the atomic boundary exists to
prevent, and the reason §3.4 put both in one block from the first draft. The staging table,
not the boundary, was wrong.

**Stage 3 now closes FR-PUR-006, 007, 008, 009, 010, 011, 013.**
**Stage 4 is FR-PUR-012 and FR-PUR-015.**

**Nothing newly blocking is pulled forward.** BD-1 governs *payment allocation* (FR-PUR-012)
and the supplier ledger is identical under either of its options — §5.1 records that
explicitly. FR-PUR-011 was never blocked; it was only mis-staged.

### D-PUR-10 — `inventory.services.receive_stock` is widened to accept no reason code.

**Ruled 2026-08-27.** A narrow enabling seam correction, **not a new inventory feature.**

```
reason_code: ReasonCode          →    reason_code: ReasonCode | None = None
```

**Why it is required.** `record_movement` beneath it already implements BR-007 correctly —
*"A stock movement needs a source document **or** a reason code"* — and accepts either. The
wrapper is **narrower than the thing it wraps**: its parameter is required and typed
`ReasonCode`, so a document-backed receipt cannot be expressed through it, and `mypy` is
blocking (stage 6) so `reason_code=None` will not compile past the gate.

**Behaviour for every existing caller is unchanged**: all of them pass a reason code, and
`record_movement`'s validation, direction check and constraint are untouched.

**The call chain is mandatory and is asserted, not merely intended:**

```
purchasing.services.record_goods_receipt
  → inventory.services.receive_stock          (OWNER check, abs(), Type.RECEIPT)
    → inventory.services.record_movement      (the single write path, BR-007)
      → _resolve_source → SOURCE_DOCUMENT_REGISTRY[GoodsReceipt] = "GOODS_RECEIPT"
```

**Four things this ruling explicitly forbids:**

1. bypassing `receive_stock`
2. calling `record_movement` directly from `purchasing`
3. inventing a `GOODS_RECEIPT` **reason code** — that would put a reason code on a
   document-backed movement and muddy the very distinction BR-007 draws
4. adding a `GOODS_RECEIPT` **movement type** — D-PUR-7, unchanged

**Registration follows the existing R-2 mechanism**, copied from `fulfilment/registry.py`:
a `purchasing/registry.py` assigning `SOURCE_DOCUMENT_REGISTRY[GoodsReceipt] = "GOODS_RECEIPT"`,
imported from `PurchasingConfig.ready()`. The dependency points the right way — `purchasing`
knows `inventory`, and `inventory` continues to know nothing above it. **The type string comes
from the registry, never from a literal at a call site**, and `_resolve_source` refuses any
unregistered model.

---

## 5. Independent review — reconciliation

### 5.1 Approved and carried unchanged

The independent review of 2026-08-18 concurred with, and this document retains: pattern reuse across models, fields, state machines and services · **stock provenance via `receive_stock()` with direct `StockMovement` writes forbidden and enforced by an adversarial AST test** · the atomic `record_goods_receipt` boundary · the immutable derived-balance supplier ledger · a new `purchasing` app with the supplier ledger extending `ledger` · **no `client_uuid`** · **no speculative REST API** · sufficiency of the PO line snapshots · `PROTECT` foreign keys preserving historical integrity · the partial unique index on `is_preferred`.

### 5.2 Two deliberate divergences

Recorded rather than silently adopted, following `M9_Design_Review` §6's treatment of an independent review as **corroboration, not authority**.

**Divergence 1 — the review's Critical Defect #1 rests on a role this system does not have.**

It argues from *"A/P clerks frequently need to pay specific, recent, high-value GRNs… while deliberately leaving older, disputed items unpaid"* and concludes that Option B must be the **default**.

The repository seeds **four roles: `OWNER`, `SALESMAN`, `DELIVERY`, `RETAILER`.** There is no A/P clerk, no accountant and no purchasing role. `inventory/services.py:205` records why: *"Owner only in V1: there is no separate warehouse role… the client confirmed one person does everything."* Supplier payments would be recorded by the owner.

This does not settle the question — an owner may still want to pay a specific GRN. It does mean the review's confidence (*"almost certainly"*, *"likely to fail UAT"*) is unsupported by anything in this corpus, and that defaulting to B on that basis would adopt an assumption about a business we can simply ask. **Ruling: neither default. Ask (BD-1).**

**Divergence 2 — over-receipt.**

**Settled 2026-08-27 by D-PUR-4, and the review's instinct was half right.** It recommended **rejection** as the default, on the sound asymmetry that relaxing a rule is cheaper than tightening one. That is a **technical** argument for a **commercial** decision, and it presumes the current behaviour is rejection when in fact no behaviour exists at all. **Ruling: no default; three options; blocked (BD-2).**

---

## 6. DR-10 approval interface contract — required, not implemented

D5 **consumes** this contract. D5 does not define, own or implement it.

**Request semantics.** A single shared entry point, called from within the issuing service's transaction, taking the document, the actor and a threshold key. It answers one question: *may this document proceed?* It is a **precondition, never a post-issue flag** — a PO that reached `ISSUED` before approval has already escaped the control.

**State machine.** `PENDING → APPROVED` · `PENDING → REJECTED`. Terminal on both. Held on a shared `core.Approval` (`entity_type`, `entity_id`, `requested_by`/`_at`, `decided_by`/`_at`, `decision`, `reason`), generic over documents — **one table, not one per domain**.

**Behaviour the caller must be able to rely on**, each outcome distinguishable:

| Outcome | Caller sees | PO result |
| --- | --- | --- |
| Below threshold | proceed | `ISSUED` |
| `PENDING` | a **distinct, non-exception** signal | stays `DRAFT`; an approval request now exists |
| `APPROVED` | proceed | `ISSUED` |
| `REJECTED` | a domain exception | stays `DRAFT`; reason recorded |

> **`PENDING` must not be an exception.** *"Awaiting a decision"* is a normal outcome, and modelling it as an error forces every caller into exceptions for control flow.

**Threshold lookup.** From `BusinessProfile`, beside the other configurable values, by key — never a constant in `purchasing`, never a purchase-specific settings table.

**Atomicity.** The approval record and the state change it authorises commit or roll back together, in the caller's transaction — the rule `record_audit` already follows.

**Audit.** Request and decision are both `record_audit` events carrying actor, entity and reason, written in the same transaction.

**How `issue_purchase_order` consumes it.** One call, at one point, and nothing else in `purchasing` knows approvals exist:

```
issue_purchase_order(actor, purchase_order)          @transaction.atomic
    guard: status is DRAFT and at least one line exists
    │
    ├── decision = core.services.request_approval(    ← THE ONLY CALL SITE
    │       actor=actor, entity_type="purchase_order", entity_id=po.pk,
    │       threshold_key="purchase_approval_threshold", amount=po.total_amount)
    │
    ├── BELOW_THRESHOLD → continue
    ├── APPROVED        → continue
    ├── PENDING         → return po, still DRAFT. Not an exception
    └── REJECTED        → raise ApprovalRejected. Still DRAFT
    │
    _transition(DRAFT → ISSUED); set issued_at / issued_by
    record_audit(Action.ISSUE)
```

**The gate sits inside the atomic block and before the transition**, so a pending or rejected PO changes no status and the approval record rolls back with whatever it refused. `po_number` is unaffected either way — it was allocated at creation (D-PUR-8), so an approval outcome can never consume or waste one.

| Outcome | PO status after | Caller sees |
| --- | --- | --- |
| `BELOW_THRESHOLD` · `APPROVED` | `ISSUED` | the issued PO |
| `PENDING` | **`DRAFT`** | the unchanged PO; an approval request now exists |
| `REJECTED` | **`DRAFT`** | `ApprovalRejected`, carrying the reason |

> **BD-4 is required at exactly one point: before `request_approval` may be called at all.** Until BD-4 rules whether DR-10 is in v1.0 and what the threshold is, **that call site does not exist.** Stage 2 ships `issue_purchase_order` with its guard, its transition and its audit row and **no approval call — not a placeholder, not a stub, not a `TODO` branch.** FR-PUR-014 stays open; adding it later changes one function and no other line.

---

## 7. Business decisions required before implementation

| # | Decision | Question | Blocks | Owner |
| --- | --- | --- | --- | --- |
| **BD-1** | Supplier payment allocation | *Must a supplier payment be explicitly allocated by a user to specific outstanding receipt(s), or is deterministic oldest-outstanding-first settlement acceptable?* | FR-PUR-012, FR-PUR-015 | Business owner |
| ~~**BD-2**~~ | ~~Over-receipt policy~~ | **CLOSED 2026-08-27 — Option C.** Configurable per-line tolerance, `BusinessProfile.over_receipt_tolerance_percent`, default `0`. See **D-PUR-4** | — | ~~Business owner~~ |
| **BD-3** | Sales velocity | Confirm **V3 demand velocity**; then window, units-or-packs, cancellation/return handling, zero-sales display | FR-PUR-004 | Business owner |
| **BD-4** | PO approval threshold | Is DR-10 in v1.0 at all? If so, the threshold value and who decides | FR-PUR-014 (`S`) | Product Architect + Business owner |
| **BD-5** | Supplier opening balances | Do existing supplier payables migrate at go-live, as customer opening balances did (M6-11)? | data migration, not code | Business owner |

> **BD-5 was raised by neither review.** The customer ledger has a one-`OPENING`-per-customer constraint and a go-live import behind it. If the distributor has existing payables, the supplier ledger needs the same — and it is far cheaper to design now than to retrofit onto a live ledger.

---

## 8. Dependency and blocking matrix

| Req | Stage | Blocked by | Buildable now? |
| --- | :-: | --- | :-: |
| FR-PUR-001 Supplier master | 1 | — | **yes** |
| FR-PUR-002 Product ↔ Supplier | 1 | 001 | **yes** |
| FR-PUR-003 PO + lines | 2 | 001 | **yes** |
| FR-PUR-005 Lifecycle | 2 | 003 | **yes** — transitions are independent of approval |
| — `issue_purchase_order` | 2 | **DR-10 contract (§6)** | **no** — contract first |
| FR-PUR-006 Goods receipt | **3** | 003, 005 | **yes** — BD-2 closed by D-PUR-4 |
| FR-PUR-009 Receipt guards | **3** | 005, 006 | **yes** |
| FR-PUR-013 Multiple receipts | **3** | 006 | **yes** |
| FR-PUR-007 Stock provenance | **3** | 006, **D-PUR-10 seam** | **yes** — enablers exist and are constraint-enforced |
| FR-PUR-008 Variance | **3** | 006 | **yes** — predicate fixed by D-PUR-4; variance itself is derived |
| FR-PUR-011 Supplier ledger | **3** *(was 4 — D-PUR-9)* | 001 | **yes** — unaffected by BD-1 |
| FR-PUR-010 Payable from receipt | **3** *(was 4 — D-PUR-9)* | 006, 011 | **yes** |
| FR-PUR-012 Supplier payment | 4 | 011, **BD-1** | **no** |
| FR-PUR-015 Reporting | 4 | 005, 008, 011, **BD-1** | **no** — BD-1 only |
| FR-PUR-004 Velocity | — | **BD-3** | **no** — stock half yes |
| FR-PUR-014 Approval | — | **DR-10**, **BD-4** | **no** |

**Stage 1 is unblocked by everything above.**

---

## 9. Acceptance matrix — the 13 implementable requirements

| ID | Test that closes it | Tier |
| --- | --- | --- |
| 001 | unit: create/update supplier, code uniqueness, deactivation. integration: `webadmin` supplier CRUD round-trip | unit + integration |
| 002 | unit: associate/dissociate; **at most one preferred per product**, proven by constraint violation | unit |
| 003 | unit: PO with lines; snapshot fields frozen against a later product rename. integration: form round-trip | unit + integration |
| 005 | unit, table-driven over **every** allowed and forbidden transition, including `CANCELLED` unreachable from `PARTIALLY_RECEIVED` | unit |
| 006 | unit: receipt against an `ISSUED` PO writes GRN + lines | unit |
| 007 | **adversarial**: after a receipt a `RECEIPT` `StockMovement` exists with `source_document_type='GOODS_RECEIPT'` and the matching id; **and no D5 code writes `StockMovement` directly** (AST test, mirroring `test_order_inventory_boundary.py`) | adversarial |
| 008 | unit, **table-driven over the D-PUR-4 predicate**: under, exact, within tolerance, beyond tolerance; cumulative across two receipts; per-line independence; default tolerance `0` rejects any overage | unit + integration |
| 009 | unit: receipt against `DRAFT` and against `CANCELLED` both rejected | unit |
| 010 | unit: a receipt creates exactly one `SupplierLedgerEntry`, correct sign, correct source document | unit |
| 011 | **adversarial**: raw SQL `UPDATE`/`DELETE` on `supplier_ledger_entry` refused; balance ≡ `SUM(amount)` over randomised seeds — port `test_financial_immutability.py` and the `05` §5A.7 invariant | adversarial |
| 012 | unit: payment and reversal; the ledger reflects both. integration: `webadmin` payment round-trip | unit + integration |
| 013 | unit: **two** receipts against one PO → `PARTIALLY_RECEIVED` then `RECEIVED`; totals correct; no double stock | unit |
| 015 | unit: report selectors. integration: **three-way wiring — menu, route, CSV** — closing TD-29's gap for this report | unit + integration |

> **One cross-cutting adversarial test to add:** *stock may increase only through a document or a reason code, and a `GOODS_RECEIPT` source must reference a real GRN.* That is §1's finding turned into a contract.

---

## 10. Consequences to handle before Stage 1

1. **`import-linter` — 3 contracts, currently 144 files / 271 dependencies.** A new app changes the graph. `purchasing` may import `core`, `catalogue`, `inventory`, `ledger`, `identity`; **nothing may import `purchasing`**. The contracts must place the new package explicitly or stage 5 of `make verify` fails.
2. **`INSTALLED_APPS`** gains `purchasing`. `reporting` must stay ownerless — four AST tests assert it owns no models.
3. **TD-29 is live here.** *"Nothing asserts a newly added report is wired into `REPORT_MENU`, the API router and the CSV path."* FR-PUR-015 adds reports; this is the eighth-report scenario TD-29 predicted.
4. **Documentation before schema.** `04_Database_Design.md` gains the tables before the migration is written, per the project workflow.

---

## 11. Sign-off

| # | Item | Owner | State |
| --- | --- | --- | --- |
| 1 | §3 architecture — entities, lifecycle, invariants, boundaries | All | ☐ |
| 2 | §4 D-PUR-1 … D-PUR-5 | All | ☐ |
| 3 | §6 DR-10 interface contract | Product Architect | ☐ |
| 4 | §7 BD-1 … BD-5 tabled with the business | Business owner | ☐ |
| 5 | §8 staging and blocking matrix | Engineering | ☐ |
| 6 | This document accepted as the design of record | All | ☐ |

> **Stage 1 may begin once items 1, 2 and 5 are signed.** BD-1…BD-5 and DR-10 block later stages, not the supplier master.
