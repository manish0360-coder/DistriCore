"""Request and response shapes.

Serialisers validate and marshal. They contain no business rules — those live in
``services.py`` (N-01). Money and quantity are rendered as decimal strings (AD-02).
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class NoopSerializer(serializers.Serializer):
    """Placeholder so SimpleJWT's settings validate. Its own views are not used."""


class OtpRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)


class OtpVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=10, trim_whitespace=True)
    device_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class PasswordLoginSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(max_length=128, write_only=True)
    device_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class RefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(required=False, allow_blank=True, default="")


class UserSerializer(serializers.Serializer):
    """Read-only projection of a user. Built from ``services.user_payload``."""

    id = serializers.IntegerField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True)
    language = serializers.CharField(read_only=True)
    roles = serializers.ListField(child=serializers.CharField(), read_only=True)
    customer_id = serializers.IntegerField(read_only=True, allow_null=True)

    def to_representation(self, instance: dict[str, Any]) -> dict[str, Any]:
        return instance
