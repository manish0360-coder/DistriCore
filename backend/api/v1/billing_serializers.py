"""Fulfilment, billing and ledger payloads (05 §9.4-9.6).

**Write serialisers accept almost nothing.** Issuing an invoice takes an order and a
date; every figure is derived server-side from snapshots already on the order. A client
that could supply amounts could supply wrong ones, and the invoice is a legal document
(M5-2, FR-BIL-008).
"""

from __future__ import annotations

from rest_framework import serializers


# --------------------------------------------------------------------------- delivery
class DeliverySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    sales_order_id = serializers.IntegerField(read_only=True)
    order_number = serializers.CharField(source="sales_order.order_number", read_only=True)
    customer_name = serializers.CharField(source="sales_order.customer.shop_name", read_only=True)
    client_uuid = serializers.UUIDField(read_only=True)
    assigned_user_id = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    dispatched_at = serializers.DateTimeField(read_only=True)
    delivered_at = serializers.DateTimeField(read_only=True)
    recipient_name = serializers.CharField(read_only=True)
    failure_reason = serializers.CharField(read_only=True)
    photo_media_id = serializers.IntegerField(read_only=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True)


class DeliveryCreateSerializer(serializers.Serializer):
    sales_order_id = serializers.IntegerField()
    assigned_user_id = serializers.IntegerField()
    client_uuid = serializers.UUIDField(required=False, allow_null=True)


class DispatchSerializer(serializers.Serializer):
    # D-8: an override is a decision, so it carries a reason or it is not an override.
    override_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class DeliveryCompleteSerializer(serializers.Serializer):
    # TD-39 / `05` §6, §9.4 `Idem ✓`. **In the body**, per AD-09: the value is part of the
    # resource — stored, queried and reported on — not a transport concern, so it is not a
    # header. Optional: a caller that omits it gets exactly the previous behaviour.
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    recipient_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    delivered_at = serializers.DateTimeField(required=False, allow_null=True)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    photo_media_id = serializers.IntegerField(required=False, allow_null=True)
    device_id = serializers.CharField(required=False, allow_blank=True, max_length=64)

    def validate(self, attrs: dict) -> dict:
        """Coordinates are captured together or not at all, matching the CHECK."""
        has_lat = attrs.get("latitude") is not None
        has_lng = attrs.get("longitude") is not None
        if has_lat != has_lng:
            raise serializers.ValidationError(
                {"latitude": "Latitude and longitude must be given together."}
            )
        return attrs


class DeliveryFailSerializer(serializers.Serializer):
    # TD-39. `05` §9.4 marks `/fail` `Idem ✓` alongside `/complete`; §6's "Applies to"
    # line names only `/complete`, which is a documentation gap this milestone also closes.
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    reason = serializers.CharField(max_length=500)
    device_id = serializers.CharField(required=False, allow_blank=True, max_length=64)


# --------------------------------------------------------------------------- invoice
class InvoiceLineSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    line_number = serializers.IntegerField(read_only=True)
    product_code = serializers.CharField(read_only=True)
    product_name = serializers.CharField(read_only=True)
    hsn_code = serializers.CharField(read_only=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)
    unit_name = serializers.CharField(read_only=True)
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    discount_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    taxable_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    tax_rate_percent = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    cgst_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    sgst_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    igst_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)


class InvoiceSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    invoice_number = serializers.CharField(read_only=True)
    financial_year = serializers.CharField(read_only=True)
    sales_order_id = serializers.IntegerField(read_only=True)
    customer_id = serializers.IntegerField(read_only=True)
    invoice_date = serializers.DateField(read_only=True)
    status = serializers.CharField(read_only=True)
    seller_legal_name = serializers.CharField(read_only=True)
    seller_gstin = serializers.CharField(read_only=True)
    seller_state_code = serializers.CharField(read_only=True)
    buyer_name = serializers.CharField(read_only=True)
    buyer_gstin = serializers.CharField(read_only=True)
    buyer_state_code = serializers.CharField(read_only=True)
    buyer_state_assumed = serializers.BooleanField(read_only=True)
    subtotal_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    discount_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    taxable_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    cgst_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    sgst_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    igst_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    round_off_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    lines = InvoiceLineSerializer(many=True, read_only=True)


class InvoiceCreateSerializer(serializers.Serializer):
    """Everything else is derived. See the module docstring."""

    sales_order_id = serializers.IntegerField()
    invoice_date = serializers.DateField(required=False, allow_null=True)
    client_uuid = serializers.UUIDField(required=False, allow_null=True)


class InvoiceCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


# --------------------------------------------------------------------------- credit note
class CreditNoteLineInputSerializer(serializers.Serializer):
    invoice_line_id = serializers.IntegerField()
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, required=False, allow_null=True
    )


class CreditNoteCreateSerializer(serializers.Serializer):
    invoice_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=500)
    reason_code_id = serializers.IntegerField(required=False, allow_null=True)
    credit_note_date = serializers.DateField(required=False, allow_null=True)
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    lines = CreditNoteLineInputSerializer(many=True)

    def validate_lines(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError("A credit note needs at least one line.")
        return value


class CreditNoteSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    credit_note_number = serializers.CharField(read_only=True)
    invoice_id = serializers.IntegerField(read_only=True)
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    customer_id = serializers.IntegerField(read_only=True)
    credit_note_date = serializers.DateField(read_only=True)
    reason = serializers.CharField(read_only=True)
    taxable_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    cgst_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    sgst_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    igst_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    round_off_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    lines = InvoiceLineSerializer(many=True, read_only=True)


# --------------------------------------------------------------------------- ledger
class LedgerEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    entry_date = serializers.DateField(read_only=True)
    entry_type = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    narration = serializers.CharField(read_only=True)
    source_document_type = serializers.CharField(read_only=True)
    source_document_id = serializers.IntegerField(read_only=True)
    sales_order_id = serializers.IntegerField(read_only=True)


class CustomerBalanceSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    settled_balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    open_order_value = serializers.DecimalField(max_digits=14, decimal_places=2)
    credit_exposure = serializers.DecimalField(max_digits=14, decimal_places=2)
    credit_limit_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    available_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
