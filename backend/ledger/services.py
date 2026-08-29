"""Ledger business rules.

**This module is the only writer of CustomerLedgerEntry and SupplierLedgerEntry.** Nothing
else in the codebase may create one — that single constraint is what makes BR-005
enforceable rather than aspirational, exactly as ``inventory.services`` is the only writer
of ``StockMovement``.

The two ledgers share this module, one source-document registry and one amount validator.
They are the same mechanism pointed in opposite directions: receivables record what is owed
to us, payables what we owe. Splitting them would have duplicated the immutability rule, the
derived-balance rule and R-2 (D-PUR-3).

Under R-3 a ledger entry writes **no audit row**: it is immutable and already carries
actor, timestamp, amount, narration and its source document. An audit row would
duplicate a record that cannot change.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import models

from core.exceptions import ValidationFailed
from core.fields import to_money
from ledger.models import CustomerLedgerEntry, SupplierLedgerEntry

logger = logging.getLogger("districore.ledger")

# --------------------------------------------------------------------------------
# R-2 — permitted source documents.
#
# 04 T-22 gives source_document_type/id no foreign key, because they point at three
# different tables. The compensating control is this registry plus the rule that services
# accept a validated model INSTANCE, never a raw (type, id) pair.
#
# Populated by the owning modules at import time: `billing` registers Invoice and
# CreditNote (M5); `receivables` registers Payment (M6). Registration lives with the
# model's own module so this one imports nothing from above it.
# --------------------------------------------------------------------------------
SOURCE_DOCUMENT_REGISTRY: dict[type[models.Model], str] = {}


def _resolve_source(document: Any) -> tuple[str, int | None]:
    """Validate a source document instance and return its (type, id) pair.

    The whole of R-2: the caller must possess the thing, not merely name it.
    """
    if document is None:
        return "", None
    model = type(document)
    if model not in SOURCE_DOCUMENT_REGISTRY:
        raise ValidationFailed(
            f"{model.__name__} is not a permitted ledger source document.",
            errors=[
                {
                    "field": "source_document",
                    "code": "UNREGISTERED_SOURCE",
                    "message": model.__name__,
                }
            ],
        )
    if getattr(document, "pk", None) is None:
        raise ValidationFailed(
            "A ledger source document must be saved before it can be referenced.",
            errors=[{"field": "source_document", "code": "UNSAVED", "message": model.__name__}],
        )
    return SOURCE_DOCUMENT_REGISTRY[model], document.pk


#: Sign required per entry type, mirroring ``ck_cle_sign``. Checked here so the caller
#: gets a usable error instead of an IntegrityError; the constraint remains the guarantee.
_SIGN_RULES: dict[str, str] = {
    CustomerLedgerEntry.Type.INVOICE: "+",
    CustomerLedgerEntry.Type.OPENING: "+",
    CustomerLedgerEntry.Type.PAYMENT: "-",
    CustomerLedgerEntry.Type.CREDIT_NOTE: "-",
    CustomerLedgerEntry.Type.WRITE_OFF: "-",
}

#: The payables equivalent, mirroring ``ck_sle_sign`` (D-PUR-3). Deliberately a **second
#: table rather than extra keys in the first**: both enums spell "PAYMENT" and "OPENING",
#: so one shared dict keyed by bare strings would silently merge two accounting vocabularies
#: and the first divergent code added to either side would be validated against the wrong one.
#:
#: `OPENING` is absent, and its absence is the rule: `04` T-34 signs it *"as the opening
#: position requires"*, because an opening position with a supplier can legitimately be a
#: credit. `dict.get` returns `None` for it, which means no sign check — the same way
#: `ADJUSTMENT` is untested on the customer side.
_SUPPLIER_SIGN_RULES: dict[str, str] = {
    SupplierLedgerEntry.Type.GOODS_RECEIPT: "+",
    SupplierLedgerEntry.Type.PAYMENT: "-",
    SupplierLedgerEntry.Type.DEBIT_NOTE: "-",
}


def _validated_amount(
    *,
    entry_type: str,
    amount: Decimal | str | int,
    valid_types: list[str],
    sign_rules: dict[str, str],
) -> Decimal:
    """Type, non-zero and sign checks shared by both ledgers.

    Extracted when the supplier ledger arrived (D5 Stage 3). The rules are identical on
    both sides — only the vocabulary differs — and two copies would have been two places
    for the zero-amount rule to drift.
    """
    if entry_type not in valid_types:
        raise ValidationFailed(
            "Unknown ledger entry type.",
            errors=[{"field": "entry_type", "code": "INVALID", "message": str(entry_type)}],
        )

    money = to_money(amount)
    if money == 0:
        raise ValidationFailed(
            "A ledger entry cannot be zero.",
            errors=[{"field": "amount", "code": "ZERO", "message": "0.00"}],
        )

    required = sign_rules.get(entry_type)
    if required == "+" and money < 0:
        raise ValidationFailed(
            f"A {entry_type} entry increases what is owed and must be positive.",
            errors=[{"field": "amount", "code": "SIGN", "message": str(money)}],
        )
    if required == "-" and money > 0:
        raise ValidationFailed(
            f"A {entry_type} entry reduces what is owed and must be negative.",
            errors=[{"field": "amount", "code": "SIGN", "message": str(money)}],
        )
    return money


def record_entry(
    *,
    actor: Any,
    customer: Any,
    entry_type: str,
    amount: Decimal | str | int,
    narration: str,
    entry_date: date | None = None,
    source_document: Any = None,
    sales_order: Any = None,
) -> CustomerLedgerEntry:
    """Append one entry to the ledger. The single write path.

    Deliberately takes **no lock**. Two concurrent entries for one customer do not
    contend: appends never conflict and ``SUM`` sees both. Concurrency safety here is
    structural, not defensive — the same property the stock ledger has, for the same
    reason.

    **The caller supplies a signed amount and the sign must agree with the type.** The
    service does not helpfully negate a positive payment: a sign error is a symptom of a
    call site that has the accounting backwards, and silently correcting it hides that.
    """
    amount = _validated_amount(
        entry_type=entry_type,
        amount=amount,
        valid_types=CustomerLedgerEntry.Type.values,
        sign_rules=_SIGN_RULES,
    )

    source_type, source_id = _resolve_source(source_document)

    entry = CustomerLedgerEntry(
        customer=customer,
        entry_date=entry_date or date.today(),
        entry_type=entry_type,
        amount=amount,
        sales_order=sales_order,
        source_document_type=source_type,
        source_document_id=source_id,
        narration=narration[:255],
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    entry.save()

    logger.info(
        "ledger_entry",
        extra={
            "entry_id": entry.pk,
            "customer": customer.code,
            "entry_type": entry_type,
            "amount": str(amount),
        },
    )
    return entry


def record_supplier_entry(
    *,
    actor: Any,
    supplier: Any,
    entry_type: str,
    amount: Decimal | str | int,
    narration: str,
    entry_date: date | None = None,
    source_document: Any = None,
) -> SupplierLedgerEntry:
    """Append one entry to the supplier ledger. The single write path.

    The payables twin of :func:`record_entry`, and identical in every property that
    matters: no lock (appends do not contend), a caller-supplied signed amount that must
    agree with the type, and **no audit row** (R-3).

    **It has no `sales_order` parameter.** The customer version carries one because a
    receivable is traceable to the order that created it; a payable is traceable to the
    purchase order only *through* the goods receipt, which is already the source document.
    A second, redundant pointer would be a second thing to keep consistent.

    Takes no transaction of its own — it runs inside the caller's, so a receipt that
    fails after the ledger write leaves no liability behind.
    """
    amount = _validated_amount(
        entry_type=entry_type,
        amount=amount,
        valid_types=SupplierLedgerEntry.Type.values,
        sign_rules=_SUPPLIER_SIGN_RULES,
    )

    source_type, source_id = _resolve_source(source_document)

    entry = SupplierLedgerEntry(
        supplier=supplier,
        entry_date=entry_date or date.today(),
        entry_type=entry_type,
        amount=amount,
        source_document_type=source_type,
        source_document_id=source_id,
        narration=narration[:255],
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    entry.save()

    logger.info(
        "supplier_ledger_entry",
        extra={
            "entry_id": entry.pk,
            "supplier": supplier.code,
            "entry_type": entry_type,
            "amount": str(amount),
        },
    )
    return entry
