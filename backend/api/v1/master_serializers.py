"""Master-data request and response shapes (05 §9.2).

Money and quantity render as decimal strings (AD-02). Serialisers validate and marshal
only — every rule lives in services.py (N-01).
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class MediaSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    purpose = serializers.CharField(read_only=True)
    content_type = serializers.CharField(read_only=True)
    size_bytes = serializers.IntegerField(read_only=True)
    url = serializers.SerializerMethodField()

    def get_url(self, obj: Any) -> str:
        return f"/api/v1/media/{obj.pk}"


class MediaUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    purpose = serializers.CharField(max_length=30)
    client_uuid = serializers.UUIDField(required=False, allow_null=True, default=None)


class ProductSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    hsn_code = serializers.CharField(read_only=True)
    tax_rate_percent = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    selling_price = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    unit_name = serializers.CharField(read_only=True)
    pack_size = serializers.IntegerField(read_only=True)
    pack_name = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    image = MediaSerializer(source="image_media", read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class ProductWriteSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=200)
    selling_price = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    hsn_code = serializers.CharField(max_length=8, required=False, allow_blank=True, default="")
    tax_rate_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0, min_value=0, max_value=100
    )
    unit_name = serializers.CharField(max_length=20, required=False, default="PCS")
    pack_size = serializers.IntegerField(required=False, default=1, min_value=1)
    pack_name = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default="CASE"
    )
    image_media_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class ProductPatchSerializer(ProductWriteSerializer):
    code = serializers.CharField(max_length=32, required=False)
    name = serializers.CharField(max_length=200, required=False)
    selling_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, min_value=0
    )
    is_active = serializers.BooleanField(required=False)


class ZoneSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    road_name = serializers.CharField(read_only=True)
    pin_code = serializers.CharField(read_only=True)
    panchayat = serializers.CharField(read_only=True)
    ward_number = serializers.CharField(read_only=True)
    city = serializers.CharField(read_only=True)
    assigned_user_id = serializers.IntegerField(read_only=True, allow_null=True)
    is_active = serializers.BooleanField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class ReasonCodeSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    direction = serializers.CharField(read_only=True)
    is_restockable = serializers.BooleanField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)


class CustomerSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    shop_name = serializers.CharField(read_only=True)
    owner_name = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True)
    alt_phone = serializers.CharField(read_only=True)
    gstin = serializers.CharField(read_only=True)
    zone = ZoneSerializer(read_only=True)
    billing_address = serializers.CharField(read_only=True)
    delivery_address = serializers.CharField(read_only=True)
    credit_limit_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    credit_days = serializers.IntegerField(read_only=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class CustomerWriteSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField(required=False, allow_null=True, default=None)
    code = serializers.CharField(max_length=32)
    shop_name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=20)
    billing_address = serializers.CharField()
    owner_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    alt_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    gstin = serializers.CharField(max_length=15, required=False, allow_blank=True, default="")
    zone_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    delivery_address = serializers.CharField(required=False, allow_blank=True, default="")
    credit_limit_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, min_value=0
    )
    credit_days = serializers.IntegerField(required=False, min_value=0)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True, default=None
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True, default=None
    )


class CustomerPatchSerializer(CustomerWriteSerializer):
    code = serializers.CharField(max_length=32, required=False)
    shop_name = serializers.CharField(max_length=200, required=False)
    phone = serializers.CharField(max_length=20, required=False)
    billing_address = serializers.CharField(required=False)
    is_active = serializers.BooleanField(required=False)
