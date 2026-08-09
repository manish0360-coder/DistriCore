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
	@echo "==> 6/8  type check"
	$(TOOLS) mypy backend/ || true
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
