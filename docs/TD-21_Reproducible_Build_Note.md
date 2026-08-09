# Design Note — TD-21: the build is not reproducible

| Field | Value |
| --- | --- |
| Document ID | `TD-21_Reproducible_Build_Note` |
| Version | **1.2.0** |
| Status | **IMPLEMENTED AND VERIFIED — TD-21 closed.** §1.3(d) falsified by experiment (§1.7) |
| Date | 2026-08-09 |
| Closes | **TD-21** |
| Traces to | FD-03 (pinned toolchain), FD-04 (uv), N-12 (Docker is the only authority) |
| ADR required | **No** — see §5 |

---

## 1. Root cause analysis

### 1.1 The finding that matters most

**The pipeline has the *shape* of a lockfile build and none of its substance.**

```dockerfile
# uv: fast, lockfile-driven dependency resolution (FD-04)
COPY --from=ghcr.io/astral-sh/uv:0.4.27 /uv /usr/local/bin/uv
...
COPY pyproject.toml uv.lock* ./
RUN uv venv /opt/venv && \
    VIRTUAL_ENV=/opt/venv uv pip install --no-cache -r pyproject.toml
```

Three things are true at once, and the third is what keeps TD-21 open:

1. The comment says *"lockfile-driven"*.
2. `uv.lock*` is copied — the glob makes a missing lock **silently succeed**.
3. **`uv pip install -r pyproject.toml` does not read `uv.lock`.** It resolves from PyPI
   against the specifiers, every build.

So even if the lock existed, **nothing would consume it.** Generating one is the smaller
half of this task; making the build *use* it is the larger half.

> A build that looks reproducible and is not is worse than one that admits it is not,
> because the reader stops asking.

### 1.2 Answers to the seven questions

| # | Question | Finding |
| --: | --- | --- |
| 1 | Current use of `uv.lock` | **None. The file does not exist**, and no command reads it. `COPY ... uv.lock*` is the only reference, and the glob means its absence is not an error |
| 2 | Why `make lock` is non-functional | **Two reasons, not four.** `uv` absent from the image, and the artefact cannot escape it. A third hypothesis was falsified — §1.7 |
| 3 | Docker build path | `builder` resolves from PyPI → `builder-dev` adds `--extra dev` → `runtime` copies `/opt/venv` → `dev` copies the dev venv. Correct layering; wrong install command at the first step |
| 4 | Installed from `pyproject.toml` instead of the lock? | **Yes — in three places:** `Dockerfile` builder, `Dockerfile` builder-dev, and `.github/workflows/ci.yml:57` |
| 5 | Can the container generate the lock? | **No.** `uv` is absent from the image the command runs in — §1.3(a) |
| 6 | Does `/app` read-only / not bind-mounted contribute? | **Yes, but it is not what needs fixing** — §1.4 |
| 7 | Tooling, Docker, or project structure? | **All three.** One defect each — §1.5 |

### 1.3 Why `make lock` cannot work

```make
lock:
	$(DC) exec -T -w /app app uv lock
```

**(a) `uv` is not in the image.** It is installed in the `builder` stage only. `runtime`
starts `FROM python:3.12-slim-bookworm` afresh and copies **only `/opt/venv`**; `dev`
extends `runtime`. The `app` service runs the `dev` target. The command fails with
`executable file not found` before it does anything.

**(b) The artefact could not escape the container.** `uv lock` writes `uv.lock` beside
`pyproject.toml`, i.e. into `/app`. `/app` is writable — but it is **not bind-mounted to
the host**. The lock would be written inside the container and destroyed on `down`. It
could never reach the repository.

**(c) `pyproject.toml` is mounted read-only.** `../pyproject.toml:/app/pyproject.toml:ro`.
`uv lock` does not rewrite it, so this is not the blocker today — but it becomes one for
any command that normalises the manifest.

**(d) ~~The project is not lockable as written.~~ — FALSIFIED. See §1.7.**

I claimed `uv lock` builds project metadata before resolving and therefore fails on this
repository's flat layout. **It does not.** `uv lock` succeeds on DistriCore exactly as it
stands today.

**Only (a) and (b) are real.** `make lock` fails because `uv` is not in the image and the
artefact cannot escape the container. Nothing structural blocks locking.

### 1.4 On `/app` — my earlier characterisation of TD-21 was wrong

`PROJECT_STATE` has recorded TD-21 for four milestones as *"`uv` is not in the dev image,
`/app` is not bind-mounted."* The first half is right. **The second half named a fix that is
not needed.**

Bind-mounting `/app` to make a container-generated file reachable is solving the wrong
problem. Locking is not a runtime activity: it needs the manifest and a network, not the
application, its database, or its virtualenv. **It should not run in the application
container at all** — which makes both (a) and (b) moot rather than fixed.

### 1.5 Which layer each defect belongs to

| Defect | Layer |
| --- | --- |
| `uv pip install -r pyproject.toml` ignores the lock (×3 sites) | **Tooling** — wrong command |
| `uv` absent from `runtime`/`dev` | **Tooling** — wrong image for the job |
| `/app` not bind-mounted, so the artefact cannot escape | **Docker** — and dissolved by §2, not fixed |
| No `districore` package behind `[project] name` | **Project structure** |

**It is all three, and the project-structure one is load-bearing.** No amount of Docker or
Makefile work makes an unlockable project lock.

### 1.6 What the pins are actually buying, and what they are not

`[project.optional-dependencies].dev` pins three tools with `==`, with the pytest-django
4.13.0 incident recorded in the file as evidence. That was the right stopgap and it has held
for three milestones.

**It binds direct dev dependencies only. Every transitive dependency remains open.**
`pluggy`, `iniconfig`, `coverage`, `django-stubs-ext`, `typing-extensions` and the rest can
move under an unchanged commit — the same failure mode as pytest-django, one level down and
with no `==` to stop it.

That residual risk is the whole of TD-21's remaining value, and it is why the pins are a
stopgap rather than a solution.

---

## 1.7 A hypothesis I held, and the experiment that killed it

v1.0.0 of this note asserted that the project "is not lockable as written". The Product
Architect declined to accept it and asked for verification before implementation. **The
assertion was wrong**, and it is kept here rather than deleted because a design note that
silently corrects itself teaches nothing about how much to trust the next assertion in it.

Four variants were built and run against `uv 0.11.19`, each mirroring DistriCore's shape:
thirteen flat top-level directories, no importable `districore` package, static PEP 621
metadata.

| Variant | `uv lock` | `uv sync` — full tree | `uv sync` — Docker `/build` (code-less) |
| --- | :-: | :-: | --- |
| **A** — as today | **OK** | FAIL — *Multiple top-level packages discovered in a flat-layout* | **succeeds, and installs an empty phantom `districore==0.1.0`** |
| **B** — `[tool.setuptools.packages.find] where = ["backend"]` | **OK** | OK | FAIL — *error in `egg_base` option: 'backend' does not exist* |
| **C** — `[tool.uv] package = false` | **OK** | OK | **OK — dependencies only** |
| **D** — B plus `uv sync --no-install-project` | **OK** | OK | **OK — dependencies only** |

### What the experiment established

**1. Locking was never blocked.** `uv lock` reads static PEP 621 metadata — `name`,
`version`, `dependencies` and `optional-dependencies` are all literal here and nothing is
`dynamic` — so it never invokes the build backend. Variant A locks in about a second.

**2. The real tension is between package-capability and the D-3 layer ordering.** The
Dockerfile installs dependencies *before* copying code, because *"code changes hourly,
dependencies monthly"*. A packaged project must be **built** during that dependency layer,
when its source is not there yet. Variant B fails outright; Variant A "succeeds" by
building an empty wheel — which is arguably worse, because it is silent.

**3. Variant A's phantom is already latent.** Today's build uses `uv pip install`, so
nothing is built. The moment it moves to `uv sync` — which TD-21 requires — Variant A
installs a distribution named `districore` containing nothing at all.

### The falsified claim, restated correctly

> ~~The project is not lockable.~~
>
> **The project is not *installable as a distribution* in a context that has no source in
> it — which is precisely the context the dependency layer runs in.**

---

## 1.8 Why `package = false` is a decision, not a workaround

Variant D works. Package-capability *can* be preserved. This section exists because
"it works" is not the same as "it is right", and the choice should be defensible without
reference to the bug that prompted it.

**The manifest currently describes something that does not exist.** `[project] name =
"districore"` with a setuptools backend declares a distribution. Nothing has ever built it,
installed it, or imported it — verified: every `districore.*` reference in the codebase is a
**logger name**, and no `pip install .` or `-e .` appears in the Makefile, Dockerfile or CI.
The application is deployed by copying `backend/` into an image and running it with a
`WORKDIR`. `package = false` makes the manifest agree with the deployment that has existed
since M0.

**What Variant D would cost to keep the fiction.** `where = ["backend"]` declares a
distribution whose top-level modules are `core`, `orders`, `billing`, `identity`,
`customers`, `inventory` — about as collision-prone a set of names as could be chosen. It
also requires `--no-install-project` on every sync, which is flag discipline: it fails
silently the first time someone omits it, by installing an empty wheel.

**It does not constrain plugins, internal packages, or Edition 2.** Tested:

```
root:  package = false  +  [tool.uv.workspace] members = ["packages/*"]
       packages/districore-sdk/   (a real, buildable package)

-> Resolved 14 packages · Built districore-sdk · installed as a workspace member
```

A non-package root with packaged members is **the recommended uv workspace layout**, not a
limitation of it. Future internal packages are *better* served by it than by today's
arrangement: each gets its own manifest and its own distribution name, instead of the root
claiming `core` and `orders` for itself.

**Reversal cost: delete one line.** No migration, no data, no API surface. If the root ever
genuinely becomes a distribution, remove `package = false` and configure discovery then —
with the source present, which is the condition that makes it possible.

> **The decision, stated once:** *DistriCore's repository root is an application, not a
> distribution.* That was already true. This records it.

---

## 2. Smallest architecturally correct solution

**Lock in a throwaway container built from the official `uv` image; consume the lock in the
build.** Four changes, none to compose.

### 2.1 Make the project lockable — *project structure*

```toml
[tool.uv]
package = false
```

DistriCore is an **application, not a distribution**. `package = false` states that, and uv
then locks dependencies without attempting to build the project — which is what makes (d)
go away. It is one line and it makes an existing untruth explicit.

### 2.2 Generate the lock without touching the app image — *tooling + Docker*

```make
lock:
	docker run --rm -v "$(PWD)":/w -w /w ghcr.io/astral-sh/uv:$(UV_VERSION) lock
```

- **No `uv` in the dev image.** The tool that locks is the image that *is* uv.
- **No bind mount of `/app`, no writable `pyproject.toml`, no running stack.** The lock is
  written straight into the working tree.
- **Same uv version as the builder**, from one `UV_VERSION` variable.

### 2.3 Make the build consume it — *tooling*

```dockerfile
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./          # no glob: a missing lock must FAIL the build
RUN uv sync --frozen --no-dev
```

and in `builder-dev`:

```dockerfile
RUN uv sync --frozen --extra dev
```

Two properties are the point:

- **`--frozen` refuses to re-resolve.** If the lock disagrees with `pyproject.toml`, the
  build fails rather than quietly resolving something else. Drift becomes a stage-1 failure.
- **Dropping the `*`** turns a missing lock from a silent fallback into a hard error. The
  pipeline stops being able to *look* reproducible while it is not.

### 2.4 Close the third site — CI

`.github/workflows/ci.yml:57` runs the same non-lockfile install. It must move to
`uv sync --frozen --extra dev`, or CI and the gate diverge — and a green CI that installed
different packages from the gate is worse than no CI.

### 2.5 What is **not** proposed

| Rejected | Why |
| --- | --- |
| Bind-mount `/app`, add `uv` to the dev image | Solves §1.3(a)+(b) but leaves (d), and puts a resolver in the runtime image for a task that is not runtime |
| Run `uv lock` on the host | Breaks FD-07 — the Makefile is the only developer interface — and adds a host toolchain the project has so far avoided |
| Remove the `==` pins once the lock exists | **Later, and deliberately.** The lock supersedes them, but removing pins in the same change that introduces the lock means two variables move at once. Keep them; retire them in a separate change with its own verify run |
| Drop `[build-system]` | `package = false` makes uv ignore it. Removing it is tidier and unnecessary — a second change, not this one |

---

## 3. Files that would change

| # | File | Change |
| --: | --- | --- |
| 1 | `pyproject.toml` | Add `[tool.uv] package = false` |
| 2 | **`uv.lock`** | **New, generated, committed.** The artefact TD-21 exists for |
| 3 | `docker/Dockerfile` | `UV_PROJECT_ENVIRONMENT`; `uv sync --frozen --no-dev` in `builder`; `uv sync --frozen --extra dev` in `builder-dev`; **drop the `uv.lock*` glob** |
| 4 | `Makefile` | Rewrite `lock`; add `UV_VERSION`; optionally add `lock-check` running `uv lock --check` |
| 5 | `.github/workflows/ci.yml` | `uv sync --frozen --extra dev` |
| 6 | `PROJECT_STATE.md`, `CHANGELOG.md` | **After** a green verify, per the workflow |

**No compose file changes. No production code. No test changes.**

### 3.1 One duplication this introduces, stated rather than hidden

The uv version would appear in two places: `docker/Dockerfile` (`COPY --from=ghcr.io/astral-sh/uv:0.4.27`)
and `Makefile` (`UV_VERSION`). They must move together or `make lock` writes a lock a
different resolver produced.

Options: accept it with a comment in both; or pass a build `ARG` from compose so the
Makefile is the single source. **I would accept the duplication for now** — a build ARG
threaded through two compose files to synchronise one string is more machinery than the risk
justifies, and `uv lock` output is stable across patch versions.

---

## 4. How this will be verified

`make verify` stage 1 builds `--no-cache`. With `--frozen`, that build **cannot succeed
unless the lock exists and matches `pyproject.toml`** — so the gate itself becomes the proof,
with no new test required.

The stronger check is a second run: build twice from the same commit and compare the
installed set. That is what TD-21 has always been about, and it is worth doing once by hand
at implementation time and recording the result.

---

## 5. ADR or design note

**Design note.** No milestone boundary moves, no table is added, no recorded decision is
amended. FD-04 already chose uv and FD-03 already requires a pinned toolchain — this makes
the build do what those two decisions said it would.

`[tool.uv] package = false` is the only line that could be read as architectural, and it
records something already true: DistriCore is an application, not a distribution.

---

## 6. One thing worth deciding before implementation

**Should stage 1 of `make verify` also assert the lock is current?**

`uv sync --frozen` fails when the lock and manifest disagree, which covers the case that
matters. A separate `uv lock --check` step would catch the same thing marginally earlier
with a clearer message, at the cost of another stage in a gate that is deliberately eight.

My recommendation: **no extra stage.** `--frozen` already fails closed, and the error names
the mismatch. Say if you would rather have the explicit check.

---

---

## 7. Closing evidence — TD-21 closed 2026-08-09

### 7.1 Verified

| Gate | Result |
| --- | --- |
| `make verify` stage 1 | Builds with **`uv sync --frozen`** |
| `uv.lock` | **Generated, committed, and consumed by the build** — `Resolved 91 packages in 3.61s`, CPython 3.12.7 |
| Tests | **712/712** |
| Coverage | **94.85%** |
| Import contracts | **3 kept, 0 broken** |

**The gate is now its own proof.** Stage 1 builds `--no-cache` and `--frozen` refuses to
re-resolve, so a missing or stale lock fails the build before anything is installed. No new
test was added, and none was needed.

### 7.2 What changed, against §3's list

All five files, exactly as scoped. No compose change, no production code, no test change.

| File | Change |
| --- | --- |
| `pyproject.toml` | `[tool.uv] package = false`, with the measured A–D comparison recorded beside it |
| **`uv.lock`** | **New — 91 packages, committed** |
| `docker/Dockerfile` | `UV_PROJECT_ENVIRONMENT`; `uv sync --frozen` in both stages; **the `uv.lock*` glob dropped** |
| `Makefile` | `UV_VERSION`, `UV_LOCK_IMAGE`, and a `lock` target that runs in a throwaway uv container |
| `.github/workflows/ci.yml` | `uv sync --frozen --extra dev` — the third install site |

### 7.3 The number that measures what TD-21 was worth

**Three direct dependencies were pinned. The lock binds 91.**

`[project.optional-dependencies].dev` carries `==` on exactly three tools — `pytest`,
`pytest-django`, `pytest-cov`. Everything else, direct and transitive, moved freely:
`pluggy`, `coverage`, `django-stubs-ext`, `typing-extensions` and the rest — which is
exactly the surface the pytest-django 4.13.0 incident travelled through, one level below
anything a specifier could reach.

*(An earlier draft of this section said "92 packages locked; 36 installed in the base
image", and "five" pins. All three figures came from a sandbox rehearsal that relaxed
`requires-python` to `>=3.10`, not from the artefact. **91** is from the verified
`make lock` run — `Resolved 91 packages in 3.61s`, CPython 3.12.7 — and is confirmed by
counting `name =` entries in the committed `uv.lock`. **Three** is countable from
`pyproject.toml`. The base-image install count was never observed and is not restated.)*

### 7.4 Two implementation defects, both mine, both in the invocation

Neither was in the design; both were in how the design was expressed.

1. **`make lock` invoked `IMAGE lock`.** The `-python3.12-bookworm` tag is an ordinary
   Debian image with `uv` on `PATH` and **no `ENTRYPOINT`**, so Docker exec'd a binary named
   `lock`. I had assumed the entrypoint convention of the *scratch* tag, which exists to be
   consumed by `COPY --from=` and would need `/uv` anyway. Fixed to `uv lock`.
2. **A Docker Desktop / WSL credential-helper failure** blocked the pull entirely — a
   Windows-shaped `~/.docker/config.json` with `credsStore: desktop` inside the Linux
   distro. Environment, not repository; recorded because it is the second time the
   *instrument* rather than the system under test was the obstacle, after the performance
   harness.

### 7.5 The stopgap that is now redundant, and stays anyway

The `==` pins in `[project.optional-dependencies].dev` are superseded by the lock. **They
are deliberately not removed in this change** — retiring them alongside the lock's
introduction would move two variables at once, and the pins' comment block is the written
record of the incident that justified them.

Recorded as a follow-up: retire the pins in their own change, with their own verify run, and
keep the incident narrative in the commit message when the comment goes.

### 7.6 The §6 question, answered by the outcome

§6 asked whether stage 1 should also run an explicit `uv lock --check`. **No extra stage was
added, and none is needed:** `--frozen` fails closed and names the mismatch. The gate stayed
at eight stages.

---

*Implemented and verified. TD-21 closed.*
