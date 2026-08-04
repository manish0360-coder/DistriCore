"""Audit rows must be unmodifiable through every available path (N-04, I-12).

Enforced in three layers; this file attacks all three. If any of these tests passes
by accident — that is, if a mutation succeeds — every historical audit record becomes
unprovable and the guarantee is worthless.
"""

from __future__ import annotations

import pytest
from django.db import connection

from core.models import AuditLog, AuditLogImmutable
from core.services import record_audit

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]


@pytest.fixture
def entry(owner):
    return record_audit(
        action=AuditLog.Action.LOGIN_SUCCESS,
        entity_type="app_user",
        entity_id=owner.pk,
        actor=owner,
        surface=AuditLog.Surface.WEB,
    )


def test_instance_save_is_refused(entry):
    entry.action = AuditLog.Action.CANCEL
    with pytest.raises(AuditLogImmutable):
        entry.save()


def test_instance_delete_is_refused(entry):
    with pytest.raises(AuditLogImmutable):
        entry.delete()


def test_queryset_update_is_refused(entry):
    with pytest.raises(AuditLogImmutable):
        AuditLog.objects.filter(pk=entry.pk).update(action=AuditLog.Action.CANCEL)


def test_queryset_delete_is_refused(entry):
    with pytest.raises(AuditLogImmutable):
        AuditLog.objects.filter(pk=entry.pk).delete()


def test_database_trigger_refuses_update_even_via_raw_sql(entry):
    """The last line of defence: the database says no even if the code asks."""
    with pytest.raises(Exception) as exc_info:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE audit_log SET action = 'CANCEL' WHERE id = %s", [entry.pk])
    assert "append-only" in str(exc_info.value).lower()


def test_database_trigger_refuses_delete_even_via_raw_sql(entry):
    with pytest.raises(Exception) as exc_info:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM audit_log WHERE id = %s", [entry.pk])
    assert "append-only" in str(exc_info.value).lower()


def test_row_survives_every_attack(entry):
    for attack in (
        lambda: AuditLog.objects.filter(pk=entry.pk).update(action="CANCEL"),
        lambda: AuditLog.objects.filter(pk=entry.pk).delete(),
    ):
        with pytest.raises(AuditLogImmutable):
            attack()
    entry.refresh_from_db()
    assert entry.action == AuditLog.Action.LOGIN_SUCCESS
