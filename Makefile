# The only developer interface (FD-07). If a command is not here, it is not a command.
.DEFAULT_GOAL := help
SHELL := /bin/bash
DC     := docker compose -f docker/compose.yml -f docker/compose.dev.yml --env-file .env
DCPROD := docker compose -f docker/compose.yml -f docker/compose.prod.yml --env-file .env
# manage.py lives in backend/ -> that is the cwd for Django commands.
RUN    := $(DC) exec -T app
# Quality tools must run from the PROJECT ROOT so that the command is byte-identical
# to the one CI runs (FD-07). PYTHONPATH lets import-linter resolve the app packages.
TOOLS  := $(DC) exec -T -w /app -e PYTHONPATH=/app/backend app
# Locking is not a runtime activity: it needs the manifest and a network, not the
# application, its database or its virtualenv. So it runs in a throwaway uv container
# against the working tree — which is why `uv` is absent from the app image and `/app`
# does not need to be bind-mounted (TD-21 §1.4).
#
# **UV_VERSION must match the `COPY --from=ghcr.io/astral-sh/uv:...` in docker/Dockerfile.**
# The resolver that writes the lock and the one that reads it have to agree.
UV_VERSION    := 0.4.27
UV_LOCK_IMAGE := ghcr.io/astral-sh/uv:$(UV_VERSION)-python3.12-bookworm

# The second toolchain (M8 task 1). TD-21's reasoning applies unchanged: a version range
# is not a pin, and the resolver that writes the lock must be the one that reads it.
#
# **Read from the file, never restated here.** `.flutter-version` is what a developer's
# fvm/asdf reads and this is what the container uses — two consumers of one fact, which is
# the shape that drifts. The first draft hard-coded it here and added a test that the two
# agreed; deriving it deletes the class instead of policing it. A test now asserts only
# that no literal creeps back in.
FLUTTER_VERSION := $(shell cat mobile/.flutter-version 2>/dev/null)
# Built here, not pulled. `ghcr.io/cirruslabs/flutter` stopped publishing on 2026-05-01 —
# before Flutter 3.44 existed — so no tag for the frozen version was ever cut. See the
# header of docker/flutter.Dockerfile.
FLUTTER_IMAGE := districore/flutter:$(FLUTTER_VERSION)
# Flutter runs in a throwaway container against the working tree — it needs the sources and
# a network, not the application or its database. Same shape as `make lock`, including
# `--user`, so `pubspec.lock` is written owned by the developer rather than by root.
FLUTTER_RUN := docker run --rm \
	--user "$$(id -u):$$(id -g)" \
	-e HOME=/tmp -e PUB_CACHE=/tmp/pub-cache \
	-v "$(CURDIR)/mobile":/w -w /w \
	$(FLUTTER_IMAGE)
# **Any command that needs packages must run in the SAME container as its `pub get`.**
#
# `PUB_CACHE` is /tmp inside a `--rm` container, but `.dart_tool/package_config.json` — the
# map from package name to source — is written into the *mounted* tree and records absolute
# paths into that cache. So a second `docker run` starts with an empty /tmp and inherits a
# package map pointing at files that no longer exist: `pub get` says "Got dependencies!"
# and the next container reports every import as `uri_does_not_exist`.
#
# Chained in one container rather than sharing a named volume, deliberately: a persistent
# cache is mutable state outside `pubspec.lock`, which is the thing TD-21 exists to remove.
# The cost is re-fetching ~32 small pure-Dart packages per run (~10s); the SDK itself is
# already in the image.
FLUTTER_SH := $(FLUTTER_RUN) sh -c
# **`flutter analyze` is not `dart analyze`.** `dart analyze` fails on errors and warnings
# and lets infos through; the flutter tool turns `--fatal-infos` ON by default, so a single
# `prefer_const_constructors` suggestion exits 1 and the run never reaches `flutter test`.
#
# The gate we want: **errors fail, warnings and infos do not.** Strictness is chosen per
# rule in `mobile/analysis_options.yaml` under `errors:` — where `unused_import` is already
# promoted — rather than by a blanket policy over every lint `flutter_lints` ships. A
# blanket policy is the kind that gets switched off wholesale the first time it is noisy,
# and this project has watched an advisory gate rot for six milestones once already (TD-2).
#
# Errors are always fatal; there is no flag to soften them, which is the point.
FLUTTER_ANALYZE_SEVERITY := --no-fatal-infos --no-fatal-warnings
# **The API base URL has no application default** (M8 task 4 M4). `00` §9's rule — *"secrets
# and production endpoints have no default and must fail"* — applied to the second
# toolchain: `AppConfig.fromEnvironment()` throws before `runApp` when this define is absent,
# so an unconfigured build cannot reach a device pointing at a plausible wrong host.
#
# `api.test` is a **verification-only** value and lives here, in the gate, precisely so that
# it cannot become a fallback in `lib/`. It is not resolvable and every request through it
# fails loudly, which is the property wanted: if it ever ships, it is obvious immediately.
# The production hostname does not exist yet — `00` §6 A-04 buys the domain before M11 — and
# is supplied by the release build, not by this file.
#
# `flutter analyze` does not need it: nothing is evaluated at analysis time.
MOBILE_DART_DEFINES := --dart-define=DISTRICORE_API_BASE_URL=https://api.test

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- lifecycle --------------------------------------------------------------
.PHONY: brief
brief: ## Generate the session bootstrap (ADR-0005 §5.2). Paste into a new AI session.
	@./scripts/brief.sh

.PHONY: up
up: .env ## Build and start the dev stack
	$(DC) up -d --build --wait
	@echo "  web    http://localhost:8000/"
	@echo "  health http://localhost:8000/healthz"

.PHONY: down
down: ## Stop the stack (keeps data)
	$(DC) down

.PHONY: clean
clean: ## Stop and DELETE all data volumes
	$(DC) down -v

.PHONY: rebuild
rebuild: ## Rebuild images from scratch
	$(DC) build --no-cache

.PHONY: logs
logs: ## Tail application logs
	$(DC) logs -f app

.env:
	@echo "ERROR: .env missing. Run: cp .env.example .env" && exit 1

# --- development ------------------------------------------------------------
.PHONY: shell
shell: ## Django shell inside the container
	$(DC) exec app python manage.py shell

.PHONY: bash
bash: ## Shell inside the app container
	$(DC) exec app bash

.PHONY: dbshell
dbshell: ## psql inside the database container
	$(DC) exec db psql -U $${POSTGRES_USER:-districore} -d $${POSTGRES_DB:-districore}

.PHONY: migrate
migrate: ## Apply migrations
	$(RUN) python manage.py migrate

.PHONY: makemigrations
makemigrations: ## Generate migrations
	$(DC) exec app python manage.py makemigrations

.PHONY: lock
lock: ## Regenerate uv.lock. Commit the result — the build now requires it (TD-21)
	docker run --rm \
		--user "$$(id -u):$$(id -g)" \
		-e UV_CACHE_DIR=/tmp/uv-cache \
		-e UV_PYTHON_DOWNLOADS=never \
		-v "$(CURDIR)":/w -w /w \
		$(UV_LOCK_IMAGE) uv lock
	@echo ""
	@echo "  uv.lock regenerated — COMMIT IT. Stage 1 of \`make verify\` now fails without it."

.PHONY: superuser
superuser: ## Create a login. Does NOT grant a role — run `make owner` next
	$(DC) exec app python manage.py createsuperuser
	@echo ""
	@echo "  A login is not an authorisation. createsuperuser writes app_user only;"
	@echo "  the admin needs an OWNER role (FR-IAM-005). Grant it with:"
	@echo ""
	@echo "      make owner PHONE=<the number you just used>"
	@echo ""

.PHONY: owner
owner: ## Grant OWNER (FR-IAM-014). Creates the user if absent. PHONE=... [NAME=...] [REASON=...]
	@test -n "$(PHONE)" || { echo "PHONE is required, e.g. make owner PHONE=7903324153"; exit 1; }
	$(DC) exec app python manage.py bootstrap_owner \
		--phone "$(PHONE)" --full-name "$(NAME)" --reason "$(REASON)"

# --- quality ----------------------------------------------------------------
.PHONY: lint
lint: ## ruff check
	$(TOOLS) ruff check .

.PHONY: format
format: ## ruff format
	$(TOOLS) ruff format .

.PHONY: typecheck
typecheck: ## mypy
	$(TOOLS) mypy backend/

.PHONY: contracts
contracts: ## import-linter — enforces N-01 and N-02
	$(TOOLS) lint-imports

.PHONY: test
test: ## Full test suite with coverage gate
	$(TOOLS) pytest --cov --cov-report=term-missing

.PHONY: test-adversarial
test-adversarial: ## Only the adversarial suite (02 §25.2)
	$(TOOLS) pytest -m adversarial -v

# --- NFR-SEC-009: the dependency audit ---------------------------------------
#
# **`run --rm --no-deps`, not `exec` — and that is the whole fix.** Every other quality
# target uses `$(TOOLS)`, which is `exec` into a *running* stack, because they are used
# during a `make up` session. `audit` is not: the natural moment to run it is straight after
# `make verify`, and verify's last act is `$(DC) down -v`. So `make verify && make audit`
# could never work — it failed with `service "app" is not running`, which reads like a
# Docker problem and is really a sequencing one.
#
# A one-shot container is the repository's existing answer for work that needs an image but
# not a session: `make lock` and `FLUTTER_RUN` both use `docker run --rm` for exactly this.
#
#   --no-deps    pip-audit reads a virtualenv, not a database. Starting Postgres to scan a
#                lockfile would make the audit fail when the database is unhealthy.
#   --entrypoint **the second half of the same point, and it is not optional.** The image's
#                ENTRYPOINT is `docker/entrypoint.sh`, which blocks on `waiting for
#                database...` for 60s and then applies migrations before it execs anything.
#                `--no-deps` stops Postgres being *started*; it does not stop the entrypoint
#                *waiting* for it, so the audit died with `database unreachable after 60s`
#                having never run. Overriding the entrypoint runs `pip-audit` as PID 1.
#   .env         the same prerequisite `up` declares, so a clean checkout gets the one-line
#                diagnosis instead of a compose error.
#
# **The environment is still the built one**, which is what makes this evidence rather than a
# convenience: the override replaces the *startup procedure*, not the image. It installs from
# `uv.lock` with `uv sync --frozen`, so `pip-audit` with no target audits exactly what the
# build installs (NFR-SEC-009's *"dependencies"*).
#
# No `-w` and no `PYTHONPATH`: unlike ruff and import-linter, pip-audit reads the interpreter's
# own environment and neither needs a working directory nor imports the application.
AUDIT := $(DC) run --rm --no-deps -T --entrypoint pip-audit app

# **One exemption, and it is spelled here and in `.github/workflows/ci.yml`.** Two copies of
# one fact is the shape that drifts, so `test_the_local_audit_matches_the_ci_audit` asserts
# they are identical and `test_every_ignored_vulnerability_is_a_recorded_decision` asserts
# both are documented. CVE-2026-49452 / PYSEC-2026-3412 / GHSA-jhhc-3hcp-qhm5 are three
# identifiers for one WeasyPrint issue with no published fix — docs/M10_Security_Review.md §3.3.
AUDIT_IGNORES := --ignore-vuln CVE-2026-49452 \
                 --ignore-vuln PYSEC-2026-3412 \
                 --ignore-vuln GHSA-jhhc-3hcp-qhm5

.PHONY: audit
audit: .env ## NFR-SEC-009 dependency scan — same command CI runs
	@echo "==> pip-audit --strict, against the image built from uv.lock"
	@echo "    exempted, and NOT hidden: CVE-2026-49452 / PYSEC-2026-3412 /"
	@echo "    GHSA-jhhc-3hcp-qhm5 — one WeasyPrint CSS-injection issue with no published"
	@echo "    fix in any version. Unreachable while presentational hints stay disabled."
	@echo "    Decision M10.5-1, review by 2026-12-07 — docs/M10_Security_Review.md §3.3."
	@echo ""
	$(AUDIT) --strict $(AUDIT_IGNORES)

# --- performance and scalability evidence (NFR-PER-001/003/005, NFR-SCA-001/003) ---
#
# **NOT part of `make verify`, and that is a decision rather than an omission.** The DR-8
# dataset takes minutes to build and hundreds of thousands of rows to hold; an 8-stage gate
# that every commit waits on has no place for it. NFR-PER-005 calls itself a *release* gate,
# not a commit gate.
#
# It is a target rather than a remembered command for the same reason `restore-rehearsal`
# is: a release gate you have to reconstruct a three-line `docker compose exec` for is a
# release gate that gets skipped.
#
#   make perf                      # DR-8 envelope — the profile the requirements need
#   make perf PROFILE=m7           # the M7 shape, for comparison with 2026-08-09 only
#   make perf STAGE=reports        # one stage; the gate needs all of them
#
# Exits non-zero on any breach. **Do not raise a threshold to make it green** — the fix is
# an index or a domain optimisation recorded with the measurement that justified it (M7 §7).
# **The corpus never touches the development database.** ~750,000 synthetic financial
# documents, written without their services, undoable only by dropping the database — run
# against `districore` that would end any demonstration from real data, and would move the
# source counts a B-3 restore rehearsal reads.
#
# **A separate database inside the same PostgreSQL container**, which is the convention
# `ops/restore.sh` already uses for `districore_restore_test`. Same server, same `db_data`
# volume, same image, same Django, same migrations, same selectors, same harness — one
# different `DATABASE_URL` and nothing else. No second service, no second compose file, no
# second application configuration to drift out of step with the first.
PERF_DB   := districore_perf
#: `psql` inside `db`, as the superuser the container was initialised with. `POSTGRES_USER`
#: is read from the container's own environment rather than restated here, the way
#: `ops/restore.sh` reads it — one credential, one source.
PERF_PSQL := $(DC) exec -T db sh -c
#: The app container, with `DATABASE_URL`'s database name swapped for the disposable one.
#: `${DATABASE_URL%/*}` drops the trailing `/<database>`; everything else — host, port,
#: user, password, options — is inherited from `.env` exactly as the application uses it.
PERF_URL  := DATABASE_URL="$${DATABASE_URL%/*}/$(PERF_DB)"

.PHONY: perf-db
perf-db: .env ## Drop, recreate and migrate the disposable performance database
	@case "$(PERF_DB)" in districore|districore_prod) \
	  echo "REFUSED: '$(PERF_DB)' is a working database. The performance corpus is"; \
	  echo "         written directly, bypasses every service, and cannot be undone."; \
	  exit 2;; esac
	@echo "==> recreating $(PERF_DB) (disposable; the dev database is not touched)"
	$(PERF_PSQL) 'psql -U "$$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS $(PERF_DB);"'
	$(PERF_PSQL) 'psql -U "$$POSTGRES_USER" -d postgres -c "CREATE DATABASE $(PERF_DB);"'
	@echo "==> migrating $(PERF_DB) — the same migrations the application runs"
	$(DC) exec -T app sh -c '$(PERF_URL) python manage.py migrate --noinput'
	@echo "==> seeding an OWNER through the repository's own FR-IAM-014 path"
	$(DC) exec -T app sh -c '$(PERF_URL) python manage.py bootstrap_owner \
	  --phone 9000000000 --full-name "Perf Harness" --noinput \
	  --reason "NFR-PER/SCA measurement fixture"'

.PHONY: perf-clean
perf-clean: .env ## Drop the disposable performance database
	@case "$(PERF_DB)" in districore|districore_prod) \
	  echo "REFUSED: '$(PERF_DB)' is a working database."; exit 2;; esac
	$(PERF_PSQL) 'psql -U "$$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS $(PERF_DB);"'
	@echo "==> $(PERF_DB) dropped"

.PHONY: perf
perf: perf-db ## NFR-PER/SCA evidence against the DR-8 five-year dataset. Writes JSON evidence
	@echo ""
	@echo "==> performance and scalability evidence"
	@echo "    database: $(PERF_DB)  (disposable — recreated above, dev database untouched)"
	@echo "    profile : $(or $(PROFILE),dr8)   stage: $(or $(STAGE),all)"
	@echo "    This builds a five-year DR-8 dataset. Minutes, not seconds."
	@echo ""
	@# `--json -` and redirect on the HOST: `../ops` is mounted read-only so stage-7
	@# contracts can read it, so the container cannot write its own evidence file.
	$(DC) exec -T -w /app -e PYTHONPATH=/app/backend app sh -c \
	  '$(PERF_URL) python ops/report_performance.py \
	    --profile "$(or $(PROFILE),dr8)" --stage "$(or $(STAGE),all)" --json -' \
	  > ops/perf-latest.json
	@echo ""
	@echo "==> raw evidence: ops/perf-latest.json"
	@echo "    \`make perf-clean\` drops $(PERF_DB) when you are done with it."

# --- mobile (M8) ------------------------------------------------------------
# NOT part of `make verify`, and that is a recorded decision, not an omission:
#   * The gate's 8 stages are Python. Adding a ~1 GB Flutter image to a no-cache build
#     would cost every backend change minutes for a toolchain it does not touch.
#   * The M8 contracts that MUST be blocking — layering, no-secrets, P-3, P-6 — are
#     enforced from `backend/tests/adversarial/test_mobile_boundary.py`, which reads the
#     Dart sources and runs inside stage 7. They are structural, so they need a parser,
#     not a compiler.
#   * What is NOT yet gated is "does the Dart compile". Promoting `mobile-verify` to
#     stage 9 is the right end state and is recorded as TD-37 — deliberately not done
#     blind, because an untested stage in the only authority is worse than none.
.PHONY: mobile-pin
mobile-pin: ## Fail unless the Flutter pin is readable — every mobile target depends on it
	@test -n "$(FLUTTER_VERSION)" || { \
		echo "mobile/.flutter-version is missing or empty. It is the pin; refusing to guess."; \
		exit 1; }
	@echo "  Flutter $(FLUTTER_VERSION)"

.PHONY: mobile-image
mobile-image: mobile-pin ## Build the pinned Flutter toolchain image (cached after the first run)
	docker build \
		-f docker/flutter.Dockerfile \
		--build-arg FLUTTER_VERSION=$(FLUTTER_VERSION) \
		-t $(FLUTTER_IMAGE) \
		docker/

.PHONY: mobile-lock
mobile-lock: mobile-image ## Resolve mobile/pubspec.lock in the pinned Flutter container
	$(FLUTTER_RUN) flutter pub get
	@echo "  pubspec.lock written. Commit it — it is the pin (TD-21)."

.PHONY: mobile-codegen
mobile-codegen: mobile-image ## Drift/build_runner code generation (task 3). Commit the .g.dart output
	$(FLUTTER_SH) 'flutter pub get --enforce-lockfile && dart run build_runner build --delete-conflicting-outputs'

.PHONY: mobile-analyze
mobile-analyze: mobile-image ## Dart static analysis
	$(FLUTTER_SH) 'flutter pub get --enforce-lockfile && flutter analyze $(FLUTTER_ANALYZE_SEVERITY)'

.PHONY: mobile-test
mobile-test: mobile-image ## Dart unit tests (domain — no device)
	$(FLUTTER_SH) 'flutter pub get --enforce-lockfile && flutter test $(MOBILE_DART_DEFINES)'

.PHONY: mobile-verify
mobile-verify: mobile-image ## Mobile gate: frozen install, analyze, test
	@test -f mobile/pubspec.lock || { \
		echo "mobile/pubspec.lock is missing. Run 'make mobile-lock' and commit it."; \
		exit 1; }
	$(FLUTTER_SH) 'flutter pub get --enforce-lockfile && flutter analyze $(FLUTTER_ANALYZE_SEVERITY) && flutter test $(MOBILE_DART_DEFINES)'

# --- THE M8 -> M9 DEVICE GATE -----------------------------------------------
#
# `00` §19.2: "Outbox survives kill, restart and storage exhaustion."
#
# **These targets run on the HOST, not in the pinned container, and that is a deviation
# worth naming rather than hiding.** `docker/flutter.Dockerfile` carries no Android SDK, no
# JDK and no adb — `grep -i android` returns nothing — so the container that every other
# mobile target uses cannot reach a device at all. N-12 says `make verify` is the only
# authority; this gate cannot live inside it, and its result is therefore a **dated
# artefact** (`docs/M8_Verification_Report.md`), not a reproducible stage. That is the same
# class of gap as TD-37 and it is stated here so nobody discovers it during a release.
#
# Restart is NOT here. `M8_Design_Review` §14.11 assigns it to task 3's hermetic gate, and
# `mobile/test/outbox_test.dart` group "durability across reopen" already proves it inside
# `make mobile-verify`. Duplicating it on a device would add a slower copy of a passing test.
ANDROID_APP_ID := com.districore.app.dev

# **Which device the gates drive, and why it must be named.**
#
# `flutter drive` with no `-d` and more than one visible device does not fail — it **asks**,
# and then waits. On Windows that set routinely includes the Windows desktop, Chrome and
# Edge alongside the emulator, so the gate stops on a prompt with no further output and
# looks exactly like a hang. Measured 2026-08-30: a host `flutter drive` sat for thirty
# minutes producing nothing. A gate that can block on a question is not a gate.
#
# **The only `?=` in this file, deliberately.** Every other variable is `:=` because it is a
# property of the project. This one is a property of the *machine*, so an environment
# variable or a command-line override must win:
#
#     make mobile-device-kill MOBILE_DEVICE_ID=emulator-5556
#
# The scope the gates are proven against is unchanged and is **Pixel 8a API 34,
# android-x64, Google APIs** (D-M9-8 §6, TD-45). Pointing this at another device does not
# widen that scope; a report citing such a run must say which device it used.
MOBILE_DEVICE_ID ?= emulator-5554

# **The WSL <-> Windows boundary, and why the gates cross it rather than avoid it.**
#
# `make` runs in WSL. The emulator, the Android SDK and the adb **server** are Windows-side,
# and WSL2 is a separate VM whose `localhost` is not Windows' — so a Linux `adb` installed in
# WSL would start its *own* server, see zero devices, and fail at the same guard with the
# same message, having solved nothing. The fix is not a second adb; it is to invoke the
# Windows one through WSL interop, which talks to the Windows server natively.
#
# Every adb call in the three device gates uses **device-side paths only** (`adb shell
# dd|rm|df|pm`, `adb devices`), so no host path crosses the boundary and no WSL -> Windows
# path translation is needed. `emulator-trust-ca` is deliberately NOT converted: its
# `adb push build/...` passes a *host* path, which is a different problem, and it is a
# development helper rather than a gate.
#
# **One canonical SDK, and everything derived from it.** Restating `platform-tools` in two
# places is the drift shape `FLUTTER_VERSION` already refuses by reading `.flutter-version`
# instead of naming a number.
#
# **Auto-detection is deliberately NOT used.** `$(shell command -v adb)` would silently
# prefer a Linux adb on a machine that has one — selecting the binary that *cannot see the
# emulator*, which is precisely the failure this exists to prevent, minus the clear error.
MOBILE_ANDROID_SDK ?= /mnt/e/Android/Sdk
ADB                ?= $(MOBILE_ANDROID_SDK)/platform-tools/adb.exe

# **`FLUTTER_HOST`, not `FLUTTER`, and the name is load-bearing.** Four variables above are
# already about Flutter *in the pinned container* — `FLUTTER_SH`, `FLUTTER_RUN`,
# `FLUTTER_IMAGE`, `FLUTTER_VERSION`. A bare `FLUTTER` sitting among them meaning the
# opposite thing is a misreading waiting to happen. `ADB` needs no suffix: the container has
# no adb at all, so there is nothing to disambiguate it from.
#
# **`adb.exe` needs no wrapper; `flutter.bat` does, and that asymmetry is the whole point.**
# `adb.exe` is a PE binary, so WSL's binfmt_misc interop hands it to Windows and it runs —
# which is why `$(ADB)` above is a bare path and works. A `.bat` is not a binary: there is
# nothing for binfmt to recognise, so the kernel falls through to the shell and **bash reads
# the batch file as a shell script**. Measured 2026-08-31 against the path below:
#
#     @ECHO: command not found          <- the batch @ECHO OFF directive
#     $'\r': command not found          <- every CRLF line ending
#     syntax error near unexpected token <- FOR %%i IN (...)
#
# Flutter ships no `flutter.exe` on Windows, only `flutter.bat` beside a `flutter` bash
# script that is meant for a POSIX Flutter install. So the batch file must be handed to the
# Windows command interpreter, and this is not optional or workstation-specific.
FLUTTER_HOST ?= /mnt/d/chromeDownload/flutter_windows_3.44.7-stable/flutter/bin/flutter.bat

# The runner. `FLUTTER_RUN` is the same shape one layer down — a command *prefix* that says
# where Flutter executes — so the host equivalent is named for it rather than inventing a
# convention. `FLUTTER_HOST` stays the single overridable fact; this is derived, exactly as
# `ADB` is derived from `MOBILE_ANDROID_SDK`.
#
# **A script, not an inline `cmd.exe /D /C "$$(wslpath -w …)"`.** That inline form was tried
# first and a gate run reached cmd.exe as
#
#     D:\chromeDownload\flutter_windows_3.44.7-stableflutter\bin\flutter.bat
#
# — the separator before `flutter` gone, which cmd cannot resolve and which presented as a
# thirty-minute hang rather than an error. The make expansion was then reproduced under
# instrumented stubs and proved byte-exact, so the loss is downstream of bash, in interop's
# command-line construction or cmd's parsing. **A Make variable cannot verify its own
# expansion**; that is the whole reason this moved to a script. `scripts/win-flutter.sh`
# checks the translation component-by-component, refuses a path carrying a non-printing
# character, and then asks cmd.exe itself whether the file exists at the path it was handed
# — the only check positioned to see a corruption that happens on the Windows side.
#
# `FLUTTER_HOST` crosses as an environment variable rather than an argument so that the one
# string this is all about is never re-parsed by a shell. `$(CURDIR)` because the recipes
# `cd mobile` first, and cmd.exe must inherit that directory to find the Flutter project.
FLUTTER_HOST_RUN = FLUTTER_HOST='$(FLUTTER_HOST)' $(CURDIR)/scripts/win-flutter.sh

# The emulator's alias for the host loopback (`00` §7.3), and the certificate identity
# `docker/compose.dev.yml` gives Caddy. Stated once; the two must not drift apart.
DEV_API_HOST := 10.0.2.2
DEV_API_BASE_URL := https://$(DEV_API_HOST)
DEV_CA := build/districore-dev-ca.crt

.PHONY: dev-ca
dev-ca: ## Extract Caddy's development root CA from the running dev stack
	@mkdir -p build
	$(DC) exec -T caddy cat /data/caddy/pki/authorities/local/root.crt > $(DEV_CA)
	@test -s $(DEV_CA) || { \
		echo "The CA is empty. Is the dev stack up? Caddy mints it on first start:"; \
		echo "  make up  &&  sleep 5  &&  make dev-ca"; exit 1; }
	@echo "  wrote $(DEV_CA)"
	@openssl x509 -in $(DEV_CA) -noout -subject -dates

.PHONY: dev-ca-b64
dev-ca-b64: dev-ca ## Print the --dart-define for the development trust anchor
	@echo
	@echo "  Dio verifies through dart:io's HttpClient, which reads BoringSSL's roots inside"
	@echo "  the Dart VM — not Android's user CA store and not network_security_config.xml."
	@echo "  The certificate therefore reaches the app through the build, like the base URL."
	@echo
	@echo "--dart-define=DISTRICORE_DEV_CA_B64=$$(base64 -w0 $(DEV_CA))"

.PHONY: emulator-trust-ca
emulator-trust-ca: dev-ca ## Install that CA into the RUNNING emulator's user trust store
	@adb devices | grep -qw device || { echo "No emulator. Start the AVD first."; exit 1; }
	@echo "==> hashing (Android names CA files by subject hash)"
	$(eval CA_HASH := $(shell openssl x509 -inform PEM -subject_hash_old -in $(DEV_CA) | head -1))
	@test -n "$(CA_HASH)" || { echo "could not hash $(DEV_CA)"; exit 1; }
	@echo "==> pushing as $(CA_HASH).0"
	@cp $(DEV_CA) build/$(CA_HASH).0
	@if adb root >/dev/null 2>&1 && adb shell 'mkdir -p /data/misc/user/0/cacerts-added' 2>/dev/null; then \
		adb push build/$(CA_HASH).0 /data/misc/user/0/cacerts-added/$(CA_HASH).0 && \
		adb shell chmod 644 /data/misc/user/0/cacerts-added/$(CA_HASH).0 && \
		echo "  installed to the user trust store. Reboot the AVD: adb reboot"; \
	else \
		adb push $(DEV_CA) /sdcard/Download/districore-dev-ca.crt && \
		echo "  adb root is unavailable on this image (Google Play images disallow it)."; \
		echo "  FALLBACK, once: on the emulator open"; \
		echo "    Settings > Security > More security settings > Encryption & credentials"; \
		echo "    > Install a certificate > CA certificate > Install anyway"; \
		echo "    > pick Download/districore-dev-ca.crt"; \
	fi
	@echo
	@echo "  The debug build already opts in to user CAs — see"
	@echo "  mobile/android/app/src/debug/res/xml/network_security_config.xml."
	@echo "  Then:  cd mobile && flutter run --dart-define=DISTRICORE_API_BASE_URL=$(DEV_API_BASE_URL)"

.PHONY: mobile-android-scaffold
mobile-android-scaffold: mobile-image ## One-time: generate mobile/android/ with the PINNED Flutter
	@test ! -d mobile/android || { \
		echo "mobile/android/ already exists. Delete it deliberately before regenerating."; \
		exit 1; }
	$(FLUTTER_SH) 'flutter create --platforms=android --org com.districore.app .'
	@echo
	@echo "  Generated with the pinned SDK, so Gradle/AGP/Kotlin match .flutter-version."
	@echo
	@echo "  THREE EDITS BY HAND — stated, not scripted, because a generated tree should be"
	@echo "  reviewed rather than patched blind. The file is build.gradle or build.gradle.kts"
	@echo "  depending on what this SDK emits; the values are the same either way."
	@echo
	@echo "  1. android/app/build.gradle[.kts] — namespace and applicationId"
	@echo "         namespace     = \"com.districore.app\""
	@echo "         applicationId = \"com.districore.app\"   # intended production identifier"
	@echo
	@echo "  2. android/app/build.gradle[.kts] — buildTypes"
	@echo "         debug   { applicationIdSuffix = \".dev\" }   # installs as $(ANDROID_APP_ID)"
	@echo "         release { /* NO signingConfig */ }"
	@echo
	@echo "  3. MOVE the generated activity so its package matches the namespace:"
	@echo "         from android/app/src/main/kotlin/com/districore/app/districore/MainActivity.kt"
	@echo "         to   android/app/src/main/kotlin/com/districore/app/MainActivity.kt"
	@echo "         and change its first line to: package com.districore.app"
	@echo "     WHY: --org appends the pubspec name, so the generated package is"
	@echo "     com.districore.app.districore. Setting namespace WITHOUT moving the activity"
	@echo "     makes the manifest's relative .MainActivity resolve to a class that does not"
	@echo "     exist, and the app dies at launch with ClassNotFoundException — after a"
	@echo "     successful build, which is the worst place to find it."
	@echo
	@echo "  No release signingConfig. No keystore is generated here (00 §2.3, K-1)."
	@echo "  com.districore.app is a CHOSEN identifier. Nothing here reserves it externally."

# **The two phases below use `flutter drive`, not `flutter test`, and that is the whole
# premise of this gate.**
#
# `flutter test <an integration_test file>` **uninstalls its package when the run ends**,
# which deletes `/data/user/0/<id>/` and the database with it. These two phases are two
# invocations that must share app-private state: phase 2 opens the file phase 1 left behind
# mid-transaction. Under `flutter test` that teardown makes phase 2 open an empty database
# and report zero rows — **indistinguishable from the data loss this gate exists to detect,
# and therefore a false positive for its own subject.**
#
# Measured 2026-08-25: `adb shell pm list packages` finds no `districore` package after a
# run, **including after a run that passed**. `flutter drive --keep-app-running` leaves the
# install and its data in place, verified the same day.
# `mobile/test_driver/integration_test.dart` has been in the tree since M8 for exactly this
# and was never wired up — its own docstring names a `make` target that does not exist.
# **One preflight, not three.** These four checks were copied into each gate and had already
# drifted inside a single change: the encryption gate's device check lacked the `tr -d` that
# the other two carry, and said something different when it failed. A `.PHONY` prerequisite
# runs before the target's recipe and is stated once, so the next check added is added once.
#
# Every message names the variable to override, because the failure is always a property of
# the workstation and never of the repository.
.PHONY: device-gate-preflight
device-gate-preflight:
	@$(ADB) devices 2>/dev/null | tr -d "\r" | grep -qw device || { \
		echo "No device from $(ADB)"; \
		echo "make runs in WSL; the emulator and its adb server are Windows-side, so the"; \
		echo "Windows adb.exe is invoked through WSL interop. Check in order:"; \
		echo "  1. the AVD is running   2. MOBILE_ANDROID_SDK=$(MOBILE_ANDROID_SDK) exists"; \
		echo "  3. $(ADB) devices lists $(MOBILE_DEVICE_ID)"; \
		echo "Override with:  make <target> MOBILE_ANDROID_SDK=/mnt/<drive>/path/to/Sdk"; \
		exit 1; }
	@test -x "$(CURDIR)/scripts/win-flutter.sh" || { \
		echo "scripts/win-flutter.sh is missing or not executable."; \
		echo "It is the only supported way to reach Windows Flutter from WSL, and it owns"; \
		echo "every check on FLUTTER_HOST — launcher present, no space, cmd.exe reachable,"; \
		echo "and the path still intact once Windows has seen it. Restore it with:"; \
		echo "  chmod +x scripts/win-flutter.sh"; \
		exit 1; }

.PHONY: mobile-device-kill
mobile-device-kill: device-gate-preflight ## M8->M9 gate, kill. Needs a connected AVD. Host Flutter + adb.
	@echo "==> phase 1: commit five, claim three, SIGKILL"
	@echo "    Phase 1 MUST terminate abnormally. The check below is inverted, not"
	@echo "    silenced: a clean exit means the signal never landed, and that is a"
	@echo "    failure — it would leave phase 2 asserting against an orderly shutdown."
	@echo "    A death for the WRONG reason is caught by phase 2, which finds no rows."
	@echo "    The last GATE-P1 line printed says how far phase 1 got; only KILL-NOW"
	@echo "    means the signal was reached."
	@cd mobile && if $(FLUTTER_HOST_RUN) pub get --enforce-lockfile && $(FLUTTER_HOST_RUN) drive --driver=test_driver/integration_test.dart --target=integration_test/outbox_kill_test.dart --keep-app-running -d $(MOBILE_DEVICE_ID) $(MOBILE_DART_DEFINES); then \
		echo "phase 1 exited 0: SIGKILL did not land, nothing was proved"; exit 1; \
	else \
		echo "phase 1 terminated abnormally, as designed"; \
	fi
	@echo "==> phase 2: reopen and account for everything"
	cd mobile && $(FLUTTER_HOST_RUN) pub get --enforce-lockfile && $(FLUTTER_HOST_RUN) drive --driver=test_driver/integration_test.dart --target=integration_test/outbox_survives_kill_test.dart --keep-app-running -d $(MOBILE_DEVICE_ID) $(MOBILE_DART_DEFINES)

# **Both phases use `flutter drive`, for the reason stated above `mobile-device-kill`.**
#
# This gate has the same shape as that one: two invocations that must share app-private
# state. Phase B opens the database phase A left behind and asserts the rows committed
# before the disk filled are still there. Under `flutter test` the package is uninstalled
# at teardown, so phase B would open an empty database and fail with *"exhaustion
# destroyed committed work"* — a false negative that reads as the exact data loss the
# gate exists to detect. The kill gate was corrected on 2026-08-25; this one was not, and
# because it had never been run nobody saw it. **Do not put `flutter test` back.**
#
# Unlike the kill gate, both phases here are expected to SUCCEED, so neither check is
# inverted. Only the runner changed; the ballast, the phases and every assertion are
# untouched.
.PHONY: mobile-device-storage
mobile-device-storage: device-gate-preflight ## M8->M9 gate, storage exhaustion. DISPOSABLE AVD ONLY.
	@echo "==> phase A: a write under exhaustion must be refused as StorageFull"
	@echo "    The test fills the disk itself, from inside the running app, and releases it in"
	@echo "    a finally. There is no ballast to place here and no BALLAST_MB to size: an APK"
	@echo "    cannot be installed onto a full disk, and the drive step always installs."
	cd mobile && $(FLUTTER_HOST_RUN) pub get --enforce-lockfile && $(FLUTTER_HOST_RUN) drive --driver=test_driver/integration_test.dart \
		--target=integration_test/outbox_storage_full_test.dart --keep-app-running \
		-d $(MOBILE_DEVICE_ID) \
		$(MOBILE_DART_DEFINES) --dart-define=GATE_PHASE=full
	@echo "==> phase B: everything committed before the failure is still there"
	cd mobile && $(FLUTTER_HOST_RUN) pub get --enforce-lockfile && $(FLUTTER_HOST_RUN) drive --driver=test_driver/integration_test.dart \
		--target=integration_test/outbox_storage_full_test.dart --keep-app-running \
		-d $(MOBILE_DEVICE_ID) \
		$(MOBILE_DART_DEFINES) --dart-define=GATE_PHASE=drained

# **NFR-SEC-008 / FR-SYN-016 — encrypted at rest, on a device.**
#
# `02` states the verification method in three words: *"Device inspection test"*. This is it.
#
# **Two phases proving two different things, and they are NOT the same artefact.**
# `flutter test integration_test/…` does not run the APK `flutter build apk` produces — it
# compiles the app and the test into its own instrumentation APK and installs that. So phase
# A proves the *shipping* binary carries an encrypting SQLite, and phase B proves the *running*
# app writes an encrypted file. What links them is not a file, it is the build hook: both
# resolve `package:sqlite3` through the same `user_defines` in the same `pubspec.yaml`. Each
# half independently rules out the failure the other could miss, which is why both are here.
#
# **Scope: Pixel 8a API 34 emulator, android-x64.** Not arm64, not physical hardware. A report
# citing this run must say so.
#
# **Needs no dev stack, no CA, no network** — unlike every other device workflow here.
.PHONY: mobile-device-encryption
mobile-device-encryption: device-gate-preflight ## NFR-SEC-008 device gate. Pixel 8a API 34 / android-x64. Host Flutter + adb.
	@echo "==> phase A: the SHIPPING artefact carries an encrypting SQLite"
	cd mobile && $(FLUTTER_HOST_RUN) pub get --enforce-lockfile && $(FLUTTER_HOST_RUN) build apk --debug \
		--target-platform android-x64 $(MOBILE_DART_DEFINES)
	@unzip -l mobile/build/app/outputs/flutter-apk/app-debug.apk \
		| grep -q 'lib/x86_64/libsqlite3mc\.so' || { \
		echo "no libsqlite3mc.so in the APK: the build hook did not select an encrypting"; \
		echo "SQLite. Check the 'hooks:' block in mobile/pubspec.yaml."; exit 1; }
	@echo "    libsqlite3mc.so present"
	@if unzip -l mobile/build/app/outputs/flutter-apk/app-debug.apk \
		| grep -q 'lib/x86_64/libsqlite3\.so'; then \
		echo "the APK carries UPSTREAM libsqlite3.so. That library has no codec, so"; \
		echo "PRAGMA key is an unrecognised pragma and is silently ignored: the outbox"; \
		echo "would ship in cleartext. This check is inverted, not silenced."; exit 1; \
	fi
	@echo "    libsqlite3.so absent"
	@if unzip -l mobile/build/app/outputs/flutter-apk/app-debug.apk \
		| grep -q 'libsqlcipher\.so'; then \
		echo "the APK carries libsqlcipher.so. Encryption comes from the sqlite3 build hook"; \
		echo "(sqlite3mc), not from a plugin — a second cipher library in the artefact is a"; \
		echo "false signal about which one is in use, and it is exactly what made a plaintext"; \
		echo "outbox look correct for a milestone. Removed at Change 3; re-add deliberately"; \
		echo "or not at all."; exit 1; \
	fi
	@echo "    no unused cipher library"
	@echo "==> phase B: the RUNNING app proves the file on disk is encrypted"
	cd mobile && $(FLUTTER_HOST_RUN) pub get --enforce-lockfile && $(FLUTTER_HOST_RUN) test \
		integration_test/encryption_at_rest_test.dart $(MOBILE_DART_DEFINES)

# --- THE GATE ---------------------------------------------------------------
.PHONY: verify
verify: ## Docker verification — the ONLY authority (N-12, 00 §5.2)
	@echo "==> 1/8  clean build (no cache: proves dependencies are declared)"
	$(DC) build --no-cache app
	@echo "==> 2/8  start, wait for healthchecks"
	$(DC) up -d --wait
	@echo "==> 3/8  no missing migration"
	$(RUN) python manage.py makemigrations --check --dry-run
	@echo "==> 4/8  lint"
	$(TOOLS) ruff check .
	@echo "==> 5/8  import contracts (N-01, N-02)"
	$(TOOLS) lint-imports
	@echo "==> 6/8  type check (BLOCKING since TD-2/TD-18)"
	$(TOOLS) mypy backend/
	@echo "==> 7/8  tests + coverage gate"
	$(TOOLS) pytest --cov --cov-fail-under=80
	@echo "==> 8/8  health endpoint"
	@curl -fsS http://localhost:8000/healthz | head -c 400; echo
	$(DC) down -v
	@printf "PASS  %s  %s\n" "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$$(git rev-parse --short HEAD 2>/dev/null || echo nogit)" > .verify-result
	@echo ""
	@echo "  VERIFIED. This is the only result that counts (N-12)."

# --- operations -------------------------------------------------------------
.PHONY: backup
backup: ## Encrypted database dump
	./ops/backup.sh

# --- B-3: RESTORE REHEARSAL --------------------------------------------------
#
# 00 §19.2, M10 -> M11: "Restore rehearsed and recorded (B-3); security review complete."
# B-1: "A backup that has never been restored does not count as a backup."
# B-3: "Restore is tested quarterly and the result recorded, with date and duration, in
#       docs/runbooks/restore-from-backup.md"
#
# `ops/restore.sh` has existed since P0 and had no `make` target, which is most of why the
# rehearsal log is empty: `00` §5 says "every routine operation is a make target", and an
# operation you have to remember the arguments for is not routine.
#
# **This target rehearses. It never touches the live database.** `restore.sh` defaults its
# target to `districore_restore_test`, and the guard below refuses to run if a caller passes
# the production name — the one mistake in this procedure that cannot be undone.
#
# **It times the restore and prints the row to paste**, because B-3 asks for a duration and a
# rehearsal that ends in "it worked" answers half the requirement. It does NOT write the log
# itself: a recorded result must be recorded by the person who watched it.
#
#   make restore-rehearsal ARCHIVE=/srv/backups/districore-20260907T0300Z.dump.gpg
#
.PHONY: restore-rehearsal
restore-rehearsal: ## B-3: restore the latest backup into a scratch DB and time it
	@test -n "$(ARCHIVE)" || { \
	  echo "ARCHIVE is required."; \
	  echo "  make restore-rehearsal ARCHIVE=/srv/backups/districore-<stamp>.dump.gpg"; \
	  echo "  ls -t /srv/backups/districore-*.dump* | head -1   # the latest"; \
	  exit 2; }
	@test -f "$(ARCHIVE)" || { echo "not found: $(ARCHIVE)"; exit 2; }
	@case "$(TARGET_DB)" in districore|districore_prod) \
	  echo "REFUSED: '$(TARGET_DB)' is the live database. A rehearsal restores into a scratch DB."; \
	  exit 2;; esac
	@echo "==> B-3 restore rehearsal"
	@echo "    archive : $(ARCHIVE)"
	@echo "    target  : $(or $(TARGET_DB),districore_restore_test)  (scratch, never live)"
	@started=$$(date -u +%s); \
	 started_at=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	 if ./ops/restore.sh "$(ARCHIVE)" "$(or $(TARGET_DB),districore_restore_test)"; then \
	   outcome=PASS; \
	 else \
	   outcome=FAIL; \
	 fi; \
	 elapsed=$$(( $$(date -u +%s) - started )); \
	 echo ""; \
	 echo "==> restore $$outcome in $${elapsed}s"; \
	 echo ""; \
	 echo "    B-3 asks for the result to be RECORDED — a FAIL is the most valuable row"; \
	 echo "    that table will ever hold. Paste this into 'Rehearsal log' in"; \
	 echo "    docs/runbooks/restore-from-backup.md:"; \
	 echo ""; \
	 printf "    | %s | %s | %ss | %s | <your name> |\n" \
	   "$$started_at" "$$(basename '$(ARCHIVE)')" "$$elapsed" "$$outcome"; \
	 echo ""; \
	 echo "    RTO target is ~2 hours (ADR-012, FD-16)."; \
	 test "$$outcome" = PASS

.PHONY: prod-up
prod-up: ## Start the production stack (on the server)
	$(DCPROD) up -d --build --wait

# --- B1: FR-SYN-010 ACCEPTANCE ----------------------------------------------
#
# 02 FR-SYN-010: "Full sync of a typical daily volume MUST complete within 2 minutes of
# reconnection at the DR-8 envelope." 02 NFR-PER-004 names the method: "Timed sync at
# representative volume." This target IS that measurement, and it is the only evidence that
# can discharge the requirement. TD-41 shipped the retry cadence; the cadence bounds when an
# attempt starts, not when a sync completes.
#
# **The first device gate that talks to a real server.** Every earlier one is local-only:
# MOBILE_DART_DEFINES points at https://api.test, a hostname that resolves to nothing. So
# this target carries its own defines — the emulator's host alias and the dev CA — and does
# not touch that variable.
#
# Prerequisites, in order:
#   make up                 the dev stack, including the caddy TLS terminator
#   make dev-ca             extract Caddy's internal root
#   make emulator-trust-ca  install it (the Dart VM reads BoringSSL's roots, so the CA also
#                           reaches the app through --dart-define below)
#   scripts/seed-b1.sh      the salesman, the zone and the customers
#
# DISPOSABLE AVD RECOMMENDED: this leaves the app signed in to a dev server.
#
#: **The `/api/v1` prefix is load-bearing.** Every path in the app is relative — `/auth/login`,
#: `/auth/me`, `/auth/refresh`, `/sync/push`, `/sync/pull` — and `backend/config/urls.py`
#: mounts the whole API under `path("api/v1/", ...)`. A base URL without the prefix reaches
#: `path("", include("webadmin.urls"))` instead and every request 404s. This was written
#: without it once and cost an emulator run: Caddy showed `POST /auth/login` routed and Django
#: answered `Not Found: /auth/login`. `startup_orchestration_test.dart` had already recorded
#: the rule — *"the API is mounted at `/api/v1/`, so a base URL without one would not reach an
#: endpoint on a real deployment"* — and all six mobile test files use `.../api/v1`.
#: `AppConfig` preserves a path prefix and trims a trailing slash, so this concatenates cleanly.
B1_BASE_URL       ?= https://10.0.2.2/api/v1
B1_OPERATIONS     ?= 200
B1_PHONE          ?= +919876500001
B1_PASSWORD       ?= b1-acceptance-only
#: How long after the measure phase starts the radio comes back. Must be long enough for
#: `flutter drive` to install, launch and reach the first failed attempt.
B1_RECONNECT_AFTER ?= 150

#: **`$(CURDIR)/$(DEV_CA)`, not `$(DEV_CA)`** — the same rule `FLUTTER_HOST_RUN` states above:
#: *"`$(CURDIR)` because the recipes `cd mobile` first"*. `DEV_CA` is relative to the repository
#: root, and these defines are expanded inside `cd mobile && …`, so a bare path resolves to
#: `mobile/build/districore-dev-ca.crt` and `base64` reports no such file. The build then
#: carries no trust anchor and every request fails as a login failure, which points at the
#: wrong layer entirely.
B1_DEFINES = --dart-define=DISTRICORE_API_BASE_URL=$(B1_BASE_URL) \
	--dart-define=DISTRICORE_DEV_CA_B64=$$(base64 -w0 $(CURDIR)/$(DEV_CA)) \
	--dart-define=B1_OPERATIONS=$(B1_OPERATIONS) \
	--dart-define=B1_PHONE=$(B1_PHONE) \
	--dart-define=B1_PASSWORD=$(B1_PASSWORD)

B1_DRIVE = $(FLUTTER_HOST_RUN) drive --driver=test_driver/integration_test.dart \
	--target=integration_test/sync_reconnect_test.dart --keep-app-running \
	-d $(MOBILE_DEVICE_ID)

.PHONY: mobile-device-sync-latency
mobile-device-sync-latency: device-gate-preflight ## B1: FR-SYN-010 timed sync. Needs the dev stack, the seed and a trusted dev CA.
	@# **The guard must test the path the recipe will actually read.** This checked `$(DEV_CA)`
	@# from the repository root while `B1_DEFINES` read it from `mobile/`, so it passed while
	@# the thing it guards was broken — a precondition that cannot fail for the reason it
	@# claims. Both now name one absolute path.
	@test -f $(CURDIR)/$(DEV_CA) || { \
		echo "$(CURDIR)/$(DEV_CA) is missing. Run 'make up' then 'make dev-ca', then"; \
		echo "'make emulator-trust-ca' with the AVD running."; exit 1; }
	@echo "==> phase 1/3 online: authenticate and cache identity + customers"
	@$(ADB) shell svc wifi enable  >/dev/null 2>&1 || true
	@$(ADB) shell svc data enable  >/dev/null 2>&1 || true
	cd mobile && $(FLUTTER_HOST_RUN) pub get --enforce-lockfile && $(B1_DRIVE) $(B1_DEFINES) --dart-define=GATE_PHASE=online
	@echo "==> phase 2/3 queue: radio OFF, queue $(B1_OPERATIONS) real VISIT_CREATE rows"
	@$(ADB) shell svc wifi disable >/dev/null 2>&1 || true
	@$(ADB) shell svc data disable >/dev/null 2>&1 || true
	cd mobile && $(B1_DRIVE) $(B1_DEFINES) --dart-define=GATE_PHASE=queue
	@echo "==> phase 3/3 measure: radio returns after $(B1_RECONNECT_AFTER)s, mid-run"
	@echo "    The restore is backgrounded because the drive holds the foreground and Dart"
	@echo "    cannot toggle a radio. t0 is read from the cadence itself, so the exact"
	@echo "    instant the radio returns does not have to be known here - it only has to"
	@echo "    fall between two attempts, which any value inside the run does."
	@( sleep $(B1_RECONNECT_AFTER); \
	   $(ADB) shell svc wifi enable >/dev/null 2>&1 || true; \
	   $(ADB) shell svc data enable >/dev/null 2>&1 || true; \
	   echo "==> radio restored" ) &
	cd mobile && $(B1_DRIVE) $(B1_DEFINES) --dart-define=GATE_PHASE=measure
	@echo
	@echo "==> B1 complete. The GATE:b1 lines above are the evidence record."
	@echo "    x86_64 emulator only - TD-45 is unchanged by this run."

