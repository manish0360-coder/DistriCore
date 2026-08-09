# Next Task

> M7 is verified and closed: `docs/M7_Verification_Report.md` **v1.3.0** — 8/8, **712/712**,
> 3 contracts kept. Design authority `docs/M7_Design_Review.md` v1.2.0. Post-M7 fixes in
> §10–§12; owner bootstrap in `docs/Owner_Bootstrap_Design_Note.md` v1.1.0; TD-30 in
> `docs/TD-30_Factory_Creation_Path_Note.md` v1.0.0.

**Milestone:** M8 — Mobile app (Flutter, `S2`/`S3`)
**State:** **not started. Three engineering items should close first — see below.**

> **The install works end to end for the first time.** `git clone && make up && make owner`
> now yields a system the owner can sign in to. That was true at **no previous commit**, and
> no test caught it, because the suite reached that state through `UserFactory` (TD-30).

---

## Do these before M8 opens

All four are cheap now and become entangled the moment a second toolchain and a second
platform enter the repository.

| # | Item | Why now, not later |
| --: | --- | --- |
| ~~TD-30~~ | ~~Make `UserFactory` use the production creation path~~ | **Closed.** Creation half structurally; role half by direct coverage (`docs/TD-30_Factory_Creation_Path_Note.md` §3) |
| ~~TD-27~~ | ~~Run `ops/report_performance.py`~~ | **Closed.** Measured 11.7 s, found a quadratic in the §5A walk, fixed to **0 breach(es)** — before M8's second runtime could conflate the measurement |
| ~~TD-21~~ | ~~Make the build reproducible~~ | **Closed.** `uv.lock` pins 91 packages; all three install sites use `uv sync --frozen`; a missing lock fails stage 1. Done **before** the Dart toolchain arrives, which was the point |
| ~~TD-2/TD-18~~ | ~~Make `mypy` blocking~~ | **Closed at the fourth attempt.** Zero errors across 115 files; stage 6 and CI both fail on a type error. Three of the 24 were signatures that lied |
| **1** | **TD-32 — retire the `==` dev pins**, superseded by the lock | Small, but it must not ride along with anything: the pins and the lock are two ways of doing one job, and removing one while the other is new means two variables move together. **`mypy` and `django-stubs` keep theirs** — see below |

> **The type gate changes what a lock refresh means.** `make lock` can now break stage 6
> under unchanged source, by moving `mypy` or `django-stubs` — the pytest-django failure
> mode relocated to a different gate. So TD-32 retires the *pytest* pins and **leaves
> `mypy` and `django-stubs` pinned**, and any future lock refresh is its own change with
> its own verify run.

### What TD-30 cost, and what it left behind

Both post-M7 defects lived in the factory's blind spot:

| Defect | What the factory hid |
| --- | --- |
| Phone normalisation | Factory phones were already canonical, so the missing write-path rule never showed |
| Owner bootstrap deadlock | Factory users arrived **with roles**, so the absence of any way to grant the first one never showed |

Closing it exposed a third, unrelated defect class — **TD-31**: four tests read the wall
clock while asserting against a hard-coded period. One failed the morning the date rolled;
three more would have failed on 1 September. All four are fixed by stating the instant.

> **The role half of TD-30 is closed by discipline, not by mechanism.** `UserFactory(roles=[...])`
> still writes `UserRole` directly. If the fixture layer is ever reworked, route it through
> `grant_role` / `bootstrap_owner` then.

### What TD-27 found, and what it settled

`make verify` green did **not** mean the reports were fast enough. The suite exercises tens
of rows; at the DR-8 envelope — 73,000 invoices, 292,000 lines, 103,000 ledger entries —
**receivables ageing took 11.7 s and the dashboard 11.8 s**, both breaching FR-RPT-015.

**One root cause.** `_annulled_entry_ids` was called inside a comprehension *condition*, so
it re-ran once per entry: O(n²) where O(n) was intended, ~10.6 million entry-visits. The
function is pure, so hoisting it changed nothing but the cost. **0 breach(es)** after.

Two things worth carrying into M8:

- **The design named the right suspect for the wrong reason.** Receivables was flagged as
  the only Python-walk report — true, but no query was slow. The cost was an algorithmic
  defect, not the walk's size.
- **Top customers, the independent reviewer's suspect, measured 0.221 s.** The index concern
  did not materialise, and no index was added. A prediction that proves wrong is worth
  recording too.

**Re-run the harness after any change to a report or to the §5A walk.** It is not part of
`make verify` and never will be — an 858-second dataset build has no place in an 8-stage
gate — so nothing else will catch a regression of this class.

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
