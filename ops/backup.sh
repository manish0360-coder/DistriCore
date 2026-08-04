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
docker compose -f docker/compose.yml -f docker/compose.prod.yml exec -T db \
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
