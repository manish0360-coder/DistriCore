# Project State

| | |
| --- | --- |
| Phase | **Phase 1 — Implementation** |
| Current milestone | **M2 — Inventory & stock ledger** — verified 8/8, 245/245 tests, 93.56% coverage |
| Next milestone | **M3 — Pricing** (not started) |
| Edition | 1a |
| Design corpus | `docs/00`–`05`, frozen |

## Milestones

| # | Milestone | State |
| --- | --- | --- |
| P0 | Engineering Foundation | Complete |
| M0 | Foundation — identity, roles, OTP, audit, health, logging | **Verified & tagged** — `docs/M0_Verification_Report.md` |
| M1 | Master data — zones, customers, products, reason codes, media | **Verified & tagged** — `docs/M1_Verification_Report.md` |
| M2 | Inventory — stock ledger | **Verified** — `docs/M2_Verification_Report.md` |
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

| Milestone | Stages | Tests | Coverage | Contracts | Verify cycles |
| --- | :-: | --: | --: | :-: | :-: |
| M0 | 8/8 | 100 | 87.30% | 3 kept | 4 |
| M1 | 8/8 | 192 | 93.01% | 3 kept | 4 |
| M2 | 8/8 | **245** | **93.56%** | 3 kept | **1** |

> M2 passed on the first cycle. Every decision was frozen in `M2_Design_Review.md` before
> code was written and none was revised during implementation. That is the return on a
> design review.

## Structural gates

| Gate | State |
| --- | --- |
| `ops/check_structural_columns.py` | **Satisfied at M2.** `location_id` and `lot_id` present on every movement from the first row (ADR-0004, E-06) |
| `lint-imports` — 3 contracts | Kept. Has caught 4 violations across 3 milestones, all introduced by the rule's author |
| `make verify` | 8 blocking stages. The only authority (N-12) |

## Blocking before M3

| # | Item | Owner |
| --- | --- | --- |
| 1 | M2 committed, tagged `m2-inventory`, pushed | Engineering |
| 2 | **TD-17 — trigger escape hatch into `incident-response.md`** | Engineering (do in M3) |
| 3 | TD-1 — confirm `uv.lock` is committed | Engineering |
| 4 | TD-15 — assign a milestone to `offer` | Product Architect |

**No irreversible decisions are outstanding for M3.** Pricing writes no new ledger.

## Technical debt

Full list in `docs/M2_Verification_Report.md` §7. Highest priority:

| # | Item | Due |
| --- | --- | --- |
| TD-11 | **SMS / DLT registration not started — blocks go-live** | Now |
| TD-17 | Trigger escape hatch not written into the runbook | M3 |
| TD-1 | `uv.lock` committed | Now |
| TD-14 | `Product._has_history()` still inert — stock movements now exist | M4 |
| TD-16 | `SOURCE_DOCUMENT_REGISTRY` accept path proven only by monkeypatch | M5 |

**Closed:** TD-5 (M1) · TD-12, TD-13 (M2).
