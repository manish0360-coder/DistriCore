# Project State

| | |
| --- | --- |
| Phase | **Phase 1 — Implementation** |
| Current milestone | **M0 — Foundation** — verified 8/8, tagged `m0-foundation` |
| Next milestone | M1 — Master data (products, customers, zones) |
| Edition | 1a |
| Design corpus | `docs/00`–`05`, frozen |

## Milestones

| # | Milestone | State |
| --- | --- | --- |
| P0 | Engineering Foundation | Complete (repo, Docker, CI, standards, ADRs) |
| M0 | Foundation — identity, roles, OTP, audit, health, logging | **Verified & tagged** — see `docs/M0_Verification_Report.md` |
| M1 | Master data | Not started |
| M2 | Inventory core | Not started |
| M3 | Pricing | Not started |
| M4 | Orders (web) | Not started |
| M5 | Fulfilment & billing | Not started |
| M6 | Receivables | Not started |
| M7 | Reporting | Not started |
| M8 | Mobile app | Not started |
| M9 | Sync | Not started |
| M10 | Hardening | Not started |
| M11 | Go-live | Not started |
| M12 | Retailer role (Edition 1b) | Not started |

## Technical debt

Tracked in `docs/M0_Verification_Report.md` §6. Two items are scheduled into M1:

| # | Item | Due |
| --- | --- | --- |
| TD-1 | Commit `uv.lock` — builds are not yet byte-reproducible (FD-03, FD-04) | M1 |
| TD-5 | `app_user.customer_id`, deferred until the customer table exists | M1 |

## Open items carried forward

| # | Item | Owner | Blocks |
| --- | --- | --- | --- |
| P0-8 | **SMS / DLT registration submitted** — unbounded external lead time | Business | M8 go-live |
| CF-1 | Statutory e-invoicing obligation confirmed? | Business | M5 |
| K-1 | Android upload keystore generated and backed up twice | Engineering | M8 |
| I-01…I-12 | Irreversible decisions signed off (`04` §17) | All | M2 schema |

## Amendments to the frozen corpus

| ADR | Amends | Summary |
| --- | --- | --- |
| 0002 | `00` §4.1, `03` §2.1 | `platform` module renamed `core` — it shadowed the stdlib |
| 0003 | — | `django.contrib.admin` excluded — it bypasses the service layer |
| 0004 | `00` §15.3, §20.1 | §15.3 is a per-table checklist; stock columns bound to M2 by a CI gate |
