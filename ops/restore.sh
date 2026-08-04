#!/usr/bin/env bash
# Restore. Written to be followed under stress by someone who did not write it (B-4).
# Rehearsed quarterly and the result recorded (B-3) — an untested backup is a belief.
set -euo pipefail

ARCHIVE="${1:?usage: restore.sh <dump-file> [target-db]}"
TARGET="${2:-districore_restore_test}"

if [[ "$ARCHIVE" == *.gpg ]]; then
    echo "[restore] decrypting"
    gpg --batch --yes --decrypt --passphrase "${DISTRICORE_BACKUP_PASSPHRASE:?passphrase required}" \
        --output "${ARCHIVE%.gpg}" "$ARCHIVE"
    ARCHIVE="${ARCHIVE%.gpg}"
fi

echo "[restore] restoring into '$TARGET' (NOT the live database)"
docker compose -f docker/compose.yml exec -T db \
    psql -U "${POSTGRES_USER:-districore}" -c "DROP DATABASE IF EXISTS $TARGET;"
docker compose -f docker/compose.yml exec -T db \
    psql -U "${POSTGRES_USER:-districore}" -c "CREATE DATABASE $TARGET;"
docker compose -f docker/compose.yml exec -T db \
    pg_restore -U "${POSTGRES_USER:-districore}" -d "$TARGET" --no-owner < "$ARCHIVE"

echo "[restore] verifying"
docker compose -f docker/compose.yml exec -T db psql -U "${POSTGRES_USER:-districore}" -d "$TARGET" -c \
    "SELECT 'app_user' t, count(*) FROM app_user
     UNION ALL SELECT 'audit_log', count(*) FROM audit_log;"

echo "[restore] done. Record the date and duration in docs/runbooks/restore-from-backup.md (B-3)."
