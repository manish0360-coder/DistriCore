# Runbook — Restore from backup

> **A backup that has never been restored does not count as a backup** (B-1).

## Two layers, two procedures — read this first

There are two recovery mechanisms and they answer different questions. Using the wrong one
under pressure wastes the hours the RTO is made of.

| You need | Use | Recovers to |
| --- | --- | --- |
| Last night's database — a bad migration, a wrong bulk change, a version upgrade gone wrong | **Logical**, below | The nightly dump, up to ~24 h ago |
| A specific instant — an accidental delete at 14:32, an operator mistake you can time | **PITR**, below | Any instant covered by the WAL archive |
| The host is gone | **Total host loss**, below | Within ~15 minutes of the failure (NFR-AVA-001) |

WAL **cannot** be replayed into a logical restore: `pg_restore` builds a new cluster on a new
timeline. If you need a point in time, you need the physical base backup plus the archive —
which is the second procedure, not a variation of the first.

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

## Real recovery from the nightly dump

**For the "last night's database" case only** — a bad migration, a wrong bulk change, a
PostgreSQL version upgrade that has to be redone. It recovers to the dump, so up to a day of
work is lost. If you can time the damage, or the host is gone, use one of the two procedures
below instead; this one cannot reach either.

1. Provision a host; install Docker.
2. `git clone` the repository; check out the deployed tag.
3. Restore `.env` from the password manager.
4. `docker compose -f docker/compose.yml -f docker/compose.prod.yml up -d db`
5. `./ops/restore.sh <archive> districore`
6. Start the application; confirm `/healthz`.
7. Verify: user count, audit row count, most recent audit timestamp.

---

## PITR — recover to a specific instant

**This is the procedure NFR-AVA-001 is about.** It reads the **offsite** archive, because the
local one does not exist in the scenario the requirement was written for.

```bash
make pitr-rehearsal TARGET_TIME='2026-09-12 14:35:00+00'
```

It picks the newest base backup at or before the target, decrypts it and every offsite WAL
segment, recovers a **scratch** cluster, and prints the newest business fact that survived.
Nothing it builds touches the live cluster or the live volumes, and the scratch tree — which
holds a fully decrypted copy of the database — is deleted when it exits.

**How to rehearse it so the answer means something.** Recovering to "now" proves the
machinery runs and nothing about the recovery point. Instead:

1. Note the UTC time. Write something through the app — one login is enough, it lands in
   `audit_log`.
2. Note the UTC time again. **Wait six minutes**: up to 300 s for `archive_timeout` to close
   the segment, then up to 300 s for the shipping timer.
3. Recover to the second time you noted.
4. `newest_fact_recovered` must include the write from step 1. **The gap between it and step
   2 is the achieved RPO** — that number, not the configuration, is the evidence.

If the write is missing, the chain has a hole. Do not adjust the target time until it
appears: read `pg_stat_archiver` and the `districore-wal-ship` journal, because a rehearsal
retried until it passes is not a rehearsal.

---

## Real recovery — total host loss

The case the continuous layer exists for. Targets: **RPO ≤ 15 minutes · RTO ≤ 4 hours**
(NFR-AVA-001; `docs/M11.2_Recovery_Report.md`).

1. Provision a host; install Docker, `gpg` and `rclone`.
2. `git clone` the repository; check out the deployed tag.
3. Restore `.env` from the password manager — **including `DISTRICORE_BACKUP_PASSPHRASE`,
   without which the archive is unreadable** — and the `rclone` remote configuration.
4. Recover the cluster to the latest available point:
   ```bash
   ./ops/restore-pitr.sh "$(date -u +'%Y-%m-%d %H:%M:%S+00')"
   ```
   Confirm `newest_fact_recovered` is close to the failure time. **Check this before going
   further**: the scratch cluster is where you find out the archive is short, and finding out
   after you have started serving traffic is much worse.
5. Start the stack, then load the recovered state into it. Two routes — take the first:
   - **Preferred** — `docker compose … up -d db`, then `./ops/restore.sh` the newest
     nightly dump into `districore`, and accept the dump's recovery point *only if* step 4
     showed the archive is intact and you then replay onto it. If any doubt remains, use the
     second route.
   - **Physical** — stop `db`, replace the `db_data` volume's contents with the cluster step 4
     recovered, and start it. Faster and exact, and it is the route that actually delivers the
     15 minutes.
6. Start the application; confirm `/healthz` reports `database.ok` and `disk.ok`.
7. **Re-arm the continuous layer before anything else**: install both timers
   (`docs/runbooks/deploy.md` step 2) and confirm `recovery_ready: true`. A recovered host
   with no archive is one incident away from the same position.
8. Verify: user count, audit row count, newest audit timestamp. Record the outcome below.

---

## Rehearsal log — logical layer

> **Observed runs only.** Do not fill this table from anything but a rehearsal someone
> watched — an invented row is worse than an empty one, because an empty table is honest
> about what nobody has done.
>
> Record a **FAIL** just as carefully. A rehearsal that failed is the most valuable row here.

| Date | Archive | Duration | Outcome | By |
| --- | --- | --- | --- | --- |
| 2026-09-07T16:56:43Z | districore-20260907T163713Z.dump.gpg | 8s | PASS | Manish Kumar |

2026-09-07: restored into `districore_restore_test`; the live database was not targeted.
Decryption was GPG AES256.CFB. Source and restored counts agreed: `app_user` 1, `audit_log` 1
— non-zero on both sides, which is what makes the PASS mean something (B-1).

**This row bounds `pg_restore`, not recovery, and it says nothing about RPO.** 8 s is how
long a dump took to load into a scratch database. NFR-AVA-001 is discharged by the log
below.

---

## PITR rehearsal log — continuous layer (NFR-AVA-001)

> **Empty, and deliberately so.** The mechanism exists; no rehearsal has run, because one
> requires A-03 and A-05 and neither is provisioned. `02` §21.6 verifies this requirement
> *by rehearsal* — so until there is a row here the verdict is **NOT MEASURED**, which is
> what `docs/M11.2_Recovery_Report.md` records.
>
> **Observed runs only.** A row asserting a recovery point nobody measured is worse than an
> empty table, because the next reader will believe it. Record a **FAIL** just as carefully:
> a rehearsal that lost data is the most valuable row this table will ever hold.
>
> **Achieved RPO** is the gap between `newest_fact_recovered` and the last write before the
> simulated failure — not the target, not `archive_timeout`. If you cannot state it, the
> rehearsal did not answer the question.

| Date | Recovery target | Duration | Achieved RPO | Outcome | By |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
