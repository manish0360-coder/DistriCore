# Runbook — Restore from backup

> **A backup that has never been restored does not count as a backup** (B-1).

## Rehearsal — quarterly, recorded

```bash
ls -t /srv/backups/districore-*.dump* | head -1        # the latest archive
make restore-rehearsal ARCHIVE=/srv/backups/districore-<timestamp>.dump.gpg
```

Restores into `districore_restore_test`. **Never** into the live one during a rehearsal — the
target refuses `districore` outright, because that is the one mistake here that cannot be
undone.

`make restore-rehearsal` **times the restore and prints the log row to paste below**. B-3 asks
for a date *and a duration*; a rehearsal that ends in "it worked" answers half of it. The
target does not write the row itself: a recorded result should be recorded by the person who
watched it.

The underlying script is unchanged and still usable directly:

```bash
./ops/restore.sh /srv/backups/districore-<timestamp>.dump.gpg districore_restore_test
```

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

> **Empty, and deliberately so.** The mechanism was added at M10 (`make restore-rehearsal`);
> **no rehearsal has been run**, so B-3 is not passed and the `00` §19.2 M10 → M11 gate is not
> met. Do not fill this table from anything but an observed run — an invented row is worse
> than an empty one, because an empty table is honest about what nobody has done.
>
> Record a **FAIL** just as carefully. A rehearsal that failed is the most valuable row here.

| Date | Archive | Duration | Outcome | By |
| --- | --- | --- | --- | --- |
| | | | | |
