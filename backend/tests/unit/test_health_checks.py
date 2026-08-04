"""Health check branches (00 §13).

The failure branches matter more than the success branch: a health endpoint that
cannot report a failure is decoration.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.utils import timezone

from core.health import _check_backup, _check_database, _check_disk

pytestmark = pytest.mark.django_db


def test_database_check_passes_when_reachable():
    assert _check_database()["ok"] is True


def test_disk_check_reports_usage(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    result = _check_disk()
    assert set(result) >= {"ok", "used_percent", "free_gb"}


def test_disk_check_fails_above_the_threshold(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DISK_WARN_PERCENT = 0
    assert _check_disk()["ok"] is False


def test_disk_check_never_raises_on_a_bad_path(settings):
    settings.MEDIA_ROOT = Path("/nonexistent/path/that/cannot/exist")
    result = _check_disk()
    assert result["ok"] is False
    assert "error" in result


def test_backup_check_reports_a_missing_stamp(settings, tmp_path):
    settings.BACKUP_STAMP_PATH = str(tmp_path / "never-written")
    result = _check_backup()
    assert result["ok"] is False
    assert result["reason"] == "no backup stamp yet"


def test_backup_check_passes_for_a_fresh_stamp(settings, tmp_path):
    stamp = tmp_path / "last_success"
    stamp.write_text(timezone.now().isoformat())
    settings.BACKUP_STAMP_PATH = str(stamp)
    result = _check_backup()
    assert result["ok"] is True
    assert result["age_hours"] < 1


def test_backup_check_fails_for_a_stale_stamp(settings, tmp_path):
    """The most under-monitored failure in small systems (00 §13.1)."""
    stamp = tmp_path / "last_success"
    stamp.write_text("old")
    settings.BACKUP_STAMP_PATH = str(stamp)
    settings.BACKUP_MAX_AGE_HOURS = 0
    assert _check_backup()["ok"] is False


def test_healthz_returns_503_when_a_critical_check_fails(client, settings):
    settings.DISK_WARN_PERCENT = 0
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
