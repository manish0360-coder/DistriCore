"""Audit service (BR-002)."""

from __future__ import annotations

import pytest

from core.models import AuditLog
from core.services import record_audit


@pytest.mark.django_db
def test_records_actor_role_snapshot(owner):
    entry = record_audit(
        action=AuditLog.Action.LOGIN_SUCCESS,
        entity_type="app_user",
        entity_id=owner.pk,
        actor=owner,
        surface=AuditLog.Surface.WEB,
    )
    assert entry.actor_user_id == owner.pk
    # Snapshot, not a join: roles change, and the audit answers who was allowed then.
    assert "OWNER" in entry.actor_role_code


@pytest.mark.django_db
def test_scrubs_sensitive_keys():
    entry = record_audit(
        action=AuditLog.Action.CREATE,
        entity_type="app_user",
        after_state={"phone": "+919876543210", "password": "hunter2", "code": "482913"},
    )
    assert entry.after_state["password"] == "[redacted]"
    assert entry.after_state["code"] == "[redacted]"
    assert entry.after_state["phone"] == "+919876543210"


@pytest.mark.django_db
def test_survives_actor_deactivation(owner):
    """Deactivating a user must never erase their audit trail (04 R-25)."""
    record_audit(action=AuditLog.Action.CREATE, entity_type="app_user", actor=owner)
    owner.is_active = False
    owner.save(update_fields=["is_active"])
    assert AuditLog.objects.filter(actor_user=owner).exists()


@pytest.mark.django_db
def test_records_request_id_for_log_correlation(owner):
    """A log says what went wrong; the audit says what happened; the id joins them."""
    from core.context import set_request_id

    set_request_id("req-abc-123")
    entry = record_audit(action=AuditLog.Action.CREATE, entity_type="app_user", actor=owner)
    assert entry.request_id == "req-abc-123"


@pytest.mark.django_db
def test_system_actor_is_permitted():
    entry = record_audit(action=AuditLog.Action.CREATE, entity_type="app_user")
    assert entry.actor_user is None
    assert entry.actor_role_code == ""


@pytest.mark.django_db
def test_truncates_oversized_fields(owner):
    entry = record_audit(
        action=AuditLog.Action.CREATE,
        entity_type="x" * 200,
        actor=owner,
        device_id="d" * 200,
        ip_address="i" * 200,
    )
    assert len(entry.entity_type) == 50
    assert len(entry.device_id) == 64
    assert len(entry.ip_address) == 45


@pytest.mark.django_db
def test_str_is_readable(owner):
    entry = record_audit(
        action=AuditLog.Action.ISSUE, entity_type="invoice", entity_id=7, actor=owner
    )
    assert "invoice#7" in str(entry)
