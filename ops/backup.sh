#!/usr/bin/env bash
# Nightly encrypted logical dump + verified offsite copy (00 §14, FD-16).
#
# **The logical layer, unchanged in mechanism and hardened in posture.** `pg_dump -Fc` is
# still what this takes, and it is still the artefact that restores into any cluster and
# survives a PostgreSQL version change. The continuous layer — `archive_command` plus
# `ops/ship-wal.sh` plus `ops/basebackup.sh` — is what delivers NFR-AVA-001's 15-minute RPO;
# this is the layer that answers "give me last night's database", and the two are kept
# separate because they fail differently.
#
# **Three defects were fixed here (C-5), and each reported success while being wrong:**
#
#   1. A missing passphrase only printed a warning, then the stamp was written anyway — so
#      `/healthz` reported a healthy backup for a dump sitting in clear (B-2 violated).
#   2. A missing remote silently skipped the offsite copy, and the stamp was written anyway
#      — so `/healthz` reported a healthy backup that existed only on the machine being
#      backed up (B-7 violated, which is the failure it is a rule about).
#   3. The stamp, the dump and the media sync all used *host* paths, while the volumes they
#      name (`backup_data`, `media_data`) are Docker named volumes mounted into the `app`
#      container. So `/healthz` — which runs in that container — could never see the stamp,
#      `backup.ok` was false on a correctly backed-up host, and `rclone sync /srv/media`
#      pointed at a host directory that does not exist. Under `set -e` that last one failed
#      the whole run, every night, on any host with a remote configured.
#
# Nothing below reports success unless the dump is encrypted, present at A-05, and proven to
# be there by reading the remote back.
set -euo pipefail

# --- fail closed on configuration ---------------------------------------------
: "${DISTRICORE_BACKUP_PASSPHRASE:?DISTRICORE_BACKUP_PASSPHRASE is required (S-07, B-2). Backups are encrypted before they leave the host — a warning is not a control}"
: "${DISTRICORE_BACKUP_REMOTE:?DISTRICORE_BACKUP_REMOTE is required (A-05, B-7). Backups are never stored solely on the machine being backed up}"

# **Staging is on the host; the stamp is in the volume.** Two different filesystems, and
# conflating them was defect 3 above. Nothing that leaves this directory is unencrypted.
STAGING="${DISTRICORE_BACKUP_DIR:-/var/backups/districore}"
STAMP="${DISTRICORE_BACKUP_STAMP_PATH:-/srv/backups/last_success}"
KEEP_DAYS="${DISTRICORE_BACKUP_KEEP_DAYS:-7}"
REMOTE_DB="${DISTRICORE_BACKUP_REMOTE%/}/db"
REMOTE_MEDIA="${DISTRICORE_BACKUP_REMOTE%/}/media"
NAME="districore-$(date -u +%Y%m%dT%H%M%SZ).dump"

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
DC=(docker compose -f docker/compose.yml --env-file .env)

for required in docker/compose.yml .env; do
    [ -f "$required" ] || {
        echo "[backup] $required not found. Run this from the repository root." >&2
        exit 2
    }
done

mkdir -p "$STAGING"

echo "[backup] dumping"
"${DC[@]}" exec -T db \
    pg_dump -U "${POSTGRES_USER:-districore}" -d "${POSTGRES_DB:-districore}" -Fc \
    > "$STAGING/$NAME"

echo "[backup] encrypting (B-2: encrypted before it leaves the host)"
gpg --batch --yes --symmetric --cipher-algo AES256 \
    --passphrase "$DISTRICORE_BACKUP_PASSPHRASE" \
    --output "$STAGING/$NAME.gpg" "$STAGING/$NAME"
rm -f "$STAGING/$NAME"
NAME="$NAME.gpg"

echo "[backup] copying offsite (B-7: never only on the machine being backed up)"
rclone copy "$STAGING/$NAME" "$REMOTE_DB/"

# **Read the remote back.** `rclone copy` exiting zero is not the claim; the claim is that
# the dump can be retrieved from A-05 tomorrow. This is the same verification
# `ops/ship-wal.sh` performs, for the same reason.
rclone lsf "$REMOTE_DB/" 2>/dev/null | tr -d '\r' | grep -qx "$NAME" || {
    echo "[backup] FAILED: $NAME is not present at the remote after copying." >&2
    echo "[backup] No stamp written — /healthz will report backup.ok: false, correctly." >&2
    exit 1
}

# --- media ---------------------------------------------------------------------
#
# **Read out of the volume, and encrypted.** The previous `rclone sync /srv/media` had two
# faults in one line: `/srv/media` is a path inside the `app` container, not on the host, and
# a sync ships proof-of-delivery photographs to A-05 **in clear**, which B-2 forbids.
#
# A full encrypted tar each night is the honest minimum and it is not free: `04` §9 sizes
# media at ~24 GB after five years, at which point a nightly full upload stops being
# reasonable. Recorded as technical debt with a threshold rather than left implicit — at
# V1 start this directory is close to empty.
echo "[backup] media (encrypted tar, read from the media_data volume)"
"${DC[@]}" exec -T app tar -C /srv -cf - media |
    gpg --batch --yes --symmetric --cipher-algo AES256 \
        --passphrase "$DISTRICORE_BACKUP_PASSPHRASE" |
    rclone rcat "$REMOTE_MEDIA/districore-media-$(date -u +%Y%m%dT%H%M%SZ).tar.gpg"

# --- retention -----------------------------------------------------------------
find "$STAGING" -name 'districore-*.dump*' -mtime "+$KEEP_DAYS" -delete

# --- stamp ---------------------------------------------------------------------
#
# Written **inside the app container**, which is where `/healthz` reads it from the
# `backup_data` volume. This is defect 3's fix: a health check that cannot go green on a
# healthy system is a health check that gets ignored, which is worse than not having one.
printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$NAME" |
    "${DC[@]}" exec -T app sh -c "mkdir -p \"\$(dirname '$STAMP')\" && cat > '$STAMP'"

echo "[backup] done: $NAME (verified at $REMOTE_DB)"
