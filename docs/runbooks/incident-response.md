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

## Escalation

Data loss or suspected data corruption → **stop writes first**, take a backup of the
current state before any repair. A repair performed on the only copy is not a repair.
