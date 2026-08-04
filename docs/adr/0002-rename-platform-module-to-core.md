# 0002 — Rename the `platform` module to `core`

Status: Accepted
Date: 2026-08-04
Deciders: Chief Systems Engineer
Amends: `00_Engineering_Foundation.md` §4.1, `03_System_Architecture.md` §2.1

## Context

The frozen design names the shared base module `platform` (`00` §4.1, `03` §2.1 module table).

`platform` is a **Python standard library module**. `manage.py` lives in `backend/`, so `backend/`
becomes `sys.path[0]`. A package at `backend/platform/` therefore shadows the standard library for
the entire process:

```
$ mkdir -p shadow/platform && touch shadow/platform/__init__.py
$ cd shadow && python -c "import platform; print(platform.__file__)"
/tmp/shadow/platform/__init__.py      # <- not the stdlib
```

Django imports `platform` in `django.db.backends`, `django.core.management` and
`django.utils.version`. The project would fail on the first `manage.py` invocation, and the error
would point at Django internals rather than at the cause.

This is a naming defect in the frozen design, not an architectural change. It was found before any
code was written.

## Options

1. **Rename to `core`** — conventional in Django projects, no stdlib collision.
2. Rename to `common` / `foundation` / `base` — equally safe, less conventional.
3. Keep `platform` and manipulate `sys.path` — fragile, surprising, and breaks any tool that
   assumes a normal import path.
4. Keep `platform` and nest it deeper (`backend/apps/platform/`) — works, but changes the module
   layout of every app for the sake of one name.

## Decision

Rename the module to `core`. Everything else about the module is unchanged: it owns
`TimeStampedModel`, `AuditLog`, the storage seam, the permission base and shared field types, and
it is depended upon by every other module (`03` §2.1).

**Terminology note.** The Django app `core` is distinct from `CORE` in the documents, which denotes
the server side generally (`02` §2.3, `05` §10.2). Code says `core`; prose says `CORE`.

## Consequences

Positive: the project starts. Negative: `00` §4.1 and `03` §2.1 now differ from the code until
amended, which this ADR records.

## Migration cost if reversed

Severe — reversing means reintroducing the defect.
