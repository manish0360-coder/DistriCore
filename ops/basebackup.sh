#!/usr/bin/env bash
# Physical base backup — the PITR anchor, and the piece without which the WAL chain is
# unrecoverable (00 §14 FD-16; NFR-AVA-001).
#
# **This is not a second copy of the nightly dump.** `ops/backup.sh` takes a *logical* dump
# (`pg_dump -Fc`): a snapshot of rows, restorable into any cluster, and the right tool for
# "give me yesterday's database". WAL cannot be replayed into it — logical restores start a
# new timeline. Point-in-time recovery needs a *physical* base backup plus every segment
# archived since, and FD-16 keeps both layers for that reason: the dump survives a
# PostgreSQL version change, the base-plus-WAL chain is what delivers a 15-minute RPO.
#
# Weekly, because the chain length is what it costs: a longer interval means more WAL to
# replay and a longer RTO, a shorter one means more uploads of the whole cluster. At the
# DR-8 envelope a week of WAL replays well inside the four-hour RTO.
set -euo pipefail

: "${DISTRICORE_BACKUP_PASSPHRASE:?DISTRICORE_BACKUP_PASSPHRASE is required (S-07, B-2). A base backup is the entire database}"
: "${DISTRICORE_BACKUP_REMOTE:?DISTRICORE_BACKUP_REMOTE is required (A-05, B-7). A base backup only on the host it came from recovers nothing}"

REMOTE_BASE="${DISTRICORE_BACKUP_REMOTE%/}/base"
REMOTE_WAL="${DISTRICORE_BACKUP_REMOTE%/}/wal"
STAMP="${DISTRICORE_BASEBACKUP_STAMP_PATH:-/srv/backups/basebackup_last_success}"
KEEP="${DISTRICORE_BASEBACKUP_KEEP:-3}"
NAME="districore-base-$(date -u +%Y%m%dT%H%M%SZ).tar.gz.gpg"

DC=(docker compose -f docker/compose.yml --env-file .env)

for required in docker/compose.yml .env; do
    [ -f "$required" ] || {
        echo "[basebackup] $required not found. Run this from the repository root." >&2
        exit 2
    }
done

# --- take it -------------------------------------------------------------------
#
# `-X fetch` embeds the WAL this base needs to reach a consistent state, which is what makes
# the base self-sufficient and what makes the retention rule below safe: any archived
# segment older than a retained base backup is genuinely redundant.
#
# `-z` is PostgreSQL's own gzip, so gpg is told not to compress again — compressing
# ciphertext-bound data twice costs CPU on the production host and saves nothing.
# Streamed, never staged: no unencrypted copy of the whole cluster is ever written to disk.
echo "[basebackup] streaming base backup -> $REMOTE_BASE/$NAME"
"${DC[@]}" exec -T db pg_basebackup \
    -U "${POSTGRES_USER:-districore}" \
    -D - -Ft -z -X fetch --checkpoint=fast |
    gpg --batch --yes --symmetric --cipher-algo AES256 --compress-algo none \
        --passphrase "$DISTRICORE_BACKUP_PASSPHRASE" |
    rclone rcat "$REMOTE_BASE/$NAME"

# --- prove it arrived ----------------------------------------------------------
remote_list="$(rclone lsf "$REMOTE_BASE/" 2>/dev/null | tr -d '\r' | grep -E '^districore-base-.*\.gpg$' | sort || true)"
printf '%s\n' "$remote_list" | grep -qx "$NAME" || {
    echo "[basebackup] FAILED: $NAME is not at the remote after upload. No stamp written." >&2
    exit 1
}

# --- retention, and the one rule that matters ----------------------------------
#
# **WAL retention is decided here, not in `ops/ship-wal.sh`.** A segment stops being needed
# only when no retained base backup needs it, and the base backup schedule is the only place
# that knows where the oldest retained chain starts. Two schedules each pruning by their own
# clock is how a recovery discovers, months later, that the chain begins after the base.
#
# Names carry a UTC timestamp, so sorting by name sorts by time — no dependence on the
# remote's idea of modification time, which varies by provider.
keep_from="$(printf '%s\n' "$remote_list" | tail -n "$KEEP" | head -1)"
for old in $(printf '%s\n' "$remote_list" | head -n -"$KEEP"); do
    echo "[basebackup] retiring base backup $old"
    rclone deletefile "$REMOTE_BASE/$old"
done

# `districore-base-20260912T023000Z.tar.gz.gpg` -> `2026-09-12 02:30:00`
oldest_ts="$(printf '%s' "$keep_from" |
    sed -E 's/^districore-base-([0-9]{4})([0-9]{2})([0-9]{2})T([0-9]{2})([0-9]{2})([0-9]{2})Z.*$/\1-\2-\3 \4:\5:\6/')"
if [ "$oldest_ts" = "$keep_from" ]; then
    echo "[basebackup] WARNING: cannot parse a timestamp from '$keep_from'." >&2
    echo "[basebackup] WAL retention SKIPPED — the archive will grow rather than risk" >&2
    echo "[basebackup] deleting a segment the oldest retained base backup still needs." >&2
else
    wal_min_age=$(( $(date -u +%s) - $(date -u -d "$oldest_ts" +%s) ))
    if [ "$wal_min_age" -gt 0 ]; then
        echo "[basebackup] pruning WAL older than $oldest_ts (${wal_min_age}s) — before the oldest retained base"
        rclone delete "$REMOTE_WAL" --min-age "${wal_min_age}s"
    fi
fi

# --- stamp ---------------------------------------------------------------------
#
# Inside the container, where `/healthz` reads it from the `backup_data` volume. WAL that is
# offsite with no base backup to replay it into is not recovery readiness, so the endpoint
# reports this separately rather than folding it into the WAL check.
printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$NAME" |
    "${DC[@]}" exec -T app sh -c "mkdir -p \"\$(dirname '$STAMP')\" && cat > '$STAMP'"

echo "[basebackup] done: $NAME ($(printf '%s\n' "$remote_list" | wc -l | tr -d ' ') retained, keep=$KEEP)"
