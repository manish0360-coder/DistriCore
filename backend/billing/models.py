"""Billing — the GST tax invoice and the credit note that corrects it.

**Everything in this module is immutable once issued** (N-04, E-02, M5-3). No service, no
admin screen and no management command may update or delete a row in ``invoice``,
``invoice_line``, ``credit_note`` or ``credit_note_line``. Correction is a new document.

Every displayed or printed value comes from the document's own row, never from a join to
current master data (FR-BIL-008, M5-2). That is what stops a price update rewriting
financial history — and it is why the seller and buyer identity are snapshotted even
though there is only ever one seller.
"""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from django.db import models

from core.fields import MoneyField, PercentField, QuantityField


def financial_year_for(on: date) -> str:
    """The Indian financial year containing ``on``, as ``2026-2027``.

    April to March. Document series do not continue across years (04 T-06), so this is
    the value that partitions them.
    """
    start = on.year if on.month >= 4 else on.year - 1
    return f"{start}-{start + 1}"


class NumberSeries(models.Model):
    """A gapless, per-financial-year document counter (04 T-06).

    **Why not a PostgreSQL SEQUENCE.** Sequences are explicitly *not* gapless — they are
    non-transactional by design, so a rolled-back transaction consumes a value
    permanently. Correct for surrogate keys; wrong for statutory document numbers, where
    a gap is a question from an auditor. A locked counter row is slower and correct, and
    correctness wins on a table that issues perhaps 200 rows a day.
    """

    class Key(models.TextChoices):
        INVOICE = "INVOICE", "Invoice"
        CREDIT_NOTE = "CREDIT_NOTE", "Credit note"

    series_key = models.CharField(max_length=20, choices=Key.choices)
    financial_year = models.CharField(max_length=9)
    prefix = models.CharField(max_length=20, blank=True)
    current_value = models.BigIntegerField(default=0)
    padding = models.SmallIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "number_series"
        ordering = ["series_key", "financial_year"]
        constraints = [
            models.UniqueConstraint(
                fields=["series_key", "financial_year"], name="uq_number_series"
            ),
            models.CheckConstraint(
                condition=models.Q(current_value__gte=0), name="ck_number_series_value"
            ),
            models.CheckConstraint(
                condition=models.Q(padding__gte=1, padding__lte=12), name="ck_number_series_padding"
            ),
        ]
        verbose_name_plural = "number series"

    def __str__(self) -> str:
        return f"{self.series_key} {self.financial_year}"

    def format(self, value: int) -> str:
        return f"{self.prefix}{value:0{self.padding}d}"


class DocumentImmutable(RuntimeError):
    """Raised on any attempt to modify or remove an issued financial document."""


class _ImmutableQuerySet(models.QuerySet):
    """Refuses bulk mutation. Each concrete document names itself in the message."""

    document_name = "document"

    def update(self, **kwargs: Any) -> int:
        raise DocumentImmutable(f"{self.document_name} is immutable once issued (M5-3, N-04)")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise DocumentImmutable(f"{self.document_name} is immutable once issued (M5-3, N-04)")


class _ImmutableDocument(models.Model):
    """Shared immutability behaviour for issued financial documents.

    Abstract, so it adds no table and no join. Composition would mean a mixin that
    cannot participate in ``Meta``; these four methods *are* the shared behaviour and
    there is nothing else to compose.

    ``_mutable_fields`` is the deliberate exception: cancellation is the one permitted
    change to an invoice (04 T-17), and it is a status transition with a reason, never a
    value edit.
    """

    _document_name: ClassVar[str] = "document"
    _mutable_fields: ClassVar[frozenset[str]] = frozenset()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            updating = set(kwargs.get("update_fields") or ())
            if not updating or not updating.issubset(self._mutable_fields):
                raise DocumentImmutable(
                    f"{self._document_name} is immutable once issued (M5-3, N-04). "
                    "Correct it with a credit note."
                )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise DocumentImmutable(f"{self._document_name} is never deleted (M5-3, N-04)")


class _MoneyDocument(_ImmutableDocument):
    """The seller/buyer snapshot and money columns shared by invoices and credit notes.

    Abstract: the two documents are statutorily distinct and are separate tables (04
    T-19), but they carry identical financial shape. Declaring it once means the GST
    split constraint, the rounding column and the snapshot fields cannot drift apart
    between them — which is exactly the drift that produces a credit note that does not
    reverse the invoice it references.
    """

    financial_year = models.CharField(max_length=9)
    customer = models.ForeignKey("customers.Customer", on_delete=models.RESTRICT, related_name="+")

    # --- seller snapshot (M5-2) -------------------------------------------
    # Four columns, for one seller. The GSTIN or address can change — a re-registration,
    # an office move — and historical documents must continue to show what was true when
    # issued. The alternative is an unprovable financial record.
    seller_legal_name = models.CharField(max_length=200)
    seller_gstin = models.CharField(max_length=15, blank=True)
    seller_address = models.TextField(blank=True)
    seller_state_code = models.CharField(max_length=2, blank=True)

    # --- buyer snapshot (M5-2) --------------------------------------------
    buyer_name = models.CharField(max_length=200)
    buyer_gstin = models.CharField(max_length=15, blank=True)
    buyer_address = models.TextField(blank=True)
    buyer_state_code = models.CharField(max_length=2, blank=True)
    # D-3: true when neither an explicit state code nor a GSTIN was available and
    # intra-state was assumed. Recorded rather than inferred, so the assumption is
    # visible to whoever has to defend the tax split later.
    buyer_state_assumed = models.BooleanField(default=False)

    # --- money -------------------------------------------------------------
    subtotal_amount = MoneyField()
    discount_amount = MoneyField(default=0)
    taxable_amount = MoneyField()
    cgst_amount = MoneyField(default=0)
    sgst_amount = MoneyField(default=0)
    igst_amount = MoneyField(default=0)
    # M5-11: stored, not a display artefact. GST invoices are conventionally rounded to
    # the rupee and the difference must be visible on the document and reproducible from
    # it, not silently absorbed by whatever renders the total.
    round_off_amount = MoneyField(default=0)
    total_amount = MoneyField()

    class Meta:
        abstract = True


class Invoice(_MoneyDocument):
    """The GST tax invoice — the legal and financial record of the sale (04 T-17)."""

    class Status(models.TextChoices):
        ISSUED = "ISSUED", "Issued"
        CANCELLED = "CANCELLED", "Cancelled"

    _document_name = "invoice"
    # The only permitted changes, and they must match the trigger in migration 0002
    # exactly. ``pdf_media`` belongs here because D-5 attaches the rendering after issue;
    # the database additionally refuses to *replace* one, so "rendered once" holds even
    # though the column is writable.
    _mutable_fields = frozenset(
        {"status", "cancelled_reason", "cancelled_at", "cancelled_by", "pdf_media"}
    )

    invoice_number = models.CharField(max_length=40, unique=True)
    number_series = models.ForeignKey(NumberSeries, on_delete=models.RESTRICT, related_name="+")
    # Nullable so a direct counter sale can be invoiced later without a schema change.
    sales_order = models.ForeignKey(
        "orders.SalesOrder", null=True, blank=True, on_delete=models.RESTRICT, related_name="+"
    )
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    invoice_date = models.DateField()

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ISSUED)
    cancelled_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    # D-5: written on first request and never regenerated. The PDF a retailer was handed
    # must not change because a template did.
    pdf_media = models.ForeignKey(
        "core.MediaFile", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    issued_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    issued_at = models.DateTimeField(auto_now_add=True)

    objects: ClassVar[models.Manager[Invoice]] = _ImmutableQuerySet.as_manager()

    class Meta:
        db_table = "invoice"
        ordering = ["-invoice_date", "-id"]
        indexes = [
            models.Index(fields=["customer", "-invoice_date"], name="ix_invoice_customer_date"),
            models.Index(fields=["invoice_date"], name="ix_invoice_invoice_date"),
            models.Index(fields=["financial_year"], name="ix_invoice_financial_year"),
            models.Index(fields=["status"], name="ix_invoice_status"),
        ]
        constraints = [
            # One invoice per order in Edition 1. A database fact, not a hope.
            models.UniqueConstraint(
                fields=["sales_order"],
                condition=models.Q(sales_order__isnull=False),
                name="uq_invoice_sales_order",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    subtotal_amount__gte=0,
                    discount_amount__gte=0,
                    taxable_amount__gte=0,
                    cgst_amount__gte=0,
                    sgst_amount__gte=0,
                    igst_amount__gte=0,
                    total_amount__gte=0,
                ),
                name="ck_invoice_amounts",
            ),
            # M5-7 — THE one GST rule worth enforcing in the database. Intra-state and
            # inter-state tax are mutually exclusive, and getting it wrong produces
            # invoices that are legally defective and cannot be corrected quietly.
            models.CheckConstraint(
                condition=(models.Q(igst_amount=0) | models.Q(cgst_amount=0, sgst_amount=0)),
                name="ck_invoice_gst_split",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="CANCELLED") | ~models.Q(cancelled_reason=""),
                name="ck_invoice_cancel",
            ),
        ]

    def __str__(self) -> str:
        return self.invoice_number


class CreditNote(_MoneyDocument):
    """The instrument that corrects an issued invoice (04 T-19).

    **It writes no stock movement** (D-7, M5-12, ADR-0009). A credit note reverses a
    *financial* fact. The physical return of goods is a separate event recorded as its
    own stock movement — by a failed delivery, or by the warehouse when the goods come
    back. Coupling the two permits the same physical goods to be restocked twice
    (Scenario F), and the frozen ``restocked`` flag is dropped for that reason.

    **Why a separate table rather than a negative invoice.** It would need its own number
    series anyway, would break every ``SUM`` and report that assumes invoices are
    positive, and would make "show me all credit notes" a sign test rather than a table
    scan. Statutorily they are distinct documents.
    """

    _document_name = "credit note"

    credit_note_number = models.CharField(max_length=40, unique=True)
    number_series = models.ForeignKey(NumberSeries, on_delete=models.RESTRICT, related_name="+")
    # A credit note always references an invoice.
    invoice = models.ForeignKey(Invoice, on_delete=models.RESTRICT, related_name="credit_notes")
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    credit_note_date = models.DateField()

    # Mandatory. A correction without a reason is not auditable.
    reason = models.TextField()
    # Categorises *why* credit was given (DAMAGE, SHORT_SUPPLY, RATE_DIFFERENCE).
    # Drives no behaviour — see the class docstring.
    reason_code = models.ForeignKey(
        "inventory.ReasonCode",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    issued_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    issued_at = models.DateTimeField(auto_now_add=True)

    objects: ClassVar[models.Manager[CreditNote]] = _ImmutableQuerySet.as_manager()

    class Meta:
        db_table = "credit_note"
        ordering = ["-credit_note_date", "-id"]
        indexes = [
            models.Index(fields=["invoice"], name="ix_credit_note_invoice"),
            models.Index(fields=["customer", "-credit_note_date"], name="ix_credit_note_cust_date"),
            models.Index(fields=["financial_year"], name="ix_credit_note_fy"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    subtotal_amount__gte=0,
                    discount_amount__gte=0,
                    taxable_amount__gte=0,
                    cgst_amount__gte=0,
                    sgst_amount__gte=0,
                    igst_amount__gte=0,
                    total_amount__gt=0,
                ),
                name="ck_credit_note_amounts",
            ),
            models.CheckConstraint(
                condition=(models.Q(igst_amount=0) | models.Q(cgst_amount=0, sgst_amount=0)),
                name="ck_credit_note_gst_split",
            ),
            models.CheckConstraint(condition=~models.Q(reason=""), name="ck_credit_note_reason"),
        ]

    def __str__(self) -> str:
        return self.credit_note_number


class _DocumentLine(_ImmutableDocument):
    """The line shape shared by invoice and credit note lines (04 T-18, T-20).

    Every value is a snapshot; the line renders from itself alone.
    """

    line_number = models.SmallIntegerField()
    # Nullable while product_code is not: the document must remain complete and
    # printable even if the product row is later removed by a data-correction exercise.
    # The foreign key is a convenience for reporting; the snapshot is the record.
    # **If the two ever disagree, the snapshot is right.**
    product = models.ForeignKey(
        "catalogue.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    product_code = models.CharField(max_length=32)
    product_name = models.CharField(max_length=200)
    hsn_code = models.CharField(max_length=8, blank=True)
    quantity = QuantityField()
    unit_name = models.CharField(max_length=20)
    unit_price = MoneyField()
    discount_amount = MoneyField(default=0)
    taxable_amount = MoneyField()
    tax_rate_percent = PercentField()
    cgst_amount = MoneyField(default=0)
    sgst_amount = MoneyField(default=0)
    igst_amount = MoneyField(default=0)
    line_total = MoneyField()

    class Meta:
        abstract = True


class InvoiceLine(_DocumentLine):
    """The line detail of a tax invoice, frozen at issue (04 T-18)."""

    _document_name = "invoice line"

    # RESTRICT, not CASCADE: CASCADE would mean a single mistaken delete of an invoice
    # silently destroys its lines. Since invoices are never deleted, RESTRICT costs
    # nothing and removes a catastrophic path.
    invoice = models.ForeignKey(Invoice, on_delete=models.RESTRICT, related_name="lines")

    objects: ClassVar[models.Manager[InvoiceLine]] = _ImmutableQuerySet.as_manager()

    class Meta:
        db_table = "invoice_line"
        ordering = ["invoice", "line_number"]
        constraints = [
            models.UniqueConstraint(fields=["invoice", "line_number"], name="uq_invoice_line"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="ck_invoice_line_qty"),
            models.CheckConstraint(
                condition=(models.Q(igst_amount=0) | models.Q(cgst_amount=0, sgst_amount=0)),
                name="ck_invoice_line_gst_split",
            ),
        ]
        indexes = [
            models.Index(fields=["invoice"], name="ix_invoice_line_invoice"),
            models.Index(fields=["product"], name="ix_invoice_line_product"),
        ]

    def __str__(self) -> str:
        return f"{self.invoice_id}:{self.line_number} {self.product_code}"


class CreditNoteLine(_DocumentLine):
    """The line detail of a credit note, frozen at issue (04 T-20)."""

    _document_name = "credit note line"

    credit_note = models.ForeignKey(CreditNote, on_delete=models.RESTRICT, related_name="lines")

    objects: ClassVar[models.Manager[CreditNoteLine]] = _ImmutableQuerySet.as_manager()

    class Meta:
        db_table = "credit_note_line"
        ordering = ["credit_note", "line_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["credit_note", "line_number"], name="uq_credit_note_line"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="ck_credit_note_line_qty"
            ),
            models.CheckConstraint(
                condition=(models.Q(igst_amount=0) | models.Q(cgst_amount=0, sgst_amount=0)),
                name="ck_credit_note_line_gst_split",
            ),
        ]
        indexes = [
            models.Index(fields=["credit_note"], name="ix_credit_note_line_cn"),
            models.Index(fields=["product"], name="ix_credit_note_line_product"),
        ]

    def __str__(self) -> str:
        return f"{self.credit_note_id}:{self.line_number} {self.product_code}"
