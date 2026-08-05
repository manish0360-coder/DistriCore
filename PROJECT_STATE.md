# Project State

| | |
| --- | --- |
| Phase | **Phase 1 — Implementation** |
| Current milestone | **M3 — Commercial Operations** — verified 8/8, 312/312 tests, 93.38% coverage |
| Next milestone | **M5 — Fulfilment & Billing** (not started; there is no M4 — ADR-0007) |
| Edition | 1a |
| Design corpus | `docs/00`–`05`, frozen |

## Milestones

| # | Milestone | State |
| --- | --- | --- |
| P0 | Engineering Foundation | Complete |
| M0 | Foundation — identity, roles, OTP, audit, health, logging | **Verified & tagged** — `docs/M0_Verification_Report.md` |
| M1 | Master data — zones, customers, products, reason codes, media | **Verified & tagged** — `docs/M1_Verification_Report.md` |
| M2 | Inventory — stock ledger | **Verified & tagged** — `docs/M2_Verification_Report.md` |
| M3 | Commercial Operations — business profile, pricing, orders, credit | **Verified** — `docs/M3_Verification_Report.md` |
| ~~M4~~ | ~~Orders~~ | **Absorbed into M3** by ADR-0007. The number is retired, not reused |
| M5 | Fulfilment & Billing | Not started |
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
| M2 | 8/8 | 245 | 93.56% | 3 kept | 1 |
| M3 | 8/8 | **312** | **93.38%** | 3 kept | 2 |

> Coverage fell 0.18 points in M3 and is recorded rather than rounded away. The gate is
> 80% and has never been moved.

## Structural gates

| Gate | State |
| --- | --- |
| `ops/check_structural_columns.py` | Satisfied since M2 — `location_id` and `lot_id` on every movement (ADR-0004, E-06) |
| `lint-imports` — 3 contracts | Kept. 84 files, 130 dependencies. Has caught 4 violations across 4 milestones, all by the rule's author |
| Order/inventory boundary | 8 adversarial tests. Orders write no stock movement and no ledger entry (M3-6) |
| `make verify` | 8 blocking stages. The only authority (N-12) |

## Blocking before M5

| # | Item | Owner |
| --- | --- | --- |
| 1 | M3 committed, tagged `m3-commercial-operations`, pushed | Engineering |
| 2 | **M5 design review written and signed** | All |
| 3 | TD-1 — confirm `uv.lock` is committed | Engineering |
| 4 | TD-15 — assign a milestone to `offer` | Product Architect |

**TD-19 (M6 layering) must be resolved before M6, not M5.**

## Technical debt

Full list in `docs/M3_Verification_Report.md` §7. Highest priority:

| # | Item | Due |
| --- | --- | --- |
| TD-11 | **SMS / DLT registration not started — blocks go-live** | Now |
| TD-2 / TD-18 | **`mypy` advisory.** M3 §4.3 proved it hides real defects — a silent truncation bug shipped past it | **M5 — raise to blocking** |
| TD-14 | `Product._has_history()` still inert. **Overdue** — both references it should check now exist | M5 |
| TD-19 | `credit_exposure` layering conflicts with `03` §2.1 at M6 | Before M6 |
| TD-1 | `uv.lock` committed | Now |
| TD-16 | `SOURCE_DOCUMENT_REGISTRY` accept path proven only by monkeypatch | M5 |

**Closed:** TD-5 (M1) · TD-12, TD-13 (M2) · **TD-17 (M3)**.
