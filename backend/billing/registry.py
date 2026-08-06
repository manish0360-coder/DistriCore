"""R-2 registration: ``Invoice`` and ``CreditNote`` are permitted ledger sources.

Registration lives here rather than in ``ledger`` so the dependency points the right
way: ``billing`` knows about ``ledger`` (it sits below), and ``ledger`` knows nothing
about anything above it. ``receivables`` will register ``Payment`` the same way at M6.
"""

from __future__ import annotations

from billing.models import CreditNote, Invoice
from ledger.services import SOURCE_DOCUMENT_REGISTRY

SOURCE_DOCUMENT_REGISTRY[Invoice] = "INVOICE"
SOURCE_DOCUMENT_REGISTRY[CreditNote] = "CREDIT_NOTE"
