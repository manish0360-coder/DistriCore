# M10 — Security Review

| Field | Value |
| --- | --- |
| Document ID | `M10_Security_Review` |
| Version | **1.1.0** |
| Status | **COMPLETE.** Eleven of eleven evidenced. NFR-SEC-009 met at M10.5: 15 of 16 findings remediated by upgrade, **one time-bound exemption** recorded at §3.3 |
| Date | 2026-09-07 · **§3 rewritten 2026-09-07 (M10.5)** |
| Milestone | M10 — Hardening (1.5 units, `00` §19.1) |
| Gate | `00` §19.2, M10 → M11: *"Restore rehearsed and recorded (B-3); **security review complete**"* |
| Depends on | `02` §21.4 · `00` §6.4, §14 · `02A` §9.3 |

---

## 1. What this document is, and what it is not

`02` §21 opens with the sentence this review exists to satisfy:

> *"A non-functional goal without a measurement method is not a requirement."*

Before M10, `grep NFR-SEC-0` across `backend/tests/` returned **two of eleven**. The
mechanisms largely existed — `prod.py` sets HSTS, SSL redirect and secure cookies, the
exception handler emits problem+json, `test_authorization_matrix.py` issues the role grid
directly at the API — but nothing tied a requirement to the thing that proves it. **A review
cannot be completed against evidence that is not traceable**, whatever the code does.

**Version 1.0.0 of this document did not declare the review passed** — NFR-SEC-009 was
failing and §3 recorded it as a blocker rather than an exemption. **M10.5 closed it** (§3), so
that clause is now spent. What remains open is the *other* half of the `00` §19.2 gate, the
restore rehearsal — §5.

**Evidence is graded, and the grades are not interchangeable:**

| Grade | Meaning |
| --- | --- |
| **A** — automated | An assertion in `make verify`. Re-run on every commit; cannot rot silently |
| **E** — external | A CI step or a device gate, outside the backend suite. Runs, but not in `make verify` |
| **M** — manual | A judgement or a procedure. Recorded with a date, or recorded as outstanding |

A requirement whose only evidence is **M** is not thereby met; it is met when the manual step
has actually been performed and dated.

---

## 2. NFR-SEC-001…011 — the matrix

| Requirement | Summary | Grade | Evidence | Verdict |
| --- | --- | :-: | --- | :-: |
| **NFR-SEC-001** | Current TLS; plaintext **rejected**, not discouraged | A + M | `test_production_settings_reject_plaintext_transport` — `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS 1 year + subdomains + preload, read **statically** from `prod.py` (§2.1). `test_production_refuses_to_start_on_a_development_secret` | **MET (config)** · downgrade attempt outstanding |
| **NFR-SEC-002** | All data access parameterised; no string-concatenated queries | A | `test_a_sql_payload_in_a_query_parameter_changes_nothing` — a real `'); DROP TABLE customer; --` through `search_customers`, asserting the row survives. `test_no_production_query_carries_a_value_into_its_sql` — AST over every non-test module | **MET** |
| **NFR-SEC-003** | All input validated server-side against an explicit schema | A | `test_malformed_input_is_refused_by_the_server_not_the_client` — three malformed bodies to `/orders` and `/payments`; **4xx, never 5xx** | **MET** |
| **NFR-SEC-004** | Output encoded contextually (XSS) | A | `test_a_stored_script_payload_is_escaped_on_the_page` — `<script>` stored in `shop_name`, rendered on the owner's customer list, asserted escaped **and** present | **MET** |
| **NFR-SEC-005** | CSRF where the surface is cookie-authenticated | A | `test_a_cookie_authenticated_post_without_a_csrf_token_is_refused` — `Client(enforce_csrf_checks=True)`; forbidden case **and** the allowed case | **MET** |
| **NFR-SEC-006** | Uploads type-validated, size-limited, outside the web root, authorised non-guessable references | A | `tests/unit/test_media.py`, `tests/adversarial/test_master_data_authorization.py`. **Not duplicated here** | **MET** |
| **NFR-SEC-007** | Secrets not in source control; supplied by environment | A + E | `test_the_secret_key_has_no_in_repository_default` · `test_an_env_file_cannot_be_committed` — asserts the **mechanism that prevents the commit**, `.gitignore` (§2.1) · gitleaks, first step in CI | **MET** |
| **NFR-SEC-008** | Device local storage encrypted at rest | E | **D-M9-8**, 2026-08-25. `make mobile-device-encryption` on a Pixel 8a API 34 emulator; two structural contracts in `test_mobile_boundary.py`. **`android-x64` only — TD-45** | **MET, bounded** |
| **NFR-SEC-009** | Dependencies scanned in CI; **a critical finding MUST block release** | A + E | `test_the_dependency_audit_cannot_be_silenced` (no `\|\| true`, `--strict` present, no `continue-on-error`) · `test_every_ignored_vulnerability_is_a_recorded_decision` · `test_weasyprint_presentational_hints_are_never_enabled`. **15/16 findings remediated by upgrade; one documented exemption, §3.3** | **MET** |
| **NFR-SEC-010** | Errors disclose no stack trace, query text or internal identifier | A | `test_an_error_response_discloses_nothing_internal` — a real refusal, body scanned for `Traceback`, `SELECT `, `File "`, `/backend/`, `django.db`. `test_production_never_runs_with_debug_enabled` (static, §2.1) | **MET** |
| **NFR-SEC-011** | Authorisation verified at the API boundary for **every** request | A | `test_authorization_matrix.py` (10 tests, the role grid) · `test_every_api_endpoint_requires_authentication_unless_listed` — resolver walk over every `v1:` route · `test_a_protected_endpoint_refuses_an_anonymous_caller` | **MET** |

### 2.1 Where each assertion runs, and why two of them are static

The first authoritative `make verify` run of this suite failed **six** times, and every failure
was the same mistake in two forms: **a repository-level contract written as an
application-runtime test.**

| Assertion | Ran wrongly as | Now |
| --- | --- | --- |
| NFR-SEC-001, 010 | `from config.settings import prod` | **Static.** `prod.py` *raises at import* unless the process holds a 50-character secret, an explicit `ALLOWED_HOSTS`, a real SMS provider and JSON logging — `00` §10.1's *"refuse to start rather than run insecurely"*. Importing it from a test would mean making the test runtime **claim to be a production runtime**, which is the property the module exists to deny. Reading the literals is also stronger in one way: it proves the value is fixed in the production module, not something an environment variable could weaken at deploy time |
| NFR-SEC-007 | `git ls-files` | **`.gitignore`.** The right question in the wrong place — the backend image contains no git, so it passed everywhere it did not matter. The assertion is now on the mechanism that *prevents* the commit, which is itself a file under source control |
| NFR-SEC-009, and this document's own accounting | reading `.github/`, `docs/` and `uv.lock` | **Bind-mounted, read-only.** `make verify` is the only authority (N-12), so a CI contract enforced where the gate cannot see it is advisory. `docker/compose.dev.yml` already carries `Makefile`, `mobile/` and `docker/` for exactly this reason, and its own comment warns that the mount list and the test's `REQUIRED_PATHS` are *"one fact in two places"* — a warning this suite then walked straight into. It now has the same precondition test, naming the same compose block. **`uv.lock` was the third instance**: it is `COPY`ed into the *builder* stage at `/build` and never into the runtime image, so the lock contract failed as a bare `FileNotFoundError` rather than as the mount problem it was. `REQUIRED_PATHS` now lists it, and `_locked_versions` fails closed with a message that names the layer |

**Nothing was weakened to fix these.** No production setting changed, `prod.py` is no less
strict, no fake secrets were injected, and no tooling was added to the runtime image. Each of
the six was a test placed in the wrong layer.

---

### Two findings recorded rather than smoothed over

**NFR-SEC-002 — four `f`-string queries, reviewed and accepted.**
`purchasing.services._next_po_number`, `_next_grn_number`, `_next_supplier_payment_number` and
`receivables.services._next_payment_number` each read
`cursor.execute(f"SELECT nextval('{SEQUENCE_CONSTANT}')")`. The interpolated name is a
module-level constant defined in `models.py` and imported; **no caller can reach it**, so
there is no injection path. Parameterising `nextval` is possible, but these are the gapless
numbering paths (M5-4, M6) and rewriting financial code to satisfy a rule that could not read
it would add risk to remove none. The contract is therefore stated as the property —
*interpolation of anything that is not a module constant* — and these four pass it.
**Available hardening, not a finding.**

**NFR-SEC-011 — four endpoints are anonymous by design**, and they are now listed rather than
implicit: `/auth/otp/request`, `/auth/otp/verify`, `/auth/login`, `/auth/refresh`. Each is a
path a caller reaches *before* holding a token. `PUBLIC_BY_DESIGN` asserts the set in both
directions, so adding a fifth is an edit somebody reviews and removing one fails loudly.

### Outstanding manual evidence

| Requirement | What is owed | Owner |
| --- | --- | --- |
| NFR-SEC-001 | A downgrade attempt against the deployed TLS endpoint, dated. The configuration is asserted; the live behaviour is not | M11, at deployment |
| NFR-SEC-004 | `02` §21.4 also names an *"automated scan"*. The stored-payload test is done; no DAST scanner is wired | M11 |
| NFR-SEC-008 | `arm64` and physical hardware (**TD-45**) | TD-45 |

---

## 3. NFR-SEC-009 — the gate, the sixteen findings, and one exemption

### 3.1 What M10 found and M10.5 fixed

**The gate was not real.** `.github/workflows/ci.yml` carried `pip-audit --strict || true` from
P0 until M10 (**TD-35**). A step that cannot fail blocks nothing, and the requirement's own
verification method is *"CI gate"*. This is the shape `mypy` held for six milestones with 24
real errors behind it (TD-2); `pip-audit` had never once been allowed to speak.

Removing the suffix made it speak: **16 findings across 4 packages**, none of them fixable
inside the constraints `pyproject.toml` then declared. M10.5 raised the three declared floors.

| Package | Before | After | Constraint before | Constraint after |
| --- | --- | --- | --- | --- |
| `django` | 5.1.15 | **5.2.17** | `>=5.1,<5.2` | `>=5.2.17,<5.3` |
| `djangorestframework` | 3.15.2 | **3.17.2** | `>=3.15,<3.16` | `>=3.17.2,<3.18` |
| `weasyprint` | 66.0 | **68.1** | `>=62,<67` | `>=68,<69` |
| `sqlparse` | 0.5.5 | **0.6.0** | *transitive, via `django`* | **`[tool.uv] constraint-dependencies`** — see §3.5 |

**Each floor is the lowest version that resolves every finding against it**, not the newest
release. `django` is 5.2.17 because PYSEC-2026-3717 is fixed there and the other six are fixed
earlier; `weasyprint` is `>=68` because the SSRF fix landed in 68.0. Django 6.0 also fixes all
seven and was **not** taken: it is a second major step with no security benefit over 5.2.17.

### 3.2 The sixteen findings, and their disposition

**Reachability is per-application, and it did not change a single decision** — everything with
a published fix was upgraded regardless. It is recorded because it is what makes the one
exemption defensible rather than convenient.

| # | Identifier | Package | Fixed in | Reachable here? | Disposition |
| --: | --- | --- | --- | --- | --- |
| 1 | PYSEC-2026-3717 / CVE-2026-15830 | django 5.1.15 | 5.2.17 | **No** — GeoDjango; `django.contrib.gis` is not in `INSTALLED_APPS` and `GEOSGeometry` appears nowhere | **FIXED** by upgrade |
| 2 | CVE-2026-48587 | django | 5.2.15 | **No** — `Vary` handling in `django.utils.cache`; no cache middleware is installed | **FIXED** |
| 3 | CVE-2026-6873 | django | 5.2.15 | **No** — `get_signed_cookie` is not used | **FIXED** |
| 4 | CVE-2026-8404 | django | 5.2.15 | **No** — `UpdateCacheMiddleware` is not installed | **FIXED** |
| 5 | CVE-2026-48588 | django | 5.2.16 | **No** — `UpdateCacheMiddleware` / `cache_page` unused | **FIXED** |
| 6 | CVE-2026-53877 | django | 5.2.16 | **No** — `GDALRaster`, GeoDjango | **FIXED** |
| 7 | CVE-2026-53878 | django | 5.2.16 | **No** — `DomainNameValidator` is not used | **FIXED** |
| 8 | CVE-2026-73228 | djangorestframework 3.15.2 | 3.17.2 | **YES** — `request.data` bypasses `DATA_UPLOAD_MAX_MEMORY_SIZE` for `application/json`. **Every write endpoint this product has is a JSON API.** The one genuinely reachable finding in the set | **FIXED** |
| 9 | CVE-2026-73229 | djangorestframework | 3.17.2 | **No** — `AdminRenderer` disclosure; the API declares `JSONRenderer` and `CsvRenderer` only | **FIXED** |
| 10 | PYSEC-2026-3696 / CVE-2026-59894 | sqlparse 0.5.5 | 0.6.0 | **No** — the Python/PHP output filters are not used | **FIXED** (transitive) |
| 11 | PYSEC-2026-3697 / CVE-2026-71491 | sqlparse | 0.6.0 | **No** — Django uses sqlparse for `sqlmigrate` formatting, never on request input | **FIXED** |
| 12 | PYSEC-2026-3698 / CVE-2026-59893 | sqlparse | 0.6.0 | **No** — as above | **FIXED** |
| 13 | PYSEC-2026-3699 / CVE-2026-54284 | sqlparse | 0.6.0 | **No** — as above | **FIXED** |
| 14 | CVE-2026-84305 | sqlparse | 0.6.0 | **No** — `ReindentFilter`, opt-in formatting | **FIXED** |
| 15 | PYSEC-2026-2034 / CVE-2025-68616 | weasyprint 66.0 | 68.0 | **Possible** — SSRF in `default_url_fetcher`; the invoice template is rendered from `string=` and is repository-controlled, but a fetcher bypass does not depend on our template being hostile | **FIXED** |
| 16 | **CVE-2026-49452 / PYSEC-2026-3412 / GHSA-jhhc-3hcp-qhm5** | weasyprint | **none published** | **No** — see below | **EXEMPTED, time-bound** |

> **Three identifiers, one issue.** CVE-2026-49452 and PYSEC-2026-3412 are aliases;
> `pip-audit` reports the CVE through its PyPI service and the PYSEC through OSV, so both are
> ignored, and GHSA-jhhc-3hcp-qhm5 with them.

### 3.3 The exemption — CVE-2026-49452, and why it is not a hidden finding

**The advisory:** *"A CSS injection issue exists in WeasyPrint when HTML presentational hints
are enabled. Unescaped attribute values are embedded into CSS."* **No published fix exists in
any version, including the 68.1 this milestone upgrades to.** Downgrading is not an option and
neither is waiting: the other WeasyPrint finding is a real SSRF that 68.0 fixes.

**The reachability argument is from WeasyPrint's source, not from the advisory's prose.**
`weasyprint/css/__init__.py::find_style_attributes` guards the entire vulnerable block:

```python
for element in tree.iter():
    ...
    if not presentational_hints:
        continue                                   # <- everything below is skipped
    ...
    if element.get('bgcolor'):
        style_attribute = f'background-color:{element.get("bgcolor")}'   # the injection
```

* `presentational_hints` defaults to **`False`** (`weasyprint/__init__.py`, DEFAULT_OPTIONS).
* This application has **one** WeasyPrint call site — `billing/pdf.py`:
  `HTML(string=render_invoice_html(invoice)).write_pdf()` — and it does not pass the argument.

So the interpolation the advisory names is never executed here.

> **DECISION — M10.5-1, 2026-09-07.** CVE-2026-49452 / PYSEC-2026-3412 / GHSA-jhhc-3hcp-qhm5
> are exempted from the NFR-SEC-009 gate, on the ground that the vulnerable path is
> unreachable while `presentational_hints` is disabled.
>
> **Review by 2026-12-07**, or immediately on any WeasyPrint release that fixes it, whichever
> is first. **This is an exemption, not a closure**: the finding remains open upstream.

**Two tests hold the decision**, because an exemption resting on an unenforced property is a
comment:

| Test | Fails when |
| --- | --- |
| `test_every_ignored_vulnerability_is_a_recorded_decision` | an identifier is silenced in CI and appears nowhere in this document, or an exemption exists with no review date |
| `test_weasyprint_presentational_hints_are_never_enabled` | `presentational_hints` is referenced anywhere in non-test backend code — i.e. the moment the reachability argument above stops being true |

The blanket ban on `--ignore-vuln` that M10 shipped is therefore **replaced by a traceability
requirement**, not relaxed: an undocumented ignore still fails the build. The ban was correct
until a finding had no fix in any version, at which point it left only two moves — a
permanently red pipeline, or deleting the gate — and both are worse than a dated record.

### 3.4 What the upgrade did not require

* **No Docker change.** WeasyPrint 68.1 loads exactly the native libraries 66.0 did —
  `gobject-2.0`, `pango-1.0`, `harfbuzz`, `harfbuzz-subset`, `fontconfig`, `pangoft2-1.0` —
  verified by diffing `weasyprint/text/ffi.py` between the two wheels. `docker/Dockerfile`
  already installs them and is unchanged.
* **No application code change.** A scan for every setting and API Django removed across 5.0
  → 5.2 found one hit, and it is **pre-existing and unrelated to the upgrade** (§4).
* **One migration, and it moves no data and emits no SQL.** 5.2's
  `ManyToManyField.deconstruct()` emits `through_fields`, which 5.1's did not, so the
  autodetector saw the recorded state of `User.roles` as incomplete. `0005_alter_user_roles`
  records what the model has always declared. `alter_field` short-circuits at *"Both sides have
  through models; this is a no-op"*, so nothing reaches the database. Generated with
  `makemigrations`, never hand-written.
* **No new dependency and no model change.**

### 3.5 The correction this milestone needed, and the gap that hid it

**Raising Django's floor did not raise `sqlparse`.** Django 5.2.17 requires only
`sqlparse>=0.3.1`, so `uv lock` kept the already-locked 0.5.5 — correct behaviour and minimal
churn — and **five advisories stayed in the lock** after `make verify` reported VERIFIED.

Three things had to line up for that to reach a green gate:

1. The remediation was inferred from a *feasibility* resolution that resolved every package to
   its newest compatible version. The lock does not do that, and nobody re-audited the lock.
2. **`make verify` does not run the dependency audit.** It is `make audit` and a CI step, so
   the eight stages — *the only authority* (N-12) — have no view of the requirement this
   milestone exists to satisfy.
3. Three documents asserted the fix, which made the claim look checked.

Fixed with `[tool.uv] constraint-dependencies = ["sqlparse>=0.6.0"]`: a **constraint**, not a
dependency, because nothing here imports sqlparse and `[project.dependencies]` is governed —
*"adding one without an ADR is a review failure"*.

**And the class is closed, not just the instance.**
`test_the_lock_contains_the_versions_the_security_review_claims` parses the floors out of §3.1
above and asserts `uv.lock` actually contains them. It runs inside `make verify`, so a
remediation this document claims and the lock does not hold now fails the gate. It is **not** a
substitute for `pip-audit` — a new advisory against a correctly locked version still needs the
scanner — but the specific failure that happened here cannot happen silently again.

**The lock contract shipped with the same defect it was written to prevent**, and that is worth
recording rather than tidying away: it read a repository file without adding it to the mount
list, so its first authoritative run said `FileNotFoundError: /app/uv.lock`. Three suites in
this milestone have now made that mistake. The precondition test is the cheap guard, and it
only works if the list is updated in the same change as the reader — which is precisely what
`docker/compose.dev.yml`'s own comment warns about.

### 3.6 `make audit` had to be runnable at all

The audit reported clean and then **did not run**. `make verify` ends with `$(DC) down -v`;
`make audit` used `$(TOOLS)`, which is `exec` into a *running* container. So the only natural
sequence — verify, then audit — died with `service "app" is not running`, and
`Makefile:191: audit Error 1` reads like a Docker problem rather than a sequencing one.

**A security gate that did not run is indistinguishable from one that passed**, unless somebody
reads the output carefully. That is the same failure mode as `|| true`, arrived at from a
different direction.

Fixed with the repository's existing one-shot pattern — `make lock` and `FLUTTER_RUN` both use
`docker run --rm` for work that needs an image but not a session:

```make
AUDIT := $(DC) run --rm --no-deps -T --entrypoint pip-audit app
audit: .env
	$(AUDIT) --strict $(AUDIT_IGNORES)
```

**`--no-deps` alone was not enough, and the second attempt proved it.** It stops Postgres being
*started*; it does not stop the image's `ENTRYPOINT` — `docker/entrypoint.sh` — from *waiting*
for it. The run blocked for sixty seconds on `waiting for database...` and exited with
`database unreachable after 60s`, having never reached `pip-audit`. Two independent routes to
the same dependency, and only one of them was closed.

Overriding the entrypoint runs `pip-audit` as PID 1: no database wait, no migrations, no
application startup. `.env` is the prerequisite `up` already declares, so a clean checkout gets
a one-line diagnosis instead of a compose error.

**The environment is still the built one** — the override replaces the *startup procedure*, not
the image, which installs from `uv.lock` with `uv sync --frozen`. `make verify` teardown is
unchanged, and `-w`/`PYTHONPATH` are dropped because pip-audit reads the interpreter's own
environment and never imports the application.

**Three contracts hold it**, and each was proved able to fail:

| Test | Fails when |
| --- | --- |
| `test_the_audit_target_does_not_require_a_running_stack` | the recipe execs, drops `--no-deps` or `--entrypoint` (the two routes back to a database dependency), loses `--strict`, gains `\|\| true`, or stops running `pip-audit` |
| `test_the_local_audit_matches_the_ci_audit` | `make audit` and CI ignore different identifiers |
| `test_that_the_make_expander_actually_expands` | the expander stops expanding, which would make the first test vacuous |

> **The first draft of the first contract could not fail, twice.** It searched the raw recipe
> for `exec` — but `$(TOOLS)` is a variable reference, so the literal lives in the *definition*
> and reverting the command passed. Expanding Make variables fixed that, and then `--strict`
> was still undetectable because the recipe's own `@echo` banner names the flag: the contract
> matched the **description** of the command instead of the command. Echo lines are now
> dropped. Both are recorded because both are the same error — asserting against the text
> rather than against the thing the text describes.

---

> **Point 2 is recorded and deliberately not fixed.** Promoting `make audit` to a ninth stage
> would make every build depend on a network call to an advisory database, and a gate that
> fails because PyPI is slow is not an authority either. The trade is real and belongs to
> whoever revisits `00` §19.2 — not to a milestone closing itself.

---

## 4. What this review does not cover

Named so that no reader mistakes its scope.

- **No penetration test.** `02` §21.4 asks for none, and inventing one is not this milestone's
  to do.
- **Dependency remediation is done** (§3), with one exemption. What is *not* covered is a
  standing upgrade cadence: NFR-SEC-005 asks for scanning, not for a schedule, and nothing
  here commits to one.
- **A pre-existing setting defect, found while scanning for Django 5.2 removals and
  deliberately not fixed here.** `config/settings/base.py` sets `STATICFILES_STORAGE`, which
  Django removed from `global_settings` **before 5.1.15** — so it is already inert, on the
  version in production today, and the upgrade neither causes nor worsens it. The practical
  effect is that WhiteNoise's `CompressedManifestStaticFilesStorage` is **not** in use and
  static assets are unhashed. It needs `STORAGES["staticfiles"]`, it changes production
  static-file behaviour, and it is unrelated to any CVE — **its own change, its own verify
  run.** Recorded rather than folded in.
- **Mobile beyond NFR-SEC-008.** `02A` §9.3's decompilation assumption is held by
  `test_mobile_boundary.py`'s P-9 contracts (no secret, no internal surface, no high-entropy
  literal in the binary), which run inside `make verify` and are unchanged by this review.
- **The restore rehearsal**, which is the gate's other half. It was run and recorded on
  2026-09-07 — `docs/runbooks/restore-from-backup.md`'s log carries the row. **B-3 is
  passed**, by a separate observed run rather than by anything in this review.

---

## 5. Gate status

| `00` §19.2, M10 → M11 | State |
| --- | :-: |
| Security review complete | **YES** — 11/11 evidenced; NFR-SEC-009 met at M10.5 with one recorded, time-bound exemption (§3.3) |
| Restore rehearsed and recorded (B-3) | **YES** — rehearsed 2026-09-07, PASS in 8s, recorded with date, duration and operator |

**Both halves are now evidenced.** B-1 is the reason B-3 could not be waived — *"a backup
that has never been restored does not count as a backup"* — and the rehearsal earned its row
the hard way: it failed twice before it passed, on a missing `--env-file` and on a recipe
that printed `PASS` after a failed restore. The log in
`docs/runbooks/restore-from-backup.md` records the run someone watched.
