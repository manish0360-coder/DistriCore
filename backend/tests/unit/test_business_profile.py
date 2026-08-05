"""Tier-3 configuration singleton (04 T-05, M3-10, D-5)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db.utils import IntegrityError

from core.exceptions import PermissionDenied
from core.models import AuditLog, BusinessProfile
from core.services import get_business_profile, update_business_profile

pytestmark = pytest.mark.django_db


def test_profile_is_created_on_demand():
    """A fresh database, a restored backup and a test database behave identically."""
    assert BusinessProfile.objects.count() == 0
    profile = get_business_profile()
    assert profile.pk == 1
    assert get_business_profile().pk == profile.pk
    assert BusinessProfile.objects.count() == 1


def test_a_second_row_is_refused_by_the_database(profile):
    """M3-10: a singleton enforced by CHECK (id = 1), not by convention."""
    from django.db import transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        BusinessProfile.objects.create(pk=2, legal_name="Impostor")


def test_only_the_owner_may_change_settings(salesman, profile):
    with pytest.raises(PermissionDenied):
        update_business_profile(actor=salesman, legal_name="Hijacked")


def test_changes_are_audited(owner, profile):
    update_business_profile(actor=owner, max_manual_discount_percent=Decimal("5.00"))
    entry = AuditLog.objects.get(entity_type="business_profile")
    assert entry.before_state["max_manual_discount_percent"] == "10.00"
    assert entry.after_state["max_manual_discount_percent"] == "5.00"


def test_otp_expiry_reads_the_profile_with_a_settings_fallback(profile, settings):
    """D-5: 04 T-05 places this on the profile; M0 read it from settings."""
    from identity.services import _otp_expiry_minutes

    profile.otp_expiry_minutes = 3
    profile.save(update_fields=["otp_expiry_minutes"])
    assert _otp_expiry_minutes() == 3
