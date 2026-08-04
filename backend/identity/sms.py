"""SMS delivery.

The provider sits behind a thin interface because DLT registration in India has an
unbounded lead time (00 A-02, P0-8) and the concrete provider may not be available
when the code is written. Two implementations exist today — console for development
and MSG91 for production — so this is not speculative abstraction (E-11).
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx
from django.conf import settings

from core.exceptions import SmsDeliveryFailed

logger = logging.getLogger("districore.sms")


class SmsProvider(Protocol):
    def send_otp(self, phone: str, code: str) -> None: ...


class ConsoleSmsProvider:
    """Development only. Logs the code instead of sending it.

    prod.py refuses to start if this provider is configured in production.
    """

    def send_otp(self, phone: str, code: str) -> None:
        logger.warning("OTP for %s is %s (console provider — development only)", phone, code)


class MemorySmsProvider:
    """Test double. Records what would have been sent."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_otp(self, phone: str, code: str) -> None:
        self.sent.append((phone, code))


class Msg91SmsProvider:
    """MSG91 transactional SMS.

    Requires a DLT-approved template. Kept to plain HTTP rather than a vendor SDK so
    that swapping provider is a new class, not a dependency change (00 §3.2).
    """

    ENDPOINT = "https://control.msg91.com/api/v5/otp"

    def __init__(self, api_key: str, sender_id: str, template_id: str) -> None:
        if not (api_key and sender_id and template_id):
            raise SmsDeliveryFailed(
                "SMS provider is not configured. DLT registration and template approval "
                "are required before OTP login can work in production (00 P0-8)."
            )
        self._api_key = api_key
        self._sender_id = sender_id
        self._template_id = template_id

    def send_otp(self, phone: str, code: str) -> None:
        try:
            response = httpx.post(
                self.ENDPOINT,
                headers={"authkey": self._api_key},
                json={
                    "template_id": self._template_id,
                    "sender": self._sender_id,
                    "mobile": phone.lstrip("+"),
                    "otp": code,
                },
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # The code itself never reaches a log line (SEC-3).
            logger.error("sms_delivery_failed", extra={"phone_suffix": phone[-4:]})
            raise SmsDeliveryFailed("Could not send the verification code.") from exc


_memory_provider = MemorySmsProvider()


def get_sms_provider() -> SmsProvider:
    """Resolve the configured provider. The single place this decision is made."""
    name = settings.SMS_PROVIDER
    if name == "console":
        return ConsoleSmsProvider()
    if name == "memory":
        return _memory_provider
    if name == "msg91":
        return Msg91SmsProvider(
            settings.SMS_API_KEY, settings.SMS_SENDER_ID, settings.SMS_TEMPLATE_ID
        )
    raise SmsDeliveryFailed(f"Unknown SMS provider: {name}")
