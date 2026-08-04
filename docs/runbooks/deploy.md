# Runbook — Deploy

Manual by decision until automation has earned it (FD-19). The operator is present at
the moment things go wrong, which is when judgement is worth more than automation.

## Before

1. `main` is green in CI.
2. `CHANGELOG.md` updated.
3. Version bumped; annotated tag pushed.
4. **Manual backup taken and verified** — `./ops/backup.sh` (B-6, MIG-7).
5. Migrations reviewed against `docs/runbooks/migration-review.md`.

## Deploy

```bash
ssh <server>
cd /opt/districore
git fetch --tags && git checkout <tag>
docker compose -f docker/compose.yml -f docker/compose.prod.yml --env-file .env up -d --build --wait
curl -fsS https://<domain>/healthz
```

Migrations run in the entrypoint under an advisory lock (D-6). No manual step.

## Smoke test — all five, in order

1. Sign in on the web admin.
2. Request an OTP on a test number; verify it.
3. `GET /api/v1/auth/me` returns the expected roles.
4. `/healthz` reports `database.ok` and `disk.ok`.
5. An audit row exists for the login.

## After

- Watch Sentry for 30 minutes.
- Rollback decision point: if unhealthy, `git checkout <previous-tag>` and redeploy.
  **Decide, do not improvise** — that is what the previous tag is for.
