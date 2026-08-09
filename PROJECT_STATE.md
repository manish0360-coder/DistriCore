# Project State

| | |
| --- | --- |
| Phase | **Phase 1 — Implementation** |
| Current milestone | **M7 — Reporting** — verified 8/8. Latest run **712/712 tests, 94.85%** (M7 plus the identity phone fix, the owner bootstrap and TD-30) |
| Next milestone | **M8 — Mobile app** (not started) |
| Edition | 1a — **back end feature-complete, and installable for the first time** |
| Design corpus | `docs/00`–`05`, frozen · `02` at v0.2.0 · amended by ADR-0007, ADR-0008, ADR-0009 |

> **Edition 1a's server side is done. One requirement in it is unverified.** FR-RPT-015
> (reports under 10 s over five years) has never been measured — the harness exists and has
> not been run. See TD-27.
>
> **`00` §20.3 criterion 2 became true on 2026-08-08.** *"A user can log in ... by password
> on web"* was never satisfiable on a clean machine through the supported path; it passed at
> M0 and every milestone since only because the suite reached that state through
> `UserFactory`, which bypasses the production creation path (TD-30).

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
| M6 | Receivables — payments, reversal, write-off, derived outstanding, statement | **Verified & tagged** — `docs/M6_Verification_Report.md` |
| M7 | Reporting — seven reports, CSV, scoping, owner dashboard | **Verified** — `docs/M7_Verification_Report.md` |
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
| M6 | 8/8 | 525 | 93.92% | 3 kept | 5 |
| M7 | 8/8 | 665 | 94.47% | 3 kept | **2** |
| M7 + identity fix | 8/8 | 685 | 94.78% | 3 kept | **1** |
| M7 + owner bootstrap | 8/8 | 703 | 94.83% | 3 kept | **1** |
| M7 + TD-30 | 8/8 | **712** | *not captured* | 3 kept | **2** |

> Coverage fell 0.18 points in M3 and 0.41 in M6. Both recorded rather than rounded away.
> The gate is 80% and has never been moved.
>
> **Only two of M6's five cycles were domain work.** One went to lint, one to migrations
> that by definition cannot be generated, one to test defects. Cycle count measures
> difficulty only when everything else holds still.
>
> **M7's two cycles are the design, not the engineering.** A milestone that writes no
> migration, takes no lock and enforces no business rule has less that can fail. Both of
> its defects were framework-integration failures — `csv.writer` quoting, DRF content
> negotiation — which **no design review can find and only stage 7 can**.

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
| `lint-imports` — 3 contracts | Kept. **139 files, 268 dependencies**, 14 root packages. Has caught 4 violations across 7 milestones, all by the rule's author |
| **`reporting` owns nothing** | No `models.py`, no `services.py`, no migration, absent from `INSTALLED_APPS`. Four AST tests assert it, including that it imports no `*.services` and no first-party `*.models` (M7-4, M7-5) |
| **One canonical phone number** | `identity/phone.py` defines it once; `UserManager._create` writes it and every lookup reads it. Migration `identity/0004` normalised existing rows and **refuses to merge collisions** (`04` T-01) |
| **The first authorised user is reachable** | `bootstrap_owner` (FR-IAM-014). Refuses while an **active** owner exists, refuses a deactivated target, audits every use as `OWNER_BOOTSTRAP` with `actor_user` NULL. **A test asserts the deadlock it exists to break**, so it cannot be deleted as redundant |
| **The factory builds users like production** | `UserFactory._create` routes through `UserManager.create_user`. A test gives it a non-canonical phone and asserts it comes back canonical — the smallest statement that the production path is taken, and it fails the moment anyone reverts it |
| Order/inventory/ledger boundary | Orders write no stock movement and no ledger entry, and cannot import the ledger's writer (M3-6) |
| Financial immutability | Raw SQL refused on `invoice`, `invoice_line`, `credit_note`, `credit_note_line`, `customer_ledger_entry` and now `payment` |
| Double-restock (Scenario F) | Impossible by construction — a credit note writes no stock (ADR-0009) |
| **§5A.7 ledger invariant** | `Σ outstanding - credit_on_account ≡ settled_balance`, asserted over five randomised seeds spanning all six entry roles |
| **One opening balance per customer** | Partial unique index. The go-live import is idempotent (M6-11) |
| `make verify` | 8 blocking stages. The only authority (N-12) |

## Blocking before M8

| # | Item | Owner |
| --- | --- | --- |
| 1 | M7, **the identity phone fix and the owner bootstrap** committed, tagged `m7-reporting`, pushed. **The tag goes here** — this is the first commit in the repository's history at which `git clone && make up && make owner` yields a usable system | Engineering |
| 2 | **TD-27 — run `ops/report_performance.py`.** FR-RPT-015 has never been measured. Do it **before** M8 adds a second toolchain, or the measurement conflates two variables | Engineering |
| 3 | **TD-21 — make the build reproducible.** Still the highest-value debt. M8 adds a Dart build; an unpinned Python build plus a new one is two unpinned builds | Engineering |
| 4 | **TD-2/TD-18 — make `mypy` blocking.** Missed at M5, M6 **and M7**. It needs its own change and a scheduled slot, not another good reason to defer | Engineering |
| 5 | **CF-1 — is statutory e-invoicing mandatory?** More expensive with every invoice issued | Business owner |
| 6 | M8 design review written and signed | All |
| 7 | TD-15 — assign a milestone to `offer` | Product Architect |

## Technical debt

Full list in `docs/M7_Verification_Report.md` §7. **M7 opened three items and closed none
it can prove.**

| # | Item | Due |
| --- | --- | --- |
| **TD-27** | **New. FR-RPT-015 has never been measured.** `ops/report_performance.py` builds the five-year dataset and times all eleven report calls; it has not been run. Named suspects: the receivables walk, and top-customers (both candidate indexes lead on `customer`, not on the date) | **Next** |
| TD-21 | **`uv.lock` absent and `make lock` non-functional** — `uv` is not in the dev image, `/app` is not bind-mounted. Pins bound direct dependencies only | **Next** |
| TD-11 | **SMS / DLT registration not started — blocks go-live.** Unbounded external lead time | Now |
| TD-2 / TD-18 | **`mypy` advisory. Missed at M5, M6 and now M7 — a third miss.** M7 §11 argued it needed its own change and kept it out; the argument was right and the item still is not done | **Schedule it** |
| TD-23 | `billing/selectors.py` scoping branches. FR-RPT-014's tests exercise exactly that surface, so it is **very likely closed — but per-file coverage was not captured**, and this table does not record what was not observed | M8 |
| TD-26 | `_walk`'s three robustness guards are exercised only by the randomised property test | M8 |
| TD-14 | `Product._has_history()` still inert. **Overdue** since M3 | M8 |
| TD-22 / TD-25 | Advisory `mypy` diagnostics — **24 errors in 7 files, six of them new in `reporting/selectors.py`**. Fourth consecutive milestone with the gate advisory, second in which the untyped surface grew while it stayed that way | M8 |
| **TD-29** | **New.** Nothing asserts a *newly added* report is wired into `REPORT_MENU`, the API router and the CSV path. The eighth report will be added by someone who forgets one of the three | M8 |
| **TD-31** | **New. A test that reads the wall clock while asserting against a constant fails on a date rather than on a change.** Four instances found and fixed; two other `stocked` fixtures were left alone because they bound no period. The class is recorded because the next instance will be written by someone who has not read this row | M8 |
| **TD-28** | **New.** `?format=csv` on an unauthorised report stringifies the problem+json body through `CsvRenderer`. Cosmetic, untested error path | M10 |
| TD-24 | Move `_ImmutableDocument` to `core` (D-7, deferred by ruling) | M10 |
| TD-15 | `offer` has no milestone | Open |

**Closed:** TD-5 (M1) · TD-12, TD-13 (M2) · TD-17 (M3) · TD-16, TD-19 (M5) · **none (M6)** ·
**none confirmed (M7)** · **TD-30 (post-M7)**.

> **TD-30's creation half is closed structurally; its role half is closed by coverage
> elsewhere** (`docs/TD-30_Factory_Creation_Path_Note.md` §3). The second is a discipline
> rather than a mechanism. If the fixture layer is ever reworked, routing `roles=` through
> the services is the right thing to do then.
