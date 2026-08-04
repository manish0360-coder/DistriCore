# syntax=docker/dockerfile:1
# Multi-stage, non-root, pinned base (FD-10). Debian slim, never Alpine (musl surprises).

# --------------------------------------------------------------------------- builder
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv: fast, lockfile-driven dependency resolution (FD-04)
COPY --from=ghcr.io/astral-sh/uv:0.4.27 /uv /usr/local/bin/uv

WORKDIR /build
# Dependency layer BEFORE code layer (D-3): code changes hourly, dependencies monthly.
COPY pyproject.toml uv.lock* ./
RUN uv venv /opt/venv && \
    VIRTUAL_ENV=/opt/venv uv pip install --no-cache -r pyproject.toml

# --------------------------------------------------------------------------- dev deps
# Separate layer so the production image never carries test or lint tooling.
FROM builder AS builder-dev
RUN VIRTUAL_ENV=/opt/venv uv pip install --no-cache -r pyproject.toml --extra dev

# --------------------------------------------------------------------------- runtime
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app backend/ /app/backend/
COPY --chown=app:app docker/entrypoint.sh /app/entrypoint.sh

# /app is the PROJECT ROOT: it is where pyproject.toml lives, and therefore where
# ruff, pytest, mypy and coverage place their caches and reports. `WORKDIR` created
# it as root, so a process running as `app` could not write there.
#
# Owning only the subdirectories was the defect: the tools do not write into
# backend/, they write beside the config file. The runtime user must own the whole
# tree it works in — that is the fix, not relocating caches with env vars.
RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /srv/media /srv/backups /app/staticfiles \
    && chown -R app:app /app /srv/media /srv/backups

USER app
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", "--threads", "2", \
     "--timeout", "30", "--graceful-timeout", "30", \
     "--access-logfile", "-", "--error-logfile", "-"]

# --------------------------------------------------------------------------- dev
# Used by compose.dev.yml only. Adds pytest, ruff, mypy and import-linter, which
# `make verify` runs inside the container (N-12: the gate must run where the code runs).
FROM runtime AS dev

USER root
COPY --from=builder-dev /opt/venv /opt/venv
RUN chown -R app:app /opt/venv /app
USER app

ENV DJANGO_SETTINGS_MODULE=config.settings.dev
