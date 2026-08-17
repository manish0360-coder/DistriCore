"""`POST /sync/push` request shape (05 §11.2)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from sync.services import MAX_BATCH


class SyncOperationSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField()
    operation_type = serializers.CharField(max_length=40)
    client_created_at = serializers.DateTimeField()
    payload = serializers.JSONField(required=False, default=dict)

    def validate_payload(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise serializers.ValidationError("payload must be an object.")
        # **PU-4.** `device_id` is sent once per batch and does not appear inside a
        # payload. Refusing rather than ignoring: a client that sends one there believes
        # it is being attributed, and silently dropping it would lose the attribution
        # C-10 exists to protect while looking like it worked.
        if "device_id" in value:
            raise serializers.ValidationError(
                "device_id is batch-level (PU-4); it must not appear in a payload."
            )
        return value


class SyncPushSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=64)
    operations = SyncOperationSerializer(many=True, allow_empty=True)

    def validate_operations(self, value: list[Any]) -> list[Any]:
        if len(value) > MAX_BATCH:
            raise serializers.ValidationError(
                f"A batch may carry at most {MAX_BATCH} operations."
            )
        return value
