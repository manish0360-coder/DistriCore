# Runbooks

Operational procedures, written **before** they are needed. A restore procedure first
written during an outage is not a procedure (`00` §4.3).

| Runbook | Use when |
| --- | --- |
| [deploy](deploy.md) | Shipping a release |
| [first-owner](first-owner.md) | **Nobody can sign in.** A new installation, or an owner locked out of a live one (FR-IAM-014) |
| [go-live-data](go-live-data.md) | **ACT-E** — loading and reconciling the opening position at go-live |
| [restore-from-backup](restore-from-backup.md) | Quarterly rehearsal, or a real recovery |
| [android-keystore](android-keystore.md) | **K-1** — generating and backing up the release keystore. **Once, ever**; lose it and the app can never be updated |
| [rotate-secrets](rotate-secrets.md) | Rotation, or after a suspected exposure |
| [incident-response](incident-response.md) | Something is wrong in production |
| [migration-review](migration-review.md) | **Every** pull request containing a migration |
