# Runbook — Restore from backup

> **A backup that has never been restored does not count as a backup** (B-1).

## Rehearsal — quarterly, recorded

```bash
./ops/restore.sh /srv/backups/districore-<timestamp>.dump.gpg districore_restore_test
```

Restores into a scratch database. **Never** into the live one during a rehearsal.

## Real recovery

1. Provision a host; install Docker.
2. `git clone` the repository; check out the deployed tag.
3. Restore `.env` from the password manager.
4. `docker compose -f docker/compose.yml -f docker/compose.prod.yml up -d db`
5. `./ops/restore.sh <archive> districore`
6. Start the application; confirm `/healthz`.
7. Verify: user count, audit row count, most recent audit timestamp.

Targets: **RPO ≈ 1 hour** local · **RTO ≈ 2 hours** (ADR-012, FD-16).

## Rehearsal log

| Date | Archive | Duration | Outcome | By |
| --- | --- | --- | --- | --- |
| | | | | |
