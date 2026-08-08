# Project State

| | |
| --- | --- |
| Phase | **Phase 1 — Implementation** |
| Current milestone | **M6 — Receivables** — verified 8/8, 525/525 tests, 93.92% coverage |
| Next milestone | **M7 — Reporting** (not started) |
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
| M5 | Fulfilment & Billing — delivery, dispatch, GST invoice, credit note, ledger | **Verified & tagged** — `docs/M5_Verification_Report.md` |
| M6 | Receivables — payments, reversal, write-off, derived outstanding, statement | **Verified** — `docs/M6_Verification_Report.md` |
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
| M5 | 8/8 | 449 | 94.33% | 3 kept | 4 |
| M6 | 8/8 | **525** | **93.92%** | 3 kept | **5** |

> Coverage fell 0.18 points in M3 and 0.41 in M6. Both recorded rather than rounded away.
> The gate is 80% and has never been moved.
>
> **Only two of M6's five cycles were domain work.** One went to lint, one to migrations
> that by definition cannot be generated, one to test defects. Cycle count measures
> difficulty only when everything else holds still.

## Pinned verification environment

Introduced at M5 after a toolchain change broke the gate under unchanged source.
**The pins held through M6** — the stopgap works; TD-21 remains the durable fix.

| Component | Version |
| --- | --- |
| Python · Django | 3.12.13 · 5.1.15 |
| pytest · **pytest-django** · pytest-cov | 9.1.1 · **4.12.0** · 7.1.0 |

## Structural gates

| Gate | State |
| --- | --- |
| `ops/check_structural_columns.py` | Satisfied since M2 — `location_id` and `lot_id` on every movement (ADR-0004, E-06) |
| `lint-imports` — 3 contracts | Kept. **130 files, 242 dependencies**, 13 root packages. Has caught 4 violations across 6 milestones, all by the rule's author |
| Order/inventory/ledger boundary | Orders write no stock movement and no ledger entry, and cannot import the ledger's writer (M3-6) |
| Financial immutability | Raw SQL refused on `invoice`, `invoice_line`, `credit_note`, `credit_note_line`, `customer_ledger_entry` and now `payment` |
| Double-restock (Scenario F) | Impossible by construction — a credit note writes no stock (ADR-0009) |
| **§5A.7 ledger invariant** | `Σ outstanding - credit_on_account ≡ settled_balance`, asserted over five randomised seeds spanning all six entry roles |
| **One opening balance per customer** | Partial unique index. The go-live import is idempotent (M6-11) |
| `make verify` | 8 blocking stages. The only authority (N-12) |

## Blocking before M7

| # | Item | Owner |
| --- | --- | --- |
| 1 | M6 committed, tagged `m6-receivables`, pushed | Engineering |
| 2 | **TD-21 — make the build reproducible.** Highest-value debt in the repo | Engineering |
| 3 | **`02` FR-REC-004/006/008 still read "M, v1.0".** A cold reader will conclude Edition 1 allocates payments to invoices | Product Architect |
| 4 | **CF-1 — is statutory e-invoicing mandatory?** More expensive with every invoice issued | Business owner |
| 5 | M7 design review written and signed | All |
| 6 | TD-15 — assign a milestone to `offer` | Product Architect |

## Technical debt

Full list in `docs/M6_Verification_Report.md` §7. **M6 opened three items and closed none.**

| # | Item | Due |
| --- | --- | --- |
| TD-21 | **`uv.lock` absent and `make lock` non-functional** — `uv` is not in the dev image, `/app` is not bind-mounted. Pins bound direct dependencies only | **Next** |
| TD-11 | **SMS / DLT registration not started — blocks go-live.** Unbounded external lead time | Now |
| TD-2 / TD-18 | **`mypy` advisory. Set for M5, missed. Carried to M6, missed again.** Recorded as a second miss, not re-dated | M7 |
| TD-26 | **New.** `_walk`'s three robustness guards are exercised only by the randomised property test. Changing the seeds could silently remove coverage of branches that took two cycles to find | M7 |
| TD-14 | `Product._has_history()` still inert. **Overdue** since M3 | M7 |
| TD-23 | `billing/selectors.py` — uncovered lines are **authorisation** branches | M7 |
| TD-22 / TD-25 | 17 advisory `mypy` diagnostics; 6 are ours (2 new in `receivables/selectors.py`) | M7 |
| TD-24 | **New.** Move `_ImmutableDocument` to `core` (D-7, deferred by ruling) | M10 |
| TD-15 | `offer` has no milestone | Open |

**Closed:** TD-5 (M1) · TD-12, TD-13 (M2) · TD-17 (M3) · TD-16, TD-19 (M5) · **none (M6)**.
