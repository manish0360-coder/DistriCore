"""Synchronisation endpoints (05 §11).

The view parses and shapes; `sync.services` coordinates; the domain modules decide. M9.1
implements push only — pull and `/sync/status` are M9.3.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.sync_serializers import SyncPushSerializer
from sync import services as sync_services


class SyncPushView(APIView):
    """`POST /sync/push`.

    **`202`, not `200`** (05 §11.2). The batch was received and processed *per operation*;
    some may not have succeeded, and a `200` would imply the whole batch did — which is
    exactly the ambiguity that loses transactions.

    Authentication is the existing stack: `IsAuthenticated` over the JWT, so an expired
    access token produces the same `401 TOKEN_EXPIRED` every other endpoint does and the
    client's existing `RefreshInterceptor` handles it. No second refresh mechanism.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "sync_push"

    def post(self, request: Request) -> Response:
        payload = SyncPushSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        results = sync_services.process_push(
            actor=request.user,
            device_id=payload.validated_data["device_id"],
            operations=payload.validated_data["operations"],
        )
        return Response(
            {
                # `05` P-2 / C-5: the client stores this and never uses its own clock.
                "server_time": timezone.now(),
                "results": results,
            },
            status=status.HTTP_202_ACCEPTED,
        )
