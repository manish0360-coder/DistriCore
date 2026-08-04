"""Health endpoint (00 §13).

Checks the things whose failure means the system is down from the point of view of
someone using it — not merely that the process is running. A process that is up but
cannot reach its database is down.
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


def _check_backup() -> dict[str, Any]:
    """Backups fail silently for months and are discovered during a restore.

    Surfacing the last success here makes the §13.1 alert possible.
    """
    stamp = Path(settings.BACKUP_STAMP_PATH)
    if not stamp.exists():
        return {"ok": False, "reason": "no backup stamp yet"}
    age_hours = (datetime.now(UTC).timestamp() - stamp.stat().st_mtime) / 3600
    return {
        "ok": age_hours <= settings.BACKUP_MAX_AGE_HOURS,
        "age_hours": round(age_hours, 1),
    }


@never_cache
def healthz(request: HttpRequest) -> JsonResponse:
    checks = {
        "database": _check_database(),
        "disk": _check_disk(),
        "backup": _check_backup(),
    }
    # Backup age must not take the service out of rotation — it is an alert, not an
    # outage. Database and disk are genuine liveness signals.
    critical_ok = checks["database"]["ok"] and checks["disk"]["ok"]
    body = {
        "status": "ok" if critical_ok else "unhealthy",
        "environment": settings.DISTRICORE_ENV,
        "checks": checks,
    }
    return JsonResponse(body, status=200 if critical_ok else 503)
