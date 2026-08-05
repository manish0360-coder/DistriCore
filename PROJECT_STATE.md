# Project State

| | |
| --- | --- |
| Phase | **Phase 1 — Implementation** |
| Current milestone | **M1 — Master data** — verified 8/8, 192/192 tests, 93.01% coverage |
| Next milestone | **M2 — Inventory & stock ledger** (plan proposed, not started) |
| Edition | 1a |
| Design corpus | `docs/00`–`05`, frozen |

## Milestones

| # | Milestone | State |
| --- | --- | --- |
| P0 | Engineering Foundation | Complete |
| M0 | Foundation — identity, roles, OTP, audit, health, logging | **Verified & tagged** — `docs/M0_Verification_Report.md` |
| M1 | Master data — zones, customers, products, reason codes, media | **Verified** — `docs/M1_Verification_Report.md` |
| M2 | Inventory core — stock ledger | Plan proposed, awaiting approval |
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

## Verification history

| Milestone | Stages | Tests | Coverage | Contracts |
| --- | :-: | --: | --: | :-: |
| M0 | 8/8 | 100 | 87.3% | 3 kept |
| M1 | 8/8 | **192** | **93.01%** | 3 kept |

## Blocking before M2

| # | Item | Owner |
| --- | --- | --- |
| 1 | **Irreversible decisions I-02 … I-12 signed off** (`04` §17) — M2 writes `stock_movement` | All |
| 2 | TD-1 — confirm `uv.lock` is committed | Engineering |
| 3 | TD-15 — assign a milestone to `offer` (roadmap gap) | Product Architect |

## Technical debt

Full list in `docs/M1_Verification_Report.md` §6. Highest priority:

| # | Item | Due |
| --- | --- | --- |
| TD-12 | No zone create/edit screen — the customer form's zone dropdown is empty on a fresh install | M2 |
| TD-13 | No product image upload in the admin form | M2 |
| TD-11 | **SMS / DLT registration not started — blocks go-live** | Now |
| TD-1 | `uv.lock` committed | Now |

**Closed:** TD-5 (`app_user.customer_id`) in M1.
