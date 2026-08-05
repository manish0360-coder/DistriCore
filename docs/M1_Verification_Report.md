# M1 — Master Data: Verification Report

| Field | Value |
| --- | --- |
| Document ID | `M1_Verification_Report` |
| Status | **Final — permanent engineering record** |
| Milestone | M1 — Master data |
| Date | 2026-08-05 |
| Verification | `make verify` — **8 of 8 stages passed** |
| Tests | **192 / 192** |
| Coverage | **93.01%** (gate 80%, unchanged) |
| Author | Chief Systems Engineer |

> Permanent record of what M1 built and proved. Not a changelog. Not amended — M2 gets
> its own report.

---

## 1. Executive Summary

### What M1 achieved

M1 delivered the reference data every later milestone reads: **zones, customers, products,
reason codes and media**. Five tables, three new modules, fourteen API endpoints, eleven
admin routes.

It also closed the first debt item from M0: `app_user.customer` now exists, so a retailer
login is bound to exactly one shop and `AD-11` token-derived scoping is real rather than
a placeholder returning `None`.

Nothing transactional was built. No stock, no orders, no invoices, no payments.

### Why it matters

Three properties were established that M2 onwards depends on:

1. **Owner-only authority is enforced in services, not in views.** Credit limits and
   prices are separate service functions with their own audit actions, because they are
   distinct authorities. A salesman reaches 403 through the API, the admin form, or a
   direct service call — there is one gate, not three.
2. **Retailer scoping is structural.** `visible_customers()` derives scope from the actor.
   The endpoints accept no `customer_id`, so there is no parameter to tamper with. Four
   adversarial tests attack this directly, including enumeration and parameter injection.
3. **Money has one canonical form.** `core.fields.to_money()` fixes rounding once
   (NFR-INT-006, OI-7). Every money value entering the domain is quantized at the point of
   entry, so the stored value, the audited value and the wire value are the same string.
   This was not true when M1 began — see §4.3.

---

## 2. Final Verification Results

| # | Stage | Result |
| --- | --- | :-: |
| 1 | Clean build (`--no-cache`) | PASS |
| 2 | Containers healthy | PASS |
| 3 | Migrations complete | PASS |
| 4 | Lint (`ruff check`) | PASS |
| 5 | Architecture contracts (`lint-imports`) | PASS — 3 kept, 0 broken |
| 6 | Type check (`mypy`) | PASS |
| 7 | Tests + coverage | PASS — **192/192, 93.01%** |
| 8 | Health endpoint | PASS |

### Delta from M0

| | M0 | M1 | Δ |
| --- | --: | --: | --: |
| Tests | 100 | **192** | +92 |
| Coverage | 87.3% | **93.01%** | +5.7 pt |
| Test files | 11 | 18 | +7 |
| Tables | 5 | **10** | +5 |
| Migrations | 4 | 10 | +6 |
| Django modules | 4 | 7 | +3 |
| API endpoints | 6 | 14 | +8 |
| Admin routes | 3 | 11 | +8 |
| Import contracts | 3 | 3 | — |
| `type: ignore` | 2 | 2 | — |

### What was built

| Table | Purpose | Design ref |
| --- | --- | --- |
| `zone` | Road, PIN, panchayat, ward, city — the client's own five fields | 04 T-07 |
| `customer` | Retailer master, credit terms, coordinates | 04 T-09 |
| `product` | Code, price, GST rate, HSN, pack size, image | 04 T-10 |
| `reason_code` | Owner-maintained stock explanations; 8 seeded | 04 T-08 |
| `media_file` | One upload path, one validation, one authorisation | 04 T-25 |

Modules `catalogue`, `customers` and `inventory` follow `03` §2.1. **`inventory` contains
only `ReasonCode`** — the stock ledger is M2, under the ADR-0004 gate, which still
correctly reports "not yet, expected before M2".

---

## 3. Design Decisions

No new ADRs. Three decisions taken within the frozen design, recorded here.

### 3.1 Credit limit and price are separate service functions

`set_credit_limit()` and `set_price()` are not fields inside a general update. Each has a
distinct authority (owner-only) and a distinct audit action
(`CREDIT_LIMIT_CHANGE`, `PRICE_CHANGE`). Folding them into `update_*` would lose both:
FR-CUS-005 requires owner-only credit changes, and PO-6 makes price changes a margin
control worth auditing separately.

`update_customer()` and `update_product()` therefore *route* those fields to the dedicated
functions rather than writing them. A salesman patching `credit_limit_amount` gets 403
whichever entry point they use.

### 3.2 Scope is derived, never accepted

`customers.selectors.visible_customers(actor)` is the single scoping rule. Owner sees all;
salesman and delivery see their assigned zones plus unzoned customers; retailer sees only
their own shop. A scope violation raises `ResourceNotFound`, never `PermissionDenied` —
a 403 would confirm the record exists (05 §4.1).

### 3.3 `Product._has_history()` exists and returns `False`

FR-PRD-003 forbids changing `pack_size` once a product has been transacted, because it
would silently rewrite historical quantities. M1 has no transactional tables, so the hook
is inert. It exists now so M2 (stock movements) and M4 (order lines) extend one function
rather than rediscovering the rule twice. Recorded as TD-13 so it is not forgotten.

---

## 4. Bugs Found During Verification

Three defects. One was caught by a static gate, one by a system check, one by a test.

### 4.1 `CheckConstraint` given a Python bool instead of an expression

**Root cause.** The paired-coordinate constraint was written
`Q(latitude__isnull=True) == Q(longitude__isnull=True)`. `==` on two `Q` objects evaluates
to a Python `bool` at import time, not to an expression Django can compile.

**Why it happened.** The intent — "both set or neither" — reads naturally as an equality.
It is not one.

**Fix.** `Q(both null) | Q(both not null)`.

**Lesson.** `manage.py check` caught it before any migration was written. Constraint
expressions are code that runs at import; they deserve the same scrutiny as a query.

### 4.2 A delivery layer reached a model — caught by `lint-imports`, again

**Root cause.** `MediaDetailView` imported `core.models.MediaFile` *inside a method body*
to look up a file. `grimp` analyses statically and does not care where the import sits, so
the N-02 contract broke.

**Fix.** `core.selectors.get_media()`. The view no longer knows the model exists.

**Lesson.** This is the second milestone in which the contract caught a violation
introduced by the engineer who wrote the rule — M0 §4.7 was the first. Both would have
passed self-review. **The evidence for mechanical enforcement is now empirical, not
theoretical.**

### 4.3 Money had no canonical representation — the M1 defect worth remembering

**Symptom.** An audit assertion expected `"0.00"`; the audit recorded `"0"`.

**Root cause — not where the symptom appeared.** `MoneyField(default=0)` put a Python
`int` into a money field. Django does not reload after `create()`, so a freshly created
instance held `0`, not `Decimal("0.00")`, and `str(0)` is `"0"`. A second instance of the
same class: `set_credit_limit` stored `Decimal("2500")` unquantized, so the audit said
`"2500"` while the database returned `"2500.00"`.

The audit serializer was reporting the inconsistency faithfully. **The domain value was
already wrong.**

**Which representation is canonical.** Settled by the frozen design, not by preference:

| Source | States |
| --- | --- |
| `04` §1.6 | Money is `NUMERIC(14,2)` — scale 2 is the column scale |
| `05` AD-02, §3 | Money on the wire is `"12450.00"`; quantity `"24.000"` |
| NFR-INT-006 | Rounding defined **once**, applied consistently, documented |
| **FR-AUD-005** | **A transaction must be reconstructible from audit records** |

FR-AUD-005 decides it. `"0"` and `"0.00"` are the same number and different strings. An
audit that records one while the document records the other cannot be diffed, and a
reconciliation would report a false difference. **`"0.00"` is canonical.**

**Fix — three layers, at the source, not at the symptom.**

1. `core.fields` now defines rounding once: `MONEY_SCALE`, `QUANTITY_SCALE`,
   `PERCENT_SCALE` and `to_money()` / `to_quantity()` / `to_percent()` with
   `ROUND_HALF_UP`. This implements NFR-INT-006 and OI-7 rather than assuming them. They
   construct via `Decimal(str(value))`, never `Decimal(float)`, which would import the
   float error N-07 forbids.
2. The field classes coerce their own defaults, so an unsaved instance already holds
   `Decimal("0.00")`.
3. Services quantize where money enters the domain. Call sites pass raw `Decimal`s and
   `record_audit()` canonicalises them recursively through dicts and lists — removing
   scattered `str()` calls (NFR-MNT-001) and preventing JSON from coercing a `Decimal`
   to a float.

**No migration was required.** `makemigrations` reported no changes: Django compares
deconstructed kwargs and `Decimal("0.00") == 0`, so the *schema* default was always
correct. Only the in-memory Python value was wrong — precisely the defect.

**One assertion changed:** `after_state == "2500"` became `"2500.00"`. That assertion was
pinning the non-canonical form the implementation happened to emit; both sides now assert
the specification. Seventeen regression tests were added
(`tests/unit/test_canonical_decimals.py`), including that the stored value and the audited
value are the same string.

**Lesson.** A default value is part of the type contract. `MoneyField(default=0)` looks
harmless and violates N-07 in spirit — an `int` is not a `Decimal`. More generally: when a
value has a canonical form, fix it where the value **enters** the domain, not where it is
displayed. Normalising in the audit serializer alone would have left the wire, the admin
and every future report free to disagree.

---

## 5. Engineering Quality Metrics

| Metric | Value |
| --- | --- |
| Tests | **192**, all passing |
| — unit | 96 |
| — integration | 70 |
| — adversarial | 26 |
| Coverage | **93.01%** (gate 80%, never lowered) |
| Verification stages | 8, all blocking |
| Architecture contracts | 3, kept |
| Migrations | 10, graph verified acyclic |
| Tables | 10 |
| API endpoints | 14 |
| Ruff findings | 0 |
| Genuine mypy errors | 0 |
| `type: ignore` | 2, both documented |

### Adversarial coverage added in M1

| Test | Verifies |
| --- | --- |
| Retailer enumerates other shops | 404 for every id, never 403 (05 §4.1) |
| Retailer sends `?customer_id=` | Ignored — no parameter exists to widen scope (AD-11) |
| Retailer raises own credit limit | 403; value unchanged |
| Salesman raises a credit limit by PATCH | 403; value unchanged |
| Product creation by every role | Owner 201, all others 403 |
| Renamed executable uploaded as `.jpg` | Rejected on **content**, not extension |
| Media fetched anonymously | 401 — never a guessable public path |

---

## 6. Known Technical Debt

Carried from M0, plus four new items. **Two are functional gaps in M1, recorded rather
than glossed.**

| # | Item | Impact | Resolve by |
| --- | --- | --- | --- |
| **TD-12** | **No zone create/edit screen.** `create_zone()` and `update_zone()` exist and are tested, and the customer form offers a zone dropdown — but the owner cannot create a zone except through the shell. The dropdown is empty on a fresh install. | **Functional gap.** Zones are needed for salesman scoping | **M2** — two views and one form |
| **TD-13** | **No product image upload in the admin form.** `POST /api/v1/media` works and is tested; `product_form.html` has no image field, so the owner cannot attach an image from the web admin. The client's requirement is "images + rate" | **Functional gap** for the retailer portal (M12) | **M2** |
| TD-14 | `Product._has_history()` returns `False` | Inert hook | Extend at M2 (stock) and M4 (order lines) |
| TD-15 | **`offer` has no milestone.** `05` §9.2 groups `/offers` under master data; `00` §19.1 does not list it in M1, and no later milestone claims it | Roadmap gap | **Product Architect to assign.** Needed before M12 |
| TD-1 | `uv.lock` — confirm the file generated by `make lock` is committed | Reproducibility (FD-03/04) | **Confirm now** |
| TD-2 | `mypy` advisory in stage 6 | Type-safety erosion | M3 |
| TD-3 | `djangorestframework-stubs` not adopted | Reduced checking at the API boundary | M3 |
| TD-4 | `pip-audit` advisory in CI | Vulnerability blind spot | M10 |
| TD-6 | `outstand()` `hasattr` shim | Version-drift shim | Remove once TD-1 pins a version |
| TD-7 | `auth_permission` / `auth_group` unused | Two dead tables | Not planned |
| TD-8 | Restore never rehearsed | Unproven recovery | M11, gated |
| TD-9 | Sentry unproven in production | Unknown error visibility | M11 |
| TD-10 | Repository on `/mnt/e` contrary to FD-01 | Developer velocity | Any time |
| TD-11 | **SMS / DLT registration not started** | **Blocks go-live** | Start now; needed by M8 |

**Closed in M1:** TD-5 (`app_user.customer_id`).

> **TD-12 and TD-13 are the honest reading of M1.** The domain, the API and the tests are
> complete; two owner-facing screens are not. Neither blocks M2, because M2 consumes
> products and reason codes rather than zones or images. Both should close early in M2
> rather than accumulating.

---

## 7. M2 Entry Criteria

M2 (inventory and the stock ledger) may assume the following. Anything not listed, M2
must not assume.

### Complete

| # | Assumption |
| --- | --- |
| 1 | `make verify` passes 8/8 from a clean clone |
| 2 | `Product` exists with `pack_size`, `to_base_units()`, price and tax rate |
| 3 | `ReasonCode` exists with 8 seeded rows, `direction` and `is_restockable` |
| 4 | `Customer` and `Zone` exist with scoping rules and selectors |
| 5 | `MediaFile` exists with a validated upload path and authorised retrieval |
| 6 | `core.fields.to_money` / `to_quantity` — canonical scales and rounding, defined once |
| 7 | `record_audit()` canonicalises `Decimal` recursively; audit is append-only |
| 8 | Four import contracts hold; `inventory` already sits in the layered graph |
| 9 | Migration conventions established; graph verified acyclic |

### Required before M2 begins

| # | Precondition | State |
| --- | --- | --- |
| 1 | This report reviewed | Pending |
| 2 | M1 committed, tagged `m1-master-data`, pushed | Pending |
| 3 | TD-1 (`uv.lock`) confirmed committed | **Pending** |
| 4 | **Irreversible decisions I-02 … I-12 signed off** (`04` §17) | **Required — M2 writes the stock ledger** |
| 5 | TD-15 (`offer` milestone) assigned by the Product Architect | Pending |

> **Precondition 4 is not optional.** M2 creates `stock_movement`, the table `04` §17 rates
> as the most expensive in the system to get wrong. I-03 (`location_id`, `lot_id`), I-05
> (derived balances) and I-07 (exact decimals) all take physical effect in that migration.

---

## 8. Lessons Learned

1. **A default value is part of the type contract.** `MoneyField(default=0)` reads as
   harmless and put an `int` where the design says `Decimal`. Canonical form must be fixed
   where a value *enters* the domain, not where it is displayed — otherwise the wire, the
   audit and every future report are each free to disagree.
2. **Mechanical architecture enforcement has now paid twice.** M0 §4.7 and M1 §4.2 were
   both violations introduced by the author of the rule, and both would have passed
   self-review. An import inside a function body is still an import.
3. **Route authority through one function, not one flag.** Credit limit and price have
   their own service functions because they have their own authority and their own audit
   action. Every entry point converges on the same gate.
4. **Derive scope; never accept it.** The endpoints take no `customer_id`. There is nothing
   to tamper with, which is a stronger property than validating a parameter correctly at
   every call site.
5. **Record the gaps.** TD-12 and TD-13 are real and would have been easy to omit from a
   report that only lists what works. A verification report that cannot say what is missing
   is not a verification report.

---

*M1 complete and verified. No transactional features implemented. M2 begins only after
this report is reviewed and its entry criteria are met.*
