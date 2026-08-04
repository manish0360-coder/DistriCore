# Runbook — Rotate secrets

Written **before** production, not after an incident (SEC-6).

> **If a secret has ever been committed, it is compromised.** The response is
> rotation, not history rewriting — rewriting history does not un-fetch a clone (SEC-7).

| Secret | Effect of rotating | Procedure |
| --- | --- | --- |
| `DISTRICORE_SECRET_KEY` | **All sessions and all JWTs invalidate.** Every user re-authenticates | Generate 64 random chars, update `.env`, restart. Announce first |
| `POSTGRES_PASSWORD` | Brief downtime | `ALTER ROLE districore WITH PASSWORD '…'`, update `.env`, restart |
| SMS API key | None if done in order | Create the new key at the provider, update `.env`, restart, then revoke the old |
| Server SSH key | Lockout risk | Add the new key, verify login in a second session, **then** remove the old |
| Backup passphrase | **Old archives stay encrypted with the old passphrase** | Keep both until every archive under the old one has expired |
| Android upload keystore | **Cannot be rotated** | K-1. There is no procedure. This is why it is backed up twice |

## After any rotation

1. Update the password manager entry.
2. Restart affected services and confirm `/healthz`.
3. Record the date here.
