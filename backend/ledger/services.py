"""Ledger business rules.

**This module is the only writer of CustomerLedgerEntry.** Nothing else in the codebase
may create one — that single constraint is what makes BR-005 enforceable rather than
aspirational, exactly as ``inventory.services`` is the only writer of ``StockMovement``.

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
from ledger.models import CustomerLedgerEntry

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
    if entry_type not in CustomerLedgerEntry.Type.values:
        raise ValidationFailed(
            "Unknown ledger entry type.",
            errors=[{"field": "entry_type", "code": "INVALID", "message": str(entry_type)}],
        )

    amount = to_money(amount)
    if amount == 0:
        raise ValidationFailed(
            "A ledger entry cannot be zero.",
            errors=[{"field": "amount", "code": "ZERO", "message": "0.00"}],
        )

    required = _SIGN_RULES.get(entry_type)
    if required == "+" and amount < 0:
        raise ValidationFailed(
            f"A {entry_type} entry increases what is owed and must be positive.",
            errors=[{"field": "amount", "code": "SIGN", "message": str(amount)}],
        )
    if required == "-" and amount > 0:
        raise ValidationFailed(
            f"A {entry_type} entry reduces what is owed and must be negative.",
            errors=[{"field": "amount", "code": "SIGN", "message": str(amount)}],
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
