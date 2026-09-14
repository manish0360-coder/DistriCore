# Runbook — Deploy

Manual by decision until automation has earned it (FD-19). The operator is present at
the moment things go wrong, which is when judgement is worth more than automation.

## First deploy only — once per host

Everything below this heading is done once. A repeat deploy starts at *Before*.

**Steps 1–2 prepare the host. Steps 3–7 need the stack running**, so run the *Deploy* section below once before them — `up -d --build --wait` is idempotent and you will run it again for the release itself. Step 3 already assumed this: `ops/backup.sh` takes a `pg_dump` through a running `db`.

**Operator-provisioned, and not in this repository** — `00` §2.5 and §2.6 schedule each at
M11: **A-03** VPS · **A-04** domain, DNS A record pointed at the host · **A-05** offsite
target reachable by `rclone` · **S-04** deploy key · **S-05** SSH key · **S-07** backup
passphrase · **A-08** uptime monitor. **K-1/S-06**, the Android keystore, is separate and
irreversible — `00` §2.3.

**1. Provision A-05 and configure `rclone`.** First, because step 2 cannot be filled in
without the bucket name and steps 3–4 cannot succeed without the remote. Nothing in this
repository creates any of it.

**The bucket** — Backblaze B2:

| Setting | Value | Why |
| --- | --- | --- |
| Region | **EU Central (Amsterdam), `eu-central-003`** | B2 has no Indian region. See the residency note below |
| Name | your choice, lowercase, globally unique | B2 bucket names are unique across all customers, so no convention can be fixed here |
| Files | **Private** | |
| Default encryption | **OFF** | Everything arrives as GPG AES256 ciphertext (B-2). Server-side encryption would encrypt ciphertext with a key the provider holds — cost without benefit |
| Object Lock | **OFF** | It would make `rclone delete --min-age` fail on locked objects, and `ops/basebackup.sh` owns retention. Immutability and client-side retention are mutually exclusive |

**The application key** — one, scoped to that bucket, **no expiry**. In the B2 console this is
the *Read and Write* access type restricted to a single bucket, which grants exactly the five
capabilities the scripts use:

| Capability | Used by |
| --- | --- |
| `listBuckets` *(this bucket only)* | rclone resolving the bucket at authorise time |
| `listFiles` | `rclone lsf` — including the twice-per-cycle verification in `ops/ship-wal.sh` |
| `readFiles` | `rclone cat` — the whole of `ops/restore-pitr.sh` |
| `writeFiles` | `rclone rcat` / `copy` |
| `deleteFiles` | `rclone delete --min-age` and `deletefile` in `ops/basebackup.sh` |

**Do not grant** `writeBuckets` · `deleteBuckets` · `bypassGovernance` · `writeKeys` ·
`deleteKeys` · **"Allow List All Bucket Names"** · bucket encryption or retention
capabilities. None is used. `writeBuckets` in particular is the one that turns a wrong path
into a silently-created second bucket instead of a loud refusal, and *"Allow List All Bucket
Names"* is the widely-repeated false fix for a `401` that is really a missing bucket segment
in `DISTRICORE_BACKUP_REMOTE`.

**An expiring key would silently end archival.** It fails closed — `/healthz` would report
`recovery_ready: false` — but it is a self-inflicted outage with a calendar fuse.

**The rclone remote** must be readable by **root**: none of the three units sets `User=`, so
`districore-backup`, `districore-wal-ship` and `districore-basebackup` all run `ops/*.sh` as
root, and rclone reads root's configuration.

```bash
sudo install -d -m 700 /root/.config/rclone
sudo rclone config create districore b2 \
    account <keyID> key <applicationKey> hard_delete true
sudo chmod 600 /root/.config/rclone/rclone.conf
```

`hard_delete true` is **not optional**. B2 versions objects: rclone's default hides a file
instead of deleting it, the original version remains, and it is still billed. Retention would
appear to work and the archive would grow for ever.

Store the keyID, the application key and the bucket name in the password manager beside
S-07 — **the archive is unreadable and unreachable without both**. `00` §2.5's register has
no S-number for this credential; that is an open Architect item, not a reason to leave it
undocumented here.

Prove it as root, the way the timers will:

```bash
sudo rclone lsd districore:                      # expect exactly your bucket
sudo rclone lsf districore:<bucket>/             # expect empty
```

> **Residency.** B2 EU is correct where the business is a sole proprietorship or partnership
> firm. If it is a company under the Companies Act 2013, Rule 3(5) of the Companies
> (Accounts) Rules requires a **daily backup on servers physically located in India** — which
> is satisfied by *adding* an India-resident destination for the nightly dump, not by changing
> provider. Confirm the entity type before go-live; it is an owner question, not an
> engineering one.

**2. `.env` on the server**, `0600`, owned by the deploy user (FD-13). Copy `.env.example`
and fill it. Two entries carry A-05 from step 1, and all three backup scripts refuse to run
without them:

```
DISTRICORE_BACKUP_REMOTE=districore:<bucket>/districore
DISTRICORE_BACKUP_PASSPHRASE=<S-07>
```

**The bucket segment is mandatory.** `districore:districore` — remote plus prefix, bucket
omitted — makes rclone read `districore` as a bucket name, fail to find it, and try to create
it; the scoped key refuses and the error reads `failed to create bucket: 401 unauthorized`.
That message is accurate and describes a problem you do not have.

Three further entries must name the same domain, and the stack refuses to start otherwise:

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

**3. Install the nightly backup** (`00` §14 FD-16, B-5). The script has always existed;
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

**4. Install the continuous layer** — this is what NFR-AVA-001's 15-minute RPO rests on
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

**5. Point the uptime monitor (A-08) at `https://<domain>/healthz`.** That endpoint reports
database, disk, backup age and `recovery_ready`; the monitor polling it is what turns three
of `00` §13.1's four alerts into email. Without it nothing watches, whatever the endpoint
says.

**6. Bootstrap the first owner.** A fresh database has **no users at all**, so nothing can
sign in — and `bootstrap_owner` exists because `grant_role` requires an OWNER to act, which
is a deadlock on a new installation (FR-IAM-014). Full background:
[first-owner](first-owner.md).

```bash
cd /opt/districore
make owner PHONE=<10-digit number> NAME="<owner's name>"
```

**You will be prompted for a password. Give one.** It is required when the user is being
created, which is always the case here. **Leaving it blank creates an owner who holds the
role, is audited, and can never sign in** — `UserManager._create` calls
`set_unusable_password()` when no password is supplied, and the only symptom is *"Incorrect
phone number or password"* at the login screen. That branch is correct for retailers, who
authenticate by OTP (`04` T-01); it is not what you want for the owner.

`make owner` uses the **base** compose file — neither overlay — so it is the same command on
this host and on a workstation. Any spelling of the number works: `7903324153`,
`917903324153` and `+917903324153` normalise to one canonical form before the lookup.

Then **sign in at `https://<domain>/`** and confirm you reach the dashboard. A login is not
an authorisation: if you see *"This account cannot sign in here"*, the password was accepted
and the OWNER role is missing — re-read the output of the command above.

If the account already exists without a usable password, Django's own command sets one:

```bash
docker compose -f docker/compose.yml --env-file .env \
  exec app python manage.py changepassword +91<10-digit number>
```

Use the canonical `+91…` form there — `changepassword` is Django's and looks the user up
verbatim, unlike the login path, which normalises first.

**7. Rehearse both recoveries** — `docs/runbooks/restore-from-backup.md`. B-1: a backup that
has never been restored does not count as one, and the first real one on a new host is the
one worth proving. **Two rehearsals, not one:** the logical restore (B-3) and the **PITR
rehearsal**, which is the only thing that can discharge NFR-AVA-001. Its log is empty until
you run it here.

**The PITR rehearsal depends on step 6.** It recovers to an instant and reports
`max(audit_log.occurred_at)` — the newest business fact that survived. Without an owner who
can sign in, there is no audit row to recover and the rehearsal measures nothing.

---

## Before

1. `main` is green in CI.
2. `CHANGELOG.md` updated.
3. Version bumped; annotated tag pushed.
4. **Manual backup taken and verified** (B-6, MIG-7) — **through the unit, not the script**:

   ```bash
   sudo systemctl start districore-backup.service
   sudo journalctl -u districore-backup.service -n 20 --no-pager
   ```

   **Not `./ops/backup.sh`.** The timers run it as **root**, and rclone reads root's
   configuration at `/root/.config/rclone/rclone.conf` (step 1). Running the script as the
   deploy user reads *that user's* rclone config, which on this host does not exist — so a
   pre-release backup would fail, or worse, a second config would be created and the manual
   path would quietly diverge from the scheduled one. One execution path, one credential.

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
