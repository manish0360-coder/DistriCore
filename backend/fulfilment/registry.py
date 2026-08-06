"""R-2 registration: ``Delivery`` is a permitted stock source document.

**This closes TD-16.** ``inventory.services.SOURCE_DOCUMENT_REGISTRY`` has been empty
since M2 — deliberately, because until M5 every movement was explained by a reason code
(DV-6) and the accept path had no production caller, only a monkeypatched test.

Registration lives here rather than in ``inventory`` so that the dependency points the
right way: ``fulfilment`` knows about ``inventory`` (03 §2.1 permits it), and
``inventory`` continues to know nothing about anything above it.
"""

from __future__ import annotations

from fulfilment.models import Delivery
from inventory.services import SOURCE_DOCUMENT_REGISTRY

SOURCE_DOCUMENT_REGISTRY[Delivery] = "DELIVERY"
