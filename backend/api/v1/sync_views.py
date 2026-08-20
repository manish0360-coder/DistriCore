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

from api.v1.billing_serializers import DeliverySerializer
from api.v1.master_serializers import CustomerSerializer
from api.v1.sync_serializers import SyncPullSerializer, SyncPushSerializer
from sync import selectors as sync_selectors
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


class SyncPullView(APIView):
    """`GET /sync/pull?since=` (05 §11.1, M9.4).

    **Read-only, repeatable, and it never mutates server state** (P-6). Scope comes from the
    actor through the established selectors — `visible_customers` and `visible_deliveries` —
    never from a request parameter (AD-11): the binary is public, so a parameter a client can
    send is one an attacker can change.

    **Only `customers` and `deliveries` are returned** (D-M9.4-2). The other collections in
    §11.1's envelope are unimplemented, not empty.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        payload = SyncPullSerializer(data=request.query_params)
        payload.is_valid(raise_exception=True)

        page = sync_selectors.pull(
            actor=request.user,
            since=payload.validated_data["since"],
            # P-5: the client repeats with the **same** `since` and this token. `since` is
            # never rewritten mid-pull.
            page_token=payload.validated_data["page_token"] or None,
        )

        body = {
            # P-2 / C-5: the client stores this and sends it as the next `since`. It never
            # uses its own clock.
            "server_time": page["server_time"],
            "since": page["since"],
            "has_more": page["has_more"],
            "customers": {
                # The frozen representations, reused rather than restated. A pull that
                # shaped customers differently from `GET /customers` would be a second
                # contract for one resource.
                "updated": CustomerSerializer(page["customers"]["updated"], many=True).data,
                "deactivated_ids": page["customers"]["deactivated_ids"],
            },
            "deliveries": {
                "updated": DeliverySerializer(page["deliveries"]["updated"], many=True).data,
            },
        }

        # **Present exactly when `has_more`, absent otherwise** (D-M9.4-8). A token on a
        # final page would invite a client to fetch one more time and receive nothing.
        if page["next_page_token"] is not None:
            body["next_page_token"] = page["next_page_token"]

        return Response(body)


class SyncStatusView(APIView):
    """`GET /sync/status` (05 §11.5, M9.3).

    **The device is identified by the JWT `device_id` claim, never by the request**
    (D-M9.3-1). FR-SYN-011 requires sync to authenticate *both user and device*, and a
    client-supplied identifier would let any device ask about any other. Taking it from the
    token makes isolation a property of authentication rather than of a filter.

    Read-only: nothing here mutates an operation, a status or a retention state.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        # `request.auth` is the validated token. A session minted without a `device_id` —
        # both auth serializers default it to `""` — yields the empty string rather than a
        # missing claim, which reports zeroes instead of raising.
        device_id = request.auth.get("device_id", "") if request.auth else ""
        return Response(sync_selectors.device_status(device_id=device_id))
