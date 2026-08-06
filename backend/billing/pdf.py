"""Invoice PDF rendering (D-5, FR-BIL-017).

**Generated on first request, then cached forever.** The three options were weighed in
`M5_Design_Review.md` §5:

* eager at issue — preserves the rendering exactly, but ~3.6 GB/year of storage against
  a volume where `04` §18 already identifies media as the binding constraint;
* lazy every time — free, but **if the template changes, an old invoice re-renders
  differently from the paper the retailer is holding**;
* render once on demand and keep it — any PDF that was ever delivered is preserved
  byte-for-byte, and invoices nobody downloads cost nothing.

The legal document is the *data*, all of which is snapshotted on the invoice row
(FR-BIL-008). The PDF is a rendering — but a rendering that was handed to someone must
never change, which is why the database refuses to replace one (migration 0002).

Rendering is deliberately **outside** the issue transaction (F-7): a failed render must
not roll back an invoice that is legally valid without it.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.template.loader import render_to_string

from billing.models import Invoice
from billing.selectors import invoice_lines
from core.media import PURPOSE_INVOICE_PDF, store_generated
from core.models import MediaFile

logger = logging.getLogger("districore.billing")


def render_invoice_html(invoice: Invoice) -> str:
    """The invoice as HTML. **One template, two outputs** — this is also the web view.

    Every value comes from the invoice and its lines, never from a join to current
    master data (FR-BIL-008, M5-2).
    """
    return render_to_string(
        "billing/invoice_document.html",
        {
            "invoice": invoice,
            "lines": invoice_lines(invoice),
            "intra_state": invoice.igst_amount == 0,
        },
    )


def _render_pdf_bytes(invoice: Invoice) -> bytes:
    """HTML to PDF. Imported lazily so a missing native library cannot break startup."""
    from weasyprint import HTML

    return HTML(string=render_invoice_html(invoice)).write_pdf()  # type: ignore[no-any-return]


def invoice_pdf(*, actor: Any, invoice: Invoice) -> MediaFile:
    """Return this invoice's PDF, rendering it once if it does not exist yet.

    Concurrent first requests are serialised on the invoice row, so exactly one
    rendering is stored and both callers receive it. Without the lock two renders would
    race and the second would be refused by the database — correct, but a 500 for a user
    who did nothing wrong.
    """
    if invoice.pdf_media_id:
        return invoice.pdf_media

    content = _render_pdf_bytes(invoice)

    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if locked.pdf_media_id:
            return locked.pdf_media  # another request won; its rendering is the record

        media = store_generated(
            content=content,
            relative_dir="invoice_pdf",
            filename=f"{locked.invoice_number.replace('/', '-')}.pdf",
            content_type="application/pdf",
            purpose=PURPOSE_INVOICE_PDF,
            actor=actor,
        )
        locked.pdf_media = media
        locked.save(update_fields=["pdf_media"])

    invoice.pdf_media = media
    invoice.pdf_media_id = media.pk
    logger.info(
        "invoice_pdf_rendered",
        extra={"invoice_id": locked.pk, "media_id": media.pk, "bytes": len(content)},
    )
    return media
