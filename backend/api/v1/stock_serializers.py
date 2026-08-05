"""Stock payload shapes (05 §9.7). Quantities are decimal strings (AD-02)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class StockOnHandSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    unit_name = serializers.CharField(read_only=True)
    pack_size = serializers.IntegerField(read_only=True)
    on_hand = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)
    on_hand_packs = serializers.SerializerMethodField()

    def get_on_hand_packs(self, obj: Any) -> str:
        """Convenience for display. The ledger stores base units only (M2-6)."""
        if not obj.pack_size:
            return "0"
        return str(int(obj.on_hand // obj.pack_size))


class StockMovementSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    product_id = serializers.IntegerField(read_only=True)
    product_code = serializers.CharField(source="product.code", read_only=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)
    movement_type = serializers.CharField(read_only=True)
    reason_code = serializers.CharField(source="reason_code.code", read_only=True, default=None)
    source_document_type = serializers.CharField(read_only=True)
    source_document_id = serializers.IntegerField(read_only=True, allow_null=True)
    notes = serializers.CharField(read_only=True)
    occurred_at = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class StockMovementWriteSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    # Plain strings: a serialiser must not import a model (N-02). The authoritative
    # list is inventory.services.WRITABLE_MOVEMENT_TYPES, which validates again.
    movement_type = serializers.ChoiceField(choices=["RECEIPT", "ISSUE", "ADJUSTMENT"])
    reason_code_id = serializers.IntegerField()
    in_packs = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
