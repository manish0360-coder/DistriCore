#!/usr/bin/env bash
# Container entrypoint. Migrations run here under an advisory lock so two
# containers starting together cannot race the same migration (D-6).
set -euo pipefail

echo "[entrypoint] waiting for database..."
python - <<'PY'
import os, sys, time
import psycopg
url = os.environ["DATABASE_URL"]
for attempt in range(60):
    try:
        with psycopg.connect(url, connect_timeout=2):
            print("[entrypoint] database ready")
            sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        if attempt % 10 == 0:
            print(f"[entrypoint] waiting ({exc.__class__.__name__})")
        time.sleep(1)
print("[entrypoint] database unreachable after 60s", file=sys.stderr)
sys.exit(1)
PY

if [ "${DISTRICORE_RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] applying migrations under advisory lock"
  python - <<'PY'
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
django.setup()
from django.core.management import call_command
from django.db import connection

LOCK_ID = 8734112  # arbitrary but fixed: only DistriCore uses it
with connection.cursor() as cur:
    cur.execute("SELECT pg_advisory_lock(%s)", [LOCK_ID])
try:
    call_command("migrate", "--noinput")
finally:
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])
PY
fi

if [ "${DISTRICORE_COLLECTSTATIC:-true}" = "true" ]; then
  python manage.py collectstatic --noinput --clear >/dev/null
fi

echo "[entrypoint] starting: $*"
exec "$@"
