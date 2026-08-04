# Changelog

Generated from Conventional Commits (`00` §6.2). Versions follow SemVer (FD-18).

## [Unreleased]

### M0 — Foundation

**Added**

- Project scaffolding: Docker Compose (dev/prod), multi-stage non-root image, Caddy with
  automatic TLS, Makefile as the sole developer interface, GitHub Actions CI.
- `core` module: `TimeStampedModel`, append-only `AuditLog`, exact numeric field types,
  request-id correlation middleware, role primitives, storage seam, `/healthz`.
- `identity` module: custom user model keyed on mobile number, four seeded roles,
  many-to-many role assignment, OTP request/verify with hashed codes and rate limiting,
  password authentication, SMS provider interface (console / MSG91).
- `api/v1`: six authentication endpoints, RFC 9457 problem+json error handling,
  page-number pagination, scoped throttling.
- `webadmin`: server-rendered login, logout and placeholder shell.
- Structured JSON logging to stdout with request-id correlation; Sentry wiring.
- Runbooks: deploy, restore, rotate secrets, incident response, migration review.
- 47 tests across unit, integration and adversarial suites.

**Security**

- Argon2 password hashing; OTP codes stored hashed, never plaintext.
- `audit_log` immutability enforced in Python, by database trigger, and by test.
- Production settings refuse to start on unsafe configuration.
- Three-layer secret scanning: `.gitignore`, pre-commit, CI.
