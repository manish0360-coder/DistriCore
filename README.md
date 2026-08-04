# DistriCore

Sales & Distribution Management Platform. Version 1 serves a single distributor; the same codebase
is designed to become a commercial SaaS product (`docs/01_Project_Vision.md`).

## Run it

Requires Docker and Docker Compose v2. Nothing else — the application never runs outside a
container (`docs/00_Engineering_Foundation.md` FD-02).

```bash
cp .env.example .env
make up          # build, migrate, start
make verify      # the ONLY authoritative check (N-12)
```

Web admin: <http://localhost:8000/> · Health: <http://localhost:8000/healthz>

`make help` lists every command.

## Where the documents are

The design corpus in `docs/` is the source of truth. Where code and documents disagree, the
documents win until formally amended (C-1).

| Document | Contents |
| --- | --- |
| `00_Engineering_Foundation.md` | The project constitution — standards, workflow, non-negotiables |
| `01_Project_Vision.md` | Why the product exists |
| `02_Requirements_Specification.md` | What it must do |
| `02A_Product_Editions.md` | What is built when, and what it costs |
| `03_System_Architecture.md` | How it is structured |
| `04_Database_Design.md` | The schema |
| `05_API_Contracts.md` | The API |
| `adr/` | Decisions and their reasoning |

## Status

**M0 — Foundation.** Identity, OTP login, roles, audit, health, logging. No business features yet
(`00` §20.2).
