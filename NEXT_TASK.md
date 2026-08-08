# Next Task

> M7 is verified and closed: `docs/M7_Verification_Report.md` **v1.2.0** — 8/8, **703/703,
> 94.83%**, 3 contracts kept. Design authority `docs/M7_Design_Review.md` v1.2.0. Post-M7
> fixes in §10–§11; owner bootstrap in `docs/Owner_Bootstrap_Design_Note.md` v1.1.0.

**Milestone:** M8 — Mobile app (Flutter, `S2`/`S3`)
**State:** **not started. Four engineering items should close first — see below.**

> **The install works end to end for the first time.** `git clone && make up && make owner`
> now yields a system the owner can sign in to. That was true at **no previous commit**, and
> no test caught it, because the suite reached that state through `UserFactory` (TD-30).

---

## Do these before M8 opens

All four are cheap now and become entangled the moment a second toolchain and a second
platform enter the repository.

| # | Item | Why now, not later |
| --: | --- | --- |
| **1** | **TD-30 — make `UserFactory` use the production creation path.** | **It hid two defects in a row.** M8 builds a client whose entire relationship with the server is authentication, and the factory every auth test uses does not exercise how real users are made. Fix this **before** writing M8's auth tests, not after |
| **2** | **TD-27 — run `ops/report_performance.py`.** FR-RPT-015 has never been measured | M8 adds a Dart build and a second runtime. Measuring after that switch conflates two variables, and the harness already exists |
| **3** | **TD-21 — make the build reproducible.** `uv.lock` absent, `make lock` non-functional | An unpinned Python build plus a brand-new Dart build is **two** unpinned builds. The M5 toolchain drift that broke a green gate under unchanged source is the precedent |
| **4** | **TD-2/TD-18 — make `mypy` blocking.** Missed at M5, M6 **and M7** | M7 §11 argued it deserved its own change rather than a third ride on someone else's milestone. That argument was correct and the item still is not done. **The next milestone that keeps it out for good reasons should be the one that schedules it instead** |

### On TD-30 specifically — it is now first for a reason

`DjangoModelFactory` calls `Manager.create()`, so no factory-built user has ever gone through
`UserManager._create`, and `UserFactory(roles=[...])` grants roles by a path production could
not reach. Both post-M7 defects lived exactly there:

| Defect | What the factory hid |
| --- | --- |
| Phone normalisation | Factory phones were already canonical, so the missing write-path rule never showed |
| Owner bootstrap deadlock | Factory users arrived **with roles**, so the absence of any way to grant the first one never showed |

**A clean install could fail while the suite stayed green — and did, for eight milestones.**

### On TD-27 specifically

`make verify` green does **not** mean the reports are fast enough. The suite exercises tens
of rows; FR-RPT-015 requires under 10 seconds over five years — roughly 73,000 invoices and
292,000 lines at the DR-8 envelope.

Two suspects were named in the design and remain unmeasured:

- **receivables** — the only report whose figures come from a row-by-row Python walk (§5A)
  rather than a database aggregate. It walks every ledger entry for every visible customer.
- **top customers** — `ix_invoice_customer_date` and `ix_credit_note_cust_date` **both lead
  on `customer`**, so neither serves a date-range scan that then groups.

If a report breaches, the fix is an index or a domain optimisation **recorded with the
measurement that justified it** (M7 §7) — never a reporting shortcut, and never a stored
aggregate (M7-4).

---

## M8 — what it is

The first milestone that changes language and platform. One Flutter binary serving
`SALESMAN`, `DELIVERY` and later `RETAILER` (DV-4), against the API M0–M7 has already
built.

**The Edition 1a back end is feature-complete.** M8 adds no server-side capability; it adds
a client. That is worth stating because it sets the shape of the design review: the
questions are about the device, not about the domain.

### The condition DV-4 is accepted on, and it is absolute

> **The binary is publicly downloadable and must be assumed fully decompiled** (`02A` §9.3,
> DV-4). It may contain no internal-only logic, endpoint or secret that server-side
> authorisation does not independently enforce.

Every milestone so far has kept authorisation in `core` and out of the delivery layers
(N-06, BR-003). M8 is where that discipline is tested by someone holding the client.

### K-1 — the one irreversible thing in M8

> **If the Android release keystore is lost, the application on Google Play can never be
> updated again.** Not by you, not by Google (`00` §2.3).

Generated once, stored in the password manager, backed up to **two locations that are not
the development machine**, never in Git (S-06, N-11). Done at M8, verified at M11.

### Known external dependency

**TD-11 — SMS/DLT registration.** `00` §2.4 says to start it at Phase 0 and it has not
started. `00` §2.5 records the contingency: if DLT approval is not complete by M8, the
fallback is owner-provisioned passwords for internal users and deferred retailer
self-registration — **a recorded deviation, not a silent scope change.**

---

## Workflow, unchanged

1. Review the frozen corpus first — `00`, `01`, `02` v0.2.0, `02A`, `03`, `04`, `05`.
2. Identify specification conflicts **before** proposing a design.
3. Write `docs/M8_Design_Review.md`: governing principle, worked scenarios, irreversible
   decisions with reversal cost, concurrency, boundaries, task decomposition, self-critique,
   sign-off.
4. Independent architecture review before implementation.
5. Implement one logically complete milestone.
6. `make verify` 8/8 — the only authority (N-12).
7. Verification report, then documentation, then commit.

**No weakened tests. No lowered coverage. No bypassed contracts.**

---

## What M7 leaves behind, for the M8 designer

| Item | Note |
| --- | --- |
| `reporting` owns nothing | Four AST tests enforce it. If M8 wants a figure on the device, the selector goes in the **domain**, not in `reporting` (D-3) |
| **First-owner bootstrap** | `make owner` / `manage.py bootstrap_owner`, documented in `docs/runbooks/first-owner.md`. M8's device provisioning will need users with roles — use this path, not a factory shortcut |
| **TD-29** | Nothing asserts a newly added report is wired into `REPORT_MENU`, the API router **and** the CSV path. The eighth report will be added by someone who forgets one of the three |
| **TD-28** | `?format=csv` on an unauthorised report stringifies the problem+json body. Cosmetic, untested error path |
| TD-23 | `billing/selectors.py` scoping branches — **very likely closed by FR-RPT-014's tests, but per-file coverage was not captured**, so it is not recorded as closed |
| The lesson worth carrying | **A design review cannot find a defect on a path the tests do not take.** M7's two defects lived in the seam with a library; the two after it lived in the seam with the test suite's own scaffolding. Four reviews found none of them; the only thing that did was running the real thing |

## Blocking, not owned by engineering

| Item | Owner |
| --- | --- |
| **CF-1 — is statutory e-invoicing mandatory?** (`02` OI-1). More expensive with every invoice issued | Business owner |
| **TD-11 — SMS/DLT registration.** Now inside M8's critical path | Business owner |
| **TD-15 — `offer` has no milestone** | Product Architect |
