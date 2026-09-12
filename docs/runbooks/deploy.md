# Runbook — Deploy

Manual by decision until automation has earned it (FD-19). The operator is present at
the moment things go wrong, which is when judgement is worth more than automation.

## First deploy only — once per host

Everything below this heading is done once. A repeat deploy starts at *Before*.

**Operator-provisioned, and not in this repository** — `00` §2.5 and §2.6 schedule each at
M11: **A-03** VPS · **A-04** domain, DNS A record pointed at the host · **A-05** offsite
target reachable by `rclone` · **S-04** deploy key · **S-05** SSH key · **S-07** backup
passphrase · **A-08** uptime monitor. **K-1/S-06**, the Android keystore, is separate and
irreversible — `00` §2.3.

**1. `.env` on the server**, `0600`, owned by the deploy user (FD-13). Copy `.env.example`
and fill it. Three entries must name the same domain, and the stack refuses to start
otherwise:

```
DISTRICORE_DOMAIN=distri.example.com
DISTRICORE_ALLOWED_HOSTS=distri.example.com
DISTRICORE_CSRF_TRUSTED_ORIGINS=https://distri.example.com
```

`DISTRICORE_DOMAIN` is what Caddy obtains the certificate for. `compose.prod.yml` requires
it — a deploy without it stops at interpolation rather than serving an untrusted
`localhost` certificate for a domain you have already bought.

`DJANGO_SETTINGS_MODULE=config.settings.prod`, `DISTRICORE_DEBUG=false`,
`DISTRICORE_LOG_FORMAT=json`, a real `DISTRICORE_SMS_PROVIDER` and a `DISTRICORE_SECRET_KEY`
of at least 50 characters — `config/settings/prod.py` asserts all five at import and refuses
to start if any is wrong.

**2. Install the nightly backup** (`00` §14 FD-16, B-5). The script has always existed;
nothing scheduled it, so a fresh host has no backups and `/healthz` reports
`backup.ok: false` for ever.

**First, confirm the scripts are executable.** They are mode `100755` in git since M11.2, but
the repository is developed on a Windows mount where `core.filemode=false`, so the bit can be
dropped again by a future re-add without anyone noticing locally. A unit whose `ExecStart` is
not executable fails with `203/EXEC` — scheduled and inert, which is the M11.1 defect exactly.
No test can catch this: the backend image has no git, and a bind-mounted file's permissions
are the mount's, not the index's.

```bash
ls -l /opt/districore/ops/*.sh          # every one must be -rwxr-xr-x
chmod +x /opt/districore/ops/*.sh       # if any is not
```

```bash
sudo cp /opt/districore/ops/districore-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now districore-backup.timer
systemctl list-timers districore-backup.timer     # confirm the next run
sudo systemctl start districore-backup.service    # prove it works now, do not wait
```

Then confirm `/healthz` reports `backup.ok: true`.

**`DISTRICORE_BACKUP_PASSPHRASE` and `DISTRICORE_BACKUP_REMOTE` are now mandatory.** All
three backup scripts refuse to run without them and write no success stamp — unencrypted
data must not leave the host (B-2) and a backup that never leaves it does not survive losing
it (B-7). A warning was what they used to do, and `/healthz` reported health for an
unencrypted host-only dump the whole time.

**3. Install the continuous layer** — this is what NFR-AVA-001's 15-minute RPO rests on
(`docs/M11.2_Recovery_Report.md`). PostgreSQL archives WAL to the `wal_archive` volume on
its own; these two timers encrypt it, ship it to A-05, and keep a base backup to replay it
into:

```bash
sudo cp /opt/districore/ops/districore-wal-ship.{service,timer} /etc/systemd/system/
sudo cp /opt/districore/ops/districore-basebackup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now districore-wal-ship.timer districore-basebackup.timer

# Take the first base backup now. Until one exists, PITR is impossible and the WAL
# archive has nothing to be replayed into — do not wait for Sunday.
sudo systemctl start districore-basebackup.service
sudo systemctl start districore-wal-ship.service
systemctl list-timers 'districore-*'
```

Then confirm **`recovery_ready: true`** on `/healthz`. That one boolean requires all three
links — PostgreSQL still archiving, WAL verified present at A-05, and a base backup to
recover into — and it is the field the monitor watches. If it is false, the three
`wal_archive` / `wal_offsite` / `basebackup` checks say which link is missing.

**4. Point the uptime monitor (A-08) at `https://<domain>/healthz`.** That endpoint reports
database, disk, backup age and `recovery_ready`; the monitor polling it is what turns three
of `00` §13.1's four alerts into email. Without it nothing watches, whatever the endpoint
says.

**5. Rehearse both recoveries** — `docs/runbooks/restore-from-backup.md`. B-1: a backup that
has never been restored does not count as one, and the first real one on a new host is the
one worth proving. **Two rehearsals, not one:** the logical restore (B-3) and the **PITR
rehearsal**, which is the only thing that can discharge NFR-AVA-001. Its log is empty until
you run it here.

---

## Before

1. `main` is green in CI.
2. `CHANGELOG.md` updated.
3. Version bumped; annotated tag pushed.
4. **Manual backup taken and verified** — `./ops/backup.sh` (B-6, MIG-7).
5. Migrations reviewed against `docs/runbooks/migration-review.md`.

## Deploy

```bash
ssh <server>
cd /opt/districore
git fetch --tags && git checkout <tag>
docker compose -f docker/compose.yml -f docker/compose.prod.yml --env-file .env up -d --build --wait
curl -fsS https://<domain>/healthz
```

Migrations run in the entrypoint under an advisory lock (D-6). No manual step.

## Smoke test — all six, in order

1. Sign in on the web admin.
2. Request an OTP on a test number; verify it.
3. `GET /api/v1/auth/me` returns the expected roles.
4. `/healthz` reports `database.ok` and `disk.ok`.
5. `/healthz` reports `recovery_ready: true` — a deploy that silently stopped the archiver
   leaves the business with a 24-hour recovery point and nothing else complains.
6. An audit row exists for the login.

## After

- Watch Sentry for 30 minutes.
- Rollback decision point: if unhealthy, `git checkout <previous-tag>` and redeploy.
  **Decide, do not improvise** — that is what the previous tag is for.
