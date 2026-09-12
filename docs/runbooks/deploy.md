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
`backup.ok: false` for ever:

```bash
sudo cp /opt/districore/ops/districore-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now districore-backup.timer
systemctl list-timers districore-backup.timer     # confirm the next run
sudo systemctl start districore-backup.service    # prove it works now, do not wait
```

Then confirm `/healthz` reports `backup.ok: true`.

**3. Point the uptime monitor (A-08) at `https://<domain>/healthz`.** That endpoint already
reports database, disk and backup age; the monitor polling it is what turns three of
`00` §13.1's four alerts into email. Without it nothing watches, whatever the endpoint says.

**4. Rehearse the restore** — `docs/runbooks/restore-from-backup.md`. B-1: a backup that has
never been restored does not count as one, and the first real one on a new host is the one
worth proving.

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

## Smoke test — all five, in order

1. Sign in on the web admin.
2. Request an OTP on a test number; verify it.
3. `GET /api/v1/auth/me` returns the expected roles.
4. `/healthz` reports `database.ok` and `disk.ok`.
5. An audit row exists for the login.

## After

- Watch Sentry for 30 minutes.
- Rollback decision point: if unhealthy, `git checkout <previous-tag>` and redeploy.
  **Decide, do not improvise** — that is what the previous tag is for.
