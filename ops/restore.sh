#!/usr/bin/env bash
# Restore. Written to be followed under stress by someone who did not write it (B-4).
# Rehearsed quarterly and the result recorded (B-3) — an untested backup is a belief.
set -euo pipefail

ARCHIVE="${1:?usage: restore.sh <dump-file> [target-db]}"
TARGET="${2:-districore_restore_test}"

# **`--env-file .env`, explicitly, and it is not decoration.**
#
# `-f docker/compose.yml` sets compose's PROJECT DIRECTORY to `docker/`, so its automatic
# `.env` discovery looks for `docker/.env` — which does not exist. `.env` lives at the
# repository root. `compose.yml` declares `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?...}`
# with no default, so the interpolation fails and the command dies before touching
# PostgreSQL:
#
#     required variable POSTGRES_PASSWORD is missing a value
#
# Every Makefile invocation carries `--env-file .env` through `$(DC)`. These scripts were
# the only two compose callers that did not, which is why the first real B-3 rehearsal
# failed here and nowhere else.
COMPOSE_ENV="--env-file .env"

# Prerequisites, checked before anything is decrypted, so a wrong working directory fails
# as a wrong working directory (B-4: followed under stress by someone who did not write it).
for required in docker/compose.yml .env; do
    [ -f "$required" ] || {
        echo "[restore] $required not found. Run this from the repository root." >&2
        exit 2
    }
done


if [[ "$ARCHIVE" == *.gpg ]]; then
    echo "[restore] decrypting"
    gpg --batch --yes --decrypt --passphrase "${DISTRICORE_BACKUP_PASSPHRASE:?passphrase required}" \
        --output "${ARCHIVE%.gpg}" "$ARCHIVE"
    ARCHIVE="${ARCHIVE%.gpg}"
fi

echo "[restore] restoring into '$TARGET' (NOT the live database)"
docker compose -f docker/compose.yml $COMPOSE_ENV exec -T db \
    psql -U "${POSTGRES_USER:-districore}" -c "DROP DATABASE IF EXISTS $TARGET;"
docker compose -f docker/compose.yml $COMPOSE_ENV exec -T db \
    psql -U "${POSTGRES_USER:-districore}" -c "CREATE DATABASE $TARGET;"
docker compose -f docker/compose.yml $COMPOSE_ENV exec -T db \
    pg_restore -U "${POSTGRES_USER:-districore}" -d "$TARGET" --no-owner < "$ARCHIVE"

echo "[restore] verifying"
docker compose -f docker/compose.yml $COMPOSE_ENV exec -T db psql -U "${POSTGRES_USER:-districore}" -d "$TARGET" -c \
    "SELECT 'app_user' t, count(*) FROM app_user
     UNION ALL SELECT 'audit_log', count(*) FROM audit_log;"

echo "[restore] done. Record the date and duration in docs/runbooks/restore-from-backup.md (B-3)."
