#!/usr/bin/env bash
# Point-in-time recovery rehearsal — proving the CHAIN, not just a dump (B-1, NFR-AVA-002).
#
# `ops/restore.sh` rehearses the logical layer: decrypt a `pg_dump`, `pg_restore` it, count
# rows. It cannot say anything about NFR-AVA-001, because a 15-minute RPO is a property of
# the continuous layer — a physical base backup plus every WAL segment archived since — and
# a logical restore does not touch that chain at all.
#
# This script recovers a real cluster from the offsite base backup, replays the offsite WAL
# to a requested instant, and reports **the latest business fact that survived**. That number
# is the achieved recovery point. It is the only honest evidence for the requirement, and it
# is why `docs/M11.2_Recovery_Report.md` refuses to claim compliance from configuration.
#
#   ./ops/restore-pitr.sh '2026-09-12 14:35:00+00'
#
# Everything it builds is scratch and is deleted at the end. It never opens the live cluster,
# the live volumes, or the live database.
set -euo pipefail

TARGET_TIME="${1:?usage: restore-pitr.sh '<recovery target time, e.g. 2026-09-12 14:35:00+00>'}"
: "${DISTRICORE_BACKUP_PASSPHRASE:?DISTRICORE_BACKUP_PASSPHRASE is required — the offsite archive is encrypted (B-2)}"
: "${DISTRICORE_BACKUP_REMOTE:?DISTRICORE_BACKUP_REMOTE is required — this rehearsal recovers from A-05, which is the copy that matters}"

REMOTE_BASE="${DISTRICORE_BACKUP_REMOTE%/}/base"
REMOTE_WAL="${DISTRICORE_BACKUP_REMOTE%/}/wal"
IMAGE="${DISTRICORE_PITR_IMAGE:-postgres:16-alpine}"
CONTAINER=districore-pitr-rehearsal
WAIT_SECONDS="${DISTRICORE_PITR_WAIT_SECONDS:-900}"
DB_USER="${POSTGRES_USER:-districore}"
DB_NAME="${POSTGRES_DB:-districore}"
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/districore-pitr-XXXXXX")"

# **Refuse to be pointed at anything live.** The one mistake in this procedure that cannot be
# undone is recovering over the production cluster, so the scratch directory is created by
# `mktemp` rather than accepted as an argument, and the container name is fixed.
cleanup() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    # The scratch tree contains a fully decrypted copy of the database. It does not outlive
    # the rehearsal — this is the same reasoning that removes the plaintext dump in
    # `ops/backup.sh` rather than leaving it next to the encrypted one.
    docker run --rm -v "$SCRATCH:/pitr" "$IMAGE" sh -c 'rm -rf /pitr/pgdata' >/dev/null 2>&1 || true
    rm -rf "$SCRATCH"
}
trap cleanup EXIT

echo "==> PITR rehearsal"
echo "    target time : $TARGET_TIME"
echo "    scratch     : $SCRATCH"

# --- choose the base backup ----------------------------------------------------
#
# The newest base backup taken **at or before** the target, because a base backup from after
# the target cannot be rewound to it. Names carry a UTC timestamp, so name order is time
# order.
target_stamp="$(date -u -d "$TARGET_TIME" +%Y%m%dT%H%M%SZ)"
base="$(rclone lsf "$REMOTE_BASE/" 2>/dev/null | tr -d '\r' |
    grep -E '^districore-base-[0-9]{8}T[0-9]{6}Z\.tar\.gz\.gpg$' | sort |
    awk -v t="districore-base-${target_stamp}" '$0 <= t' | tail -1)"

[ -n "$base" ] || {
    echo "[pitr] no base backup at $REMOTE_BASE is older than $TARGET_TIME." >&2
    echo "[pitr] The chain cannot start after the point it must recover to." >&2
    echo "[pitr] Run ./ops/basebackup.sh, then rehearse a target after it." >&2
    exit 1
}
echo "    base        : $base"

# --- fetch and decrypt ---------------------------------------------------------
#
# Decryption is on the host because `gpg` is here and not in the PostgreSQL image — the same
# split `ops/backup.sh` and `ops/ship-wal.sh` use. Nothing is written back to the remote.
mkdir -p "$SCRATCH/wal"
echo "[pitr] fetching base backup"
rclone cat "$REMOTE_BASE/$base" |
    gpg --batch --yes --decrypt --passphrase "$DISTRICORE_BACKUP_PASSPHRASE" \
        > "$SCRATCH/base.tar.gz"

echo "[pitr] fetching WAL archive"
segments=0
for encrypted in $(rclone lsf "$REMOTE_WAL/" 2>/dev/null | tr -d '\r' | grep -E '\.gpg$' | sort); do
    rclone cat "$REMOTE_WAL/$encrypted" |
        gpg --batch --yes --decrypt --passphrase "$DISTRICORE_BACKUP_PASSPHRASE" \
            > "$SCRATCH/wal/${encrypted%.gpg}"
    segments=$((segments + 1))
done
echo "[pitr] $segments segments decrypted"

# --- build the cluster ---------------------------------------------------------
#
# Unpacked and owned inside a container, not on the host: PostgreSQL refuses a data
# directory it does not own at mode 0700, and a host `tar` would leave it owned by whoever
# ran this script. Running the unpack as root in the same image avoids guessing the uid.
#
# **The recovery settings go in `postgresql.auto.conf`, and the base carries none of ours.**
# Production's WAL settings are command-line flags in `docker/compose.yml`, so they are not
# in the `postgresql.conf` the base backup copied — which is why this cluster does not try
# to archive, and why it needs `restore_command` written explicitly.
echo "[pitr] unpacking and configuring recovery"
docker run --rm -v "$SCRATCH:/pitr" "$IMAGE" sh -ec "
    mkdir -p /pitr/pgdata
    tar -xzf /pitr/base.tar.gz -C /pitr/pgdata
    cat >> /pitr/pgdata/postgresql.auto.conf <<CONF
# Written by ops/restore-pitr.sh — rehearsal only.
restore_command = 'cp /pitr/wal/%f %p'
recovery_target_time = '$TARGET_TIME'
recovery_target_action = 'promote'
archive_mode = off
CONF
    touch /pitr/pgdata/recovery.signal
    chown -R postgres:postgres /pitr/pgdata
    chmod 700 /pitr/pgdata
"

echo "[pitr] starting recovery"
docker run -d --name "$CONTAINER" \
    -v "$SCRATCH/pgdata":/var/lib/postgresql/data \
    -v "$SCRATCH/wal":/pitr/wal:ro \
    "$IMAGE" >/dev/null

# --- wait for recovery to finish -----------------------------------------------
#
# `pg_isready` is not the signal: hot standby accepts connections *during* replay, so a
# query answered then would report a recovery point earlier than the one achieved.
# `pg_is_in_recovery()` going false is the signal, and it is what `recovery_target_action =
# promote` produces when the target is reached.
deadline=$(( $(date -u +%s) + WAIT_SECONDS ))
while :; do
    if docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -tAc \
        'SELECT NOT pg_is_in_recovery()' 2>/dev/null | grep -qx t; then
        break
    fi
    if [ "$(date -u +%s)" -ge "$deadline" ]; then
        echo "[pitr] FAILED: recovery did not complete within ${WAIT_SECONDS}s." >&2
        echo "[pitr] The PostgreSQL log is the diagnosis, not a guess:" >&2
        docker logs --tail 40 "$CONTAINER" >&2 || true
        exit 1
    fi
    sleep 5
done

# --- the evidence --------------------------------------------------------------
#
# **The achieved recovery point, read from a business fact.** `audit_log.occurred_at` is
# append-only (NFR-AUD-001) and written by the application, so the newest row that survived
# replay is the newest state the business would get back. Counting rows — which
# `ops/restore.sh` does — proves a restore happened; this proves *how much was kept*, which
# is the only thing RPO means.
echo ""
echo "==> recovered. Evidence:"
docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "
    SELECT
        (SELECT count(*) FROM app_user)                AS users,
        (SELECT count(*) FROM audit_log)               AS audit_rows,
        (SELECT max(occurred_at) FROM audit_log)       AS newest_fact_recovered,
        now()                                          AS recovered_at,
        '$TARGET_TIME'::timestamptz                    AS recovery_target;
"
echo ""
echo "    The gap between 'newest_fact_recovered' and the last write before the simulated"
echo "    failure IS the achieved RPO. Record it in docs/runbooks/restore-from-backup.md."
echo "    Configuration does not evidence NFR-AVA-001; this number does."
