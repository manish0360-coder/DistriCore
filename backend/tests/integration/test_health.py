"""Health endpoint (00 §13)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_healthz_reports_every_check_the_monitor_depends_on(client):
    """Six checks since M11.2, and the set is asserted exactly.

    A check silently disappearing is how a monitored failure mode becomes an unmonitored
    one — the endpoint would still answer 200 and the A-08 monitor would still be green.
    `recovery_ready` is asserted alongside them because it is the single field the monitor
    watches; `00` §13.1 permits four alerts and no more, so the three recovery checks are
    for the operator's diagnosis and this boolean is for the alert.
    """
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["checks"]) == {
        "database",
        "disk",
        "backup",
        "wal_archive",
        "wal_offsite",
        "basebackup",
    }
    assert body["checks"]["database"]["ok"] is True
    assert isinstance(body["recovery_ready"], bool)


def test_healthz_needs_no_authentication(client):
    assert client.get("/healthz").status_code == 200


def test_backup_absence_is_reported_but_not_fatal(client):
    """A missing backup is an alert, not an outage (00 §13.1)."""
    body = client.get("/healthz").json()
    assert body["checks"]["backup"]["ok"] is False
    assert body["status"] == "ok"


def test_an_unprepared_host_reports_recovery_as_not_ready(client):
    """The default posture must be "not ready", not "presumed fine".

    Nothing has shipped WAL offsite or taken a base backup in a test container, and the
    endpoint says so. A recovery position is a thing that has been established, not a thing
    that is assumed until contradicted — which is the whole argument for NFR-AVA-002.
    """
    body = client.get("/healthz").json()
    assert body["recovery_ready"] is False
    assert body["checks"]["wal_offsite"]["ok"] is False
    assert body["checks"]["basebackup"]["ok"] is False
    assert body["status"] == "ok"
