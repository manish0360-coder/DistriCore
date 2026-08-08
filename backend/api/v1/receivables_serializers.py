"""Payment and statement payloads (05 §9.6, §10.4).

A collection carries a `client_uuid` and a replay returns **200 with the original**, not
409 (05 §5). A retry after a timeout is correct client behaviour on a bad connection;
answering 409 trains clients to treat a successful write as a failure, "which is exactly
how a salesman ends up recording a payment twice."
"""

from __future__ import annotations

from rest_framework import serializers


class PaymentSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    payment_number = serializers.CharField(read_only=True)
    client_uuid = serializers.UUIDField(read_only=True)
    customer_id = serializers.IntegerField(read_only=True)
    customer_name = serializers.CharField(source="customer.shop_name", read_only=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    method = serializers.CharField(read_only=True)
    reference_number = serializers.CharField(read_only=True)
    payment_date = serializers.DateField(read_only=True)
    received_by_id = serializers.IntegerField(read_only=True)
    notes = serializers.CharField(read_only=True)
    is_reversed = serializers.BooleanField(read_only=True)
    reversed_reason = serializers.CharField(read_only=True)
    reversed_at = serializers.DateTimeField(read_only=True)


class PaymentCreateSerializer(serializers.Serializer):
    """`05` §10.4. The customer and the money; nothing derived is accepted."""

    customer_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    method = serializers.ChoiceField(choices=["CASH", "UPI", "BANK", "CHEQUE"])
    payment_date = serializers.DateField(required=False, allow_null=True)
    reference_number = serializers.CharField(
        required=False, allow_blank=True, max_length=100
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    device_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
    client_uuid = serializers.UUIDField(required=False, allow_null=True)


class PaymentCreatedSerializer(PaymentSerializer):
    """The create response.

    ``balance_after_amount`` is here because the salesman is standing in front of the
    retailer and the next question is always *"toh ab kitna baaki?"* — one field that
    removes a follow-up round trip on a connection that may not survive one (05 §10.4).
    """

    balance_after_amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class PaymentReverseSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class WriteOffSerializer(serializers.Serializer):
    """The amount is explicit, never derived from the balance (M6 §6.2)."""

    customer_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    reason = serializers.CharField(max_length=500)
    entry_date = serializers.DateField(required=False, allow_null=True)


class OutstandingItemSerializer(serializers.Serializer):
    entry_id = serializers.IntegerField()
    entry_date = serializers.DateField()
    entry_type = serializers.CharField()
    document = serializers.CharField()
    original_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    outstanding_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    age_days = serializers.IntegerField()
    bucket = serializers.CharField()


class StatementEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    entry_date = serializers.DateField()
    entry_type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    narration = serializers.CharField()


class StatementSerializer(serializers.Serializer):
    """Opening, entries, closing (05 §9.6).

    The closing figure of one period is the opening figure of the next, by construction —
    both are the same `SUM` over the same immutable rows.
    """

    customer_id = serializers.IntegerField()
    date_from = serializers.DateField(allow_null=True)
    date_to = serializers.DateField()
    opening_balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    entries = StatementEntrySerializer(many=True)
    closing_balance = serializers.DecimalField(max_digits=14, decimal_places=2)
