# 0003 — Exclude `django.contrib.admin`

Status: Accepted
Date: 2026-08-04
Deciders: Chief Systems Engineer

## Context

Django's built-in admin is one of the reasons the stack was chosen (`00` §3.1). But ADR-003 already
committed to a purpose-built, server-rendered admin for the owner, and two non-negotiables constrain
what any write path may do:

- **N-01** — all business rules live in `services.py`.
- **N-04** — issued financial documents are immutable; `audit_log` is append-only.

`django.contrib.admin` writes directly through the ORM. It bypasses `services.py` entirely, so a
stock adjustment made in the admin would write no `stock_movement`, and a `ModelAdmin` registered
without care would allow `audit_log` rows to be edited or deleted.

## Options

1. **Do not install it.** No second write path exists.
2. Install it, restricted to superusers, with every model registered read-only. Relies on every
   future model being registered correctly — one omission reopens the hole.
3. Install it unrestricted. Rejected without discussion.

## Decision

`django.contrib.admin` is not installed. Operational data inspection is done through
`manage.py shell` with service functions, or through `psql` for read-only queries.

`django.contrib.auth` **is** installed — it is required by `AUTH_USER_MODEL` and the authentication
backends. Its `auth_permission` and `auth_group` tables are framework-managed and were already
anticipated by `04` §2.3.

## Consequences

Positive: there is exactly one write path into the domain, and it is audited. Negative: no
ready-made CRUD screens for developer convenience; emergency data fixes go through service functions
or a documented `psql` runbook, both of which are the correct paths anyway.

Also: `admin.py` files are omitted from the module template in `00` §4.1.

## Migration cost if reversed

Low to add later — but adding it reopens an unaudited write path into financial data.
