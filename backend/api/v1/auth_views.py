"""Authentication endpoints (05 §9.1).

Views parse, delegate to a service, and shape the response. Every rule — rate limits
on codes, attempt counting, account state, auditing — lives in ``identity.services``.
"""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from api.v1.serializers import (
    LogoutSerializer,
    OtpRequestSerializer,
    OtpVerifySerializer,
    PasswordLoginSerializer,
    RefreshSerializer,
)
from core.exceptions import RefreshExpired
from core.services import client_ip
from identity import services as identity_services


def _decode_refresh(raw: str) -> RefreshToken:
    """Decode an encoded refresh token, verifying signature, expiry and blacklist.

    SimpleJWT annotates ``Token.__init__(token: Token | None)``, but the parameter it
    actually takes — and the only way the library is ever used — is the *encoded string*.
    The upstream annotation is wrong. The suppression is confined to this one line rather
    than repeated at every call site.
    """
    return RefreshToken(raw)  # type: ignore[arg-type]


def _issue_tokens(user: Any, device_id: str = "") -> dict[str, Any]:
    """Mint an access/refresh pair.

    Claims are a cache, not an authority: services re-read roles from the database on
    any request that changes money or stock (05 §7.1).
    """
    refresh = RefreshToken.for_user(user)
    refresh["roles"] = sorted(user.role_codes())
    refresh["device_id"] = device_id
    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
        "expires_in": int(refresh.access_token.lifetime.total_seconds()),
        "user": identity_services.user_payload(user),
    }


class OtpRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_scope = "otp_request"

    def post(self, request: Request) -> Response:
        payload = OtpRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        challenge = identity_services.request_otp(
            phone=payload.validated_data["phone"],
            ip_address=client_ip(request),
        )
        # 202: the code was accepted for delivery. Whether the number is registered is
        # deliberately not disclosed (FR-IAM-004).
        return Response(
            {
                "expires_in_seconds": challenge.expires_in_seconds,
                "attempts_allowed": challenge.attempts_allowed,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class OtpVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_scope = "otp_verify"

    def post(self, request: Request) -> Response:
        payload = OtpVerifySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = identity_services.verify_otp(
            phone=payload.validated_data["phone"],
            code=payload.validated_data["code"],
            device_id=payload.validated_data["device_id"],
            ip_address=client_ip(request),
        )
        return Response(
            _issue_tokens(user, payload.validated_data["device_id"]), status=status.HTTP_200_OK
        )


class PasswordLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_scope = "login"

    def post(self, request: Request) -> Response:
        payload = PasswordLoginSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = identity_services.authenticate_password(
            phone=payload.validated_data["phone"],
            password=payload.validated_data["password"],
            ip_address=client_ip(request),
        )
        return Response(
            _issue_tokens(user, payload.validated_data["device_id"]), status=status.HTTP_200_OK
        )


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        payload = RefreshSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            refresh = _decode_refresh(payload.validated_data["refresh_token"])
            # Rotation with reuse detection: blacklisting the presented token means a
            # replay of it is rejected on arrival (05 §7.1).
            refresh.blacklist()
            # Then MUTATE this token object into a fresh one. Re-parsing str(refresh)
            # would decode the token we just blacklisted, and verification would reject
            # it — which is exactly how every valid refresh came back 401. This is the
            # sequence SimpleJWT's own TokenRefreshSerializer performs.
            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            if hasattr(refresh, "outstand"):
                refresh.outstand()  # track the new jti; absent on older 5.x
        except TokenError as exc:
            raise RefreshExpired("Please sign in again.") from exc
        return Response(
            {
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh),
                "expires_in": int(refresh.access_token.lifetime.total_seconds()),
            }
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        payload = LogoutSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        token = payload.validated_data["refresh_token"]
        if token:
            try:
                _decode_refresh(token).blacklist()
            except TokenError:
                pass  # already invalid: logout is idempotent
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(identity_services.user_payload(request.user))
