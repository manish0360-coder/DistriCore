# Runbook — Incident response

## Triage, in this order

1. `/healthz` — up? database reachable? disk?
2. `docker compose ps` — is a container restarting?
3. `docker compose logs --tail=200 app` — JSON lines; grep the `request_id`.
4. Sentry — stack trace and affected user.

## Common causes

| Symptom | Likely cause | Action |
| --- | --- | --- |
| 503 from `/healthz` | Database down or disk full | `docker compose ps db`; check `checks.disk` |
| App restarting | Migration failed at boot, or a bad `.env` | `docker compose logs app` — prod settings list every misconfiguration by name |
| OTP not arriving | SMS provider or DLT template rejected | Provider dashboard; `DISTRICORE_SMS_PROVIDER` |
| Slow responses | Media disk near full, or an unindexed query | `/healthz` disk; `pg_stat_statements` |
| 401 everywhere after deploy | `DISTRICORE_SECRET_KEY` changed — every token invalidated | Intended if rotated; otherwise restore the key |

## Correlating a user report to a log line

Every response carries `X-Request-Id`. Ask for it, then:

```bash
docker compose logs app | grep '<request-id>'
```

The same value is on the `audit_log` row for that request. A log says *what went
wrong*; the audit says *what happened*; the request id joins them (`00` §12.4).

## Append-only tables — the escape hatch (TD-17)

`audit_log` and `stock_movement` carry `BEFORE UPDATE` and `BEFORE DELETE` triggers. They
are the guarantee behind every derived balance and every historical claim the business
makes. **The trigger is not a code path and must never be disabled from application code.**

### First, it is almost certainly not needed

| Situation | Correct action |
| --- | --- |
| A stock movement is wrong | Post a **compensating movement** with a reason code. The ledger records that a correction happened, which is the point |
| A movement was posted twice | Compensate the duplicate. Do not delete it |
| An audit row is wrong | It is not. An audit row records what happened, including a mistake |
| A migration needs to rewrite history | Stop. Raise an ADR |

### If it is genuinely unavoidable

Requires table ownership, so it cannot be done by the application role. **Two people, one
written justification, and a backup first.**

```bash
# 1. Take and VERIFY a backup. Not optional.
./ops/backup.sh
./ops/restore.sh /srv/backups/<archive> districore_preflight_check

# 2. Record the justification in this file's log below BEFORE touching anything.

# 3. Disable, act, re-enable — in one transaction so a crash cannot leave it off.
psql -U postgres -d districore <<'SQL'
BEGIN;
ALTER TABLE stock_movement DISABLE TRIGGER stock_movement_no_update;
-- the single, specific statement, with a WHERE clause naming exact ids
ALTER TABLE stock_movement ENABLE TRIGGER stock_movement_no_update;
COMMIT;
SQL

# 4. Verify the trigger is back on.
psql -U postgres -d districore -c "\d+ stock_movement" | grep -i trigger
```

### Log — every use, without exception

| Date | Table | Rows | Justification | Authorised by | Backup verified |
| --- | --- | --- | --- | --- | :-: |
| | | | | | |

> An empty log is the expected state. A non-empty log is a signal that something upstream
> needs fixing, not that the procedure is working.

## Escalation

Data loss or suspected data corruption → **stop writes first**, take a backup of the
current state before any repair. A repair performed on the only copy is not a repair.
