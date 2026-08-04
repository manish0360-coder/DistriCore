"""Selectors and the storage seam."""

from __future__ import annotations

import pytest
from django.core.files.storage import FileSystemStorage

from core.models import AuditLog
from core.permissions import Role
from core.selectors import audit_for_entity
from core.services import client_ip, record_audit
from core.storage import get_media_storage
from identity.selectors import active_users_with_role, get_active_user_by_phone

pytestmark = pytest.mark.django_db


def test_audit_for_entity_returns_newest_first(owner):
    for action in (AuditLog.Action.LOGIN_SUCCESS, AuditLog.Action.ROLE_GRANT):
        record_audit(action=action, entity_type="app_user", entity_id=owner.pk, actor=owner)
    entries = list(audit_for_entity("app_user", owner.pk))
    assert len(entries) == 2
    assert entries[0].occurred_at >= entries[1].occurred_at


def test_audit_for_entity_is_scoped(owner):
    record_audit(action=AuditLog.Action.CREATE, entity_type="app_user", entity_id=owner.pk)
    assert audit_for_entity("invoice", owner.pk).count() == 0


def test_active_users_with_role(salesman, owner):
    assert list(active_users_with_role(Role.SALESMAN)) == [salesman]
    assert list(active_users_with_role(Role.OWNER)) == [owner]


def test_active_users_with_role_excludes_deactivated(salesman):
    salesman.is_active = False
    salesman.save(update_fields=["is_active"])
    assert active_users_with_role(Role.SALESMAN).count() == 0


def test_get_active_user_by_phone(salesman):
    assert get_active_user_by_phone(salesman.phone) == salesman
    assert get_active_user_by_phone("+919999999999") is None


def test_storage_seam_resolves_to_the_configured_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    storage = get_media_storage()
    assert isinstance(storage, FileSystemStorage)
    assert str(tmp_path) in storage.location


def test_client_ip_prefers_the_proxy_header(rf):
    request = rf.get("/", HTTP_X_REAL_IP="203.0.113.7")
    assert client_ip(request) == "203.0.113.7"


def test_client_ip_takes_the_first_forwarded_hop(rf):
    request = rf.get("/", HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1")
    assert client_ip(request) == "203.0.113.7"


def test_client_ip_falls_back_to_remote_addr(rf):
    assert client_ip(rf.get("/")) == "127.0.0.1"


def test_client_ip_handles_no_request():
    assert client_ip(None) == ""
