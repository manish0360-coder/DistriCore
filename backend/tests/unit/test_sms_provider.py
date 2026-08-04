"""SMS provider resolution and the provider contract.

The canonical contract is ``SmsProvider.send_otp(phone, code) -> None``. The ``sent``
list belongs to MemorySmsProvider alone: it is a test affordance, and putting it on
ConsoleSmsProvider would mean production code accumulating live OTP codes in memory
(SEC-3). See docs/M0_Completion_Report.md §5.
"""

from __future__ import annotations

import logging

import pytest

from core.exceptions import SmsDeliveryFailed
from identity.sms import (
    ConsoleSmsProvider,
    MemorySmsProvider,
    Msg91SmsProvider,
    get_sms_provider,
)


def test_test_settings_resolve_the_memory_double(settings):
    assert isinstance(get_sms_provider(), MemorySmsProvider)


def test_console_provider_is_selected_for_development(settings):
    settings.SMS_PROVIDER = "console"
    assert isinstance(get_sms_provider(), ConsoleSmsProvider)


def test_unknown_provider_is_rejected_loudly(settings):
    settings.SMS_PROVIDER = "carrier-pigeon"
    with pytest.raises(SmsDeliveryFailed):
        get_sms_provider()


def test_console_provider_logs_instead_of_sending(caplog):
    with caplog.at_level(logging.WARNING, logger="districore.sms"):
        ConsoleSmsProvider().send_otp("+919876543210", "482913")
    assert "482913" in caplog.text
    assert "development only" in caplog.text


def test_memory_provider_records_what_would_have_been_sent():
    provider = MemorySmsProvider()
    provider.send_otp("+919876543210", "482913")
    assert provider.sent == [("+919876543210", "482913")]


def test_console_provider_does_not_expose_a_sent_list():
    """Asserted explicitly: this is a deliberate contract boundary, not an omission."""
    assert not hasattr(ConsoleSmsProvider(), "sent")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"api_key": "", "sender_id": "S", "template_id": "T"},
        {"api_key": "K", "sender_id": "", "template_id": "T"},
        {"api_key": "K", "sender_id": "S", "template_id": ""},
    ],
)
def test_msg91_refuses_to_construct_while_unconfigured(kwargs):
    """DLT registration is incomplete (P0-8); failing loudly beats sending nothing."""
    with pytest.raises(SmsDeliveryFailed) as exc:
        Msg91SmsProvider(**kwargs)
    assert "DLT" in str(exc.value)


def test_msg91_settings_path_is_reachable(settings):
    settings.SMS_PROVIDER = "msg91"
    settings.SMS_API_KEY = ""
    with pytest.raises(SmsDeliveryFailed):
        get_sms_provider()
