"""OTP rules (FR-IAM-004, 04 T-04)."""

from __future__ import annotations

import pytest
from django.utils import timezone

from core.exceptions import (
    AccountInactive,
    OtpAttemptsExceeded,
    OtpExpired,
    OtpInvalid,
    OtpRateLimited,
)
from identity.models import OtpRequest
from identity.services import _normalise_phone, request_otp, verify_otp


@pytest.mark.django_db
def test_code_is_hashed_never_stored_plaintext(salesman, sms):
    request_otp(phone=salesman.phone)
    otp = OtpRequest.objects.latest("created_at")
    sent_code = sms.sent[-1][1]
    assert otp.code_hash != sent_code
    assert sent_code not in otp.code_hash


@pytest.mark.django_db
def test_verify_consumes_the_code(salesman, sms):
    request_otp(phone=salesman.phone)
    code = sms.sent[-1][1]
    user = verify_otp(phone=salesman.phone, code=code)
    assert user.pk == salesman.pk
    assert OtpRequest.objects.latest("created_at").is_consumed
    # Single use: the same code must not work twice.
    with pytest.raises(OtpInvalid):
        verify_otp(phone=salesman.phone, code=code)


@pytest.mark.django_db
def test_wrong_code_increments_attempts(salesman, sms):
    request_otp(phone=salesman.phone)
    with pytest.raises(OtpInvalid):
        verify_otp(phone=salesman.phone, code="000000")
    assert OtpRequest.objects.latest("created_at").attempt_count == 1


@pytest.mark.django_db
def test_attempts_are_capped(salesman, sms, settings):
    request_otp(phone=salesman.phone)
    for _ in range(settings.OTP_MAX_ATTEMPTS):
        with pytest.raises(OtpInvalid):
            verify_otp(phone=salesman.phone, code="000000")
    with pytest.raises(OtpAttemptsExceeded):
        verify_otp(phone=salesman.phone, code="000000")


@pytest.mark.django_db
def test_expired_code_rejected(salesman, sms):
    request_otp(phone=salesman.phone)
    code = sms.sent[-1][1]
    otp = OtpRequest.objects.latest("created_at")
    otp.expires_at = timezone.now() - timezone.timedelta(seconds=1)
    otp.save(update_fields=["expires_at"])
    with pytest.raises(OtpExpired):
        verify_otp(phone=salesman.phone, code=code)


@pytest.mark.django_db
def test_request_is_rate_limited(salesman, sms):
    for _ in range(3):
        request_otp(phone=salesman.phone)
    with pytest.raises(OtpRateLimited):
        request_otp(phone=salesman.phone)


@pytest.mark.django_db
def test_unknown_phone_sends_nothing_but_does_not_disclose(sms):
    """Response shape is identical; no SMS is sent (FR-IAM-004)."""
    before = len(sms.sent)
    challenge = request_otp(phone="+919999999999")
    assert challenge.expires_in_seconds > 0
    assert len(sms.sent) == before


@pytest.mark.django_db
def test_inactive_account_rejected(salesman, sms):
    request_otp(phone=salesman.phone)
    code = sms.sent[-1][1]
    salesman.is_active = False
    salesman.save(update_fields=["is_active"])
    with pytest.raises(AccountInactive):
        verify_otp(phone=salesman.phone, code=code)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("9876543210", "+919876543210"),
        ("+919876543210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("98765 43210", "+919876543210"),
    ],
)
def test_phone_normalisation(raw, expected):
    """Without this, three spellings are three different users."""
    assert _normalise_phone(raw) == expected


@pytest.mark.django_db
def test_failed_attempt_survives_the_rejection(salesman, sms):
    """Regression: the counter must COMMIT even though verify_otp raises.

    The original implementation wrapped the whole function in @transaction.atomic, so
    raising OtpInvalid rolled the increment back. The cap in FR-IAM-004 never engaged
    and an OTP could be brute-forced indefinitely. This pins the transaction boundary.
    """
    request_otp(phone=salesman.phone)
    pk = OtpRequest.objects.latest("created_at").pk

    for expected in (1, 2, 3):
        with pytest.raises(OtpInvalid):
            verify_otp(phone=salesman.phone, code="000000")
        # Re-read from the database, not from a cached instance.
        assert OtpRequest.objects.get(pk=pk).attempt_count == expected


@pytest.mark.django_db
def test_code_is_consumed_even_when_the_account_is_rejected(salesman, sms):
    """A used code must not be replayable after an account-state rejection."""
    request_otp(phone=salesman.phone)
    code = sms.sent[-1][1]
    salesman.is_active = False
    salesman.save(update_fields=["is_active"])

    with pytest.raises(AccountInactive):
        verify_otp(phone=salesman.phone, code=code)

    assert OtpRequest.objects.latest("created_at").is_consumed
    # Reactivating must not make the spent code work again.
    salesman.is_active = True
    salesman.save(update_fields=["is_active"])
    with pytest.raises(OtpInvalid):
        verify_otp(phone=salesman.phone, code=code)
