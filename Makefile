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

.PHONY: audit
audit: ## Dependency vulnerability scan
	$(TOOLS) pip-audit

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

.PHONY: mobile-analyze
mobile-analyze: mobile-image ## Dart static analysis
	$(FLUTTER_SH) 'flutter pub get --enforce-lockfile && flutter analyze $(FLUTTER_ANALYZE_SEVERITY)'

.PHONY: mobile-test
mobile-test: mobile-image ## Dart unit tests (domain — no device)
	$(FLUTTER_SH) 'flutter pub get --enforce-lockfile && flutter test'

.PHONY: mobile-verify
mobile-verify: mobile-image ## Mobile gate: frozen install, analyze, test
	@test -f mobile/pubspec.lock || { \
		echo "mobile/pubspec.lock is missing. Run 'make mobile-lock' and commit it."; \
		exit 1; }
	$(FLUTTER_SH) 'flutter pub get --enforce-lockfile && flutter analyze $(FLUTTER_ANALYZE_SEVERITY) && flutter test'

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

.PHONY: prod-up
prod-up: ## Start the production stack (on the server)
	$(DCPROD) up -d --build --wait
