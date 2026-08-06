# Project State

| | |
| --- | --- |
| Phase | **Phase 1 — Implementation** |
| Current milestone | **M5 — Fulfilment & Billing** — verified 8/8, 449/449 tests, 94.33% coverage |
| Next milestone | **M6 — Receivables** (not started) |
| Edition | 1a |
| Design corpus | `docs/00`–`05`, frozen · amended by ADR-0007, ADR-0008, ADR-0009 |

## Milestones

| # | Milestone | State |
| --- | --- | --- |
| P0 | Engineering Foundation | Complete |
| M0 | Foundation — identity, roles, OTP, audit, health, logging | **Verified & tagged** — `docs/M0_Verification_Report.md` |
| M1 | Master data — zones, customers, products, reason codes, media | **Verified & tagged** — `docs/M1_Verification_Report.md` |
| M2 | Inventory — stock ledger | **Verified & tagged** — `docs/M2_Verification_Report.md` |
| M3 | Commercial Operations — business profile, pricing, orders, credit | **Verified & tagged** — `docs/M3_Verification_Report.md` |
| ~~M4~~ | ~~Orders~~ | **Absorbed into M3** by ADR-0007. The number is retired, not reused |
| M5 | Fulfilment & Billing — delivery, dispatch, GST invoice, credit note, ledger | **Verified** — `docs/M5_Verification_Report.md` |
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
| M3 | 8/8 | 312 | 93.38% | 3 kept | 2 |
| M5 | 8/8 | **449** | **94.33%** | 3 kept | **4** |

> Coverage fell 0.18 points in M3 and is recorded rather than rounded away. The gate is
> 80% and has never been moved.
>
> **Only two of M5's four cycles were domain work.** One went to a production defect in
> `issue_invoice`; one went entirely to a test framework that changed underneath unchanged
> source (`M5_Verification_Report` §4.4). Cycle count measures milestone difficulty only
> when the environment holds still.

## Pinned verification environment

Recorded because M5 proved it is load-bearing. Changing any of these is a deliberate act
with a verify run attached.

| Component | Version |
| --- | --- |
| Python · Django | 3.12.13 · 5.1.15 |
| pytest · **pytest-django** · pytest-cov | 9.1.1 · **4.12.0** · 7.1.0 |

`pytest-django 4.13.0` breaks `_django_db_helper` against this codebase and cost a full
verify cycle. See TD-21.

## Structural gates

| Gate | State |
| --- | --- |
| `ops/check_structural_columns.py` | Satisfied since M2 — `location_id` and `lot_id` on every movement (ADR-0004, E-06) |
| `lint-imports` — 3 contracts | Kept. **116 files, 205 dependencies**, 12 root packages. Has caught 4 violations across 5 milestones, all by the rule's author |
| Order/inventory/ledger boundary | 9 adversarial tests. Orders write no stock movement and no ledger entry, and cannot import the ledger's writer (M3-6) |
| Financial immutability | 20 adversarial tests driving **raw SQL** at the triggers on `invoice`, `invoice_line`, `credit_note`, `credit_note_line`, `customer_ledger_entry` |
| Double-restock (Scenario F) | Proven impossible by construction — a credit note writes no stock (ADR-0009) |
| `make verify` | 8 blocking stages. The only authority (N-12) |

## Blocking before M6

| # | Item | Owner |
| --- | --- | --- |
| 1 | M5 committed, tagged `m5-fulfilment-billing`, pushed | Engineering |
| 2 | **TD-21 — make the build reproducible.** Highest-value debt in the repo | Engineering |
| 3 | **CF-1 — is statutory e-invoicing mandatory?** Now more expensive: invoices exist, so a late *yes* means re-transmitting history | Business owner |
| 4 | M6 design review written and signed | All |
| 5 | TD-15 — assign a milestone to `offer` | Product Architect |

**TD-19 is closed** — ADR-0008 moved the ledger to its own module, resolving the M6
layering conflict a milestone early.

## Technical debt

Full list in `docs/M5_Verification_Report.md` §7. Highest priority:

| # | Item | Due |
| --- | --- | --- |
| TD-21 | **`uv.lock` does not exist and `make lock` cannot create it** — `uv` is absent from the dev image, `/app` is not bind-mounted, and `uv lock` likely needs `[tool.uv] package = false`. Pins bound direct dependencies only | **Next** |
| TD-11 | **SMS / DLT registration not started — blocks go-live.** Unbounded external lead time | Now |
| TD-2 / TD-18 | **`mypy` advisory. The M3 report set this for M5 and M5 did not do it.** Recorded as missed, not silently re-dated | M6 |
| TD-14 | `Product._has_history()` still inert. **Overdue** since M3 | M6 |
| TD-23 | `billing/selectors.py` at 78% — uncovered lines are the salesman and retailer **authorisation** branches | M6 |
| TD-22 | 15 advisory `mypy` diagnostics; 4 are ours | M6 |
| TD-15 | `offer` has no milestone | Open |

**Closed:** TD-5 (M1) · TD-12, TD-13 (M2) · TD-17 (M3) · **TD-16, TD-19 (M5)**.
