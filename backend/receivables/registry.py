"""R-2 registration: ``Payment`` is a permitted ledger source document.

The third and final Edition 1 member of ``ledger.services.SOURCE_DOCUMENT_REGISTRY``,
after ``billing`` registered ``Invoice`` and ``CreditNote`` at M5. Registration lives here
so ``ledger`` knows nothing about anything above it.
"""

from __future__ import annotations

from ledger.services import SOURCE_DOCUMENT_REGISTRY
from receivables.models import Payment

SOURCE_DOCUMENT_REGISTRY[Payment] = "PAYMENT"
