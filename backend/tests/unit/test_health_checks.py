"""Health check branches (00 §13).

The failure branches matter more than the success branch: a health endpoint that
cannot report a failure is decoration.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.utils import timezone

from core.health import (
    _check_backup,
    _check_basebackup,
    _check_database,
    _check_disk,
    _check_wal_archive,
    _check_wal_offsite,
)

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


# ------------------------------------------------ recovery readiness (NFR-AVA-001, M11.2)
#
# Three checks rather than one, because the chain has three independent failure modes and a
# single `backup: ok` cannot tell them apart. The branches below are the failures; the
# success branch is the easy half.


def test_the_archiver_check_proves_archiving_is_actually_on_in_the_running_cluster():
    """**The one assertion that tests the compose configuration rather than the YAML.**

    `archive_mode=on` is a command-line flag in `docker/compose.yml`, and
    `test_recovery_readiness` can only confirm the text is there. This reads the value back
    out of the PostgreSQL that `make verify` actually started — so a flag that never reached
    the server, or an entrypoint wrapper that swallowed the arguments, fails here.

    It does not assert a segment has been archived: on a cluster seconds old none has, and
    `archive_timeout` is 300 s. The *reason* string carries that distinction, which is why
    the check reports one.
    """
    result = _check_wal_archive()
    assert result["archive_mode"] == "on", (
        "PostgreSQL reports archiving off. The continuous layer NFR-AVA-001 depends on is "
        "not running, whatever docker/compose.yml says."
    )
    assert isinstance(result["ok"], bool)


def test_the_archiver_check_never_raises(settings):
    """A health check that can throw is a 500 where a diagnosis should be."""
    settings.WAL_ARCHIVE_MAX_AGE_SECONDS = 0
    result = _check_wal_archive()
    assert set(result) >= {"ok", "archive_mode"}


def test_offsite_wal_reports_a_missing_stamp_rather_than_assuming_the_best(settings, tmp_path):
    """No verified offsite WAL is the state of a fresh host, and it is not health."""
    settings.WAL_STAMP_PATH = str(tmp_path / "never-written")
    result = _check_wal_offsite()
    assert result["ok"] is False
    assert result["reason"] == "no verified offsite WAL yet"
    assert result["rpo_target_seconds"] == settings.RPO_TARGET_SECONDS


def test_offsite_wal_reports_the_lag_against_the_requirement(settings, tmp_path):
    """**The RPO observable.** The number, not the intention.

    `archive_timeout` and the timer period describe an intended lag. This is the measured
    one, and it is the only thing `/healthz` is entitled to report about NFR-AVA-001.
    """
    stamp = tmp_path / "wal_offsite_last_success"
    stamp.write_text(timezone.now().isoformat())
    settings.WAL_STAMP_PATH = str(stamp)
    result = _check_wal_offsite()
    assert result["ok"] is True
    assert result["lag_seconds"] < 60
    assert result["rpo_target_seconds"] == 900, (
        "the endpoint must measure against `02` §21.6's 15 minutes, not a local preference"
    )


def test_offsite_wal_fails_once_the_lag_exceeds_the_budget(settings, tmp_path):
    """The breach, which is the branch that matters: transport has stopped."""
    stamp = tmp_path / "wal_offsite_last_success"
    stamp.write_text("stale")
    settings.WAL_STAMP_PATH = str(stamp)
    settings.WAL_OFFSITE_MAX_AGE_SECONDS = 0
    assert _check_wal_offsite()["ok"] is False


def test_a_missing_base_backup_is_reported_as_pitr_being_impossible(settings, tmp_path):
    """WAL with nothing to replay it into recovers nothing.

    Reported separately from the WAL checks on purpose: a current archive and a stale base
    backup is a chain whose replay would exceed the four-hour RTO, and no WAL check can see
    that.
    """
    settings.BASEBACKUP_STAMP_PATH = str(tmp_path / "never-written")
    result = _check_basebackup()
    assert result["ok"] is False
    assert "PITR is not possible" in result["reason"]


def test_a_stale_base_backup_fails_even_though_wal_is_current(settings, tmp_path):
    stamp = tmp_path / "basebackup_last_success"
    stamp.write_text("old")
    settings.BASEBACKUP_STAMP_PATH = str(stamp)
    settings.BASEBACKUP_MAX_AGE_HOURS = 0
    assert _check_basebackup()["ok"] is False


def test_recovery_readiness_needs_all_three_links_and_is_not_the_backup_field(
    client, settings, tmp_path
):
    """The distinction the endpoint exists to make.

    A fresh nightly dump — the thing `backup.ok` reports — says nothing about whether the
    business can be recovered to five minutes ago. Here the dump is healthy and readiness is
    still false, which is precisely the state C-5 used to hide.
    """
    dump = tmp_path / "last_success"
    dump.write_text(timezone.now().isoformat())
    settings.BACKUP_STAMP_PATH = str(dump)
    settings.WAL_STAMP_PATH = str(tmp_path / "no-wal")
    settings.BASEBACKUP_STAMP_PATH = str(tmp_path / "no-base")

    body = client.get("/healthz").json()
    assert body["checks"]["backup"]["ok"] is True
    assert body["recovery_ready"] is False, (
        "a healthy nightly dump made recovery look ready. That is the false success this "
        "endpoint was changed to stop reporting."
    )
    # And still not an outage: taking the site down would not bring the backup back.
    assert body["status"] == "ok"
