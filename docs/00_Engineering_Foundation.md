# DistriCore — Engineering Foundation

### The Project Constitution

| Field | Value |
| --- | --- |
| Document ID | `00_Engineering_Foundation` |
| Version | 1.0.0 |
| Status | **Draft — pending ratification** |
| Date | 2026-08-04 |
| Phase | **Phase 0 — Engineering Foundation** |
| Owner | Chief Systems Engineer |
| Governs | Every engineering decision on DistriCore, permanently |
| Depends on | `01_Project_Vision.md` v0.2.0 · `02_Requirements_Specification.md` v0.1.0 · `02A_Product_Editions.md` v0.2.0 · `03_System_Architecture.md` v0.1.0 |

---

## Preamble

### P.1 Standing

This document is the **constitution** of the DistriCore project. It governs *how* engineering is done. It does not describe features, data or interfaces — those live in documents 01 through 05.

Where any other document, tool, habit or convenience conflicts with this one, **this document wins** until it is formally amended (§P.4).

### P.2 The governing tension

DistriCore must satisfy two objectives that pull in opposite directions:

| | Objective | Consequence |
| --- | --- | --- |
| **A** | Version 1 must be cheap, fast and small enough for a single distributor on a ₹10,000–20,000 annual envelope | Every hour and every rupee of infrastructure must be justified |
| **B** | The same codebase must become a commercial multi-tenant SaaS over several years | Decisions that are expensive to reverse must be got right *now* |

**The rule that resolves the tension — and the single most important sentence in this document:**

> **Build no behaviour you do not need today. Preserve every shape whose later correction would require rewriting historical data or auditing every call site.**

Behaviour is cheap to add. Shape is expensive to change. Every decision below is classified by which it is, and priced accordingly.

### P.3 Non-negotiables

Twelve rules. They may be amended only by explicit revision of this document, never by exception, expedience or a comment in a pull request.

| # | Rule | Source |
| --- | --- | --- |
| N-01 | Business rules live in `services.py`. Views, serialisers, templates and tasks contain none. | ADR-006 |
| N-02 | No module imports another module's models. Cross-module access is through `services.py` only. | ADR-005 |
| N-03 | Stock on hand and party balances are **derived** from ledgers, never stored as mutable figures. | BR-004, BR-005 |
| N-04 | Issued financial documents are immutable. Correction is a new document. | BR-006 |
| N-05 | Every stock movement carries a source document or a reason code. | BR-007 |
| N-06 | Authorisation is enforced server-side on every request, independently of client. | BR-003 |
| N-07 | Money is `Decimal`. Floating point is forbidden in monetary or quantity paths. | NFR-INT-005 |
| N-08 | Every timestamp is stored in UTC. | §18 |
| N-09 | Migrations are schema-agnostic — no hardcoded schema name, all DDL repeatable on an empty schema. | ADR-007 |
| N-10 | `stock_movement` carries `location_id` and `lot_id` from the first migration. | C-14 |
| N-11 | Secrets never enter Git. Not once, not temporarily, not in a branch that will be deleted. | NFR-SEC-007 |
| N-12 | **A change is not done until it passes verification inside Docker.** Local success is not evidence. | Client mandate |

### P.4 Amendment process

1. Open an issue titled `ADR: <decision>` describing the problem and at least two options.
2. Write an ADR in `docs/adr/NNNN-title.md` using the standard template (§4.4).
3. The Product Architect and Chief Systems Engineer both approve.
4. Amend this document, bump its version, record the change in `docs/adr/README.md`.
5. Only then may code change.

**Reversing a non-negotiable (N-01…N-12) additionally requires a written migration plan with a cost estimate.** Those twelve rules exist because their violation is expensive to detect and expensive to undo.

### P.5 Roles

| Role | Held by | Authority |
| --- | --- | --- |
| Product Architect / Research Director | ChatGPT | Requirements, product direction, architecture proposals |
| Chief Systems Engineer | Claude | Engineering standards, architecture ratification, code review, this document |
| Implementation Assistant | DeepSeek via Ollama | Drafting code under §6.9 governance. **Never authoritative.** |
| Final Authority | **Docker verification** | No human opinion overrides a failing container (N-12) |

### P.6 Decision record format

Every recommendation below carries the same five fields, per the brief:

**Why** · **Alternatives** · **Trade-offs** · **Long-term impact** · **Migration cost if changed later**

Migration cost uses a fixed scale:

| Scale | Meaning |
| --- | --- |
| **Trivial** | Under 1 day |
| **Low** | 1–3 days |
| **Medium** | 1–2 weeks |
| **High** | 3–6 weeks |
| **Severe** | Over 6 weeks, or effectively a rewrite |

### P.7 Ratified in this document

| Ref | Decision | Status |
| --- | --- | --- |
| ADR-002 | **Backend stack: Python + Django + DRF + PostgreSQL** | **Ratified.** Open since `03` §14; confirmed. Everything below assumes it |
| ADR-003 | Server-rendered admin (Django templates + HTMX), not an SPA | Carried forward |
| ADR-007 | Schema-per-tenant strategy; **no `tenant_id` column** | Carried forward |
| ADR-012 | RPO ≈ 1 hour, RTO ≈ 2 hours | Carried forward — see §14 |
| ADR-013 | Outbox synchronisation, not bidirectional reconciliation | Carried forward |

---

# PART A — ENVIRONMENT

## 1. What Environment Is Required to Build Version 1

### 1.1 The environment model

Four layers. Each has a different lifetime and a different rule about what may live in it.

```
┌──────────────────────────────────────────────────────────┐
│  L1  WINDOWS 11 HOST                                     │
│      IDE, browser, Android Studio, emulator, Git client  │
│      Rule: no project runtime ever runs here             │
│  ┌────────────────────────────────────────────────────┐  │
│  │  L2  WSL2 UBUNTU                                    │  │
│  │      Source tree, git, Python tooling, docker CLI    │  │
│  │      Rule: the only place the repo is checked out    │  │
│  │  ┌──────────────────────────────────────────────┐   │  │
│  │  │  L3  DOCKER COMPOSE                           │   │  │
│  │  │      web · postgres · caddy                   │   │  │
│  │  │      Rule: the ONLY place code executes       │   │  │
│  │  │      This is the verification authority       │   │  │
│  │  └──────────────────────────────────────────────┘   │  │
│  │  L4  FLUTTER TOOLCHAIN (host-side, talks to L3)      │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

### FD-01 — The repository lives inside the WSL2 filesystem, never on `/mnt/c` or `/mnt/e`

**Decision.** The working tree lives at `~/projects/districore` inside WSL2. It is **not** checked out to a Windows drive and accessed across the WSL boundary.

**Why.** Cross-filesystem I/O between WSL2 and Windows drives is roughly an order of magnitude slower for the many-small-files access pattern that Git, Python imports, Docker build contexts and test runners all produce. It also breaks inotify file-watching, which silently disables Django's autoreload and any watch-mode tooling. This is the single most common cause of "Docker on Windows is slow" and it is entirely self-inflicted.

**Alternatives.** (a) Repo on `E:\Projects\DistriCore`, accessed from WSL via `/mnt/e` — rejected on the performance and file-watching grounds above. (b) Windows-native Python with Docker Desktop — rejected: production is Linux, and path, permission and line-ending differences produce defects that only appear in production. (c) Full Linux workstation — best but not the confirmed environment.

**Trade-offs.** Windows tools reach the tree over `\\wsl$\Ubuntu\...`, which is slower for Explorer but irrelevant for VS Code Remote WSL, which runs its server *inside* WSL and is unaffected.

**Long-term impact.** Development environment matches production (Linux, case-sensitive, POSIX permissions). The class of "works on my machine" defects caused by OS mismatch is eliminated at the start rather than debugged for years.

**Migration cost if changed later.** *Trivial* — re-clone. But the cost of *not* doing it is paid continuously in slow builds and phantom bugs, which is why it is decided here and not left to habit.

> **Note on the current folder.** `E:\Projects\DistriCore` holds the four planning documents and is the folder connected to this session. At Phase 0 execution, the canonical tree moves into WSL2 and `E:\Projects\DistriCore` becomes either a git remote clone or is retired. This is task **P0-1**.

---

### FD-02 — All application code executes only inside Docker

**Decision.** The application, database and proxy run exclusively in containers. Nothing is installed into WSL "so it can be run quickly."

**Why.** Two reasons, and the second matters more than the first. (1) Environment parity — the container that passes tests locally is byte-identical to the one deployed. (2) **It makes N-12 meaningful.** If code can run outside Docker, someone will eventually verify outside Docker, and the verification authority becomes advisory. A rule that can be bypassed conveniently will be bypassed under deadline pressure.

**Alternatives.** (a) Native virtualenv for speed, Docker only for release — rejected: guarantees drift between the two, and destroys the verification gate. (b) Devcontainers — a good option that formalises the same idea; deferred because Docker Compose already achieves it and devcontainers add a second configuration surface for one developer. Reconsider when the team reaches three.

**Trade-offs.** Slightly slower feedback loop (container start ~2s with warm layers). Debugger attachment requires configuration once. Both are one-time costs.

**Long-term impact.** Onboarding a second developer becomes `git clone && docker compose up`. Deployment is not a separate skill from development.

**Migration cost if changed later.** *Low* to abandon; *Medium* to introduce later once habits have formed around native execution.

---

### FD-03 — Pin every version explicitly; no floating major versions

**Decision.** Python `3.12.x` · PostgreSQL `16.x` · Django `5.x` · Flutter pinned to a specific stable release recorded in `.flutter-version` · JDK `17` · base images pinned by minor tag (`python:3.12-slim-bookworm`), never `latest`.

**Why.** Unpinned dependencies mean the build is a function of *when* it runs. That converts reproducible failures into intermittent ones, which are an order of magnitude more expensive to diagnose.

**Alternatives.** (a) `latest` tags — rejected outright. (b) Digest pinning (`@sha256:…`) — maximum reproducibility, but requires a tool to update digests and adds friction disproportionate to a one-developer project. Adopt at SaaS stage.

**Trade-offs.** Upgrades become deliberate work rather than something that happens to you. That is the point.

**Long-term impact.** Any commit can be rebuilt years later. Essential once the product is supporting paying customers on multiple versions.

**Migration cost if changed later.** *Trivial* to tighten; *High* to recover from an unpinned build that broke silently and was not noticed for months.

---

### FD-04 — `uv` for Python dependency management, with a committed lockfile

**Decision.** `pyproject.toml` declares dependencies; `uv.lock` pins the fully resolved graph; both are committed. Docker builds install from the lockfile only.

**Why.** A lockfile is mandatory for reproducibility (FD-03). Among the tools that provide one, `uv` resolves and installs 10–100× faster than pip, which materially shortens every Docker rebuild — the operation performed most often in a Docker-mandatory workflow (FD-02). It reads standard `pyproject.toml`, so nothing is proprietary.

**Alternatives.** (a) `pip` + `requirements.txt` — no real lockfile, no resolver guarantees. (b) `pip-tools` — solid and boring, but slower and two files to manage. (c) Poetry — mature, but slower and historically opinionated about packaging in ways that complicate Docker builds. (d) PDM — capable, smaller ecosystem.

**Trade-offs.** `uv` is newer than pip-tools and Poetry. The risk is mitigated by its use of standard `pyproject.toml` metadata: abandoning it means regenerating a lockfile, not rewriting dependency declarations.

**Long-term impact.** Fast, reproducible builds; CI cache-friendly.

**Migration cost if changed later.** *Trivial* — `uv pip compile` produces a `requirements.txt` any tool can consume.

---

### FD-05 — Tailwind via the standalone CLI binary; **no Node.js in the backend toolchain**

**Decision.** CSS is built by the Tailwind standalone executable, invoked from a Makefile target and during the Docker build. Node.js, npm and `package.json` do not exist in the backend repository.

**Why.** ADR-003 chose server-rendered HTML precisely to avoid a second build pipeline. Introducing Node solely to compile CSS would reintroduce exactly what that decision eliminated: a second runtime, a second lockfile, a second dependency-vulnerability surface, and a second thing to keep current. The standalone binary produces identical output with none of that.

**Alternatives.** (a) Tailwind via npm — the conventional route; rejected as above. (b) Tailwind CDN — acceptable in development only; unacceptable in production (no purging, large payload, third-party dependency on every page load, NFR-PER-001). (c) Hand-written CSS — cheaper to start, more expensive to keep consistent. (d) Bootstrap — heavier and harder to keep visually clean.

**Trade-offs.** The binary must be version-pinned and fetched in the Docker build. Minor.

**Long-term impact.** The backend stays a single-language project. Node enters only if and when a genuine JavaScript application is built — an Edition 3 concern.

**Migration cost if changed later.** *Trivial* — the same config file works under the npm toolchain.

---

## 2. Version 1 Engineering Setup Checklist

Your workstation baseline — Windows 11, WSL2 Ubuntu, Docker Desktop, VS Code Remote WSL, Git with GitHub SSH, Python, Ollama/DeepSeek, Flutter SDK — is **accepted as stable and is not re-verified here.**

Below is only what DistriCore additionally requires.

### 2.1 Tooling — inside WSL2

| # | Item | Mandatory? | Why it exists | Notes |
| --- | --- | :-: | --- | --- |
| T-01 | `uv` | **Yes** | Python dependency resolution and lockfile (FD-04) | Single-binary install |
| T-02 | `make` | **Yes** | One entry point for every developer command. Prevents undocumented tribal knowledge in shell history | `build-essential` |
| T-03 | Tailwind standalone CLI, version-pinned | **Yes** | CSS build without Node (FD-05) | Fetched in Docker build; a host copy is convenience only |
| T-04 | `pre-commit` | **Yes** | Runs formatter, linter and secret scan before a commit exists (N-11) | Installed via `uv tool` |
| T-05 | `gitleaks` | **Yes** | Secret scanning, in pre-commit and in CI | Enforces N-11 |
| T-06 | `rclone` | Later | Offsite backup transport (§14) | Needed at deployment milestone, not now |
| T-07 | `psql` client | Optional | Convenience. `docker compose exec db psql` is equivalent | |
| T-08 | `direnv` | Optional | Auto-loads `.envrc` per directory | Reduces manual export mistakes |

### 2.2 Runtime versions to confirm once

| # | Check | Required | If wrong |
| --- | --- | --- | --- |
| V-01 | Python in WSL | 3.12.x | Only matters for host tooling; the container version is authoritative |
| V-02 | Docker Compose | v2 (`docker compose`, not `docker-compose`) | Compose file syntax in this project assumes v2 |
| V-03 | Docker Desktop WSL integration enabled for the Ubuntu distro | Enabled | Otherwise the `docker` CLI is unreachable from WSL |
| V-04 | Git `core.autocrlf` | `false` inside WSL | CRLF in shell scripts breaks container entrypoints in ways that look like permission errors |
| V-05 | WSL memory limit (`.wslconfig`) | ≥ 8 GB if the Android emulator runs alongside Docker | Emulator plus Docker plus VS Code on 8 GB total will thrash |

### 2.3 Mobile toolchain — deferred to milestone M8

Not required until the Flutter application begins. Listed so the lead time is known, not so it is installed now.

| # | Item | Mandatory? | Why | Lead time |
| --- | --- | :-: | --- | --- |
| M-01 | Android Studio + Android SDK, API 34 platform | **Yes** | Build toolchain. Min API 26 per DR-3 | Large download |
| M-02 | JDK 17 | **Yes** | Required by current Android Gradle Plugin | |
| M-03 | Android SDK licences accepted | **Yes** | `flutter doctor --android-licenses`; builds fail confusingly otherwise | Minutes |
| M-04 | Emulator image, API 26 **and** API 34 | **Yes** | Must test the floor and a current release, not just one | |
| M-05 | A physical Android device | **Strongly advised** | Emulators do not reproduce real GPS, real camera, or real intermittent connectivity — and offline behaviour is the hardest thing in this product to get right (R-1) | |
| M-06 | **Android release keystore, generated and backed up** | **Yes** | See the warning below | Minutes to create, permanent to lose |

> ### The single most dangerous item in this document
>
> **If the Android release keystore is lost, the application on Google Play can never be updated again.** Not by you, not by Google. The only remedy is publishing a new listing under a new package name and asking every retailer and salesman to uninstall and reinstall.
>
> **Rule K-1.** The keystore and its passwords are generated once, stored in the password manager, and backed up to at least two locations that are not the development machine. This is done at M8 and verified at M11. It is never committed to Git (N-11).
>
> Google Play App Signing reduces but does not eliminate this exposure — the upload key still matters. Treat the rule as absolute.

### 2.4 Accounts and services

| # | Account | Mandatory? | When | Cost | Why |
| --- | --- | :-: | --- | --- | --- |
| A-01 | GitHub repository, **private** | **Yes** | Now (P0-2) | Free | Source of truth, CI, code review |
| A-02 | **SMS / OTP provider** | **Yes** | Before M0 completes | ~₹600/yr at V1 volume | **OTP login is Version 1 scope** per the client proposal. Indian options: MSG91, Fast2SMS, Twilio. DLT registration is required for Indian SMS and has a lead time of days to weeks — see below |
| A-03 | VPS provider | **Yes** | Milestone M11 | ₹500–700/mo | Production host |
| A-04 | Domain registrar | **Yes** | Before M11 | ~₹1,000/yr | TLS via Caddy needs a real domain |
| A-05 | Offsite backup target | **Yes** | M11 | ~₹600/yr | §14. Any S3-compatible or object store reachable by `rclone` |
| A-06 | Google Play Developer | **Yes** | Before first release | ₹2,200 once | App distribution |
| A-07 | Sentry (free tier) or self-hosted GlitchTip | **Strongly advised** | M0 | Free | §13. Without it, production errors are discovered by the client telephoning you |
| A-08 | Uptime monitor (UptimeRobot free) | Advised | M11 | Free | §13 |

> **A-02 carries hidden lead time.** Indian SMS delivery requires DLT (Distributed Ledger Technology) registration of the sender entity, header and message templates with a telecom operator. Approval commonly takes several days and templates are rejected for small formatting reasons. **Start this at Phase 0, not at M8**, or OTP login will be the thing that delays go-live.
>
> **Contingency.** If DLT approval is not complete by M8, the fallback is owner-provisioned passwords for internal users and deferred retailer self-registration — a temporary measure, recorded as a known deviation, not a silent scope change.

### 2.5 Secrets and certificates to create

| # | Secret | Where it lives | Created at | Rotation |
| --- | --- | --- | --- | --- |
| S-01 | Django `SECRET_KEY` (separate per environment) | Password manager → server `.env` | P0-4 | On suspected compromise. Rotating invalidates sessions |
| S-02 | PostgreSQL password | Password manager → server `.env` | P0-4 | Annually |
| S-03 | SMS provider API key | Password manager → server `.env` | With A-02 | Annually |
| S-04 | GitHub Actions deploy key or PAT | GitHub Secrets | M11 | Annually |
| S-05 | Server SSH key | Local `~/.ssh`, passphrase-protected | M11 | Annually |
| S-06 | Android upload keystore + passwords | Password manager + two offline backups | M8 | **Never** — rotation is not possible (K-1) |
| S-07 | Backup encryption passphrase | Password manager + offline | M11 | Never rotate without re-encrypting archives |
| S-08 | TLS certificates | **Not created manually** | — | Caddy obtains and renews automatically |

**Nothing above ever enters Git.** Enforced by `.gitignore`, `gitleaks` in pre-commit (T-05) and `gitleaks` in CI (§17). Three layers because this is the one class of mistake that cannot be undone by a revert — a secret pushed to GitHub is compromised permanently, even from a deleted branch.

### 2.6 Phase 0 execution tasks

| # | Task | Output | Blocks |
| --- | --- | --- | --- |
| P0-1 | Move the canonical tree into WSL2 (FD-01) | `~/projects/districore` | Everything |
| P0-2 | `git init`, private GitHub repo, branch protection on `main` | Repository exists | Everything |
| P0-3 | Repository skeleton per §4; `.gitignore`, `.editorconfig`, `LICENSE`, `README`, `Makefile` | Committed skeleton | M0 |
| P0-4 | `.env.example`, secrets created and stored (§2.5) | Documented secrets | M0 |
| P0-5 | Docker Compose dev stack that starts and passes a healthcheck (§8) | `make up` works | N-12 becomes enforceable |
| P0-6 | `pre-commit` hooks: ruff, ruff-format, gitleaks (§6) | Hooks active | First commit |
| P0-7 | CI pipeline: lint, test, build, secret scan (§17) | Green pipeline on an empty project | M0 merge |
| P0-8 | **Start DLT / SMS provider registration (A-02)** | Application submitted | M8 |
| P0-9 | `docs/adr/0001-record-architecture-decisions.md` and ADR index | ADR process live | Amendments |
| P0-10 | Ratify this document | Signed §P.4 | Implementation |

> **P0-8 is deliberately early.** It is the only Phase 0 task with an external dependency and an unbounded waiting period. Everything else is under your control.

---

## 3. Why Every Dependency Exists

The complete Version 1 dependency surface. **A dependency not on this list does not get added without an ADR** — this is how a lean project stays lean.

### 3.1 Runtime — mandatory

| Dependency | Why it exists | Cost of removing it |
| --- | --- | --- |
| Python 3.12 | Language runtime (ADR-002) | Rewrite |
| Django 5 | Auth, ORM, migrations, admin, CSRF, sessions, templates. Roughly 4–6 units of MVP work not written | Rewrite |
| Django REST Framework | Serialisation, viewsets, auth classes for the Flutter client. Hand-rolling this is weeks of work with worse validation | High |
| PostgreSQL 16 | Exact decimal arithmetic (N-07), real transactions (NFR-INT-001), schema-per-tenant (ADR-007). **SQLite cannot deliver the concurrency or the tenancy path** | Severe |
| psycopg | PostgreSQL driver | Trivial |
| Gunicorn | WSGI server. Django's dev server is single-threaded and explicitly not for production | Trivial |
| WhiteNoise | Static file serving from the app container without a separate volume mount | Trivial |
| Caddy | TLS termination with **automatic certificate issue and renewal**. Removes an entire category of operational work and an entire class of outage | Low (Nginx + certbot, more moving parts) |
| `django-environ` or `pydantic-settings` | Typed environment parsing (§9). Without it, config errors surface as runtime `AttributeError` in production instead of a startup failure | Low |

### 3.2 Feature-driven — mandatory, each traceable to a confirmed requirement

| Dependency | Requirement it serves | Alternative considered |
| --- | --- | --- |
| WeasyPrint | GST invoice PDF (FR-BIL-017). Renders the same HTML template used for the on-screen invoice — one template, two outputs | ReportLab: more code, no template reuse. `wkhtmltopdf`: unmaintained |
| Pillow | Product images, POD photos, visit photos — resize on upload (§7 of the proposal) | None realistic |
| `djangorestframework-simplejwt` | Mobile authentication (§5 of `03`) | Hand-rolled JWT: a security-critical wheel not worth reinventing |
| `django-axes` | Login rate limiting (FR-IAM-004) | Custom middleware: more code, worse coverage |
| SMS provider SDK or plain HTTP | OTP login (V1 scope) | Plain `httpx` against the REST API — **preferred**, keeps the provider swappable |
| HTMX | Server-rendered interactivity (ADR-003) | A single vendored JS file. No build step |

### 3.3 Development — mandatory

| Dependency | Why | Optional? |
| --- | --- | --- |
| pytest + pytest-django | Test runner. Better fixtures and parametrisation than Django's default runner | No |
| pytest-cov | Coverage gate (NFR-TST-001) | No |
| `ruff` | Linter **and** formatter in one tool. Replaces flake8 + isort + black at a fraction of the runtime | No |
| `mypy` + `django-stubs` | Static typing (NFR-MNT-003) | Start at `--strict` on `services.py` only, widen over time |
| `factory-boy` | Test data construction. Hand-built fixtures rot and become a maintenance tax | No |
| `pre-commit` | Runs the above before a commit exists | No |
| `gitleaks` | Secret scanning (N-11) | No |
| `pip-audit` | Dependency vulnerability scan (NFR-SEC-009) | No |

### 3.4 Optional — explicitly deferred

| Dependency | Would give | Why NOT in V1 | Revisit at |
| --- | --- | --- | --- |
| Redis | Cache, sessions, broker | Nothing in V1 needs it. Postgres handles sessions and locks. A second stateful service to run, monitor and back up (ADR-004) | Edition 2, if measured |
| Celery | Background jobs | Image resize ~200 ms, PDF ~300 ms — both fine inline. A broker is directed against (ADR-010) | When a job genuinely exceeds a request budget |
| `django-debug-toolbar` | Query inspection | Genuinely useful; dev-only dependency | May add now — dev group only |
| Sentry SDK | Error tracking | Free tier, ~2 hours to wire | **Recommended at M0** (§13) |
| `django-storages` | S3-compatible media | Local disk is sufficient and free (ADR-009). Django's storage API is already the seam (EP-J) | Edition 2 |
| `drf-spectacular` | OpenAPI schema | Useful for the Flutter client contract | Recommended at M4, when the API stabilises |

> **The governing rule for §3.** Every entry names the requirement it serves. Adding a dependency without a named requirement is how a 22-unit MVP becomes a 40-unit one, one convenient library at a time. **New dependencies require an ADR.**

---

# PART B — REPOSITORY AND WORKFLOW

## 4. Repository Structure

### FD-06 — Single repository (monorepo) containing backend, mobile, docs and ops

**Decision.** One private GitHub repository holds backend, Flutter application, documentation, ADRs, infrastructure and scripts.

**Why.** Backend and mobile share an API contract that changes together. In separate repositories, a breaking change is two pull requests in two places with no atomic relationship, and the contract drifts. One repository makes a contract change a single reviewable commit. At one developer, the coordination overhead of multiple repositories is pure loss.

**Alternatives.** (a) Separate backend/mobile/infra repos — appropriate at team scale with independent release cadences; premature here. (b) Git submodules — the coordination cost of polyrepo plus operational friction. (c) Monorepo tooling (Nx, Bazel) — solves problems this project will not have for years.

**Trade-offs.** CI must path-filter so a Dart change does not run Python tests. That is roughly ten lines of workflow configuration.

**Long-term impact.** Splitting later is straightforward because the directory boundary is already clean; `git filter-repo` preserves history per subtree.

**Migration cost if changed later.** *Low* — one day per extracted component, history preserved.

### 4.1 Structure

```
districore/
├── README.md                     # what this is, how to run it, where the docs are
├── LICENSE
├── Makefile                      # THE developer interface — see FD-07
├── .editorconfig
├── .gitignore
├── .env.example                  # every variable, documented, no real values
├── .pre-commit-config.yaml
├── pyproject.toml                # deps, ruff, mypy, pytest config — one file
├── uv.lock
│
├── docker/
│   ├── Dockerfile                # multi-stage: builder → runtime
│   ├── compose.yml               # base
│   ├── compose.dev.yml           # overrides: mounts, autoreload, exposed db
│   ├── compose.prod.yml          # overrides: gunicorn, restart policy, no mounts
│   ├── Caddyfile
│   └── entrypoint.sh
│
├── docs/
│   ├── 00_Engineering_Foundation.md      # this document
│   ├── 01_Project_Vision.md
│   ├── 02_Requirements_Specification.md
│   ├── 02A_Product_Editions.md
│   ├── 03_System_Architecture.md
│   ├── 04_Database_Design.md             # next
│   ├── 05_API_Contracts.md
│   ├── adr/                              # numbered, immutable decision records
│   │   ├── README.md                     # index + status
│   │   └── 0001-record-architecture-decisions.md
│   ├── runbooks/                         # operational procedures
│   │   ├── deploy.md
│   │   ├── restore-from-backup.md
│   │   ├── rotate-secrets.md
│   │   └── incident-response.md
│   └── client/
│       └── DistriCore_Client_Proposal.pdf
│
├── backend/
│   ├── manage.py
│   ├── config/
│   │   ├── settings/{base,dev,prod,test}.py
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── logging.py
│   │
│   ├── platform/                 # base model, audit, permissions, storage seam
│   ├── identity/
│   ├── catalogue/
│   ├── customers/
│   ├── pricing/
│   ├── inventory/
│   ├── orders/
│   ├── fulfilment/
│   ├── billing/
│   ├── receivables/
│   ├── field/
│   ├── sync/
│   ├── reporting/
│   │
│   ├── api/v1/                   # DRF delivery layer — no business logic
│   ├── webadmin/                 # templates, views — no business logic
│   │   ├── templates/
│   │   └── static/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── adversarial/          # the six requirements of 02 §25.2
│       └── factories/
│
├── mobile/                       # Flutter, single binary, role-based
│   ├── .flutter-version
│   └── lib/{core,data,features,shared}/
│
├── ops/
│   ├── backup.sh
│   ├── restore.sh
│   ├── deploy.sh
│   └── seed_demo.py
│
└── .github/
    ├── workflows/{ci.yml,codeql.yml}
    ├── pull_request_template.md
    └── ISSUE_TEMPLATE/
```

**Every Django module has the same five files.** Uniformity is not decoration — it means a developer opening any module knows where the rules live without exploring, and N-01 and N-02 become visible in the file layout rather than only in this document.

```
<module>/
├── models.py        # tables this module owns. Nothing else.
├── services.py      # THE public interface. All business rules. All writes.
├── selectors.py     # read queries
├── admin.py
└── tests/
```

### FD-07 — The `Makefile` is the only developer interface

**Decision.** Every routine operation is a `make` target: `make up`, `make down`, `make test`, `make lint`, `make migrate`, `make shell`, `make verify`, `make logs`, `make backup`.

**Why.** Commands that live only in shell history are undocumented, unshareable and inconsistent between machines. A Makefile is executable documentation that cannot go stale, because it is the thing actually being run. It also lets CI and a human invoke the *identical* command — which is what makes `make verify` a meaningful gate rather than an approximation of one.

**Alternatives.** (a) Shell scripts in `scripts/` — equivalent, without the discoverability of `make help`. (b) `just` — nicer syntax, one more tool to install. (c) Documented raw commands in README — rots within weeks.

**Trade-offs.** Make's syntax is unfriendly (tabs, `.PHONY`). The targets here are thin wrappers, so this barely surfaces.

**Long-term impact.** Onboarding is `make help`. CI and local verification cannot diverge.

**Migration cost if changed later.** *Trivial*.

### 4.2 What must never appear in the repository

| Never | Why |
| --- | --- |
| `.env` with real values | N-11 |
| Keystores, certificates, private keys | N-11, K-1 |
| Database dumps with real customer data | Privacy; the client's retailers did not consent |
| Compiled artefacts, `__pycache__`, `build/` | Noise; conflicts |
| Uploaded media | Belongs on a volume, not in history |
| Large binaries | Git history is permanent — a 50 MB mistake is carried forever by every clone |

### 4.3 Documentation standards

| Rule | Detail |
| --- | --- |
| Numbered documents are the specification | `00`–`05`. Changing behaviour means changing the document in the **same pull request** (NFR-DOC-001, C-9) |
| ADRs are immutable | Once accepted, an ADR is never edited. It is superseded by a new ADR that references it. The record of *why* must survive the decision |
| Runbooks are written before they are needed | A restore procedure first written during an outage is not a procedure |
| README answers three questions only | What is this, how do I run it, where are the docs |
| Code comments explain **why**, never **what** | The code states what. A comment restating it is a second thing to keep true |
| Every module has a docstring | One paragraph: what this module owns and what it must never do |

### 4.4 ADR template

```markdown
# NNNN — <Title>

Status: Proposed | Accepted | Superseded by ADR-MMMM
Date: YYYY-MM-DD
Deciders: <names>

## Context
What forces are at play? What constraint or requirement drives this?

## Options
1. <Option> — pros / cons
2. <Option> — pros / cons

## Decision
What was chosen.

## Consequences
Positive, negative, and what becomes harder.

## Migration cost if reversed
Trivial | Low | Medium | High | Severe — and why.
```

---

## 5. Development Workflow: Idea → Code → Verification → Commit → Release

### 5.1 The pipeline

```
  IDEA
   │  Is it in the confirmed scope (02A §13)?
   │  NO  → change request, priced separately. Not built quietly.
   │  YES ↓
  ISSUE               labelled, linked to a requirement ID (FR-xxx-nnn)
   │
   │  Architectural? → ADR first (§P.4). No code before the ADR is accepted.
   ↓
  BRANCH             feat/<issue>-<slug>, from main
   │
   ↓
  CODE               services.py first, then delivery layer, then tests
   │                 DeepSeek may draft — under §6.9
   ↓
  LOCAL CHECK        make lint · make test        (fast feedback, NOT authority)
   │
   ↓
  ┌───────────────────────────────────────────────────────┐
  │  DOCKER VERIFICATION       make verify                │
  │  Clean build · migrate · full suite · healthcheck     │
  │  ***  THE ONLY AUTHORITY (N-12)  ***                  │
  └───────────────────────────────────────────────────────┘
   │  fail → back to CODE. No exceptions, no "it's only a typo".
   ↓
  COMMIT             Conventional Commits (§6.2); pre-commit hooks run
   │
   ↓
  PULL REQUEST       CI repeats verification on neutral hardware
   │                 review checklist (§6.6)
   ↓
  MERGE              squash to main; main is always releasable
   │
   ↓
  RELEASE            tag, build image, deploy, smoke test (§16)
```

### 5.2 `make verify` — the definition of the gate

```
make verify:
  1. docker compose build --no-cache app      # no stale layer can hide a broken dependency
  2. docker compose up -d --wait              # healthchecks must pass
  3. docker compose exec app python manage.py migrate --check   # no missing migration
  4. docker compose exec app ruff check .
  5. docker compose exec app mypy backend/
  6. docker compose exec app pytest --cov --cov-fail-under=80
  7. curl -f http://localhost/healthz
  8. docker compose down -v                   # leave nothing behind
```

**Why `--no-cache` on the build.** A cached layer can conceal a dependency that was installed locally but never declared. Rebuilding clean is the only way the container proves the declaration is complete. It costs a few minutes; it prevents the failure mode where production is the first environment to discover a missing package.

**Why step 3.** Django will happily run against a schema that does not match the models. `migrate --check` fails if a model change has no migration — catching, at commit time, the single most common cause of a broken deploy.

### 5.3 Why Docker verification is the final authority

| Claim | Reality |
| --- | --- |
| "It works on my machine" | Your machine has state: installed packages, environment variables, a warm database, a file you forgot to commit |
| "The tests passed locally" | Against your database, your Python, your `.env` |
| "It's a one-line change" | One-line changes cause outages precisely because they skip verification |

The container is the only environment that is (a) built from the repository alone, (b) identical to production, and (c) reproducible by anyone. **It is therefore the only environment whose verdict means anything.** A human may not override it — not the Chief Systems Engineer, not the client, not a deadline.

---

## 6. Standards

### 6.1 Branch strategy

### FD-08 — Trunk-based development with short-lived branches

**Decision.** `main` is always releasable and protected. Work happens on branches named `feat/…`, `fix/…`, `docs/…`, `chore/…`, `refactor/…`, `test/…`, merged by squash within roughly three days. Releases are **tags on `main`**, not long-lived branches.

**Why.** Long-lived branches accumulate merge debt, and merge debt is paid at the worst possible time — when trying to ship. At one developer, git-flow's `develop`/`release`/`hotfix` structure is ceremony protecting against a coordination problem that does not exist. Short branches also keep pull requests small, and small pull requests get genuinely reviewed rather than skimmed.

**Alternatives.** (a) git-flow — appropriate when supporting several released versions simultaneously; that is an Edition 3 concern. (b) Commit straight to `main` — fastest, but loses the CI gate and code review, both of which are load-bearing here. (c) GitHub Flow — essentially this, and this is it.

**Trade-offs.** Requires discipline to keep branches short and `main` releasable. Feature work spanning weeks must be merged behind an inactive code path rather than accumulating on a branch.

**Long-term impact.** When the product supports multiple customer versions (Edition 3), add release branches *then*, from a codebase already accustomed to a clean trunk.

**Migration cost if changed later.** *Trivial* — adding release branches to trunk-based development is additive.

**Branch protection on `main`:** no direct pushes · pull request required · CI must pass · conversations resolved · linear history.

> Even as a single developer, self-review through a pull request catches a meaningful number of defects — because reading a diff engages different attention than writing it did. The rule is kept.

### 6.2 Commit conventions

**Conventional Commits**, enforced by a commit-msg hook.

```
<type>(<scope>): <subject>

<body — why, not what>

Refs: FR-ORD-001
```

Types: `feat` · `fix` · `docs` · `refactor` · `test` · `chore` · `perf` · `build` · `ci`
Scopes: the module name (`orders`, `billing`, `sync`, `mobile`, `docker`, `docs`).

**Why.** Machine-readable history enables automatic changelog generation and, later, automatic version bumping. More immediately, it forces a moment's thought about what a change actually is — a commit that cannot be typed is usually a commit doing several things at once.

**Alternatives.** Free-form (unparseable, degrades within weeks) · gitmoji (cute, less machine-readable).

**Migration cost if changed later.** *Trivial* going forward; historical commits cannot be retyped.

**Rules.** One logical change per commit · imperative mood · body explains *why* · reference the requirement ID · **never** `wip`, `fix stuff`, or `.`.

### 6.3 Coding standards

| Rule | Tool | Enforced |
| --- | --- | --- |
| Formatting: `ruff format`, line length 100 | ruff | pre-commit + CI |
| Linting: pycodestyle, pyflakes, bugbear, isort, security | ruff | pre-commit + CI |
| Typing: `mypy --strict` on `services.py` and `selectors.py`; standard elsewhere | mypy + django-stubs | CI |
| No business logic outside `services.py` | Review (§6.6) | Review |
| No cross-module model imports | import-linter | CI |
| No raw SQL without parameters | ruff security rules + review | CI + review |
| Docstring on every module and every public service function | Review | Review |
| Functions short enough to hold in mind — roughly 50 lines | Review | Review |

**Naming.** Models singular (`Order`) · services are verbs (`create_order`, `issue_invoice`) · selectors are nouns (`get_customer_balance`) · booleans read as assertions (`is_active`, `has_credit`) · money always carries the unit in the name where ambiguity is possible (`total_amount`, never `total`).

**Import-linter contracts** encode N-01 and N-02 mechanically. A rule that is only in a document is a suggestion; a rule in CI is a rule.

### 6.4 Testing strategy

```
        ╱╲          Adversarial  (~5%)   the 6 requirements of 02 §25.2
       ╱  ╲                              sync replay · invoice mutation ·
      ╱────╲                             authorisation matrix · concurrency
     ╱      ╲       Integration (~25%)   API endpoint × role, real Postgres
    ╱────────╲
   ╱          ╲     Unit        (~70%)   services.py — the business rules
  ╱────────────╲
```

| Layer | Scope | Speed | Gate |
| --- | --- | --- | --- |
| Unit | One service function. Database only where the rule needs it | < 5s total early | 100% of pricing, tax, stock, ledger, credit — **including failure paths** |
| Integration | HTTP in, database out. Every endpoint, every role | < 60s | Every endpoint, authorised and unauthorised |
| Adversarial | Deliberate abuse | Slow; runs in CI | Must pass. Never skipped |

**The adversarial suite is not optional and not aspirational.** Requirements `02` §25.2 lists six things ordinary testing cannot verify. Four survive into Version 1:

| Test | Verifies | Method |
| --- | --- | --- |
| Sync replay and interruption | Zero loss, zero duplicates (FR-SYN-003/004/006) | Kill mid-batch, replay batches, skew clocks, exhaust storage |
| Invoice immutability | BR-006 / N-04 | Attempt mutation through every path including direct ORM |
| Authorisation matrix | FR-IAM-007, N-06 | Full role × capability grid issued **directly to the API**, bypassing all clients |
| Ledger concurrency | NFR-INT-002/003 | Simultaneous conflicting writes; assert no lost update and balances reconcile |

> **A green happy-path suite is not evidence for any of the four.** That is precisely why they are named here, in the constitution, rather than left to be remembered during a sprint.

**Coverage:** ≥ 80% overall (NFR-TST-001); 100% on business-rule modules. Coverage is a floor that catches untested code, not a target that proves quality — a fully covered codebase can still be wrong.

### 6.5 Definition of Done

A change is done when **all** of the following are true. Not most.

| # | Criterion |
| --- | --- |
| 1 | Implements the requirement, and only that requirement |
| 2 | Business logic is in `services.py` (N-01) |
| 3 | No cross-module model import (N-02) |
| 4 | Unit tests including **failure and edge cases**, not only happy path |
| 5 | Integration test for any new endpoint, authorised **and** unauthorised |
| 6 | `make verify` passes in Docker (N-12) |
| 7 | CI green |
| 8 | Documentation updated in the **same** pull request (NFR-DOC-001) |
| 9 | ADR written if the decision is architectural |
| 10 | No new dependency without an ADR (§3) |
| 11 | No secret added, in any form (N-11) |
| 12 | Migration reviewed against §15 if the schema changed |
| 13 | Conventional Commit message referencing the requirement ID |
| 14 | Self-reviewed through the pull request diff |

### 6.6 Code review checklist

**Correctness** — Does it do what the requirement says, and nothing more? Are failure paths handled or deliberately propagated? Are edge cases tested: zero, negative, null, empty, maximum, concurrent?

**Architecture** — Business logic only in `services.py`? Any cross-module model import? Is a rule duplicated anywhere (NFR-MNT-001)? Is an abstraction being introduced for a second caller that does not exist?

**Data integrity** — Multi-table writes in a transaction? Money and quantity `Decimal`? Timestamps UTC? Balances derived, not stored? Are issued documents left immutable?

**Security** — Authorisation checked server-side? Input validated server-side regardless of client? Queries parameterised? Anything sensitive reaching logs or error responses? Any secret introduced?

**Performance** — Any N+1 query? Any unbounded query without pagination? Any query that degrades worse than linearly with history?

**Maintainability** — Will this be comprehensible in a year? Do names say what things are? Do comments explain *why*? Is this the smallest correct change?

**Evolution** — Does this foreclose multi-warehouse, batch tracking or tenancy (§18)? Does it add unused abstraction?

> **The two review questions that matter most:** *What breaks if this is wrong in production?* and *What would this cost to reverse in two years?*

### 6.9 Governance of AI-assisted implementation

DeepSeek via Ollama is available for drafting. It is a **drafting tool, never an authority.**

| Rule | Detail |
| --- | --- |
| AI-1 | **No secret, credential, real customer record or `.env` content is ever pasted into a model prompt.** Local inference reduces but does not eliminate this discipline — it should be habitual before any hosted model is ever used |
| AI-2 | Generated code is reviewed line by line against §6.6 before commit. "The model wrote it" is not a defence |
| AI-3 | Generated code that violates N-01…N-12 is rejected outright, however convenient |
| AI-4 | AI is not used to author ADRs, security controls, migrations, or the adversarial test suite. Those require understood intent, and understanding is the deliverable |
| AI-5 | Generated tests are viewed with particular suspicion — a test that asserts current behaviour rather than required behaviour is worse than no test, because it manufactures false confidence |
| AI-6 | The committer owns the code entirely. Attribution changes nothing about responsibility |

**Why this is in the constitution.** AI assistance raises output speed and lowers the cost of producing code that *looks* right. In a system holding financial records, plausible-looking wrongness is the expensive failure mode. The verification gate (N-12) and this section exist to convert speed into leverage rather than into risk.

---

# PART C — RUNTIME AND INFRASTRUCTURE

## 7. Local Development Architecture

### 7.1 Shape

```
 WINDOWS 11
  ├── VS Code ──── Remote-WSL ──┐
  ├── Browser  → localhost:8000 │
  └── Android emulator ─────────┼──→ 10.0.2.2:8000  (host loopback from emulator)
                                │
 WSL2 UBUNTU ───────────────────┘
  ~/projects/districore   ← the only checkout (FD-01)
  │
  └── docker compose
       ├── caddy    :80/:443  → app
       ├── app      :8000     gunicorn / runserver, volume-mounted in dev
       └── db       :5432     postgres 16, named volume, exposed to host in dev only
```

### FD-09 — Volume-mount source in development; copy it in production

**Decision.** `compose.dev.yml` bind-mounts `./backend` into the container so edits are live. `compose.prod.yml` mounts nothing — the image contains the code.

**Why.** Development needs a sub-second edit-to-reload loop; mounting gives it without rebuilding. Production needs an immutable, reproducible artefact; a mount would mean the running code is whatever happens to be on the host disk, which destroys the guarantee that the tested image is the deployed image.

**Alternatives.** (a) Rebuild on every change — correct but far too slow to work in. (b) Mount in production too — makes deployment a file copy and reintroduces drift.

**Trade-offs.** Two compose overrides to maintain. Dependency changes still require a rebuild, which occasionally confuses ("I installed it, why is it missing") — solved by `make rebuild`.

**Long-term impact.** The production image is a genuine artefact that can be pinned, rolled back and audited.

**Migration cost if changed later.** *Trivial*.

### 7.2 Database in development

Real PostgreSQL in a container, never SQLite. **SQLite differs from PostgreSQL in transaction isolation, constraint enforcement, decimal handling, concurrent write behaviour and locking** — precisely the areas where this product's correctness lives (N-03, N-07, NFR-INT-002). Developing against SQLite would mean the first honest test of the ledger happens in production.

Seed data comes from `ops/seed_demo.py`: fictional products, retailers and orders. **Never a copy of the client's real data** — their retailers did not consent to their commercial records sitting on a developer's laptop.

### 7.3 Emulator connectivity

The Android emulator reaches the WSL2 backend at `10.0.2.2:8000`. A physical device requires the Windows host IP plus a firewall rule. This is documented in `docs/runbooks/` at M8 because it is the kind of ten-minute problem that costs an afternoon when undocumented.

---

## 8. Docker Architecture

### FD-10 — Multi-stage build, non-root runtime, pinned base image

**Decision.** `builder` stage installs dependencies with `uv` and builds CSS; `runtime` stage copies only the virtualenv and application code, runs as an unprivileged user, and declares a `HEALTHCHECK`.

**Why.** Multi-stage keeps build toolchains out of the shipped image — smaller surface, smaller image, faster pulls. Running as non-root is the cheapest meaningful container hardening available: it costs three lines and converts a whole class of container escape from trivial to non-trivial. The healthcheck is what makes `docker compose up --wait` a real gate rather than a hopeful pause.

**Alternatives.** (a) Single-stage — simpler, ships compilers into production. (b) Distroless — smaller and more locked-down, but debugging inside it is painful and this is a one-person operation where debugging speed matters. (c) Alpine — smaller, but musl's behaviour differs from glibc in ways that surface as obscure wheel and locale bugs. **Debian slim is the boring correct choice.**

**Trade-offs.** Slightly more complex Dockerfile. Non-root requires deliberate ownership of the media directory.

**Long-term impact.** The image is production-grade from day one, not "hardened later" — a task that in practice is never scheduled.

**Migration cost if changed later.** *Low.*

### 8.1 Compose layering

| File | Purpose | Used by |
| --- | --- | --- |
| `compose.yml` | Services, networks, volumes — the invariant core | Both |
| `compose.dev.yml` | Source mount, autoreload, exposed DB port, dev settings | `make up` |
| `compose.prod.yml` | Gunicorn, `restart: unless-stopped`, no mounts, no exposed DB | `ops/deploy.sh` |

**Why layered rather than two independent files.** Duplicated compose files diverge; the divergence is discovered in production. One base plus thin overrides means dev and prod cannot drift on anything that matters.

### 8.2 Service contract

| Service | Image | Restart | Healthcheck | Notes |
| --- | --- | --- | --- | --- |
| `caddy` | `caddy:2-alpine` | `unless-stopped` | HTTP on `/healthz` | Auto-TLS in prod; plain HTTP in dev |
| `app` | built from `docker/Dockerfile` | `unless-stopped` | `curl -f localhost:8000/healthz` | Non-root; media volume |
| `db` | `postgres:16-alpine` | `unless-stopped` | `pg_isready` | Named volume; **never** bind-mounted to the host |

**The database volume is named, not a host bind mount.** A bind mount on WSL2 crosses the filesystem boundary and is both slow and, on Windows hosts, prone to permission problems that corrupt the data directory in ways that look like database bugs.

### 8.3 Rules

| # | Rule | Why |
| --- | --- | --- |
| D-1 | No `latest` tags | FD-03 |
| D-2 | `.dockerignore` excludes `.git`, `docs`, `mobile`, tests, media | Build context size directly costs build time |
| D-3 | Dependency layer before code layer | Code changes hourly; dependencies monthly. Wrong order means a full reinstall on every edit |
| D-4 | No secret in any `ARG`, `ENV` or layer | Build args are visible in image history — permanently |
| D-5 | One process per container | Restart, healthcheck and log semantics all assume it |
| D-6 | Migrations run in the entrypoint, guarded by a lock | Prevents two containers racing the same migration |
| D-7 | Logs to stdout only | §12 |

---

## 9. Environment Variable Strategy

### FD-11 — Twelve-factor configuration, parsed and validated at startup

**Decision.** All environment-specific values come from environment variables, read once at startup through a typed parser that **fails loudly on a missing or malformed required variable**.

**Why.** The failure mode being prevented is specific and expensive: an unset variable silently defaults to `None`, the application starts, and the defect surfaces hours later as a corrupted invoice or an unsent OTP. Validating at startup converts a silent runtime failure into a loud boot failure — which is discovered in seconds by the deploy script rather than in days by the client.

**Alternatives.** (a) Settings hardcoded per environment — cannot rotate a secret without a code change. (b) A config file per environment — becomes a secret-bearing file that must not be committed, which is the problem it was meant to solve. (c) A secrets manager — correct at SaaS scale; disproportionate for one VPS today (§11).

**Trade-offs.** Every new variable must be added in three places: `.env.example`, the settings parser, and the deploy runbook. That friction is deliberate.

**Long-term impact.** Moving to a secrets manager later means changing only where values are *sourced*, not how they are *consumed*.

**Migration cost if changed later.** *Trivial.*

### 9.1 Conventions

| Rule | Detail |
| --- | --- |
| Prefix | `DISTRICORE_` on application variables. Third-party variables keep their own names (`DATABASE_URL`, `POSTGRES_PASSWORD`) |
| Naming | `SCREAMING_SNAKE_CASE`, grouped by concern: `DISTRICORE_DB_*`, `DISTRICORE_SMS_*`, `DISTRICORE_LOG_*` |
| `.env.example` | **Every** variable, with a comment, a type and a safe placeholder. Committed. Kept current — a pull request adding a variable without updating it fails review |
| `.env` | Never committed (N-11). `0600` on the server |
| Defaults | Development-safe defaults permitted; **secrets and production endpoints have no default** and must fail |
| Booleans | Explicit `true`/`false` strings, parsed strictly. `"False"` evaluating truthy is a classic and costly bug |

### 9.2 Variable groups

| Group | Examples | Secret? |
| --- | --- | :-: |
| Core | `DJANGO_SETTINGS_MODULE`, `DISTRICORE_ENV`, `DISTRICORE_DEBUG` | No |
| Security | `DISTRICORE_SECRET_KEY`, `DISTRICORE_ALLOWED_HOSTS` | **Yes** |
| Database | `DATABASE_URL` | **Yes** |
| SMS / OTP | `DISTRICORE_SMS_PROVIDER`, `DISTRICORE_SMS_API_KEY`, `DISTRICORE_SMS_SENDER_ID` | **Yes** |
| Storage | `DISTRICORE_MEDIA_ROOT`, `DISTRICORE_MAX_UPLOAD_MB` | No |
| Logging | `DISTRICORE_LOG_LEVEL`, `DISTRICORE_LOG_FORMAT` | No |
| Monitoring | `SENTRY_DSN` | **Yes** |

---

## 10. Configuration Management

### FD-12 — Three tiers of configuration, each in exactly one place

**Decision.**

| Tier | Lives in | Changed by | Requires |
| --- | --- | --- | --- |
| **1. Environment** — differs per deployment | Environment variables | Operator | Restart |
| **2. Application** — same everywhere, rarely changes | `config/settings/*.py`, version-controlled | Developer | Deploy |
| **3. Business** — the client's own rules | Database rows | The owner, in the UI | Nothing |

**Why.** Conflating these is the most common source of "we need a developer to change a discount percentage." Tier 3 is what NFR-CFG-001 and C-12 demand: tax rates, reason codes, credit limits, offer text and number series are **data the owner edits**, not constants a developer redeploys. This tiering is also what keeps the core domain-agnostic (C-12) and therefore what makes the Edition 3 vertical-packs business model possible at all.

**Alternatives.** (a) Everything in settings — every business change becomes a deploy. (b) Everything in the database — obscures deployment-critical values and complicates startup. (c) A dynamic settings package — an extra dependency for what a purpose-built table does more clearly.

**Trade-offs.** Judgement is required about which tier a new value belongs in. The test: *would the client ever want to change this without calling me?* If yes, tier 3.

**Long-term impact.** Directly determines how much of Edition 2 and 3 is configuration rather than code.

**Migration cost if changed later.** *Medium* — moving a constant into the database after release means a data migration plus a UI.

### 10.1 Settings layout

`base.py` holds everything shared. `dev.py`, `prod.py` and `test.py` import it and override. **`prod.py` asserts its own preconditions at import:** `DEBUG` false, `SECRET_KEY` not the development default, `ALLOWED_HOSTS` non-empty, TLS redirect on, secure cookies on. A misconfigured production instance must refuse to start rather than run insecurely.

**Feature flags are deliberately not introduced.** A flag framework is premature for a single deployment. Where behaviour must be switchable, it is a tier-3 configuration row. Revisit at Edition 3, when tenants need different behaviour.

---

## 11. Secrets Management

### FD-13 — Environment file on the server plus a password manager, with an explicit upgrade trigger

**Decision.** Version 1 secrets live in `/opt/districore/.env` (`0600`, owned by the deploy user) on the server, with the canonical copy in a password manager. CI secrets live in GitHub Actions Secrets. Nothing is encrypted-at-rest in the repository because **nothing secret is in the repository at all.**

**Why.** Three layers already prevent the unrecoverable mistake: `.gitignore`, `gitleaks` in pre-commit, `gitleaks` in CI. Beyond that, a secrets manager for one server and one developer adds an availability dependency and operational surface without reducing meaningful risk. The realistic threat here is accidental commit, not an attacker with filesystem access to a server they have already compromised.

**Alternatives.** (a) HashiCorp Vault — correct at scale; disproportionate now and a new service to keep running. (b) SOPS + `age` — encrypted secrets committed to the repo; genuinely good and the recommended next step, but it earns its keep when secrets must be *shared*, which is a team-of-two problem. (c) Docker secrets — designed for Swarm; awkward under plain Compose. (d) Cloud secrets manager — recurring cost, contradicts hosting-agnosticism.

**Trade-offs.** Rotation is manual and depends on the runbook being followed. Onboarding a second developer means handing over secrets out-of-band — the moment to adopt SOPS.

**Long-term impact.** Consumption is already via environment variables (FD-11), so the source can change without touching application code.

**Migration cost if changed later.** *Low* — SOPS + `age` is roughly a day, including the runbook.

### 11.1 Rules

| # | Rule |
| --- | --- |
| SEC-1 | No secret in Git — ever, including a branch that will be deleted (N-11) |
| SEC-2 | No secret in a Docker `ARG`, `ENV` or build layer (D-4) |
| SEC-3 | No secret in a log line, error message, exception body or crash report (FR-AUD-006) |
| SEC-4 | No secret in an AI prompt (AI-1) |
| SEC-5 | Distinct secrets per environment. Development values are never reused in production |
| SEC-6 | Rotation procedure written in `docs/runbooks/rotate-secrets.md` **before** production, not after an incident |
| SEC-7 | **If a secret is ever committed, it is compromised.** The response is rotation, not history rewriting. Rewriting history does not un-fetch a clone |

### 11.2 Upgrade triggers

| When | Adopt |
| --- | --- |
| Second developer joins | SOPS + `age` |
| Second environment (staging) | Same, with per-environment keys |
| Multi-tenant SaaS | Managed secrets manager with audit logging |

---

## 12. Logging Strategy

### FD-14 — Structured JSON to stdout, correlated by request ID

**Decision.** One log line per event, JSON-formatted, written to stdout only. Every line carries `timestamp` (UTC), `level`, `logger`, `request_id`, `user_id`, `message` and event-specific fields. Docker's `json-file` driver handles rotation.

**Why.** Writing to files inside a container means logs vanish when the container is replaced, and rotation becomes the application's problem. Stdout is the container-native contract: Docker captures it now, and any aggregator captures it later without an application change. JSON is chosen because the first time a production question is asked — *"what happened to invoice 4471?"* — grepping unstructured text across a day of logs is the difference between two minutes and two hours.

**Alternatives.** (a) Plain text — friendlier to read, unusable to query. (b) Log files with logrotate — reintroduces state into a stateless container. (c) Shipping to a hosted service now — recurring cost against A-19, and unnecessary at one host.

**Trade-offs.** JSON is harder to read raw. Mitigated by pretty-printing in development (`DISTRICORE_LOG_FORMAT=console`).

**Long-term impact.** Adding Loki, or any aggregator, later requires zero application change.

**Migration cost if changed later.** *Low.*

### 12.1 Levels

| Level | Use | Example |
| --- | --- | --- |
| `DEBUG` | Development only | Query detail |
| `INFO` | Normal significant events | Order confirmed, invoice issued, sync batch accepted |
| `WARNING` | Unexpected but handled | Credit limit exceeded, sync conflict raised, retry |
| `ERROR` | Failed operation, request lost | Unhandled exception, SMS delivery failure |
| `CRITICAL` | System-level failure | Database unreachable, migration failure at boot |

### 12.2 Always logged

Authentication success and failure · authorisation denial · every financial document issued · every stock adjustment · credit-limit override · sync batch outcome with counts · every unhandled exception with a stack trace.

### 12.3 Never logged

Passwords, tokens, OTP codes, session keys, API keys, full payment instrument data, and **entire request bodies** — the last because a request body will eventually contain one of the others (SEC-3, FR-AUD-006).

### 12.4 Logging is not auditing

| | Logs | Audit (`AuditLog`) |
| --- | --- | --- |
| Purpose | Diagnose problems | Prove what happened |
| Store | stdout → Docker | PostgreSQL |
| Retention | Days | Five years (FR-AUD-007) |
| Mutability | Rotated away | Append-only, never deleted (N-04 spirit, FR-AUD-002) |
| Audience | Engineer | Owner, and any future dispute |

**They are different systems and must not be conflated.** A rotated log file cannot settle an argument about a credit note in eighteen months.

---

## 13. Monitoring Strategy for Version 1

### FD-15 — Three cheap signals now; no observability stack

**Decision.**

| Signal | Tool | Cost | Answers |
| --- | --- | --- | --- |
| **Is it up?** | External uptime monitor hitting `/healthz` every 5 min | Free | The client should never be the one who tells you the server is down |
| **Is it erroring?** | Sentry free tier (or self-hosted GlitchTip) | Free | Which error, how often, which user, full stack trace |
| **Is it healthy?** | Docker healthchecks + `docker compose ps` | Free | Container-level liveness |

Plus a `/healthz` endpoint that verifies database connectivity, disk headroom and the last successful backup timestamp — **not merely that the process is running.** A process that is up but cannot reach its database is down from every point of view that matters.

**Why.** These three answer the only questions that matter at one server and one customer: *is it running, is it failing, and will I hear about it before the client does?* Prometheus, Grafana, Loki and Alertmanager would answer far more — while adding four services to run, secure, update and back up on a box budgeted at ₹600 a month.

**Alternatives.** (a) Full observability stack — correct at Edition 3; roughly triples operational surface today. (b) Nothing — the true default for projects this size, and the reason their outages are discovered by telephone. (c) Hosted APM — recurring cost against A-19.

**Trade-offs.** No historical metrics, no latency percentiles, no capacity trending. Accepted: at this scale, capacity questions are answered by looking, and correctness questions are answered by Sentry.

**Long-term impact.** Sentry from M0 means production defects are seen with a stack trace and a user context, instead of being reported as "app not working."

**Migration cost if changed later.** *Low* — adding Prometheus is additive; no application change beyond exposing metrics.

### 13.1 Alerts — deliberately few

| Condition | Channel | Why only these |
| --- | --- | --- |
| Uptime check fails twice consecutively | Email + SMS | Customer-visible outage |
| Any `CRITICAL` log | Sentry | System-level failure |
| Backup did not complete in 26 hours | Email | §14. **The most under-monitored failure in small systems** — backups fail silently for months and are discovered during a restore |
| Disk above 85% | Email | Media growth is predictable; running out is not recoverable in a hurry |

> **Four alerts, no more.** An alert channel that fires often is an alert channel that gets muted, and a muted channel is worse than none because it creates the belief that something is being watched.

---

## 14. Backup and Recovery Strategy

### FD-16 — Nightly encrypted dump, local WAL archiving, quarterly rehearsed restore

**Decision.**

| Layer | Mechanism | Frequency | Destination |
| --- | --- | --- | --- |
| Logical | `pg_dump -Fc`, encrypted | Nightly | Local, then offsite via `rclone` |
| Continuous | WAL archiving | Continuous | Separate local volume |
| Media | `rclone sync` of `/srv/media` | Nightly | Offsite |
| Config | `.env` and Caddyfile, encrypted | On change | Password manager + offsite |
| **Rehearsal** | **Full restore into a scratch container, verified** | **Quarterly** | — |

Retention: 7 daily · 4 weekly · 12 monthly. **RPO ≈ 1 hour** (WAL, local) / 24 hours (offsite). **RTO ≈ 2 hours** (ADR-012).

**Why.** The dump is the recoverable artefact; WAL narrows the loss window between dumps; offsite covers the case where the host is gone entirely; encryption covers the case where the offsite store is breached. **The rehearsal is the part that is always skipped and is the only part that proves any of it works** — an untested backup is a belief, not a backup (NFR-AVA-002).

**Alternatives.** (a) Provider snapshots only — convenient, but ties recovery to one vendor and contradicts hosting-agnosticism. (b) Streaming replication to a standby — gives a 15-minute RPO and near-zero RTO, at roughly double the infrastructure cost (ADR-012). (c) Continuous archiving to object storage (WAL-G, pgBackRest) — better, and the recommended Edition 2 upgrade. (d) Nightly dump only — simpler, RPO becomes 24 hours; rejected as too much loss for a business whose day is its ledger.

**Trade-offs.** Up to one hour of transactions can be lost in a total host failure. For a distributor, that is part of one day's orders, recoverable from paper delivery notes — a real but bounded and survivable cost, declared to the client rather than hidden.

**Long-term impact.** Sets the reliability expectation. Raising it later is a cost decision, not an architectural one.

**Migration cost if changed later.** *Low* — pgBackRest with object storage is roughly two days.

### 14.1 Rules

| # | Rule |
| --- | --- |
| B-1 | A backup that has never been restored does not count as a backup |
| B-2 | Backups are encrypted before they leave the host (S-07) |
| B-3 | **Restore is tested quarterly and the result recorded**, with date and duration, in `docs/runbooks/restore-from-backup.md` |
| B-4 | The restore runbook is written to be followed under stress by someone who did not write it |
| B-5 | Backup failure raises an alert (§13.1). Silence is not success |
| B-6 | Before any risky migration, take a manual backup and verify it (§15) |
| B-7 | Backups are never stored solely on the machine being backed up |

---

## 15. Database Migration Strategy

### FD-17 — Django migrations, forward-only, expand-and-contract, reviewed as carefully as code

**Decision.** Django's migration framework. Migrations are committed with the model change that produced them. Rollback is by **forward** migration, never by reversing in production. Schema changes that could lose data follow expand-and-contract across at least two releases.

**Why.** Reverse migrations are tested rarely and run under pressure — the worst combination. Forward-only means every path into production has been executed at least once in CI. Expand-and-contract means a deploy can be rolled back without the database becoming incompatible with the previous code, which is what makes rollback a real option instead of a theoretical one.

**Alternatives.** (a) Alembic or raw SQL — more control, loses Django's autodetection and its integration with the ORM. (b) Reversible migrations as policy — pleasant in development, unreliable in production. (c) No formal strategy — schema drift, and eventually a production database nobody can reproduce.

**Trade-offs.** Expand-and-contract takes two releases for a rename. That is the price of being able to roll back.

**Long-term impact.** This is the single largest determinant of whether Edition 2 features (batch tracking, multi-warehouse) and Edition 3 tenancy can be delivered without downtime.

**Migration cost if changed later.** *High* — a project with untrustworthy migrations has an untrustworthy schema.

### 15.1 Rules

| # | Rule | Why |
| --- | --- | --- |
| MIG-1 | One logical change per migration | A failed migration should be diagnosable |
| MIG-2 | Never edit a migration that has run anywhere but a developer's machine | Others' databases already applied it |
| MIG-3 | Schema and data migrations are separate files | Different failure modes, different recovery |
| MIG-4 | `migrate --check` is part of `make verify` (§5.2) | Catches a model change with no migration at commit time |
| MIG-5 | Destructive operations require expand-and-contract | §15.2 |
| MIG-6 | Concurrent index creation on large tables | Avoids a write lock on a live system |
| MIG-7 | Manual verified backup before any production migration | B-6 |
| MIG-8 | **No hardcoded schema name; every migration applies cleanly to an empty schema** | N-09 — this is what preserves ADR-007 tenancy |
| MIG-9 | Squash only at a release boundary, never mid-cycle | |
| MIG-10 | Every migration reviewed against this list before merge | It is the least reversible artefact in the codebase |

### 15.2 Expand and contract

```
 Release N     EXPAND    add the new column, nullable; write to both; read old
 Release N+1   MIGRATE   backfill; read new; keep writing both
 Release N+2   CONTRACT  stop writing old; drop it
```

Slower, and the only pattern under which a deploy can be rolled back without the database becoming incompatible with the code that is coming back.

### 15.3 The first migration is special

`0001_initial` establishes the shape everything else inherits. It **must** include:

| # | Requirement | Source |
| --- | --- | --- |
| 1 | `location_id` on `stock_movement`, defaulted to one seeded location | DR-2, N-10, C-14 |
| 2 | `lot_id` on `stock_movement`, defaulted to an implicit per-product lot | DR-4, N-10, C-14 |
| 3 | **No `tenant_id` anywhere** | ADR-007 |
| 4 | No hardcoded schema name | N-09 |
| 5 | `NUMERIC(14,2)` money, `NUMERIC(14,3)` quantity | N-07 |
| 6 | Database `CHECK`: a stock movement has a source document **or** a reason code | BR-007, N-05 |
| 7 | All timestamps `timestamptz`, stored UTC | N-08 |

> **Items 1 and 2 are the entire cost of keeping batch tracking and multi-warehouse as Edition 2 configuration exercises rather than Edition 2 re-architectures.** Two columns and two seeded rows. Omitting them converts a future feature into a migration of live financial history. **This is the highest-leverage paragraph in this document.**

---

## 16. Release Strategy

### FD-18 — Semantic versioning on `main`, tag-triggered, with a written release checklist

**Decision.** `MAJOR.MINOR.PATCH` on the backend. Releases are annotated tags on `main`. The Flutter application carries its own build number and tracks backend minor versions. `CHANGELOG.md` is generated from Conventional Commits (§6.2).

| Bump | When |
| --- | --- |
| MAJOR | Breaking API change — an older mobile build stops working |
| MINOR | New capability, backward compatible |
| PATCH | Fix, no contract change |

**Why.** Field devices will run older application builds after a server release (C-7). SemVer makes the compatibility question answerable: *does this break an older client?* CalVer would not. Tag-triggered releases mean the deployed artefact is identifiable and reproducible.

**Alternatives.** (a) CalVer — good for continuously deployed services with one client; poor when independently versioned mobile builds exist. (b) No versioning — makes "which version is the client on?" unanswerable during an incident.

**Trade-offs.** Discipline about what constitutes a breaking change.

**Long-term impact.** Once the SaaS supports customers on different versions, this is what makes support tractable.

**Migration cost if changed later.** *Trivial* going forward; historical tags cannot be renamed.

### 16.1 API versioning

`/api/v1/` from the first endpoint. **Within v1, changes are additive only** — new optional fields, new endpoints. Removing or renaming a field, or changing its type or meaning, requires `/api/v2/`, with v1 maintained until field devices have upgraded (C-7).

Adding the version segment now costs nothing. Adding it after devices are in the field costs a forced-upgrade campaign across every retailer and salesman.

### 16.2 Release checklist

Runs from `docs/runbooks/deploy.md`:

1. `main` green in CI
2. `CHANGELOG.md` updated
3. Version bumped; annotated tag pushed
4. **Manual backup taken and verified** (B-6)
5. Migrations reviewed against §15.1
6. Deploy: pull image, run migrations, restart, healthcheck
7. Smoke test: login · create order · issue invoice · record payment · mobile sync
8. Sentry watched for 30 minutes
9. Rollback decision point — documented, not improvised

### 16.3 Mobile release

Internal testing track → closed testing with two real salesmen → production. **Never straight to production.** A bad mobile release cannot be rolled back the way a server release can: users have already installed it.

---

## 17. CI/CD Strategy

### FD-19 — Automated CI from day one; deliberately manual CD until it has earned automation

**Decision.**

| | Trigger | Steps | When |
| --- | --- | --- | --- |
| **CI** | Every push and pull request | Secret scan → lint → type check → import contracts → tests → coverage gate → build image → `pip-audit` | **From P0-7, before any application code** |
| **CD** | Manual, from a runbook | `ops/deploy.sh` on a tag | Version 1 |
| **CD (later)** | Tag push | Automated deploy with health-gated rollback | Edition 2 |

**Why CI immediately.** A pipeline added later must be retrofitted against a codebase that has already drifted from the standards it is meant to enforce. Establishing it against an *empty* project means the first violation is caught by the first commit, and the standards are never aspirational.

**Why CD stays manual.** Automated deployment is worth having when releases are frequent and the rollback path is proven. At Version 1, releases are occasional, the operator is the author, and a scripted-but-supervised deploy makes the human present at the moment when things go wrong — which is precisely when judgement is worth more than automation. Automating it now would mean building rollback automation against a system whose failure modes are not yet known.

**Alternatives.** (a) Full CD from day one — plausible; rejected because the rollback path is unproven and a bad automated deploy at 9pm to a live distributor is a worse outcome than a manual one. (b) No CI — the standards in §6 become suggestions. (c) Self-hosted runner — saves nothing at free-tier volumes and adds a machine to maintain.

**Trade-offs.** Manual deployment is a human step that can be forgotten or done out of order. Mitigated by the script and the checklist (§16.2).

**Long-term impact.** The CI definition *is* the enforcement of this constitution. Everything in §6 that CI checks is real; everything it does not check is a hope.

**Migration cost if changed later.** *Low* — automating deployment once the runbook is stable is roughly a day.

### 17.1 Pipeline order and reasoning

| # | Stage | Fails fast because |
| --- | --- | --- |
| 1 | Secret scan (`gitleaks`) | **First.** A leaked secret is the only unrecoverable failure here — everything else can be fixed by another commit |
| 2 | Lint + format (`ruff`) | Seconds; no point testing unformatted code |
| 3 | Type check (`mypy`) | Fast; catches whole classes of defect |
| 4 | Import contracts (`import-linter`) | Enforces N-01 and N-02 mechanically |
| 5 | Unit tests | Fast feedback on business rules |
| 6 | Integration tests | Real Postgres service container |
| 7 | Adversarial tests | Slow; runs last but **blocks merge** |
| 8 | Coverage gate | ≥ 80% (NFR-TST-001) |
| 9 | Build image | Proves the Dockerfile still builds |
| 10 | `pip-audit` | Critical vulnerability blocks (NFR-SEC-009) |

Path filters keep Dart changes off the Python pipeline (FD-06).

---

# PART D — EVOLUTION

## 18. Coding Principles That Let Version 1 Become Version 4 Without a Rewrite

This section is the reason the constitution exists. Everything before it is craft; this is the part that decides whether Version 2 is an extension or a rebuild.

### 18.1 The classification that governs everything

Every decision is one of two kinds. Confusing them is how projects either over-engineer or paint themselves into a corner.

| | **Behaviour** | **Shape** |
| --- | --- | --- |
| What it is | What the code does | How data and boundaries are arranged |
| Examples | A discount rule, a report, a screen | A ledger vs a mutable balance; a column's presence; a module boundary; an API version |
| Cost to add later | Proportional to the feature | Proportional to the **history already written** |
| Rule | **Build only what is needed today** | **Get it right now** |

> **Build no behaviour you do not need. Preserve every shape whose later correction would require rewriting historical data or auditing every call site.**

This is why two columns on `stock_movement` are retained while an entire scheme engine is deferred. The columns are shape; the engine is behaviour.

### 18.2 The eleven evolution principles

---

**E-01 — Ledgers, never mutable balances.**
Stock on hand and party balances are sums over immutable movement and ledger rows (N-03).
*Enables:* batch tracking, multi-warehouse, audit, cost accounting, dispute resolution.
*If violated:* balances drift with no way to reconstruct truth. **Migration cost: Severe** — the history needed to rebuild them was never recorded.

---

**E-02 — Immutable financial documents.**
Issued invoices and credit notes are never edited (N-04). Corrections are new documents.
*Enables:* audit, GST defensibility, dispute resolution, later accounting integration.
*If violated:* the financial record cannot be trusted and no report derived from it can be defended. **Migration cost: Severe.**

---

**E-03 — All business rules in `services.py`.**
Views, serialisers, templates and tasks orchestrate; they never decide (N-01).
*Enables:* adding the retailer portal, the mobile API and any future surface without duplicating a rule. It is why `03` §2 can claim four surfaces and one rule set.
*If violated:* the same rule exists in three places and they diverge silently — the classic cause of "the app gives a different price to the website." **Migration cost: High.**

---

**E-04 — Modules communicate only through services.**
No cross-module model import (N-02), enforced by `import-linter` in CI.
*Enables:* extracting a module into a service at Edition 3 by replacing one function with an HTTP client.
*If violated:* the monolith becomes a ball of mud and extraction requires untangling every query. **Migration cost: High.**

---

**E-05 — Schema-agnostic migrations.**
No hardcoded schema name; every migration applies to an empty schema (N-09, MIG-8).
*Enables:* schema-per-tenant SaaS (ADR-007) with **no `tenant_id` column and no query-filter discipline forever.**
*If violated:* multi-tenancy requires either retrofitting a tenant column across every table and query — where one missed `WHERE` is a cross-tenant data leak — or a database per customer with all its operational cost. **Migration cost: Severe.**

---

**E-06 — The three structural dimensions on `stock_movement`.**
`location_id` and `lot_id`, defaulted, from `0001_initial` (N-10, §15.3).
*Enables:* multi-warehouse and batch/expiry as Edition 2 configuration.
*If violated:* adding them later re-keys the most sensitive table in the system, along with every balance query and any cached balance. **Migration cost: High**, against a cost today of two columns.

---

**E-07 — API versioned from the first endpoint.**
`/api/v1/`; additive changes only within a version (§16.1).
*Enables:* server evolution while old field devices keep working (C-7).
*If violated:* every breaking change becomes a forced-upgrade campaign across every salesman and retailer. **Migration cost: Medium**, plus reputational cost with the client's customers.

---

**E-08 — Configuration as data, not code.**
Tax rates, reason codes, credit limits, offer text, number series are tier-3 rows (FD-12).
*Enables:* the domain-agnostic core (C-12) and therefore the Edition 3 vertical-packs model — the entire commercial thesis of this product.
*If violated:* every industry needs a code fork, and the SaaS business is impossible. **Migration cost: High** per hardcoded rule.

---

**E-09 — Idempotent write endpoints.**
Every mutating endpoint accepts a client-generated key and is safe to retry (BR-012).
*Enables:* offline sync, retry on flaky networks, and the extension to field order capture in Edition 2 — where the endpoints already exist and only new conflict classes are added.
*If violated:* duplicate orders and duplicate payments on retry — silent financial corruption on exactly the connections this product is built for. **Migration cost: Medium.**

---

**E-10 — UTC everywhere, `Decimal` for money.**
Storage and computation in UTC (N-08); money and quantity never floating point (N-07).
*Enables:* correctness across timezones and rounding; a prerequisite for any accounting integration.
*If violated:* invoices are wrong by paise, then by rupees, and reconciliation becomes impossible. **Migration cost: High** — historical values must be recomputed, and some cannot be.

---

**E-11 — No abstraction before the second caller.**
No interface, base class, plugin registry or strategy pattern is introduced for a hypothetical future implementation.
*Enables:* a codebase that stays small enough for one person to hold in mind.
*If violated:* speculative generality — the failure mode where the framework built for future flexibility is the thing that must be removed to add the feature. **Migration cost: Medium** to remove, and the whole time it exists it slows every change.

---

### 18.3 The two principles in tension

E-06 says carry unused columns. E-11 says build no unused abstraction. These look contradictory and are not:

| | E-06 (carry it) | E-11 (do not build it) |
| --- | --- | --- |
| Concerns | A **data dimension** | **Code structure** |
| Cost today | A column and a seeded row | Interfaces, indirection, tests, comprehension |
| Cost of adding later | Rewriting historical rows | Writing the code you would have written anyway |
| Verdict | **Carry it** | **Do not build it** |

**The test:** *if I add this later, must I rewrite data that already exists?* Yes → carry the shape now. No → wait.

Applied honestly, this test produced exactly two carried columns and zero speculative frameworks. That ratio is the point.

### 18.4 Edition upgrade paths this preserves

| Edition 2 feature | Enabled by | Work required then |
| --- | --- | --- |
| Batch / expiry tracking | E-06 | Set tracking policy, build UI and expiry reports |
| Multi-warehouse | E-06 | Location UI, transfers, per-location reporting |
| Field order capture | E-09, E-03 | Four conflict classes and a resolution console on an existing outbox |
| Scheme engine | E-08, E-03 | Scheme model and evaluation inside existing price resolution |
| Purchase orders | E-01 | New documents feeding the existing stock ledger |
| **Edition 3: SaaS tenancy** | **E-05** | **Connection routing and provisioning. No schema change** |
| Edition 3: service extraction | E-04 | Replace a service call with an HTTP client |

---

## 19. Milestone-Based Implementation Roadmap

Phase 0 is this document plus §2.6. Implementation milestones follow `02` §23.1, extended with the release phasing of `02A` §13.3.

### 19.1 Roadmap

| Phase | # | Milestone | Delivers | Depends on | Effort |
| --- | --- | --- | --- | --- | --- |
| **0** | P0 | **Engineering Foundation** | Repo, Docker, CI, standards, secrets, ADR process, DLT started | — | — |
| **1a** | M0 | **Foundation** | Base model, audit, identity, roles, OTP login, `0001_initial` with §15.3 | P0 | 1.5 |
| | M1 | Master data | Products (pack size, tax rate, image), customers, zones, reason codes | M0 | 2.5 |
| | M2 | Inventory core | Stock movements, derived on-hand, stock in/out, reason-coded adjustment | M1 | 2.5 |
| | M3 | Pricing | Selling price, manual bounded discount, price resolution in `CORE` | M1 | 1.0 |
| | M4 | Orders (web) | Owner capture, 5-state lifecycle, credit limit, edit, cancel | M2, M3 | 2.0 |
| | M5 | Fulfilment & billing | Assign, dispatch, stock issue, GST invoice, number series, PDF, credit note | M4 | 3.0 |
| | M6 | Receivables | Customer ledger, payments, derived balance, statement | M5 | 1.5 |
| | M7 | Reporting | Six plain-table reports, CSV export | M6 | 1.5 |
| | M8 | Mobile app | Flutter shell, auth, delivery, visits, GPS, photo, local outbox | M5 | 3.0 |
| | M9 | Sync | Push/pull, idempotency, ordering, sync status | M8 | 2.0 |
| | M10 | Hardening | Performance, security review, adversarial suite, restore rehearsal | M9 | 1.5 |
| | M11 | **Go-live** | Deploy, opening balances, training, Play Store | M10 | — |
| **1b** | M12 | Retailer role | Login, browse, place order, view bills and status | M11 live | 3.0 |
| **2** | — | Professional | Schemes, SMS, targets, field orders, purchasing | Edition 1 proven | +36.5 |

Effort units are relative to `02A` §13.4, where the whole platform is 100 and Edition 1 is 22.

### 19.2 Gates between milestones

| Gate | Condition |
| --- | --- |
| P0 → M0 | This document ratified; CI green on an empty project; `make verify` works |
| M0 → M1 | `0001_initial` reviewed against §15.3. **Signed off explicitly** |
| M4 → M5 | Order lifecycle covered by tests including every invalid transition |
| M8 → M9 | Outbox survives kill, restart and storage exhaustion |
| M9 → M10 | Adversarial sync suite passes: zero loss, zero duplicates |
| M10 → M11 | Restore rehearsed and recorded (B-3); security review complete |
| M11 → live | Opening balances loaded and reconciled; owner signed off; training done |

### 19.3 Three risks the roadmap carries

| Risk | Milestone | Mitigation |
| --- | --- | --- |
| **DLT/SMS approval delays OTP login** | M0, M8 | P0-8 starts registration now. Fallback in §2.4 |
| **`0001_initial` ships without the structural columns** | M0 | Explicit sign-off gate; §15.3 checklist; this is unrecoverable cheaply |
| **Offline sync proves harder than estimated** | M9 | ADR-013 already removed the hard half. Adversarial suite is written before the feature is called done |

---

## 20. The First Engineering Milestone After This Foundation

### M0 — Foundation

**Not the most interesting milestone. By a wide margin the most consequential.**

Every later milestone writes data through the schema M0 establishes and inherits the base classes M0 defines. It is small in effort (1.5 units of 22) and unrecoverable in error: a missing column in `0001_initial` is not a schema addition later, it is a migration of live financial history.

### 20.1 Scope

| # | Deliverable | Traces to |
| --- | --- | --- |
| 1 | `platform` module: `TimeStampedModel`, `AuditLog` (append-only), storage seam, permission base | BR-002, N-04 |
| 2 | `identity` module: `User`, `Role`, four seeded roles, session auth (web), JWT (mobile) | FR-IAM-001…016 |
| 3 | **OTP login by mobile number**, provider behind a thin interface | V1 client scope, A-02 |
| 4 | Server-side authorisation enforced in `services.py` | N-06, BR-003 |
| 5 | **`0001_initial` satisfying every item of §15.3** | C-14, N-09, N-10 |
| 6 | `/healthz` — database, disk, last backup | §13 |
| 7 | Structured JSON logging with request-ID correlation | §12 |
| 8 | Sentry wired | §13 |
| 9 | Adversarial test: full role × capability matrix issued directly to the API | §6.4 |
| 10 | `docker compose up` on a clean machine produces a working, migrated, logged-in system | N-12 |

### 20.2 Explicitly NOT in M0

No products. No customers. No orders. No invoices. No stock. No UI beyond login and a placeholder shell.

**M0 delivers the floor everything stands on, and nothing that stands on it.** The temptation to "just add products while we're here" is the temptation that turns a verifiable foundation into an unverifiable half-feature.

### 20.3 Definition of Done for M0

| # | Criterion |
| --- | --- |
| 1 | `git clone && make up` yields a running, migrated system on a machine that has never seen the project |
| 2 | A user can log in by OTP on mobile and by password on web |
| 3 | Every role's permissions verified **directly against the API**, bypassing all clients |
| 4 | Every state change writes an `AuditLog` row; no code path can delete or edit one |
| 5 | `0001_initial` reviewed line by line against §15.3 and **signed off** |
| 6 | `make verify` passes from a clean build |
| 7 | CI green including secret scan, type check and import contracts |
| 8 | `/healthz` returns non-200 when the database is stopped |
| 9 | Logs are JSON, correlated, and contain no secret |
| 10 | An error raised in the app appears in Sentry with a stack trace |
| 11 | ADRs written for every decision taken during M0 |
| 12 | `04_Database_Design.md` updated to match what was actually built |

### 20.4 What must be true before M0 starts

| # | Precondition | Task |
| --- | --- | --- |
| 1 | This document ratified | P0-10 |
| 2 | Repository in WSL2, on GitHub, protected | P0-1, P0-2 |
| 3 | Docker stack starts and passes healthcheck | P0-5 |
| 4 | CI green on an empty project | P0-7 |
| 5 | Pre-commit hooks active including `gitleaks` | P0-6 |
| 6 | Secrets created and stored | P0-4 |
| 7 | **SMS/DLT registration submitted** | P0-8 |
| 8 | **`04_Database_Design.md` written and approved** | Next document |

> **Precondition 8 matters.** M0 writes `0001_initial`, and `0001_initial` is the least reversible artefact in the entire project. It must be designed on paper and reviewed before it is written in code. **That is the next document, and it is what should be produced after this one is ratified.**

---

## Closing

### Ratification

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Business Owner (Sponsor) | | ☐ Ratified ☐ Changes requested | |
| Product Architect (ChatGPT) | | ☐ Ratified ☐ Changes requested | |
| Chief Systems Engineer (Claude) | | ☐ Ratified ☐ Changes requested | |

Once ratified, this document is amended only through §P.4.

### Decision index

| ID | Decision | § | Migration cost if reversed |
| --- | --- | --- | --- |
| FD-01 | Repository inside WSL2 filesystem | 1 | Trivial |
| FD-02 | All code executes only in Docker | 1 | Low → Medium |
| FD-03 | Pin every version | 1 | Trivial → High |
| FD-04 | `uv` with committed lockfile | 1 | Trivial |
| FD-05 | Tailwind standalone; no Node | 1 | Trivial |
| FD-06 | Monorepo | 4 | Low |
| FD-07 | Makefile as the developer interface | 4 | Trivial |
| FD-08 | Trunk-based branching | 6 | Trivial |
| FD-09 | Mount in dev, copy in prod | 7 | Trivial |
| FD-10 | Multi-stage, non-root, pinned image | 8 | Low |
| FD-11 | Validated 12-factor config | 9 | Trivial |
| FD-12 | Three configuration tiers | 10 | Medium |
| FD-13 | `.env` on server + password manager | 11 | Low |
| FD-14 | Structured JSON logs to stdout | 12 | Low |
| FD-15 | Three monitoring signals, no stack | 13 | Low |
| FD-16 | Nightly dump, WAL, rehearsed restore | 14 | Low |
| FD-17 | Forward-only expand-and-contract migrations | 15 | High |
| FD-18 | SemVer, tag-triggered releases | 16 | Trivial |
| FD-19 | CI now, CD manual until earned | 17 | Low |
| E-01…E-11 | Evolution principles | 18 | Medium → **Severe** |

### The five things that would be most expensive to get wrong

Ranked by cost of reversal, not by effort to do correctly.

| # | Decision | Cost today | Cost of reversal | § |
| --- | --- | --- | --- | --- |
| 1 | Ledgers instead of mutable balances (E-01) | A table and a `SUM` | **Severe** — the history needed is never recorded | 18 |
| 2 | Schema-agnostic migrations (E-05) | Three disciplines | **Severe** — tenancy retrofit or a database per customer | 18 |
| 3 | Immutable documents (E-02) | Withholding an update path | **Severe** — the financial record is unprovable | 18 |
| 4 | `location_id` + `lot_id` in `0001_initial` (E-06) | **Two columns** | **High** — migration of live financial history | 15.3 |
| 5 | Business rules only in `services.py` (E-03) | Discipline | **High** — the same rule in four surfaces, diverging | 18 |

**Four of the five cost effectively nothing today.** That asymmetry is the entire argument of this document.

### Glossary

| Term | Meaning |
| --- | --- |
| **Behaviour** | What the code does. Cheap to add later |
| **Shape** | How data and boundaries are arranged. Expensive to change once history exists |
| **Structural enabler** | A data dimension carried now for a capability delivered later (E-06) |
| **Expand and contract** | Multi-release schema change that stays rollback-safe (§15.2) |
| **Docker verification** | `make verify` on a clean build. The only authority (N-12) |
| **Adversarial test** | A test that deliberately abuses the system, for requirements ordinary tests cannot verify |
| **Tier-3 configuration** | Business rules the owner edits as data, never as code (FD-12) |
| **`services.py`** | A module's only public interface; the sole location of business rules (N-01) |

---

*No application code, database table, API or user interface has been produced or authorised. The next document is `04_Database_Design.md`, and it must be approved before M0 begins.*
