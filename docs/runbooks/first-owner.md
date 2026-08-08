# Runbook — First Owner, and Owner Recovery

**When to use this:** a new installation with nobody who can sign in to the admin, or a
live system whose only owner account is unreachable.

Traces to **FR-IAM-014** (break-glass) and **FR-IAM-005** (a user must hold at least one
role). Sanctioned by ADR-0003, which routes emergency fixes through service functions
rather than a second write path.

---

## The one thing to understand first

**A login is not an authorisation.**

`manage.py createsuperuser` writes a row in `app_user`. That is identity — it lets
`authenticate_password` find you and check your password. The admin then asks a second and
entirely separate question, against `user_role`: *what may this person do?*

`is_superuser = True` does **not** answer it. That flag feeds only `has_perm`,
`has_module_perms` and `is_staff`, none of which DistriCore consults, because ADR-0003
excluded `django.contrib.admin` entirely.

A user with a password and no role authenticates successfully and is then refused with
**"This account cannot sign in here."** That message means authorisation, not credentials.

---

## First install

```bash
make up
make owner PHONE=7903324153 NAME="Mack"
```

You will be prompted for a password. Any spelling of the number works — `7903324153`,
`917903324153` and `+917903324153` are normalised to one canonical form before the lookup.

For a non-interactive install:

```bash
DISTRICORE_OWNER_PASSWORD='...' \
  docker compose -f docker/compose.yml -f docker/compose.dev.yml --env-file .env \
  exec -T app python manage.py bootstrap_owner \
    --phone 7903324153 --full-name "Mack" --noinput
```

`make superuser` still works and is still useful when you want a login without a role — but
on its own it cannot reach the admin, and it now says so.

---

## Recovering owner access

Use this when the owner's account has been deactivated or is otherwise unusable.

```bash
make owner PHONE=9876543210 NAME="Deputy" REASON="owner phone lost, 2026-08-08"
```

`REASON` is **optional and never required.** A mandatory field on a break-glass path fails
closed at the worst possible moment — the business is locked out, and the tool meant to let
them back in refuses over a text box. Give one when you have one.

### What the command will refuse to do

| Situation | Behaviour |
| --- | --- |
| An **active** owner already exists | **Refused.** Use the ordinary role-grant path, which records who granted it |
| The target account is **deactivated** | **Refused.** Granting a role to a deactivated user is a no-op you cannot see — `has_role` checks `is_active` first. Reactivate deliberately, then bootstrap |
| Roles are not seeded | **Refused.** Run migrations |

Note the asymmetry, and that it is deliberate: the command refuses while an *active* owner
exists, but proceeds when the only owner is *inactive*. A guard on "any owner" would lock
the business out of its own system permanently, which is the situation this runbook exists
to end.

---

## What gets recorded

One `audit_log` row per successful bootstrap, with action **`OWNER_BOOTSTRAP`** — its own
code, not `ROLE_GRANT`, so break-glass use is findable without inspecting JSON.

```sql
SELECT occurred_at, after_state
FROM audit_log
WHERE action = 'OWNER_BOOTSTRAP'
ORDER BY occurred_at DESC;
```

`after_state` carries the classification **and the facts it was derived from**:

| Key | Meaning |
| --- | --- |
| `mode` | `FIRST_BOOT` or `RECOVERY` — classified by the service from the database, never from what was typed |
| `users_existing` | How many users existed before the grant |
| `owner_rows_existing`, `inactive_owners` | The owner situation before the grant |
| `user_id`, `phone_suffix` | Who received the role |
| `reason` | Whatever was given, or empty |

`actor_user` is **NULL**, and `user_role.granted_by` is **NULL**. Nobody authorised this
grant; the truthful actor is an operator with shell access, who is unidentifiable. Naming
one would invent them.

**Read `mode` sceptically.** One case makes it debatable: an owner granted, later revoked —
`revoke_role` deletes the row — then bootstrapped, reads as `FIRST_BOOT`. That is why the
counts are recorded beside the label rather than instead of it.

---

## Do not do this instead

**Do not `INSERT` into `user_role` directly.** It was the only option before this command
existed, and it writes no audit row — an unaudited change to authorisation data, which is
precisely what ADR-0003 exists to prevent.

**Do not make `createsuperuser` grant OWNER.** It would make "can run a management command"
equivalent to "has full authority over the business", silently and with nothing in the
audit trail recording when it happened.
