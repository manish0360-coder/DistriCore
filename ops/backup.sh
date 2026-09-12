#!/usr/bin/env bash
# Nightly encrypted dump + offsite copy (00 §14, FD-16).
# Writes a success stamp that /healthz reads — because backups fail silently for
# months and are discovered during a restore (B-5).
set -euo pipefail

STAMP="${DISTRICORE_BACKUP_STAMP_PATH:-/srv/backups/last_success}"
DIR="$(dirname "$STAMP")"
KEEP_DAYS="${DISTRICORE_BACKUP_KEEP_DAYS:-7}"
NAME="districore-$(date -u +%Y%m%dT%H%M%SZ).dump"

mkdir -p "$DIR"

echo "[backup] dumping"
# Same reason as ops/restore.sh: the project directory is `docker/`, so compose
# never finds the root `.env` on its own and `POSTGRES_PASSWORD` fails to interpolate.
#
# **The prod overlay is not loaded, deliberately.** `db` is defined in the base file and
# `exec` attaches to whatever is already running — the overlay only adds `ports: []`, which
# `exec` does not consult, and the project name is fixed by `name: districore`. Loading it
# made this script depend on every variable the overlay interpolates, including
# `DISTRICORE_DOMAIN`, which `compose.prod.yml` now requires. A backup that stops because
# the web server has no certificate name is the B-3 defect again: a compose file loaded for
# no reason, taking the script down with it.
docker compose -f docker/compose.yml --env-file .env exec -T db \
    pg_dump -U "${POSTGRES_USER:-districore}" -d "${POSTGRES_DB:-districore}" -Fc \
    > "$DIR/$NAME"

if [ -n "${DISTRICORE_BACKUP_PASSPHRASE:-}" ]; then
    echo "[backup] encrypting (B-2: encrypted before it leaves the host)"
    gpg --batch --yes --symmetric --cipher-algo AES256 \
        --passphrase "$DISTRICORE_BACKUP_PASSPHRASE" \
        --output "$DIR/$NAME.gpg" "$DIR/$NAME"
    rm -f "$DIR/$NAME"
    NAME="$NAME.gpg"
else
    echo "[backup] WARNING: no passphrase set — dump is NOT encrypted (B-2)" >&2
fi

if [ -n "${DISTRICORE_BACKUP_REMOTE:-}" ]; then
    echo "[backup] copying offsite (B-7: never only on the machine being backed up)"
    rclone copy "$DIR/$NAME" "$DISTRICORE_BACKUP_REMOTE"
    rclone sync /srv/media "$DISTRICORE_BACKUP_REMOTE/media"
fi

find "$DIR" -name 'districore-*.dump*' -mtime "+$KEEP_DAYS" -delete

date -u +%Y-%m-%dT%H:%M:%SZ > "$STAMP"
echo "[backup] done: $NAME"
