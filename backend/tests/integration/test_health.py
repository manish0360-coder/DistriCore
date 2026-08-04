"""Health endpoint (00 §13)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_healthz_reports_all_three_checks(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["checks"]) == {"database", "disk", "backup"}
    assert body["checks"]["database"]["ok"] is True


def test_healthz_needs_no_authentication(client):
    assert client.get("/healthz").status_code == 200


def test_backup_absence_is_reported_but_not_fatal(client):
    """A missing backup is an alert, not an outage (00 §13.1)."""
    body = client.get("/healthz").json()
    assert body["checks"]["backup"]["ok"] is False
    assert body["status"] == "ok"
