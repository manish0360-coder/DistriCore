#!/usr/bin/env bash
# Continuous encrypted offsite WAL archival — the second half of FD-16's continuous layer
# and the mechanism NFR-AVA-001's "RPO <= 15 minutes" actually rests on (00 §14, 03 §4.4).
#
# PostgreSQL's `archive_command` (docker/compose.yml) copies each closed segment to the
# `wal_archive` volume and stops there: the server's shell has no `gpg` and no `rclone`, and
# a network upload inside `archive_command` would let an unreachable A-05 stall WAL
# recycling and take the database down. So this script does what `ops/backup.sh` already
# does for the nightly dump — encrypt and ship from the host (B-2: encrypted before they
# leave the host; B-7: never only on the machine being backed up).
#
# **Fail closed, everywhere.** A run that cannot encrypt, cannot reach the remote, or cannot
# prove a segment arrived exits non-zero and writes no stamp. `/healthz` then reports
# `wal_offsite.ok: false` with a real lag figure, and the A-08 monitor raises it. There is no
# path through this script that reports success for WAL that is not offsite.
set -euo pipefail

# --- fail closed on configuration, before touching anything -------------------
#
# These were optional for the nightly dump and that was the C-5 defect: `backup.sh` warned
# on stderr about a missing passphrase and then stamped success anyway, so `/healthz`
# reported a healthy backup for an unencrypted, host-only dump. Continuous archival cannot
# be optional at all — it is the requirement.
: "${DISTRICORE_BACKUP_PASSPHRASE:?DISTRICORE_BACKUP_PASSPHRASE is required (S-07, B-2). WAL is full row data and does not leave this host in clear}"
: "${DISTRICORE_BACKUP_REMOTE:?DISTRICORE_BACKUP_REMOTE is required (A-05, B-7). WAL that stays on this host does not survive losing it, which is the case NFR-AVA-001 exists for}"

REMOTE_WAL="${DISTRICORE_BACKUP_REMOTE%/}/wal"
ARCHIVE_DIR=/srv/wal_archive
STAMP="${DISTRICORE_WAL_STAMP_PATH:-/srv/backups/wal_offsite_last_success}"
# Two archive_timeout periods. Older than this and the local archive is not being fed, so
# "everything local is offsite" would be a true statement about a stalled archiver — the
# shape of false success this milestone exists to remove.
MAX_LOCAL_AGE="${DISTRICORE_WAL_ARCHIVE_MAX_AGE_SECONDS:-600}"
# How long a shipped segment stays on this host. It buys a fast local PITR without a
# download; the authoritative copy is offsite from the moment it is verified.
LOCAL_KEEP_HOURS="${DISTRICORE_WAL_LOCAL_KEEP_HOURS:-48}"

# The prod overlay is not loaded, for the reason `ops/backup.sh` records: `exec` attaches to
# a running container, the overlay adds nothing this needs, and loading it would couple WAL
# archival to `DISTRICORE_DOMAIN`. A backup that stops because the web server has no
# certificate name is the B-3 defect.
DC=(docker compose -f docker/compose.yml --env-file .env)

for required in docker/compose.yml .env; do
    [ -f "$required" ] || {
        echo "[ship-wal] $required not found. Run this from the repository root." >&2
        exit 2
    }
done

# --- what is here, and what is already there ----------------------------------
#
# **Remote state is read from the remote.** Local bookkeeping — a marker file, a cursor —
# would be a second source of truth that drifts, and the thing being claimed is "this
# segment is offsite". The only honest answer to that comes from the offsite target.
#
# WAL segment names are 24 hex characters. `.history` files carry timeline changes and
# `.backup` files label base backups; both are part of the recovery chain and both ship.
# `.part` files are in-flight copies and must not.
local_segments="$("${DC[@]}" exec -T db sh -c "ls -1 $ARCHIVE_DIR 2>/dev/null" |
    tr -d '\r' | grep -E '^([0-9A-F]{24}(\.[0-9A-F]{8}\.backup)?|[0-9A-F]{8}\.history)$' | sort || true)"

if [ -z "$local_segments" ]; then
    echo "[ship-wal] no archived segments yet — PostgreSQL has not closed one since startup" >&2
    echo "[ship-wal] nothing to ship, and nothing proved. No stamp written." >&2
    exit 0
fi

# **A real WAL segment, not whatever sorts last.** `.history` and `.backup` files share the
# hex prefix and sort *after* the segments (`.` < `0` at the suffix boundary is not what
# happens — the differing hex digit decides first), and a timeline history file is written
# once at promotion and then never touched. Using its mtime for the staleness check below
# would report a healthy archiver for one that stopped hours ago.
newest="$(printf '%s\n' "$local_segments" | grep -E '^[0-9A-F]{24}$' | tail -1)"
if [ -z "$newest" ]; then
    echo "[ship-wal] the archive holds only history/label files, no WAL segment yet." >&2
    exit 0
fi
newest_epoch="$("${DC[@]}" exec -T db stat -c %Y "$ARCHIVE_DIR/$newest" | tr -d '\r')"
age=$(( $(date -u +%s) - newest_epoch ))
if [ "$age" -gt "$MAX_LOCAL_AGE" ]; then
    echo "[ship-wal] REFUSED: newest local segment is ${age}s old (limit ${MAX_LOCAL_AGE}s)." >&2
    echo "[ship-wal] PostgreSQL has stopped archiving. Shipping what is here would stamp" >&2
    echo "[ship-wal] success for a chain that has a hole in it. Check pg_stat_archiver:" >&2
    echo "[ship-wal]   make psql -> SELECT * FROM pg_stat_archiver;" >&2
    exit 1
fi

remote_before="$(rclone lsf "$REMOTE_WAL/" 2>/dev/null | tr -d '\r' | sed 's/\.gpg$//' | sort || true)"

to_ship="$(comm -23 <(printf '%s\n' "$local_segments") <(printf '%s\n' "$remote_before"))"

# --- ship ----------------------------------------------------------------------
#
# Streamed, never staged: the segment is read out of the volume, encrypted, and written to
# the remote in one pipeline, so an unencrypted copy never exists anywhere but inside the
# host's own archive volume. `pipefail` is what makes a failure anywhere in that pipeline a
# failure of the run.
shipped=0
for segment in $to_ship; do
    echo "[ship-wal] $segment"
    "${DC[@]}" exec -T db cat "$ARCHIVE_DIR/$segment" |
        gpg --batch --yes --symmetric --cipher-algo AES256 \
            --passphrase "$DISTRICORE_BACKUP_PASSPHRASE" |
        rclone rcat "$REMOTE_WAL/$segment.gpg"
    shipped=$((shipped + 1))
done

# --- prove it, from the remote -------------------------------------------------
#
# The upload exiting zero is not the claim. The claim is that the segment is retrievable
# from A-05, so the remote is listed again and every name is checked. This is the difference
# between "we ran rclone" and "recovery readiness is verified" — and it is the one
# `/healthz` reports.
remote_after="$(rclone lsf "$REMOTE_WAL/" 2>/dev/null | tr -d '\r' | sed 's/\.gpg$//' | sort || true)"
missing="$(comm -23 <(printf '%s\n' "$local_segments") <(printf '%s\n' "$remote_after"))"
if [ -n "$missing" ]; then
    echo "[ship-wal] FAILED: these segments are not present at the remote after shipping:" >&2
    printf '[ship-wal]   %s\n' $missing >&2
    exit 1
fi

# --- retention -----------------------------------------------------------------
#
# **Local:** only segments already verified offsite, and only once they are older than the
# local window. Pruning an unshipped segment would break the chain permanently.
#
# **Remote retention is deliberately absent from this script.** A WAL segment is only
# useless once no retained base backup needs it, and this script does not know the base
# backup retention — `ops/basebackup.sh` does, and prunes WAL there, from the oldest base
# backup it keeps. Splitting it would let two schedules disagree about where the chain
# starts, which is the one form of pruning that silently destroys recoverability.
"${DC[@]}" exec -T db sh -c \
    "find $ARCHIVE_DIR -maxdepth 1 -type f -mmin +$((LOCAL_KEEP_HOURS * 60)) -delete" || true

# --- stamp ---------------------------------------------------------------------
#
# **Written inside the container, and that is the fix, not a detail.** `/healthz` runs in the
# `app` container and reads this path from the `backup_data` volume. `ops/backup.sh` wrote
# its stamp to the same path on the *host*, which is a different filesystem — so the health
# endpoint could never see it and `backup.ok` was false on a correctly backed-up host. A
# monitor that cannot go green is a monitor that gets ignored.
printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$newest" |
    "${DC[@]}" exec -T app sh -c "mkdir -p \"\$(dirname '$STAMP')\" && cat > '$STAMP'"

echo "[ship-wal] done: $shipped shipped, $(printf '%s\n' "$local_segments" | wc -l | tr -d ' ') verified offsite, newest $newest"
