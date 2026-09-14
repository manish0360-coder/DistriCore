# Next Task

## Done 2026-09-14 — M11.5, the deploy path that could not be followed

**The audit before this milestone asked one question: is A-03 really next?** It was not.
Following `docs/runbooks/deploy.md` on a fresh host produced a system **nobody could sign in
to**, and then could not measure NFR-AVA-001 — every defect discoverable only on a paid
machine, mid-deploy.

**This is the M11.1/M11.3 shape a third time:** a mechanism that is correct and that the
documented procedure cannot invoke. M11.1 found a backup script nothing scheduled. M11.3
found an A-05 nothing provisioned. M11.5 found an owner nobody creates.

| # | Defect | Fix |
| --- | --- | --- |
| 1 | **`deploy.md` never bootstrapped an owner.** A fresh database has no users, so smoke-test steps 1–3 and 6 were impossible — and `ops/restore-pitr.sh` reports `max(audit_log.occurred_at)` as its evidence, so with no login there is **no audit row to recover and NFR-AVA-001 cannot be measured at all** | New **step 6**, before the rehearsals, with the `changepassword` recovery path and a pointer to `first-owner.md` |
| 2 | **A blank password silently creates a locked-out owner.** The prompt read *"leave blank if the user exists"* — sound for recovery, misleading on first boot, which is the path every new installation takes. `UserManager._create` then calls `set_unusable_password()`; the account holds OWNER, is audited, and can never sign in. The only symptom is *"Incorrect phone number or password"* | **Wording only.** The prompt now says a password is REQUIRED for a new user. No manager, service, hashing, model, permission or command-semantics change |
| 3 | **`owner`, `superuser`, `logs` loaded the dev overlay** — the first commands an operator runs on the production host | `$(DCBASE)`, base compose only |
| 4 | **`make pitr-rehearsal` and `make restore-rehearsal` sourced nothing.** The scripts require `DISTRICORE_BACKUP_PASSPHRASE` and `DISTRICORE_BACKUP_REMOTE` via `:?`; the systemd units get them from `EnvironmentFile=`, a manual invocation had no equivalent — so `restore-from-backup.md`'s documented command **exited immediately** on a production host | `set -a; . ./.env; set +a`, plus `.env` as a prerequisite |
| 5 | **`first-owner.md` was not in the runbook index** — which is why the locked-out-owner case was diagnosed from source rather than from the document written for it | Listed |

### The instruction that repository evidence overrode

M11.5 was specified as *"make `owner`/`superuser`/`logs` use the production compose
configuration"*. **`$(DCPROD)` would have been wrong twice over**, and the repository had
already ruled on it — `ops/backup.sh` records the M11.2 finding verbatim: *"the prod overlay
is not loaded, deliberately … loading it made this script depend on every variable the
overlay interpolates, including `DISTRICORE_DOMAIN`"*, the B-3 defect, with
`test_deployment_readiness` enforcing it.

Beyond that, `compose.prod.yml` declares `DISTRICORE_DOMAIN: ${DISTRICORE_DOMAIN:?…}` and
`:?` fires on **empty**, which `.env.example` ships — so `$(DCPROD)` would have broken
`make owner` on every development machine. **`$(DCBASE)` loads neither overlay**, which is
what `exec` actually needs: it attaches to a running container under the fixed project name
`districore`. Raised before implementing; confirmed by the Product Architect.

**`.env` needed no absolute path either.** The units set `WorkingDirectory=/opt/districore`,
so `/opt/districore/.env` **is** the repository-root `.env`. One relative path, correct on
the server and on a workstation.

### 9 contracts, 18 mutations proved

Two found defects in this work: a mutation that moved the owner command after the rehearsals
**passed**, because the ordering check matched the step's own explanatory prose rather than
the command — now keyed on `make owner PHONE=`. And three mutations initially failed to fire
because `replace(…, 1)` hit an earlier occurrence; re-run precisely, all three proved.

Fail-closed is unchanged and contract-protected: sourcing `.env` **supplies** the
environment, it does not excuse it — `ops/restore-pitr.sh` and `ops/restore.sh` still refuse
by name via `:?`.

**Unchanged:** identity behaviour, authentication, hashing, models, permissions, business
logic, views, URLs, serializers, the frontend and visual system, backup design, retention,
and NFR-AVA-001 — still **binding at RPO ≤ 15 min / RTO ≤ 4 h, and still NOT MEASURED.**
Nothing here measures anything; it makes the measurement reachable.

---

## Done 2026-09-14 — M11.4, the visual system: "instrument, not ornament"

**There was no design system to redesign.** The audit found 71 lines of CSS in four
`<style>` blocks, **zero static files, zero JavaScript, zero media queries and zero focus
rules** — and `order_detail.html` shipping `.note` and `.tot` with no rule behind them
anywhere, the fragmentation already failing in production. The documented front end
(Tailwind, HTMX) had never existed.

### The direction, and what was rejected

**Two planes, one edge.** A dark **command surface** — persistent, quiet, navigation and
identity, the machine — and a light high-contrast **work surface** one elevation step above
it, carrying tables, figures and forms. Depth is planes, rules and spacing. No 3D, no
parallax, no glass, no gradient.

**Colour means state.** Three semantic colours — settled, pending, breach — and nothing
else. The four navigation accents are the single exception: they mark *where you are*, live
only on the command surface, and never touch data. This is why per-page themes were
rejected: if every screen owns a hue, the hue that means *overdue* is one of many, and the
receivables screen stops being readable at a glance.

**Rejected outright:** WebGL/Canvas/3D · per-page visual identities · HTMX · Tailwind · any
framework · any external origin. The "futuristic" quality comes from precision, hierarchy
and motion discipline; a distributor's *wow* is his ageing report opening instantly with the
rupees aligned, on his phone, in the godown.

### What changed

| Area | Before | After |
| --- | --- | --- |
| Stylesheets | 4 private `<style>` blocks | **1** — `webadmin/static/webadmin/districore.css`, via `{% static %}` |
| Navigation | **18 flat peer links** | 4 groups — Sell · Buy · Hold · Configure — with a 2px accent, collapsing on narrow screens through `<details>`/`<summary>` |
| Width | `max-width: 960px` for everything | `min(96vw, 1440px)`; dense tables scroll inside the card |
| Focus rules | **0** | One ring on every control (WCAG 2.4.7) |
| Media queries | **0** | 2 breakpoints + print; first column pinned on narrow screens |
| `prefers-reduced-motion` | **0** | All motion switched off |
| Numerals | proportional | `tabular-nums` on every figure |
| Contrast | never measured | **18 pairs measured, all AA, worst 5.73** |

### The landmine, found before it went off

`config/settings/test.py` sets `DEBUG = False`, and `STATICFILES_STORAGE` is whitenoise's
**manifest** storage, whose `url()` is skipped only when `DEBUG` is true. Dev is fine
(`DEBUG=True`); production is fine (the entrypoint runs `collectstatic`). **Tests are
neither** — and 57 of them render a web-admin page. The first `{% static %}` call would have
killed all of them with `Missing staticfiles manifest entry`, and it would have looked like a
template bug. Fixed by testing against non-manifest storage rather than by dropping
`{% static %}` and forfeiting production cache-busting.

### 17 contracts, 30 mutations proved — three of which found defects in this work

- A plain substring search accepted `parallax` from the stylesheet's own comment saying it
  has none. **Third occurrence of this class** after `backup.sh` (M11.2) and
  `test_release_signing` (K-1).
- The `<details>` assertion was satisfied by `base.html`'s *comment* describing the menu
  after the real markup had been replaced with a `<div>`.
- The token check searched for `--s1`, which `var(--s1)` satisfies in 40 rules — it was
  asserting the token is *used*, not that it *exists*.

**And I amended one of my own acceptance criteria rather than weakening the work.** The
≤12 KB budget was measured with `stat().st_size`, which counts comments and the Windows
mount's CRLF pairs; it read 16 KB for a design that is **10,405 bytes of rules and 4,453
bytes gzipped**. The criterion now measures the rules it was always about, plus a second and
stricter check on the bytes actually sent.

### Documentation corrected (item 16)

`00` FD-05 rewritten from *"Tailwind via the standalone CLI"* to what exists; T-03 and the
HTMX dependency row retired as never-installed; `03` §171 and §391 corrected. **The
amendment removes Tailwind from the document rather than adding it to the repository**,
because FD-05's reason was always "no second build pipeline" and the implementation honours
that reason more completely than the stated mechanism would have.

**Left for the Architect:** ADR-003 is still titled *"Django templates + HTMX"* in `00` §P.7
and `03` §569. Renaming a ratified ADR is not an engineering call. The decision it records —
server-rendered, not an SPA — is correct and unchanged.

**Unchanged:** every view, URL, model, serializer, permission, business rule and the invoice
PDF stylesheet, which stays independent because WeasyPrint renders a statutory document
without the screen system. The dashboard's four figures and their meaning are untouched —
`dashboard.html` argues its own case against charts and is right.

---

## Done 2026-09-13 — M11.3, A-05 production provisioning: the deploy path that could not be followed

**A-05 is locked: Backblaze B2, EU Central (Amsterdam), `eu-central-003`.** The disposable
smoke test is **CLOSED/PASS** — authentication, bucket-scoped access, 16 MiB streaming upload,
byte-exact round trip, `delete --min-age`, `deletefile`, and 1,200-object pagination. The
24-hour billing observation is deferred to production week 1, where the traffic is real; a
disposable bucket holding 1,200 static objects for a few hours cannot produce the sustained
576-listings-per-day pattern that is the actual cost driver.

**Documentation only, plus one widened contract. No mechanism changed.**

### The gap: following `deploy.md` end to end produced a broken deploy

| # | Defect | Fix |
| --- | --- | --- |
| 1 | **No step provisioned A-05 or configured `rclone`.** Steps 1–3 all assumed a working `districore:` remote that nothing ever created. A-05 was named once, in the provisioned-elsewhere list, and never returned to | New **First deploy step 1**, everything renumbered. Bucket, key, the five capabilities, the prohibited ones, `hard_delete`, and the remote path form |
| 2 | `.env.example` shipped `DISTRICORE_BACKUP_REMOTE=` **with no format** | The format, with the bucket segment marked mandatory and the failure it causes spelled out |
| 3 | **The units set no `User=`, so all three run as root** — but nothing said so, and `rclone` reads root's config | `/root/.config/rclone/rclone.conf`, 0600, stated in `deploy.md` and `restore-from-backup.md` |
| 4 | *Before* step 4 told the operator to run `./ops/backup.sh` **by hand**, as the deploy user, while the timers run it as root | Standardised on `sudo systemctl start districore-backup.service`. One execution path, one credential |

**Defect 2 is the one the smoke test found the hard way.** Setting
`districore:districore` — remote plus prefix, bucket omitted — makes rclone read the prefix
as a bucket name and attempt `b2_create_bucket`; a correctly scoped key refuses and the error
reads `failed to create bucket: 401 unauthorized`. The message is accurate and describes a
problem you do not have. The code was always right; the documentation gave no way to get it
right.

### The contract was scanning one level too narrowly

`test_every_variable_the_application_reads_is_documented` derived its list from
`backend/config/settings/*.py` only — and passed while `DISTRICORE_PITR_IMAGE` and
`DISTRICORE_PITR_WAIT_SECONDS`, read by `ops/restore-pitr.sh`, were undocumented. **That is
the same defect the contract exists to prevent, one level out.** `00` §9.1 says *the
application*; an operator restoring at 03:00 does not care which process reads a variable,
only that the file they were told to copy names it. It now scans `ops/*.sh` too — 12 more
variables, matching `${VAR:` and `${VAR}` but deliberately **not** the assignment form, since
`REMOTE_WAL=` is a local rather than an input.

Both halves landed in the same commit: the widened contract fails until the two variables are
documented. Same ordering lesson as M11.1's missing bind-mount.

### Deliberately not done

- **No format guard in the ops scripts.** Tempting after the 401, but they already fail
  closed — the upload fails, no stamp, `/healthz` reports `recovery_ready: false`. A guard
  would improve the error message, not the outcome, and would duplicate a check across four
  scripts that share no library.
- **No rclone version pin (T-06).** A real gap — rclone is an unpinned dependency of the
  entire recovery path, against TD-21's own reasoning — but `00` is authoritative and this
  blocks nothing. **TD-51.**
- **No S-09.** `00` §2.5 registers S-01…S-08 and has **no entry for the B2 application key**,
  which alone can delete every backup. Adding one means editing an authoritative document, so
  it stays an Architect decision. Until then the credential is named in `deploy.md` step 1 and
  stored beside S-07, which is where an operator will look.
- No B2 retest, no retention redesign, no Object Lock, no change to NFR-AVA-001.

### Residency, recorded

B2 EU is correct for a sole proprietorship or partnership firm. **If the business is a
company under the Companies Act 2013**, Rule 3(5) of the Companies (Accounts) Rules requires a
**daily backup on servers physically located in India** — satisfied by *adding* an
India-resident destination for the nightly dump, never by changing provider. It is an owner
question, it is noted in `deploy.md` step 1, and it does not block provisioning.

**NFR-AVA-001 remains NOT MEASURED.** Nothing here measures anything. It becomes measurable
only after a real A-03 host, a real A-05 bucket, both timers enabled, `recovery_ready: true`,
and one recorded PITR rehearsal.

---

## Done 2026-09-12 — M11.2, NFR-AVA-001: the continuous layer that was never built

**Architect decision, 2026-09-12: keep RPO ≤ 15 min / RTO ≤ 4 h. Single VPS, WAL/PITR,
continuous encrypted offsite archival. No standby.** So `03` §4.4's unsigned deviation to
≈1 hour is moot and no requirement wording changed — `02` §21.6, `01` DR-5 and `01` NFR-7 are
untouched.

**The gap was not "≈1 hour instead of 15 minutes". It was ≈24 hours.** FD-16 decided a
continuous layer — *"WAL archiving · continuous · separate local volume"* — and derived its
≈1-hour figure from it, but no WAL configuration existed anywhere: `wal_level`,
`archive_mode`, `archive_command`, `pg_basebackup`, `restore_command` and every archiving
tool returned zero hits repository-wide. The nightly dump was the only layer. **Neither
NFR-AVA-001 nor NFR-AVA-002 appeared in `backend/` or in any verification report**, which is
how it survived ten milestones.

### The mechanism, and why each piece is where it is

| Piece | Where | Why not elsewhere |
| --- | --- | --- |
| `archive_mode=on`, `archive_timeout=300`, `archive_command` | `docker/compose.yml` server flags | One fact in the file that starts the database. Consequence: a base backup copies `postgresql.conf`, so a *recovered* cluster inherits none of them — which is why the rehearsal cluster does not try to archive |
| Local `cp` to the separate `wal_archive` volume | `archive_command` | It runs inside the PostgreSQL server's shell, which has no `gpg` and no `rclone`. A network upload there would let an unreachable A-05 stall WAL recycling until `pg_wal` fills and **writes stop**. So it does the one thing that cannot block |
| Encrypt, ship, then **read the remote back** | `ops/ship-wal.sh`, 5-minutely | The host-side split `ops/backup.sh` already used (B-2). The verification is the point: `rclone` exiting zero is not the claim, retrievability from A-05 is |
| Weekly physical base backup, which also owns **WAL retention** | `ops/basebackup.sh` | WAL cannot be replayed into a logical dump. And a segment stops being needed only when no retained base backup needs it, so the schedule that knows where the oldest chain starts is the only one allowed to prune. Two schedules pruning by their own clocks is how a recovery finds the archive begins *after* the base |

**No pgBackRest, no WAL-G.** FD-16 alternative (c) calls them *"the recommended Edition 2
upgrade"*; `03` §4.2 rules out a paid tier under A-19. `archive_command` plus `rclone` needs
nothing that was not already installed for the nightly dump.

### The 15 minutes is arithmetic, and a contract guards it

```
  300 s  segment closes      archive_timeout   (docker/compose.yml)
+ 300 s  next shipping run   OnUnitActiveSec   (districore-wal-ship.timer)
+  60 s  upload allowance
  660 s  =  11 minutes  against NFR-AVA-001's 900
```

Raising `archive_timeout` to an hour to reduce write amplification is a one-line change that
converts a met requirement into an unmet one, and nothing would have noticed.
`test_the_rpo_budget_still_adds_up_to_less_than_the_requirement` recomputes the sum from all
three files.

### C-5, and two more defects of the same shape

| # | Reported success while | Fix |
| --- | --- | --- |
| C-5a | The passphrase was missing — a stderr warning, then the stamp written anyway, so `/healthz` was green for a dump lying in clear (B-2) | `:?` on both variables in all three scripts. A warning is not a control |
| C-5b | The remote was unset — offsite silently skipped, stamp written anyway, so `/healthz` was green for a backup on the machine being backed up (B-7, the rule it is a rule about) | Same, plus every script now lists the remote back and checks the name it uploaded **before** stamping |
| **C-5c** | **The stamp, the dump and the media sync all used *host* paths**, while `backup_data` and `media_data` are Docker volumes mounted into `app`. `/healthz` runs in that container, so it could **never** see a stamp — `backup.ok` was false on a correctly backed-up host — and `rclone sync /srv/media` named a directory that does not exist on the host, which under `set -e` **failed the whole run every night** on any host with a remote configured | Stamps written through `exec -T app`, into the volume the endpoint reads. Media read out of `media_data` and **encrypted** — the old sync also shipped proof-of-delivery photographs to A-05 in clear |

C-5c is the one that mattered most: every other guarantee in this milestone is unobservable
without it. A monitor that cannot go green on a healthy system is a monitor that gets muted.

### `/healthz`: four checks where there was one, plus one boolean

`backup` (the nightly dump) · `wal_archive` (**`pg_stat_archiver`** — is PostgreSQL still
archiving, and is `last_failed_time` newer than `last_archived_time`, which means `pg_wal` is
filling) · `wal_offsite` (**the RPO observable** — lag in seconds, reported next to
`rpo_target_seconds`) · `basebackup` (something to replay into) · and `recovery_ready`, the
one field A-08 watches. `00` §13.1 permits four alerts and no more, so **no fifth channel was
added**: these ride the endpoint the monitor already polls.

Separate because each link fails alone and looks fine from the others. A shipper stamp cannot
detect a stalled archiver — *"everything local is offsite"* is true of an archive that
stopped growing an hour ago.

### Evidence, not configuration

`make pitr-rehearsal TARGET_TIME='…'` recovers a scratch cluster from the **offsite** base
backup and WAL, waits for **`pg_is_in_recovery()` to go false** — not `pg_isready`, which
succeeds *during* replay and would understate what was recovered — and reports
`max(audit_log.occurred_at)`. That is the achieved recovery point. Row counts prove a restore
happened; RPO is about how much was kept.

**NFR-AVA-001 is recorded NOT MEASURED** (`docs/M11.2_Recovery_Report.md`). `02` §21.6
verifies it by rehearsal, a rehearsal needs A-03 and A-05, and neither exists. The PITR log
in the restore runbook is empty and a contract refuses a PASS on any line naming the
requirement.

**19 contracts, 44 mutations proved.** Two found defects in my own work: a plain substring
search accepted `rclone lsf_DISABLED` as verification, and the shipper's staleness check used
whatever sorted last in the archive — which can be a `.history` file written once at
promotion, so a stalled archiver would have looked healthy.

**One pre-existing gap fixed to make a general contract possible:**
`DISTRICORE_DB_CONN_MAX_AGE` was read by settings and absent from `.env.example`, against
`00` §9.1. `test_every_variable_the_application_reads_is_documented` now derives the list
from the settings modules rather than hand-listing M11.2's eight new variables — retiring the
class instead of policing an instance.

### Recorded as technical debt, not silently accepted

- **TD-49 — nightly media backup is a full encrypted tar.** Correct for B-2 and correct now
  (the directory is near-empty at V1), but `04` §9 sizes media at ~24 GB after five years, at
  which point a nightly full upload stops being reasonable. **Threshold: revisit when
  `/srv/media` exceeds 2 GB.** Incremental *and* encrypted needs a real tool (rclone crypt,
  or restic), which is an Edition 2 decision, not an eleventh-hour one.
- **TD-50 — `archive_command` uses `cp` then `mv`, without `fsync`.** A segment under its
  final name is complete, and the local archive shares a disk with the cluster it describes,
  so if that disk is intact the file is intact. The authoritative copy is offsite, which
  `rclone` checksums. Bounded, deliberate, and worth naming.
- **`03` §194 says a 40 GB volume, §216 and §575 say 80 GB.** Not resolved here — it is a
  sizing fact for A-03 provisioning and belongs to whoever buys the host.

### Found at commit time, and it would have made this milestone inert

**Every `ops/*.sh` was mode `100644` in git** — including `ops/backup.sh`, shipped at P0.
The repository is developed on a Windows mount, so `core.filemode=false` and nobody saw it.
On a fresh Linux clone `ExecStart=/opt/districore/ops/backup.sh` fails with **`203/EXEC`**,
which means the nightly backup timer M11.1 added has never been able to run on a real host,
and neither would either of M11.2's. Scheduled and unable to execute — the M11.1 defect
family, one layer further down.

Fixed in the index (`git update-index --chmod=+x`) for all five shell scripts. **No contract
guards it, and that is a considered limit rather than an omission:** the backend image has no
git, and a bind-mounted file's permissions are the mount's rather than the index's, so
nothing inside `make verify` can observe the committed mode. `docs/runbooks/deploy.md` step 2
now has the operator check it, which is the only place the fact is observable.

**Not touched:** streaming replication / EP-K (explicitly out of scope), K-1 and mobile
signing, `ops/perf-latest.json`, DR-8, LICENSE.

---

## Done 2026-09-12 — K-1, the keystore **procedure** (and the two gaps it exposed)

**Scope: the procedure only. No keystore was generated and no secret was handled.**
`M8_Design_Review` entry condition 4 — *"K-1 keystore procedure agreed"* — has been open
since M8 for a simple reason: `rotate-secrets.md` said outright that *"there is no
procedure."* AR-5 classifies losing the key as *"not an M8 code risk — an M8 **procedure**
risk"*, so what was owed was a document, and now exists:
**`docs/runbooks/android-keystore.md`** — generation command with every parameter fixed
(`-storetype PKCS12 -alias upload -keyalg RSA -keysize 2048 -validity 10000`), a temporary
location outside the repository tree, the password-manager entry, two off-machine backups
**each verified by fingerprint**, the repository-side negative checks, and a log of
non-secret facts only.

**Writing it down exposed one real gap and one misplaced rule**, both reached only by the act
of *complying* with K-1:

| # | Finding | Why it was silent |
| --- | --- | --- |
| 1 | **Nothing ignored `*.p12`** | PKCS12 is `keytool`'s default store format since JDK 9, so the file the procedure produces matched no rule — not `*.jks`/`*.keystore` in the root `.gitignore`, and not `**/*.jks`/`**/*.keystore` in Flutter's generated `mobile/android/.gitignore` either. A pattern set covering every format except the generated one reads as protection and is not. `.pepk` was missing for the same reason |
| 2 | **`key.properties` was ignored only by generated scaffolding** | The release block has no `signingConfig`; the recipe that supplies one reads `mobile/android/key.properties` — store password, key password, alias and path, **in clear**. Flutter's `mobile/android/.gitignore` *does* list it, **so this was not an open hole** — but that file is rewritten by `make mobile-android-scaffold` from the pinned SDK and guards one directory. N-11 is repository-wide and should not be inherited from a code generator, so the rule was hoisted to the root |

**Finding 1 was checked, not assumed.** `git check-ignore -v` against all five names is what
showed the nested Android file already covering `key.properties` — which corrected a stronger
claim this entry was first drafted with. Only `.p12`/`.pepk` were genuinely uncovered.

**Nine contracts in `backend/tests/adversarial/test_release_signing.py`, all fifteen
mutations proved.** They assert on **`.gitignore`**, never `git ls-files` — *"the backend
image contains no git"* (`M10_Security_Review` §NFR-SEC-007), the lesson
`test_an_env_file_cannot_be_committed` already records: the right question in the wrong place
fails in the authoritative environment and passes everywhere it does not matter. Two hold
the signing path itself — no debug key on a release build (the line `flutter create`
generates), and **no credential literal in `build.gradle.kts`, now or after the config is
added**, which is the shortest path to a working release build and a secret in source
control that no entropy scanner would reliably flag.

**Android signing implementation deliberately unchanged.** A `signingConfig` written now
would point at a keystore that does not exist and turn a correct refusal into a confusing
failure. §8 of the runbook records the one bounded change it becomes, for the first real
release build.

**K-1 is NOT complete.** The keystore does not exist, the log is empty, and nothing here
brings the M11 → live gate closer on its own.

---

## Done 2026-09-12 — M11.1, deployment readiness (repository side)

**Three gaps, each of which would have appeared for the first time in production.**

| # | Gap | Why it was silent |
| --- | --- | --- |
| 1 | `compose.prod.yml` never passed **`DISTRICORE_DOMAIN`** to Caddy | The Caddyfile is parameterised `{$DISTRICORE_DOMAIN:localhost}` and `compose.dev.yml` sets it, noting *"production supplies the real domain"*. It did not. Unset, Caddy chose its **internal** issuer and served a certificate no browser trusts — for a domain (A-04) already bought and pointed at the host. Nothing failed |
| 2 | **Nothing ran the nightly backup** | FD-16 requires nightly; `00` §13.1 alerts at 26 hours; `/healthz` reads the stamp. `ops/backup.sh` is invoked by hand in three runbooks and by `make backup` — and by no scheduler. A fresh host would have had **no backups**, `backup.ok: false` for ever, and B-1 could not begin |
| 3 | `ops/backup.sh` loaded the **production overlay it does not need** | `db` is in the base file and `exec` attaches to a running container. Loading the overlay coupled the backup to every variable it interpolates — so the moment `DISTRICORE_DOMAIN` became required, a missing certificate name would have stopped the nightly dump. The B-3 defect again: a compose file loaded for no reason, taking the script down with it |

**Fixes.** `DISTRICORE_DOMAIN: ${DISTRICORE_DOMAIN:?…}` on the production Caddy — fail closed,
the same posture `POSTGRES_PASSWORD` takes, because the value cannot be guessed and a wrong
guess is worse than a refusal. `DISTRICORE_DOMAIN` documented in `.env.example` with the note
that it must agree with `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` — three places, one name.
`ops/districore-backup.{service,timer}` — nightly at 02:30, `Persistent=true` so a host that
was off still backs up. **No new alerting was invented**: `/healthz` already reports
`backup.age_hours`, and A-08 polling it is what raises `00` §13.1's email. The producer was
the only thing missing.

`docs/runbooks/deploy.md` gained a **first deploy only** section — the runbook was written
for a repeat deploy and had no path for host number one.

**Eight contracts, all mutation-proved.** One failed on its own explanation first —
`backup.sh` now *documents* why it no longer loads the overlay, and a plain substring search
read that prose as the thing it forbids. Comments are stripped before the search, with
`test_the_comment_stripper_actually_strips` keeping that honest; the same lesson
`test_mobile_boundary` records.

**`.env.example` is now bind-mounted** into the app container. The contract that reads it
would otherwise have failed on a missing mount rather than on its subject — the M10 defect,
avoided by adding the mount in the same change as the test.

**Everything else in M11.1 is operator work and none of it exists:** A-03 host, A-04 domain
and DNS, A-05 offsite target, S-04 deploy key, S-05 SSH key, S-07 backup passphrase, A-08
uptime monitor, and **K-1/S-06** — the Android keystore, which `00` §2.3 says can never be
rotated.

**Deliberately not touched.** `STATICFILES_STORAGE` remains inert (recorded, deferred:
*"its own change, its own verify run"*), and it is not a deploy blocker because Caddy serves
`/static/*` from the collected volume. **NFR-AVA-001 is untouched** — see below.

---

## Done 2026-09-12 — M11.0, ACT-E: the opening-balance load and reconciliation

**`02` §ACT-E is the first clause of the `00` §19.2 M11 → live gate**, and its two services —
`receivables.services.load_opening_balance` and
`purchasing.services.load_supplier_opening_balance` — had **no caller outside the test
suite**. The first one's docstring speaks of *"re-running the whole import"* for an import
that did not exist. `manage.py load_opening_balances` is that import.

**R-6 is why it was worth doing carefully**: *"a corrupt starting position undermines every
derived figure permanently."* Everything fails closed.

| Property | How it behaves |
| --- | --- |
| Dry run | **the default**; `--commit` is required to write |
| Refusals | fail the run in **both** modes, each named by line number |
| Mixed input | one bad row stops the whole load; `--allow-partial` overrides and is named in the report |
| Customer re-load | idempotent — the service returns the existing entry (D-10) |
| Supplier re-load | the service *refuses*, so the command detects and reports `already carried` |
| Reconciliation | **A** file · **B** `OPENING` entries · **C** derived balances, independently computed. A ≡ B is asserted on a committed run; B ≡ C is reported, never asserted |
| Writes | through the services only — `record_entry` remains the single ledger writer (D-8) |

**Rehearsed 2026-09-12** against the disposable `districore_perf`: 3 loaded, 7 refused,
**A = B = C = 105,750.49**, re-run a no-op reporting `already carried`, development database
untouched (0 `OPENING` rows), database dropped afterwards.
`docs/runbooks/go-live-data.md` carries the full evidence.

**ACT-E is ready to execute. It has not been executed** — the real load is an owner action
against real figures, and the Load log stays empty until someone watches one.

**Two defects were found and fixed before the rehearsal, both in this milestone's own work:**

1. **The operator could not log in.** `bootstrap_owner --phone 9000000000` stores
   `+919000000000`; the command looked the raw string up. `identity/phone.py` exists because
   *"a superuser created as `7903324153` could therefore never log in"* — the same defect,
   on a new surface. The twenty contracts missed it because the fixture passed
   `owner.phone`, already canonical. Fixed by normalising through the shared function, with
   a contract that passes the ten digits an operator types.
2. **The dry run failed on a clean file.** The reconciliation gate was applied to a run that
   deliberately writes nothing, so `A ≠ B` — the expected state of *"nothing loaded yet"* —
   was scored as a failed reconciliation. The same conflation of *absent* with *failed* that
   `ops/perf_verdicts.py` was written to prevent. Reconciliation now gates a **committed**
   run only; refusals still fail both modes.

**One requirement ambiguity, raised and not resolved:** a customer who is **in credit** at
go-live has no representation. `load_opening_balance` refuses `<= 0`; the supplier side
permits any non-zero. The corpus does not rule on it. The runbook tells the operator to stop
and raise it rather than flip a sign.

**Next:** the M11 → live gate's other two clauses — owner sign-off and training — both need a
deployed system. A-03 host, A-04 domain, A-05 offsite target, S-04/S-05/S-07 and K-1 do not
exist, and every one carries external lead time.

---

## Done 2026-09-07 — M10.5, dependency hardening. **NFR-SEC-009 MET**

| Gate | Result |
| --- | --- |
| `make verify` | **VERIFIED** — 1203/1203, coverage 94.51%, migrations clean, ruff clean, contracts 3/3, mypy clean, health OK |
| `make audit` | **`No known vulnerabilities found, 1 ignored`** — the documented WeasyPrint exemption, and nothing else |

M10 made the audit gate real and it immediately reported **16 findings in 4 packages**, none
fixable inside the constraints then declared. M10.5 raised three floors:

| Package | Before | After | Why this version |
| --- | --- | --- | --- |
| `django` | 5.1.15 | **5.2.17** | The **lowest** version fixing all seven; six are fixed by 5.2.15/16, PYSEC-2026-3717 needs 5.2.17. Django 6.0 also fixes them and was **not** taken — a second major step for no security gain |
| `djangorestframework` | 3.15.2 | **3.17.2** | Both findings; the lowest that fixes either |
| `weasyprint` | 66.0 | **68.1** | SSRF fix landed in 68.0 |
| `sqlparse` | 0.5.5 | **0.6.0** | Transitive via Django, which requires only `>=0.3.1` — so it needed an explicit `[tool.uv] constraint-dependencies` floor, and the first lock silently kept 0.5.5 |

**Fifteen of sixteen are remediated by upgrade.** The sixteenth —
**CVE-2026-49452 / PYSEC-2026-3412 / GHSA-jhhc-3hcp-qhm5**, one issue under three identifiers —
has **no published fix in any WeasyPrint version**, so it is exempted on a source-level
unreachability proof, with a **review date of 2026-12-07** and two tests holding it.
`M10_Security_Review` §3.3.

> **Only one of the sixteen was actually reachable here**, and reachability changed no
> decision — everything with a fix was upgraded regardless. **CVE-2026-73228**: DRF's
> `request.data` bypasses `DATA_UPLOAD_MAX_MEMORY_SIZE` for `application/json`, and every
> write endpoint this product has is a JSON API. The other fourteen touch GeoDjango, cache
> middleware, `get_signed_cookie`, `AdminRenderer` and sqlparse's opt-in formatters — none of
> which this application uses.

**M10's blanket ban on `--ignore-vuln` became a traceability requirement**, which is stronger
rather than weaker: every ignored identifier must appear in the review, any exemption must
carry a review date, and an undocumented ignore still fails the build. A ban with no escape
hatch left only two moves once a finding had no fix anywhere — a permanently red pipeline, or
deleting the gate — and both are worse than a dated record.

### The one thing the upgrade did break — and it was never a schema change

`uv lock` succeeded, the clean build and startup passed, and **stage 3 stopped**:

```
Migrations for 'identity':
  identity/migrations/0005_alter_user_roles.py
    ~ Alter field roles on user
```

**Root cause, proven at Django's source rather than inferred.** `ManyToManyField.deconstruct()`
gained two lines between the two versions:

```python
# django 5.2.17 — absent in 5.1.15
if through_fields := getattr(self.remote_field, "through_fields", None):
    kwargs["through_fields"] = through_fields
```

`User.roles` has declared `through_fields=("app_user", "role")` since M0 — it must, because
`UserRole` has **two** FKs to `User` (the holder and the granter) and Django cannot guess which
is which. But 5.1's `deconstruct()` **dropped the argument entirely**, so `0001_initial` never
recorded it and the autodetector compared two deconstructions that were both missing it. Under
5.2 the model's deconstruction includes it and the recorded state does not, so the autodetector
correctly proposes an `AlterField`.

So it is **(c), a Django-version serialization change** — not a schema change and not model
drift. The model was always right; the migration state could not express it.

**The migration emits no SQL, and that is what makes it safe on a populated database.**
`ManyToManyField.db_parameters()` returns `{"type": None}`, both sides carry an explicit
`through`, and `BaseDatabaseSchemaEditor.alter_field` reaches:

```python
# Both sides have through models; this is a no-op.
return
```

`0005_alter_user_roles.py` was **generated by `manage.py makemigrations identity`**, not written
by hand, and `makemigrations --check` is clean across every app afterwards. `User.roles`
behaviour is untouched.

### What the upgrade did not require

No Docker change (WeasyPrint 68.1 loads exactly the native libraries 66.0 did, verified by
diffing `text/ffi.py` between the two wheels) · no application code change · no model change ·
no new dependency. **One migration**, and it moves no data and emits no SQL — above.

### One pre-existing defect found and deliberately not fixed

`config/settings/base.py` sets **`STATICFILES_STORAGE`**, which Django removed from
`global_settings` **before 5.1.15** — so it is already inert on the version running in
production today, and the upgrade neither causes nor worsens it. The effect is that
WhiteNoise's `CompressedManifestStaticFilesStorage` is **not in use** and static assets are
unhashed. It needs `STORAGES["staticfiles"]`, it changes production static-file behaviour, and
it has nothing to do with any CVE. **Its own change, its own verify run.**

**Done 2026-09-07: `make restore-rehearsal` was run against a real dump and the row recorded**
(`ab7a97e`, `eb02ae9`). It was the only remaining item in the `00` §19.2 M10 → M11 gate — B-1:
*"a backup that has never been restored does not count as a backup."* **That gate is now met on
both halves.**

---

## Done 2026-09-07 — M10 Hardening, part 1 (security review + the dependency gate)

**`00` §19.1 makes M10 the current milestone**; the M9 → M10 gate passed on 2026-09-04. The
M10 → M11 gate is *"Restore rehearsed and recorded (B-3); security review complete"*, and this
pass addressed both halves. It completed neither on the day; **M10.5 closed the first and the
2026-09-07 rehearsal closed the second.** The table below is the state *now*, not the state
this pass left behind — the narrative that follows is kept as written.

| Half | State |
| --- | :-: |
| Security review complete | **YES** — 11/11 NFR-SEC evidenced; NFR-SEC-009 met at M10.5 with one dated exemption |
| Restore rehearsed and recorded (B-3) | **YES** — rehearsed 2026-09-07, PASS in 8s, recorded in `docs/runbooks/restore-from-backup.md` |

### The blocker, and it was real — CLOSED by M10.5 on 2026-09-07

> **Read the rest of this section as the record of what this pass found, in the present tense
> it was written in.** M10.5 raised three declared floors and remediated 15 of the 16; the
> sixteenth is exempted on a source-level unreachability proof with a review date. `make audit`
> now reports *"No known vulnerabilities found, 1 ignored"*. **NFR-SEC-009 is met.**

`pip-audit --strict || true` carried a `|| true` from P0 (**TD-35**). The suffix is gone, so
the gate became honest — **and it failed on its first blocking run**:

> **16 known vulnerabilities in 4 packages**: `django` 5.1.15 (7), `djangorestframework`
> 3.15.2 (2), `sqlparse` 0.5.5 (5), `weasyprint` 66.0 (2).
>
> **No fix exists inside the declared constraints.** Every fixed version is outside
> `pyproject.toml`'s ranges — `django` needs ≥5.2, `djangorestframework` ≥3.17,
> `weasyprint` ≥68, and one weasyprint advisory has **no published fix at all**.

Remediation means changing the constraints, which reaches **ADR-002** and the pinned
verification environment. Django 5.1 → 5.2 is a framework upgrade with its own migration and
its own regression surface: **a milestone, not a line in this one.** It was escalated rather
than silenced with `--ignore-vuln`, which would have produced a green pipeline and a false
review. `docs/M10_Security_Review.md` §3.

> **`00` §19.2 gates *release*, not development.** A red audit step is the requirement
> working. The decision that is owed is *when* the dependency milestone runs — not whether
> the gate should be softened.

### What the first authoritative run cost, and it is the same lesson twice

`make verify` returned **1194 collected, 1188 passed, 6 failed** — all six in the new suite,
none in the code it was asserting. Every one was a **repository-level contract written as an
application-runtime test**: two imported `prod.py` (which refuses to import without production
secrets, by design), one shelled out to git (absent from the backend image), and three read
`.github/` and `docs/` (not mounted into it).

`docker/compose.dev.yml` had already written the warning, about `test_mobile_boundary.py`:

> *"**This list and `REQUIRED_PATHS` in that test module are one fact in two places.**
> `docker/` was added here a commit after the test that reads it, and stage 7 failed on a
> `FileNotFoundError` rather than on anything about the mobile code."*

The M10 suite walked into it from the other side — tests first, mounts never. It now carries
the same precondition test, naming the same compose block. **Nothing was weakened**: no
production setting moved, `prod.py` is no less strict, no fake secrets, no tooling added to the
runtime image. `M10_Security_Review` §2.1.

### Two things the new tests found in their own first run

Both were defects in the tests, not in the code, and both are recorded because the next
person will write the same two:

1. **`.env` was flagged as "in source control".** It is not — `.gitignore` carries `.env` and
   `.env.*`, and only `.env.example` is tracked. The test read the **filesystem**; the
   requirement says *"source control"*. It then asked git, which was the right question in a
   place with no git — so it now asserts the mechanism that *prevents* the commit,
   `.gitignore`, which is itself under source control and readable anywhere.
2. **Four `f`-string SQL sites were flagged as injection.** They interpolate a module-level
   sequence *constant* imported from `models.py`, which no caller can reach. Rewriting the
   gapless numbering paths (M5-4, M6) to satisfy a rule that could not read them would have
   added risk to financial code to remove none. The rule now states the property —
   *interpolation of anything that is not a module constant* — and is mutation-proved.

**All three of that plan are now done:** (1) the rehearsal ran and the row is recorded
(2026-09-07); (2) the dependency-upgrade milestone shipped as M10.5; (3) **`00` §19.2 M10 → M11
is met on both halves.** M10 the *milestone* is not closed — but its **performance half was
closed at M10.6 on 2026-09-08** (`docs/M10.6_Performance_Report.md`), leaving its debt
register, which that gate does not touch either.

---

## Done 2026-09-06 — TD-36 / AD-02 conformance

**Chosen by a read-only V1 priority audit, and the audit changed two beliefs.**

| Believed | Found |
| --- | --- |
| Field order capture is the biggest V1 hole — `mobile/lib/features/` has no orders module and `SyncOperation.Type` carries only `DELIVERY_COMPLETE` and `VISIT_CREATE` | **`02A` DV-1, accepted and signed:** *"Salesmen no longer capture orders in the field."* `05` §11.4: *"Edition 2 adds `ORDER_CREATE`."* FR-ORD-001/007/008/009/010 and FR-REC-011 on `S2` are **deliberately Edition 2**, not a hole |
| M8 task 6 (GPS + media) is remaining V1 product functionality | **`02` §111:** *"Priority is scoped to the release in the Rel column."* FR-FUL-008, FR-FUL-011 and FR-FUL-014 are all **`Rel = v1.1`**. Not V1 |
| FR-SYN-007's stock snapshot is blocked by a genuine contradiction (D-M9.4-1) | **FR-STK-014**, v1.0, mandatory: *"`S2` and `S3` MUST display stock as an **advisory snapshot with its capture time visible**, and MUST NOT present it as a guarantee."* `04` N-03/E-01 forbids a **stored** `quantity_on_hand`; FR-STK-014 requires a **transported advisory value carrying `as_of`**. Those are compatible, and `inventory.selectors.stock_on_hand(as_of=…)` already derives it. **The gap is a reading, not an architecture conflict — for the Product Architect to rule.** Still not worth building: DV-1 removed its consumer |

**What shipped.** A semantic `ColumnKind` on `reporting.tables.Column` — `TEXT`/`COUNT`/`MONEY`/`QUANTITY`/`RATE` — with `numeric` derived from it, and `_as_json` encoding `MONEY`/`QUANTITY`/`RATE` through `core.fields`. CSV byte-identical, client untouched, `05` **AD-02.1** added for `RATE`. `M8_Design_Review` §3.4.1b.

> **The prescribed fix in the old TD-36 row was wrong**, and that is worth keeping. *"Route `_as_json`'s numeric cells through `money_string`"* would have stringified `rank`, `oldest_days`, `documents`, `orders` and the six sync counters — the opposite defect, shipped in the same change. `numeric: bool` cannot tell a count from an amount; only a kind can.

**What the first authoritative run added.** `604f545` was green on every local proof and the Docker gate returned **1155 passed, 3 failed, 1 error**. The new contract found two defects that had been in the tree for milestones — a blank `COUNT` leaving as `""` in two total rows, and the assumption that the customer statement renders through `_as_json` when its JSON path is a DRF serializer — plus a latent `CustomerFactory` collision on **C-0142** that TD-36's case count exposed rather than caused. All three fixed forward.

> **The lesson, and it is the one this project keeps relearning.** Local proofs establish that a mechanism works; only the authoritative suite establishes that it works *everywhere the mechanism is reached*. Both real defects were on paths no local proof could take.

---

## Done 2026-09-06 — M8 task 8, Owner Companion Mode (§3.4), and OI-7 ruled

**The owner has a V1 UI.** Four read-only screens, owner-gated through the existing
`TabSpec`/`RoleShell` mechanism, over endpoints that already existed — §10.1's justification
for scheduling task 8 last held exactly.

| Screen | Endpoint | Note |
| --- | --- | --- |
| **Today** | `GET /reports/dashboard` | The four D-4 numbers. `is_money` per metric decides the encoding, so a count stays an integer (`05` §9.11.1 item 3) |
| **Pending deliveries** | `GET /deliveries?status=PENDING` | `Delivery.Status` is `PENDING\|DELIVERED\|FAILED`, so *"not yet completed"* is one value |
| **Receivables** | `GET /reports/receivables` | The report's **own** total, plus the first ten rows of a **server-ordered** list |
| **Needs attention** | `GET /orders?status=CONFIRMED` + `GET /deliveries?status=FAILED` | Two sources. Either read failing fails the board — a short list and an unbuildable one look identical, and the second silently says *"nothing needs you"* |

**OI-7 ruled with it.** M-14 stays cut (`02A` §13 governs over §7.12). **"Overdue balances"
excluded from V1**: no overdue rule exists in the corpus — `Customer.credit_days` is stored,
editable through the web admin and the API, and **read by no selector, service or rule** —
and defining one is a `receivables` decision (D-3), not a label on a phone screen.

**One additive backend change**: `assigned_user_name` on `DeliverySerializer` (`05` §9.4.1),
because §3.4 asks for *"the salesman's name"* and the payload carried only an id. No
`/users` endpoint was added: shipping a user directory to a public binary (`02A` §9.3) to
resolve a label is the wrong trade.

**Six structural contracts** in `test_mobile_boundary.py` hold the §3.4 boundary from inside
`make verify`, which is the only authority (N-12) and does not run `flutter test` (TD-37):
no write call, no period parameter, no CSV, no overdue notion, owner-only tab, and no
endpoint the API does not already route. Each was proved able to fail by mutation.

> **Two of those contracts first failed on their own explanations.** The slice documents at
> length *why* it excludes an overdue rule, and a substring scan read that sentence as the
> thing it forbids. A contract that cannot tell code from prose holds *"nobody wrote the
> word"* — a property satisfied by deleting the comment. Both now strip comments first, and
> `test_the_comment_stripper_actually_strips` keeps that honest.

---

## The immediate next action

**Both of `00` §19.2's gates now pass and both are recorded. The next action is a decision,
and it is not one an engineer may take.**

> **Updated 2026-09-04.** The M8 → M9 gate passed on 2026-09-01 and 2026-09-04
> (`docs/M8_Verification_Report.md`), and the M9 → M10 gate passed on 2026-09-04
> (`docs/M9_Verification_Report.md`) — `make verify` **8/8**, 1108 passed, coverage **94.42%**,
> `test_sync_integrity.py` **11/11** across all five fault classes of `02` §25.2.
>
> **Two rows of the table below are struck out; six remain, and five of those are questions no
> engineer may answer alone.** Both gates found real defects on the way — a full disk crashed
> the outbox instead of returning `StorageFull`, and an interrupted operation told the device to
> delete work the server had never performed. Each is recorded where it was found.
>
> **What this does not do:** it closes no milestone. A passed gate is a stated condition holding,
> not a milestone's requirements being built. M8 tasks 6 and 8 have no commit; M9's five
> contradictions and gaps are untouched. Coverage is `x86_64` emulator only (**TD-45**) and the
> device gates still cannot run in CI (**TD-42**).

**Superseded, kept for the reasoning.** *This paragraph said: "It needs no ruling from anyone.
Both targets exist, both are written, and `M8_Design_Review` §10.1 says this is the one task that
**cannot** slip. What was missing was never a decision — it was a run." That was correct, and the
runs happened on 2026-09-01 and 2026-09-04.* The encryption work of 2026-08-25 settled that question in
practice: `make mobile-device-encryption` executed on the Pixel 8a API 34 emulator and closed
NFR-SEC-008, so the harness, the AVD and the by-hand invocation path are all known to work
(TD-42 records that they cannot yet run in CI).

**This changes what is next, not what is blocked.** Until 2026-08-25 this file said *"the next
action is a decision, not an implementation."* That was true when every open item needed a
Product Architect. It is no longer true of **all** of them: D-M9-4, D-M9-6, D-M9-7 and D-M9-8
have since been ruled, and the encryption defect was found by *running the thing*, not by
deciding anything. **Items 4 and 5 below proved to be in the same category and are now closed** —
each was found to hide a real defect, not merely a missing signature.

**No milestone number is proposed here, and none should be invented.**
`docs/00_Engineering_Foundation.md` §19.1 defines **M9 = Sync** and **M10 = Hardening** and
defines no sub-milestones; `M9.1`–`M9.4` are working labels for four commits, not roadmap
entries. There is no M9.5.

**The next milestone still cannot be selected.** **Five items are open and four of them remain
questions no engineer may answer alone** — two are direct contradictions between frozen
documents. They are listed in `PROJECT_STATE.md` under *Open at M9*, unresolved and deliberately
so. **Running the two gates did not shorten that list by any decision**; it discharged the two
items that were waiting on nobody, which is exactly what a gate can do and all it can do.

**What still needs a decision, before any code:**

| # | Question | Who |
| --: | --- | --- |
| 1 | **FR-SYN-005/013/014 vs `05` §11.4.** `02` requires a `SyncConflict` in `PENDING_RESOLUTION`; `05` says *"no conflict resolution console is built, because none is needed"*. `SyncConflict` exists in no schema and no contract | Product Architect |
| 2 | **FR-SYN-009.** `05` §11.5 claims coverage that **D-M9.3-1** makes unreachable — the endpoint reads `device_id` from the JWT and can only ever describe the caller's own device | Product Architect |
| ~~3~~ | ~~**FR-RPT-009 sync health report**~~ — **CLOSED 2026-09-06 (D-M9-10).** `GET /reports/sync-health`, specified in `05` §9.11.2 and built. **No model, no field, no migration** — `sync_operation` already recorded every column. FR-SYN-015's Edition-1 quantity (`REJECTED ÷ settled`) is proposed as `02` amendment **S-7** and is **not yet written** | ~~Product Architect~~ *(S-7 ratification outstanding)* |
| 4 | ~~**M8 → M9 gate** (M8 task 10)~~ — **CLOSED 2026-09-04.** `make mobile-device-kill` passed 2026-09-01, `make mobile-device-storage` passed 2026-09-04; `docs/M8_Verification_Report.md`. *M8 tasks 6 and 8 still have no commit and remain open* | ~~Engineering~~ + Product *(tasks 6 and 8)* |
| 5 | ~~**M9 → M10 gate** — no adversarial sync suite exists~~ — **CLOSED 2026-09-04.** The suite has existed since `4d4854e` (2026-08-22); this line was written against `bf94b8e` and was seven commits stale. 11/11, `docs/M9_Verification_Report.md` | ~~Engineering~~ |
| 6 | **FR-SYN-007 remainder / stock snapshot** — D-M9.4-1's recorded CONTRACT GAP | Product Architect |
| 7 | **Orphaned `RECEIVED` recovery** — deferred by `05` §11.5 *"to M9.4/M10"*; M9.4 has passed, so it landed on M10 by default | Engineering |
| ~~8~~ | ~~**TD-41 / FR-SYN-010 + FR-SYN-017**~~ — **CLOSED 2026-09-06.** B1 passed on a Pixel 8a API 34 `x86_64` emulator: **67 046 ms of a 120 000 ms budget**, 200 operations, one push batch, one pull page. FR-SYN-017 closed by the same mechanism. **TD-45 unchanged** (`arm64`/physical unproven); transport was host loopback, not a field link | ~~Engineering~~ |
| 9 | **TD-47 — does FR-SYN-010 bind while the app is backgrounded?** `02` names no application state, and Doze/App Standby mean **no** in-process mechanism can hold the bound there. A ruling decides whether this is a `WorkManager` milestone or out of scope | Product Architect |

> **Why this is a task and not a preamble.** Until 2026-08-21 this file said *"Next: task 3"*
> and `PROJECT_STATE.md` said *"M9 — Not started"*, while fourteen commits had landed past
> both. The corpus is the single source of truth; a corpus six milestones behind the tree
> cannot answer *"what is next"*, and picking a milestone anyway means picking it from memory.

---

> **M8 Phase 1 is frozen.** Design authority `docs/M8_Design_Review.md` **v1.8.0**, signed
> 2026-08-10. Both ADRs approved: **Drift** (§5.6 — the cipher clause amended by **D-M9-8** on
> 2026-08-25 to SQLite3MultipleCiphers via the `sqlite3` build hook; the ADR's conclusion,
> Drift, is unchanged) and **Dio** (§7.5). Design principles **P-1…P-10** frozen at §1.3.
>
> **M8 Phase 2 tasks 0–5, 7 and 9 are committed**, plus TD-39; **tasks 6, 8 and 10 are not.**
> **M9 has four committed increments** (M9.1–M9.4) and is **not closed**. Commit-by-commit
> history and the open items are in `PROJECT_STATE.md`.
>
> The working tree passes the full mobile verification suite — **352 tests** (346 at `1daac33`, 324 at `e2fbc07`),
> measured by `make mobile-verify` on 2026-09-04. It was **317** when this note was written
> and **305** at commit `bf94b8e`. **Encryption at rest is closed** (FR-SYN-016, NFR-SEC-008; D-M9-8) —
> `sqlite3mc` via the build hook, keyed from the Android keystore, with `chacha20` and SQLite
> `3.53.4` **observed and recorded, not required**. Proven on a **Pixel 8a API 34 emulator,
> `android-x64` only — not arm64 and not physical hardware** (TD-45). **It closes a
> requirement, not a milestone**: the M8 → M9 durability gate and the M9 → M10 adversarial sync
> gate are both still open. Backend
> `make verify` figures for the M9 increments were not captured in the state documents and
> are **not restated here from memory**.

**Milestone:** M11 — Go-live has **started** (ACT-E built and rehearsed 2026-09-12); M10 —
Hardening is not closed, though its `00` §19.2 gate and its performance half both are.
M9 is not closed. M8 remains open on tasks 6 and 10 *(task 8 built
2026-09-06)*. **Next:** see *The immediate next action* above.

---

## What task 0 found, and why it matters more than the endpoint

Deciding how to encode one number surfaced a defect in the **seven existing** report
endpoints — the exact one P-3 exists to prevent, on the server side:

| | |
| --- | --- |
| `05` AD-02 | *"Every monetary and quantity value crosses the wire as a string."* Its rationale names Dart by name |
| Settings | `COERCE_DECIMAL_TO_STRING: True` — **but it only reaches `serializers.DecimalField`** |
| `_as_json` | Hand-builds its response dict, bypassing serialisation entirely |
| Measured | `Decimal("1180.00")` → `1180.0` under DRF's own encoder |

**The existing assertion reads `Decimal(str(body["total"]["sales"]))`.** That `str()` makes it
pass whichever type arrives. Seven endpoints carried this through four reviews and a newly
blocking type gate because the test could not fail.

**Recorded as TD-36. Not fixed in task 0** — changing the seven is a breaking change to a
published response type, so it gets its own change and its own verify run. `money_string()`
was added in task 0 to be the mechanism that fix reuses.

> **CLOSED 2026-09-06, and the closure corrects the sentence above.** `money_string()` *is*
> reused — but only for `MONEY`. Applying it to every `numeric` cell, which is what this note
> proposed, would have turned `rank`, `oldest_days`, `documents`, `orders` and the six sync
> counters into strings: the same rule over-applied, which `05` §9.11.1 item 3 had already
> warned about for `awaiting_dispatch`. The fix is a semantic `ColumnKind`, so the column says
> what it *is* and each surface derives its own behaviour. `M8_Design_Review` §3.4.1b.

> **The recurring shape, in a new place:** a rule enforced on one side of a boundary and not
> the other. Canonical on read but not on write; a grant path for the second owner and none
> for the first; and now AD-02 enforced in the serializer layer and not in the hand-built
> layer beside it.

---

## The ruling that changed the design

**§3.4 "no owner mobile role" is replaced by Owner Companion Mode.** Lightweight read-only
operational visibility on the phone; all administration and reporting stay on the web.

v1.0.0's §12.5 predicted this recommendation would be *"overturned by one sentence from the
business"* because its premise — that the owner sits at a desk — was an inference, not an
observation. **It was, within a day.** The paragraph is kept verbatim in v1.1.0 rather than
deleted.

**Two dependencies were found only after the ruling, by checking it against the code:**

| # | Finding | Effect |
| --: | --- | --- |
| ~~**OI-6**~~ | ~~`GET /reports/dashboard` does not exist.~~ Three of the four D-4 numbers were reachable; **"collected today" was not** — only a paginated `/payments` list, which the device would have had to page and sum, **deriving a figure on the device** over 2G | ✔ **Built and verified as task 0.** `05` §9.11.1 |
| **OI-7** | **"Notifications" were cut from Edition 1** — `02A` §13: *"In-app notifications (**M-14 entirely**)… 0.5"*. No model, table, endpoint or milestone exists | Blocks task 8. Recommendation: adopt `02A`'s own substitute — a **"Needs attention"** filtered read |

> **Same shape as M7's C-1…C-6.** `02A` §7.x's feature matrix predates §13's Edition-1
> re-validation, and **§13 governs.** OI-7 is a request a frozen document has already
> answered.

**Neither blocks Phase 2 from starting.** Both sit inside task 8, which §10.1 places last
precisely because nothing depends on it.

---

## Design principles — frozen, and the reason they exist

`docs/M8_Design_Review.md` §1.3 records **P-1…P-10** so a Phase 2 decision is checked in one
line instead of re-argued. The three that cannot be repaired after the fact:

| # | Principle | Why it is unrecoverable |
| --: | --- | --- |
| **P-3** | Money and quantity are `Decimal` end to end — **no `double`** | Corrupts figures that have already been sent |
| **P-6** | `client_uuid` generated before the first attempt, **never regenerated** | Defeats the server idempotency M9 depends on |
| **P-9** | The binary holds **no secret and no rule** the server does not independently enforce | A security property of a binary already downloaded |

> **These get tests, not review comments.** §12.7 admits the rest are currently advisory —
> the exact status TD-2's type gate held for six milestones before it caught 24 errors.

---

## Phase 2 task order

| # | Task | Gate |
| --: | --- | --- |
| ~~**0**~~ | ~~Backend: `GET /reports/dashboard`~~ | ✔ **DONE** — 8/8, 726/726, 94.88% |
| ~~**1**~~ | ~~Toolchain, shell, DI, router; layering + no-secrets tests~~ | ✔ **DONE** — 8/8, **742/742**, 94.88%. 16 contracts, each proved able to fail |
| ~~**2**~~ | ~~Decimal codec and the API layer~~ | ✔ **DONE** — 8/8, **743/743**, 94.88%; `mobile-verify` **38/38**, 0 errors |
| ~~**TD-39**~~ | ~~`client_uuid` on `/deliveries/{id}/complete` and `/fail`~~ | ✔ **DONE** — 8/8, **758/758**, 94.71%; `makemigrations --check` clean |
| ~~**3**~~ | ~~Drift schema, outbox, sequencer~~ | ✔ **COMMITTED** — `3009e3b`. **The kill and real-storage-exhaustion halves were deferred to task 10 by §14.11, and no recorded evidence of them was found in the repository** |
| ~~4~~ | ~~Auth: OTP, password, keystore, refresh-once, device id, offline window~~ | ✔ **COMMITTED** — `1014c88`, `cea3e84`, `5b0f035`, `1ebbe43`, `af9a1ca`, `b9d4eb4` |
| ~~5~~ | ~~Delivery: list, detail, complete, fail~~ | ✔ **COMMITTED** — `b3f738c` |
| **6** | **GPS and the separate media queue** | C-9. **No commit.** No GPS, media or photo code exists under `mobile/lib/` |
| ~~7~~ | ~~Customers, visits~~ | ✔ **COMMITTED** — `11bb370` |
| ~~8~~ | ~~**Owner Companion Mode**~~ | ✔ **BUILT 2026-09-06.** Four read-only screens over endpoints that already existed, owner-gated through the existing `TabSpec`/`RoleShell`. **OI-7 ruled** (M-14 stays cut; "Needs attention" is orders + failed deliveries; **overdue excluded** — no rule exists to read) and **TD-36 closed**, which were its two blockers. **Online-only**, so no `as_of` cache label: what the screen shows is what the request returned |
| ~~9~~ | ~~Sync-status screen~~ | ✔ **COMMITTED** — `feeb85d`, extended by M9.3 (`e26aa87`) |
| **10** | **8-hour offline soak** (NFR-OFF-001) and the **M8→M9 gate** | **Measured on a real device. No commit, and no recorded evidence of this gate was found in the repository** |

**Tasks 6 and 10 remain** *(task 8 built 2026-09-06)*. §10.1 is explicit that of the three, only task 8 could ever
move: *"task 8 is the first thing that can move to M8.1 without breaking the milestone gate —
**task 10 cannot**."* Task 10 carries the M8→M9 gate condition from `00` §19.2 — *"outbox
survives kill, restart and storage exhaustion"* — and §14.11 assigned it the two halves of
task 3's durability proof that task 3 itself did not make. **No recorded evidence of this gate
was found in the repository** — which is an absence of an artefact, not proof that nothing was
run. A soak measured on a device leaves no trace here unless someone writes it down. This
document records the absence; it does not rule on it.

**Tasks 1 and 2 precede every feature deliberately.** `reporting`'s four AST tests were
written when it had one file; that is why the contract still holds at seven. Written last,
they are worth nothing — by then the violation *is* the code.

**Task 0 was first because it is a different toolchain**, and that held: it verified and
committed on its own, before any Dart entered the repository.

**Task 1's contracts were written before the first widget, and that held too.** They are in
**Python, inside stage 7** — not in `analysis_options.yaml`, which `make verify` never runs
and which would therefore have been advisory from birth. Each of the 16 was proved able to
fail by mutating the tree, because a green test that cannot go red is not evidence.

> **Task 1 cost four infrastructure defects and zero application defects**: a dead image
> registry, a pub cache that did not survive the container boundary, an analyzer whose
> defaults differ from `dart analyze`, and a directory that was never bind-mounted. **Three
> of the four reported the wrong layer** — a missing mount surfaced as *"the Flutter pin is
> not stated exactly once"*. Expect task 2's surprises to be of the same kind, not in the
> Dart.

---

## Task 2 — the frozen boundary, as built (`M8_Design_Review` §14)

**Built, and nothing else:** Dio `ApiClient` · `AuthInterceptor` · **single-flight**
`RefreshInterceptor` · `DeviceInterceptor` · problem+json → typed `Failure` · the `Money`
codec · a `TokenStore` **interface only** · 29 Dart tests.

**Held out, and still out:** the outbox (task 3) · auth screens, the keystore and the offline
credential store (task 4) · **any dashboard DTO or dashboard-specific client code** (task 8,
§14.6) · **TD-39** · any backend change.

| # | Frozen | One line |
| --- | --- | --- |
| **D-B1** | Single-flight refresh | Concurrent `401`s share **one** refresh; each original request retries **exactly once**; a second `401` is terminal |
| **D-B2** | Structural isolation | `/auth/refresh` runs on a **separate `Dio`** carrying neither auth nor refresh interceptor — not a re-entrancy flag |
| **D-B3** | Identity-preserving retry | The retry replays the original request, **especially its `client_uuid`**. Never a new operation identity (P-6) |

> **D-B1 is not a style preference.** The server sets `ROTATE_REFRESH_TOKENS: True` **and**
> `BLACKLIST_AFTER_ROTATION: True`. Parallel refresh means the second call presents a
> blacklisted token and **reuse detection treats it as an attack** — three requests failing
> together can log a working session out.

### What task 2 found

| Finding | Where it landed |
| --- | --- |
| **`device_id` is a body field, not a header.** §7.2 only says *"on every write"*; `05` §9's examples and the DRF serializers both put it in `request.data`. A header would be accepted by the transport and **ignored by the server** — the exact attribution loss C-10 names | `DeviceInterceptor` injects into the body; a test asserts the header is absent |
| **Offline during refresh must not sign the user out.** D-B1 covers the 401 and says nothing about a refresh that never reaches the server. Clearing the keystore there would end FR-IAM-016's window at the first tunnel | Only a 401 clears. Tested |
| **`package:decimal` normalises `'11800.00'` to `'11800'`** — correct arithmetic, wrong transport, and a silent change to a field's declared scale | `Money` carries the scale it arrived with |

> **The costliest defect was in the test harness, not the code.** It stored live
> `RequestOptions`; D-B3 replays the *same* object and `AuthInterceptor` rewrites its header
> in place, so every recorded attempt showed the last token — **and the `client_uuid`
> assertion was comparing an object with itself.** A test that could not fail, guarding the
> principle that cannot be repaired later. Fixed by snapshotting each request.

---

## Entry conditions

| # | Condition | State |
| --: | --- | :-: |
| 1 | §13 signed; both ADRs approved | ✔ |
| 2 | §1.3 principles frozen | ✔ |
| 3 | **TD-32 — retire the superseded `==` dev pins** | ☐ **Missed its window.** It was to land before the Dart toolchain; the toolchain arrived first. Still owed, now without that argument |
| 4 | **K-1 — keystore procedure agreed** | ◐ **Procedure written 2026-09-12** — `docs/runbooks/android-keystore.md`. The **keystore does not exist**; K-1 itself is open. See below |
| 5 | **TD-11 — DLT registration started** | ☐ **External, unbounded** |
| ~~6~~ | ~~Flutter/Dart SDK pinned, as `uv.lock` pins Python~~ | ✔ **Done in task 1** — `mobile/.flutter-version` + `mobile/pubspec.lock` (32 packages). **By version, not by bytes: TD-38** |
| ~~7~~ | ~~OI-6 — the dashboard endpoint~~ | ✔ **Built and verified** |
| ~~8~~ | ~~**OI-7** and **TD-36** ruled~~ | ✔ **Both closed 2026-09-06.** Task 8 built |

> **Conditions 3 and 6 are one lesson.** TD-21 was closed *before* a second toolchain
> arrived, so reproducibility was settled with one language in the repository. Phase 2 adds
> the second. **Pin Dart the way Python is pinned, on the first day** — not after the first
> "works on my machine".

### K-1 — the one irreversible thing in M8

> **If the Android release keystore is lost, the application on Google Play can never be
> updated again.** Not by you, not by Google (`00` §2.3).

Generated once, stored in the password manager, backed up to **two locations that are not
the development machine**, never in Git (S-06, N-11). Done at M8, verified at M11.

**The procedure now exists: `docs/runbooks/android-keystore.md`** (2026-09-12). Entry
condition 4 asks for a procedure *agreed*, and `M8_Design_Review` AR-5 is explicit that this
is *"not an M8 code risk — an M8 **procedure** risk"* — so the condition is satisfiable
without generating anything, and that is what happened. **The keystore has not been
generated and the log in that runbook is empty.** K-1 remains an open operator action, and
the M11 verification it calls for has nothing to verify yet.

### The condition DV-4 is accepted on, and it is absolute

> **The binary is publicly downloadable and must be assumed fully decompiled** (`02A` §9.3).
> It may contain no internal-only logic, endpoint or secret that server-side authorisation
> does not independently enforce.

**Companion Mode raises the stakes on this, it does not change it.** An owner token now
reaches the app, so read-only must be enforced by the absence of a server-side write path —
**not by the absence of a button.**

---

## Workflow, unchanged

1. Review the frozen corpus and `M8_Design_Review.md` v1.1.0 §1.3 before deciding anything.
2. Identify specification conflicts **before** proposing an implementation.
3. Implement one logically complete task.
4. `make verify` 8/8 — the only authority (N-12).
5. Verification note, then documentation, then commit.

**No weakened tests. No lowered coverage. No bypassed contracts.**

---

## Carried forward

| Item | Note |
| --- | --- |
| **Uncommitted** | Task 2's code and this documentation pass await the milestone commit. **`LICENSE` also shows as modified — line endings only (LF→CRLF), no content change.** `git checkout -- LICENSE` before committing so it does not ride along |
| **Re-run `make perf`** after any change to a report or the §5A walk | Not in `make verify` and never will be — a ~430-second dataset build has no place in an 8-stage gate, so **nothing else catches a regression of that class**. It runs against the disposable `districore_perf`, never the development database |
| **TD-29** | Nothing asserts a new report is wired into `REPORT_MENU`, the API router **and** the CSV path. **Task 0 adds an eighth report endpoint — this is the first time TD-29 can actually bite** |
| **TD-31** | Clock-dependent tests. Four fixed; the class is not structurally prevented |
| **TD-37** | **Open, and costlier after task 2.** `mobile-verify` is still not in `make verify`. The 21 structural contracts are blocking, but *"does the Dart compile"* is not — and **the 317 Dart cases are invisible to the only authority.** The 829 figure does not include them. Promote to stage 9 once the toolchain image has held for a milestone |
| **TD-38** | **New. The Flutter SDK is pinned by version, not by bytes.** `make mobile-image` prints the checksum; paste it into `FLUTTER_SHA256` and the gap closes |
| ~~**TD-36**~~ | **CLOSED 2026-09-06** (`M8_Design_Review` §3.4.1b). Eight endpoints, not seven, and **not** by routing every numeric cell through `money_string()` — that would have stringified the counts. A semantic `ColumnKind`; CSV byte-identical; `05` **AD-02.1** added for `RATE` |
| Deferred debt | TD-32, TD-33 (DRF stubs), TD-34 (`ops/` outside mypy), TD-23, TD-26, TD-28, TD-15. ~~TD-35 (`pip-audit \|\| true`)~~ **closed 2026-09-07 at M10**; ~~TD-14~~ **closed** — `PROJECT_STATE.md` |
| **The lesson still standing** | **A design review cannot find a defect on a path the tests do not take.** Four reviews found none of M7's four defects; running the real thing found all of them. M8 runs on hardware no test rig replicates — §10 task 10 is the only place that gets checked |

## Blocking, not owned by engineering

| Item | Owner |
| --- | --- |
| **CF-1 — is statutory e-invoicing mandatory?** (`02` OI-1). More expensive with every invoice issued | Business owner |
| **TD-11 — SMS/DLT registration.** Inside M8's critical path | Business owner |
| **OI-7 — "Needs attention" substitute vs reopening M-14** | Product Architect |
| **TD-15 — `offer` has no milestone** | Product Architect |
