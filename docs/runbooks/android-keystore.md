# Runbook — K-1, the Android release keystore

> **If the Android release keystore is lost, the application on Google Play can never be
> updated again. Not by you, not by Google** (`00` §2.3). The only remedy is a new listing
> under a new package name and asking every retailer and salesman to uninstall and reinstall.

**Rule K-1**, verbatim from `00` §2.3:

> *The keystore and its passwords are generated once, stored in the password manager, and
> backed up to at least two locations that are not the development machine. This is done at
> M8 and verified at M11. It is never committed to Git (N-11).*

`M8_Design_Review` entry condition 4 — *"K-1 keystore procedure agreed"* — has been open since
M8. **This document is that procedure.** It does not perform it.

**Status: procedure agreed. The keystore does not exist.** `M8_Design_Review` AR-5 classifies
this correctly: *"not an M8 code risk — an M8 **procedure** risk."*

---

## What this runbook is not

**Nothing here is automated, and nothing should be.** The keystore and its passwords are
secrets: no script in this repository generates them, reads them, stores them or transports
them. The steps below are for a human at a keyboard, and the only artefacts that come back
into the repository are the **non-secret** facts in §7.

Google Play App Signing reduces this exposure — Google holds the app signing key — but **the
upload key still matters**, and losing it still requires a Play support process you may not
win. `00` §2.3: *"treat the rule as absolute."*

---

## 1. Before you start

| Need | Why |
| --- | --- |
| A JDK with `keytool` on `PATH` | `keytool -help` must work. Android Studio ships one; so does any JDK 17 |
| The password manager, open | S-06's passwords go in **as you create them**, not afterwards from memory |
| **Two** storage destinations that are **not** this machine | K-1 says at least two. A second folder on the same disk is not a second location |

Choose the two destinations before generating anything. Deciding afterwards is how one of
them quietly never happens.

Reasonable pairs: an encrypted cloud vault plus an encrypted USB stick kept elsewhere; two
USB sticks in two physical places. **Neither may be this development machine**, and neither
may be inside the repository working tree.

---

## 2. Where the file lives

**Outside the repository. Always.**

```bash
mkdir -p ~/districore-keys
chmod 700 ~/districore-keys
```

The root `.gitignore` refuses `*.jks`, `*.p12`, `*.keystore`, `*.pepk` and `key.properties` as
defence in depth (§6), but the primary protection is that the file is never inside the working
tree at all. A file that cannot be reached by `git add` does not depend on a pattern being
right — and until M11 **no pattern covered `.p12`**, which is the format §3 produces.

---

## 3. Generate — once, and only once

**One command. Do not vary it.** `-storetype PKCS12` is the modern `keytool` default; JKS is
proprietary and `keytool` warns about it. Both are valid for Play upload keys, and
`.gitignore` covers both — PKCS12 is specified here so the procedure is deterministic.

```bash
keytool -genkeypair \
  -v \
  -storetype PKCS12 \
  -keystore ~/districore-keys/districore-upload.p12 \
  -alias upload \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000
```

| Parameter | Value | Why this value |
| --- | --- | --- |
| `-storetype` | `PKCS12` | `keytool`'s default since JDK 9; no proprietary-format warning |
| `-keystore` | `~/districore-keys/districore-upload.p12` | Outside the repository (§2) |
| `-alias` | `upload` | The Android/Flutter convention, and the name the signing config will reference. Deterministic so a future reader does not guess |
| `-keyalg` · `-keysize` | `RSA` · `2048` | Google Play's requirement for an upload key |
| `-validity` | `10000` days (~27 years) | Play requires a key valid well beyond any plausible release. A key that expires is a key that cannot ship an update |

`keytool` will ask for a **store password**, then a **key password**, then the distinguished
name fields. For the DN, use the business name and country; none of it is secret and none of
it is shown to users.

**Use two different passwords**, store-level and key-level. Generate both in the password
manager — long, random, never typed from memory, never reused from anything else.

> **Do not run this twice.** A second run against the same path either fails or creates a
> second alias, and a keystore whose identity you are unsure of is one you cannot safely
> publish with. If something goes wrong before the first upload to Play, delete the file and
> all backups and start again — that is only safe *before* an app has ever been published.

---

## 4. Store the passwords — immediately, before anything else

In the password manager, one entry:

| Field | Content |
| --- | --- |
| Title | `DistriCore Android upload keystore (S-06 / K-1) — NEVER ROTATE` |
| Store password | the value you just set |
| Key password | the value you just set |
| Alias | `upload` |
| Store type | `PKCS12` |
| Filename | `districore-upload.p12` |
| Created | today's date |
| Note | *"K-1: cannot be rotated (`00` §2.5). Two off-machine backups at …"* — name the two destinations |

Attach the keystore file to the entry if the password manager supports attachments. That is
useful and it **does not count as either of the two backups** — the password manager already
holds the passwords, so one compromise or one lockout would take both halves.

---

## 5. Back up — two locations, neither this machine

Copy `districore-upload.p12` to both destinations chosen in §1.

**Then prove each copy is usable**, because `00` §14 B-1's logic applies here with nothing
changed: *"a backup that has never been restored does not count as a backup."* An unverified
keystore copy is the same bet as an unverified database dump, with a worse loss.

For **each** destination, from the copy — not the original:

```bash
keytool -list -v -storetype PKCS12 -keystore <path-to-the-copy>
```

Record the **SHA-256 fingerprint** it prints. All three — the original and both copies —
**must be identical**. A fingerprint that differs means the copy is a different key, and a
different key is a key that cannot publish an update.

**The SHA-256 fingerprint is not a secret.** Google Play displays it; it identifies the key
without revealing it. That is exactly what makes it the right thing to record.

---

## 6. Repository-side checks — these are the only steps this repository can verify

Run from the repository root. All four must hold.

```bash
# 1. Nothing keystore-shaped is tracked. Empty output.
git ls-files | grep -iE '\.(jks|p12|keystore|pepk)$|key\.properties'

# 2. Nothing keystore-shaped is even present in the tree. Empty output.
git status --porcelain | grep -iE '\.(jks|p12|keystore|pepk)$|key\.properties'

# 3. The ignore rules are real, not assumed. Each must report a matching rule.
git check-ignore -v key.properties mobile/android/key.properties x.jks x.p12 x.keystore x.pepk

# 4. The release build still carries no signing credentials.
grep -n "signingConfig\|storePassword\|keyPassword" mobile/android/app/build.gradle.kts
#    Expect: only the explanatory comment in the `release` block. No assignment.
```

`test_release_signing.py` holds checks 3 and 4 from inside `make verify`, so they cannot
quietly stop being true. Checks 1 and 2 need `git`, which the backend image does not contain
(`M10_Security_Review` §NFR-SEC-007) — so they are operator steps, and the contract instead
asserts the **mechanism that prevents the commit**, which is `.gitignore` itself.

---

## 7. Record the evidence — non-secret only

Fill the log below. **Nothing in it is a secret**: a fingerprint identifies a key without
revealing it, and the destinations are named by description, not by credential or URL.

**Never record:** either password, the DN, the file itself, a path on a cloud provider, or
anything that would help someone locate a backup.

---

## 8. What is still owed after this

**The signing configuration is not written yet, deliberately.**
`mobile/android/app/build.gradle.kts`'s `release` block carries no `signingConfig` and says
why: the generated default signed release builds with the **debug** key, *"which is
convenient and wrong"*. Adding a config now would reference a file that does not exist and
turn a correct refusal into a confusing failure.

Once §1–§7 are complete and the fingerprint is recorded, the follow-up is one bounded change:
a `release` `signingConfig` reading `storeFile`, `storePassword`, `keyAlias` and `keyPassword`
from `mobile/android/key.properties` — a file that is **gitignored**, lives only on the
machine that builds a release, and is never committed. That change belongs with the first
real release build, not before.

`00` §2.3 says K-1 is *"done at M8 and verified at M11"*. §1–§7 are the doing. The
verification at M11 is re-reading the fingerprint from both backups and confirming it still
matches the row below.

---

## K-1 log

> **Empty, and deliberately so.** The keystore has **not been generated**. This table is
> filled only by the person who generated it and verified both backups, from what they
> observed — the same posture the restore rehearsal and the go-live load take. A row here
> asserting a key exists when it does not is worse than an empty table, because the next
> reader will believe it.

| Date | Alias | Store type | Key | Validity to | SHA-256 fingerprint | Backup 1 verified | Backup 2 verified | By |
| --- | --- | --- | --- | --- | --- | :-: | :-: | --- |
| | | | | | | | | |
