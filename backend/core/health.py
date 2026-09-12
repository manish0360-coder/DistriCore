"""Health endpoint (00 §13).

Checks the things whose failure means the system is down from the point of view of
someone using it — not merely that the process is running. A process that is up but
cannot reach its database is down.

**Recovery readiness is reported here too, in four separate checks, and that separation is
the point** (NFR-AVA-001, M11.2). A 15-minute RPO is delivered by a chain — PostgreSQL
archiving WAL, the host encrypting and shipping it to A-05, and a base backup to replay it
into — and any one link can fail while the others look healthy. A single `backup: ok` field
cannot distinguish "last night's dump exists on this host" from "the business can be
recovered to five minutes ago", and reporting the first while implying the second is the
failure this milestone exists to remove.

`00` §13.1 allows four alerts and no more. Nothing here adds a fifth channel: these fields
are read by the A-08 monitor already polling this endpoint, and `recovery_ready` is the one
boolean it has to watch.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache


def _check_database() -> dict[str, Any]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}


def _check_disk() -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(settings.MEDIA_ROOT.parent)
        used_percent = round(usage.used / usage.total * 100, 1)
        return {
            "ok": used_percent < settings.DISK_WARN_PERCENT,
            "used_percent": used_percent,
            "free_gb": round(usage.free / 1024**3, 1),
        }
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}


def _stamp_age_seconds(path: str) -> float | None:
    """Seconds since a stamp file was written, or ``None`` if it never was.

    Every stamp this module reads is written **inside this container**, into the
    `backup_data` volume, by the ops scripts (`ops/backup.sh`, `ops/ship-wal.sh`,
    `ops/basebackup.sh`). They used to be written on the *host*, at the same path — a
    different filesystem — so this check could never see one and `backup.ok` was false on a
    correctly backed-up host. A health check that cannot go green gets ignored, which is
    worse than not having it.
    """
    stamp = Path(path)
    if not stamp.exists():
        return None
    return datetime.now(UTC).timestamp() - stamp.stat().st_mtime


def _check_backup() -> dict[str, Any]:
    """The **logical** layer: last night's `pg_dump`, encrypted and proven offsite.

    Backups fail silently for months and are discovered during a restore. Surfacing the
    last success here makes the §13.1 alert possible.

    This says nothing about RPO. A dump is a snapshot; the 15 minutes comes from the three
    checks below. Keeping them apart is what stops a green dump from implying a recovery
    position it does not provide.
    """
    age = _stamp_age_seconds(settings.BACKUP_STAMP_PATH)
    if age is None:
        return {"ok": False, "reason": "no backup stamp yet"}
    age_hours = age / 3600
    return {
        "ok": age_hours <= settings.BACKUP_MAX_AGE_HOURS,
        "age_hours": round(age_hours, 1),
    }


def _check_wal_archive() -> dict[str, Any]:
    """Is PostgreSQL still archiving? Asked of PostgreSQL, not of a file.

    `pg_stat_archiver` is the only authority on this. A stamp written by the shipper cannot
    detect a stalled archiver — "everything local is offsite" is perfectly true of an
    archive that stopped growing an hour ago, and that is exactly the false success this
    check exists to catch.

    **`last_failed_time` after `last_archived_time` is the dangerous state**, not merely an
    untidy one: failing `archive_command` means WAL cannot be recycled, `pg_wal` grows
    without bound, and PostgreSQL eventually refuses to write at all. It is reported as a
    failure here rather than as a 503, because taking the service out of rotation ahead of
    that would cause the outage sooner than the disk does.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT (SELECT setting FROM pg_settings WHERE name = 'archive_mode'),
                       last_archived_time,
                       last_failed_time,
                       archived_count,
                       failed_count
                  FROM pg_stat_archiver
                """
            )
            row = cursor.fetchone()
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}

    if row is None:
        return {"ok": False, "reason": "pg_stat_archiver returned no row"}

    mode, last_archived, last_failed, archived_count, failed_count = row
    result: dict[str, Any] = {
        "archive_mode": mode,
        "archived_count": archived_count,
        "failed_count": failed_count,
    }

    if mode != "on":
        result["ok"] = False
        result["reason"] = f"archive_mode={mode} — the continuous layer is not running"
        return result

    if last_archived is None:
        result["ok"] = False
        result["reason"] = "no segment archived yet"
        return result

    age = (datetime.now(UTC) - last_archived).total_seconds()
    result["last_archived_age_seconds"] = round(age)

    if last_failed is not None and last_failed > last_archived:
        result["ok"] = False
        result["reason"] = "archive_command is failing — pg_wal will fill and writes will stop"
        return result

    result["ok"] = age <= settings.WAL_ARCHIVE_MAX_AGE_SECONDS
    return result


def _check_wal_offsite() -> dict[str, Any]:
    """**The RPO observable.** Everything else about NFR-AVA-001 is configuration.

    `ops/ship-wal.sh` writes this stamp only after listing the remote back and proving every
    locally archived segment is present at A-05. So its age is an upper bound on how far
    behind the offsite recovery position is, and it is the number to watch — not
    `archive_timeout`, not the timer period, both of which merely *intend* a lag.

    `rpo_target_seconds` is reported alongside it so the endpoint states the requirement it
    is being measured against, rather than asserting health against an invisible threshold.
    """
    age = _stamp_age_seconds(settings.WAL_STAMP_PATH)
    target = settings.RPO_TARGET_SECONDS
    if age is None:
        return {
            "ok": False,
            "reason": "no verified offsite WAL yet",
            "rpo_target_seconds": target,
        }
    return {
        "ok": age <= settings.WAL_OFFSITE_MAX_AGE_SECONDS,
        "lag_seconds": round(age),
        "rpo_target_seconds": target,
    }


def _check_basebackup() -> dict[str, Any]:
    """The PITR anchor. WAL with nothing to replay it into recovers nothing.

    Reported separately from the WAL checks on purpose: an archive that is current and a
    base backup that is three months stale is a chain whose replay would take longer than
    the four-hour RTO, and neither WAL check can see that.
    """
    age = _stamp_age_seconds(settings.BASEBACKUP_STAMP_PATH)
    if age is None:
        return {"ok": False, "reason": "no base backup yet — PITR is not possible"}
    age_hours = age / 3600
    return {
        "ok": age_hours <= settings.BASEBACKUP_MAX_AGE_HOURS,
        "age_hours": round(age_hours, 1),
    }


@never_cache
def healthz(request: HttpRequest) -> JsonResponse:
    checks = {
        "database": _check_database(),
        "disk": _check_disk(),
        "backup": _check_backup(),
        "wal_archive": _check_wal_archive(),
        "wal_offsite": _check_wal_offsite(),
        "basebackup": _check_basebackup(),
    }
    # Backup age must not take the service out of rotation — it is an alert, not an
    # outage. Database and disk are genuine liveness signals.
    critical_ok = checks["database"]["ok"] and checks["disk"]["ok"]
    body = {
        "status": "ok" if critical_ok else "unhealthy",
        "environment": settings.DISTRICORE_ENV,
        # **One boolean for the monitor, three checks for the diagnosis.** `00` §13.1 permits
        # four alerts and no more, so A-08 watches this field and the operator reads the
        # checks to find out which link broke. All three must hold: archiving, verified
        # offsite delivery, and something to replay into.
        "recovery_ready": (
            checks["wal_archive"]["ok"]
            and checks["wal_offsite"]["ok"]
            and checks["basebackup"]["ok"]
        ),
        "checks": checks,
    }
    return JsonResponse(body, status=200 if critical_ok else 503)
