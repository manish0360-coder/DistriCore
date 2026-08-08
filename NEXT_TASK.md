# Next Task

> Design reasoning: `docs/M6_Design_Review.md` **v1.2.0**. No ADR — M6 amends no roadmap.
> M5 is verified and closed: `docs/M5_Verification_Report.md`.

**Milestone:** M6 — Receivables (1.5 units, `00` §19.1)
**State:** **design frozen — implementation authorised**

---

## Settled

C-1, C-2, C-3, D-4, D-5, D-6, D-8 approved · **D-7 deferred** (TD-24, M10 — verified M5
code is not modified) · **AR-2 resolved** by §5A / D-9.

**Independent review, three concerns — all three upheld (v1.2.0):**

| # | Concern | Outcome |
| --: | --- | --- |
| 1 | PK-derived `payment_number` needs an `UPDATE` the trigger forbids | **Correct.** Mechanism → `nextval` before a single INSERT (D-4) |
| 2 | The write-off lock serialises nothing | **Correct.** Removed. §6.2 states why reversal's lock is real and this was not |
| 3 | `load_opening_balance` must be idempotent | **Adopted.** Partial unique index — one `OPENING` per customer (D-10, M6-11) |

Two mechanism corrections and one added constraint. **The architecture is unchanged.**

---

## The one thing to hold in mind

> **A payment reduces what a customer owes. It does not pay an invoice.**

Which invoices are consequently settled is a **derived view** (§5A), walked oldest-first at
read time and never stored. Storing an allocation is the one thing in M6 that cannot be
undone without migrating live financial history.

---

## Tasks

Seven, each independently verifiable and committable. Task 0 was removed with D-7.

| # | Task | Gated by |
| --: | --- | --- |
| 1 | `receivables` module — `Payment` reusing `billing._ImmutableDocument`, migration incl. **`payment_number_seq`**, column-aware trigger, layers contract, register in `SOURCE_DOCUMENT_REGISTRY` | C-3, M6-2, M6-4 |
| 1b | `ledger` migration — **partial unique index**, one `OPENING` per customer | **M6-11** |
| 2 | `record_payment` — **`nextval` then ONE INSERT** (never an UPDATE), `client_uuid` savepoint, ledger entry in the same transaction, return `balance_after_amount` | M6-1, M6-2, M6-5 |
| 3 | `reverse_payment` — `SELECT … FOR UPDATE`, compensating `ADJUSTMENT`, audited | M6-3, AR-3 |
| 4 | `write_off` — **explicit amount, no lock**, owner only, reason mandatory, audited | M6-10, §6.2 |
| 5 | `load_opening_balance` through `record_entry`, **idempotent on conflict** | D-8, D-10 |
| 6 | **The §5A walk** — classify → annul → reduce → settle — plus statement and the §5A.7 invariant as a property test | **D-9**, M6-6/7/8 |
| 7 | API (6 endpoints, `05` §9.6), owner screens, boundary and adversarial suites | §9 |

### Task 6 is the hard one

Classification (§5A.3) reads `entry_type`, sign and `source_document_type`. **Three roles,
not two** — the third is *annulling*, and it is why a reversed payment must not create a
fresh zero-day debt.

Test obligations are enumerated in §13.1. The non-negotiable one:

> **Σ outstanding.remaining − credit_on_account ≡ `settled_balance(customer, as_of)`**
> asserted over a randomised sequence of all six entry types.

---

## Standing rules for this milestone

- **`reverse_payment` holds the only lock in M6** (§6). Payments append, and appends do not
  contend. A lock serialises only the writers that take it — locking anything else would be
  theatre, because every other ledger writer is lock-free by design.
- **A payment row is written once.** `nextval` first, then a single INSERT. Any `UPDATE`
  outside the four reversal columns is refused by the trigger.
- **Gate on the locked re-read, never the caller's instance.** M5 §4.1 cost 40 failures
  and opened a path to invoicing a cancelled order.
- Do not modify verified M5 code (Product Architect ruling).
- `make verify` 8/8 is the only authority (N-12).
- No weakened tests, no lowered coverage, no bypassed contracts.

---

## Also due in M6, carried from M5

| # | Item | Note |
| --- | --- | --- |
| **TD-21** | Reproducible build — `uv.lock` absent, `make lock` non-functional | **Highest-value debt.** Cost M5 a full verify cycle |
| **TD-2 / TD-18** | `mypy` blocking — **set for M5 and missed** | Do not re-date a third time |
| TD-14 | `Product._has_history()` inert — overdue since M3 | |
| TD-23 | `billing/selectors.py` 78% — the uncovered lines are **authorisation** branches | |
| TD-24 | **New.** Move `_ImmutableDocument` to `core` (D-7 deferred) | M10 |

## Blocking, not owned by engineering

| Item | Owner |
| --- | --- |
| **CF-1 — is statutory e-invoicing mandatory?** Invoices now exist, so a late *yes* means re-transmitting history | Business owner |
| **TD-11 — SMS/DLT registration.** Blocks go-live, unbounded external lead time | Business owner |
| `02` FR-REC-004/006/008 → v2.0, and `02A` §13.2's audit list, corrected once | Product Architect |
