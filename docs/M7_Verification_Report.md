# M7 — Reporting: Verification Report

| Field | Value |
| --- | --- |
| Document ID | `M7_Verification_Report` |
| Version | **1.1.0** |
| Status | **VERIFIED** — `make verify` 8/8 |
| Date | 2026-08-08 · **addendum §10 added 2026-08-08** |
| Milestone | M7 — Reporting |
| Design authority | `docs/M7_Design_Review.md` v1.2.0 (signed, independently reviewed) |
| Verify cycles to green | **2** |

> Every figure here comes from the single passing `make verify` run. Nothing from a failing
> run is reported as if it had passed.
>
> **One requirement in M7's scope is not verified by that run, and §6.1 says so first.**
> FR-RPT-015 requires a measurement no test suite performs.

---

## 1. Executive summary

M7 delivers the owner's visibility: seven reports, CSV on all of them plus the customer
statement, report scoping, and the four-number dashboard. It is the first milestone that
stores nothing.

The governing principle held throughout implementation and needed no revision:

> **A report computes nothing. It arranges, filters and totals figures the domain already
> derives.**

`reporting` has no `models.py`, no `services.py` and no migration, and is not an installed
app — it has nothing to install. Four structural tests assert that, because `03` §2.1's
*"owns nothing"* is a sentence in a document and will not survive five more milestones on
its own.

**M7 is the only milestone so far that made the system smaller in one respect.** C-7 removed
two money columns that three documents described and the schema could not support.

---

## 2. Verification results

| # | Stage | Result |
| --: | --- | --- |
| 1 | Clean build, no cache | PASS |
| 2 | Stack up, healthchecks | PASS |
| 3 | No missing migration | PASS — **and none was added**; `reporting` owns no table |
| 4 | Ruff | PASS |
| 5 | Import contracts | PASS — **3 kept, 0 broken** |
| 6 | Type check (advisory) | Ran |
| 7 | Tests + coverage | PASS — **665/665**, **94.47%** |
| 8 | Health endpoint | PASS |

### 2.1 Environment

The pinned verification toolchain introduced at M5 held for a third milestone.

| Component | Version |
| --- | --- |
| Python · Django | 3.12.13 · 5.1.15 |
| pytest · pytest-django · pytest-cov | 9.1.1 · 4.12.0 · 7.1.0 |

### 2.2 Delta across milestones

| Milestone | Stages | Tests | Coverage | Contracts | Verify cycles |
| --- | :-: | --: | --: | :-: | :-: |
| M0 | 8/8 | 100 | 87.30% | 3 kept | 4 |
| M1 | 8/8 | 192 | 93.01% | 3 kept | 4 |
| M2 | 8/8 | 245 | 93.56% | 3 kept | 1 |
| M3 | 8/8 | 312 | 93.38% | 3 kept | 2 |
| M5 | 8/8 | 449 | 94.33% | 3 kept | 4 |
| M6 | 8/8 | 525 | 93.92% | 3 kept | 5 |
| **M7** | **8/8** | **665** | **94.47%** | **3 kept** | **2** |

**+140 tests, +0.55 coverage points, and the fewest cycles since M2.** The cycle count is
worth reading carefully rather than as progress: M7 wrote no migration, took no lock,
enforced no new business rule and touched no financial document. **A read-only milestone
being the cheapest to verify is the design working, not the engineering improving.**

The layer graph now carries **14 root packages**.

> **Correction, 2026-08-08.** v1.0.0 of this report stated that `lint-imports` analysed
> "141 files and 276 dependencies". **Those numbers were not observed in the M7 verify
> run** — they came from a local sandbox execution and were written here as though they had
> been. The M7 run reported only *3 kept, 0 broken*, which is all this document can claim.
> The next verified run (§10) measured **139 files, 268 dependencies**.
>
> Recorded rather than quietly overwritten, because §1 of this report promises that every
> figure in it comes from the passing run, and for one line that was not true.

---

## 3. Architectural decisions confirmed by the run

| Decision | Confirmed by |
| --- | --- |
| **M7-1** — D-1's definition of sales | The §5.1 worked scenario reproduced exactly: 2,400 + 1,000 − 200 = **3,200.00**, not the 3,776.00 option A would give |
| **M7-2** — CSV columns are a contract | One renderer over one row shape; I-5 asserted per report, not once |
| **M7-3** — inclusive date bounds on business dates | A movement recorded today falls inside a period ending today — the timestamp-versus-date trap, tested |
| **M7-4** — `reporting` stores nothing | No migration, no model, not in `INSTALLED_APPS`; four structural tests |
| **M7-5 / D-3** — reports arrange, domains derive | AST tests forbid `*.services` and any first-party `*.models` import |
| **M7-7** — returns and variance are two traces | Both reports built, totals deliberately unequal, and §5.3's **non-invariant** asserted so nobody writes its opposite |
| **M7-8** — the four dashboard numbers | Exactly four, two marked live, no CSV offered |
| **C-7** — no cost basis, so no valuation | Both stock reports carry quantity only, and say why |
| **I-1 … I-7** | All seven asserted; I-1 parametrised over all four groupings, I-5 over all seven reports |

---

## 4. Defects found during M7

Eleven in total. **Six were found before `make verify` ran**, which is the useful number:
five of those six were in test code, and a test defect that reaches the verify stage is
indistinguishable from a source defect until someone reads it.

### 4.1 Two contradictions inside the frozen design (found during implementation)

Neither is a coding defect. Both are places where v1.2.0 disagreed with itself and
implementation had to choose.

**The sales report offers four groupings, not three.** §2 C-3 resolves *"period, customer,
product and salesman — salesman is buildable"*, and the amended FR-RPT-001 requires it. But
§8.2 copied `05` §9.11's three-value list. Two documents said salesman was in scope; only
the older parameter list omitted it. **Resolved in favour of the more inclusive reading** —
adding a `group_by` value is additive to the contract; removing one would not have been.

**§4.3's audit was optimistic in two places.** It concluded *"no new domain selector is
required."* Two were: `billing.selectors.issued_invoices` (what `CANCELLED` means to a sale)
and `orders.selectors.awaiting_dispatch` (what "awaiting dispatch" means). Both are
**predicates**, not figures, which is why an audit that asked "does this figure have an
owner?" did not find them.

> **D-3 worked exactly as designed; the audit that preceded it did not.** The rule sent both
> to the owning module rather than into `reporting`, which is the outcome the rule exists
> for. The lesson is about the audit: a checklist finds what it names.

### 4.2 Four defects in test code (found before verify)

Caught by running the two suites that need no database.

1. **Two off-by-one list indices** in the CSV assertions — my own arithmetic about which
   line was which.
2. **The boundary test flagged `django.db.models` as a violation.** It was not: the rule is
   about *our* tables, and `Sum`/`Count`/`QuerySet` are how one arranges rows. Narrowed to
   first-party packages.
3. **The scoping tests would have passed vacuously.** The out-of-zone customer had no
   transactions, so it was absent from every report whether the scoping worked or not. A
   `foreign_trade` fixture now creates a real invoice for it, **and the test asserts the
   owner can see it** before asserting the salesman cannot.

> Defect 3 is the one that mattered. It is the same class as M6 §4.4's two hidden test
> defects: **a test that cannot fail is worse than no test**, because it is counted.

### 4.3 Cycle 1 — two root causes, eight endpoints and one invariant

The only failing verify run. Two independent causes, neither visible from reading the code.

**Root cause A — the CSV writer quoted the header block.** `writer.writerow([f"# {line}"])`
quotes any field containing a comma, and the sales definition contains three. Those lines
emerged as `"# Sales = invoice taxable value, excluding..."` — beginning with `"`, not `#` —
so I-5's filter admitted prose as data and found a sentence where the column row belonged.

Header lines are prose, not a one-column row. They are now written verbatim behind a
`COMMENT_PREFIX` constant, and `header_lines()` collapses each to a single line first,
because the statement's title interpolates a shop name that a human types and could carry a
newline that would become a data row halfway down the file.

**The test now filters on `report_csv.COMMENT_PREFIX`** rather than restating `"#"`. The
renderer owns the definition of "this line is prose"; the test reads it.

**Root cause B — DRF content negotiation, not routing.** All seven report endpoints and the
statement returned **404** on `?format=csv`. The routes were correct. `format` is
`URL_FORMAT_OVERRIDE`, and `DefaultContentNegotiation.select_renderer` filters the view's
renderers to those whose `format` matches:

```python
def filter_renderers(self, renderers, format):
    renderers = [r for r in renderers if r.format == format]
    if not renderers:
        raise Http404          # not 406
```

With `JSONRenderer` as the only configured renderer, the list filtered to nothing and DRF
raised `Http404` **inside `APIView.initial()`** — before `get()` ran. The endpoints looked
missing rather than unacceptable, which is why the symptom read as a routing fault.

Fixed by registering `api.v1.renderers.CsvRenderer`. It passes through text
`reporting.csv.render` already produced, so there is still exactly one CSV implementation —
a renderer that walked the rows itself would be precisely the duplication I-5 forbids.

> **Neither defect was findable by design review.** Both are framework-integration
> failures: one in how `csv.writer` quotes, one in how DRF negotiates. This design was
> reviewed by me and independently by a second reviewer, and **neither review could have
> caught either.** That is the argument for N-12 stated as evidence rather than as policy.

### 4.4 One production wart introduced by the fix, and not fixed

If a caller passes `?format=csv` on a report they are not authorised for, negotiation
selects `CsvRenderer` and the problem+json error body is stringified through it. The
`Content-Type` stays `application/problem+json` because the exception handler forces it, so
nothing is dangerous — the body is merely ugly on an error path no test covers.

Recorded as **TD-28** rather than fixed, because fixing it means the exception handler
pinning `JSONRenderer`, which is a change to a shared error path outside M7's scope.

---

## 5. What the milestone delivered

| Area | Delivered |
| --- | --- |
| `reporting` module | `selectors.py`, `csv.py`, `tables.py`. No models, no services, no migrations, not an installed app |
| Reports | Sales (4 groupings) · stock position · stock variance · **returns** · receivables ageing · top customers · order pipeline |
| Export | One renderer, all seven, plus the M6 customer statement. Self-describing header carrying the definition |
| Dashboard | Four numbers (D-4), two marked live, no export |
| API | 7 new endpoints, `?format=csv` on 8 |
| Owner screens | 7 report screens over **one** template, plus the statement export |
| Scoping | FR-RPT-014 asserted per endpoint and per export, for owner, salesman and retailer |
| Performance harness | `ops/report_performance.py` — **written, never executed** (§6.1) |

**A third file in `reporting`.** §8.1 lists two. `tables.py` holds the shared row shape so
`csv.py` need not import `selectors.py` — which would drag every domain selector into the
exporter's import graph for three dataclasses. §8.1's prohibition is on models, services and
migrations, and it holds.

---

## 6. Known limitations

### 6.1 FR-RPT-015 is unverified, and M7 is not complete without it

> **`make verify` green does not mean the reports are fast enough.** The suite exercises
> tens of rows. FR-RPT-015 requires under 10 seconds over **five years** of history —
> roughly 73,000 invoices and 292,000 lines at the DR-8 envelope — and NFR-PER-003's stated
> method is a load test against a synthesised dataset.

`ops/report_performance.py` builds that dataset and times all eleven report calls
individually. **It has never been run.** Task 8 of the design says in terms that no report
may be declared done on the strength of a fast test-suite run; this report therefore does
not declare them done.

Two suspects were named in advance and both remain unmeasured:

- **receivables** — the only report whose figures come from a row-by-row Python walk (§5A)
  rather than a database aggregate; it walks every ledger entry for every visible customer.
- **top customers** — raised by independent review (§17.2). It aggregates across `invoice`
  and `credit_note` and groups by customer, and both candidate indexes
  (`ix_invoice_customer_date`, `ix_credit_note_cust_date`) **lead on `customer`**, so
  neither serves a date-range scan that then groups.

Recorded as **TD-27**, and it is the highest-priority item in this report.

### 6.2 Other limitations, by decision

| Limitation | Authority |
| --- | --- |
| No stock valuation on either stock report | C-7 — no cost basis until M-11 Purchasing |
| No allocated/available stock columns | C-2 — Edition 2 |
| No sales-by-category | C-3 — no category field |
| No purchase report, no scheme report, no sync health report | C-1, §3, C-4 |
| No returns **reconciliation** screen | §17.1 — requires the join ADR-0009 removed. Edition 2, with M-12 |
| Read tearing accepted on reports covering today | §6, signed |
| AR-7's third mitigation layer is a footer | §13.3 — untested prose, and still the weakest point |

### 6.3 Coverage detail was not captured

The verified run reported **94.47% overall**. Per-file figures were not recorded, so
**TD-23 cannot be confirmed closed from this run** — see §7.

---

## 7. Technical debt

### Closed by M7

**None confirmed.**

TD-23 (`billing/selectors.py` at 78%, uncovered lines being the salesman and retailer
scoping branches) was the one item M7 took. FR-RPT-014's tests exercise exactly that surface
across three roles and seven endpoints, so it is very likely closed — **but "very likely" is
not a verification result.** The per-file coverage figure was not captured from the passing
run, and this report does not claim what it did not observe. It stays open until a run
reports the number.

### New

| # | Item | Due |
| --- | --- | --- |
| **TD-27** | **FR-RPT-015 unmeasured.** The five-year harness exists and has never been run. Two named suspects. **This is the highest-value item in the repository after TD-21** | **Next** |
| **TD-28** | `?format=csv` on an unauthorised report stringifies the problem+json body through `CsvRenderer`. Cosmetic, on an untested error path | M10 |
| **TD-29** | `reporting` has no test that a *newly added* report is wired into `REPORT_MENU`, the API router and the CSV path. The eighth report will be added by someone who forgets one of the three | M8 |

### Carried

| # | Item | Note |
| --- | --- | --- |
| TD-21 | `uv.lock` absent, `make lock` non-functional | **Still the highest-value debt.** Deferred through M5, M6 and now M7 |
| TD-11 | SMS / DLT registration not started | Blocks go-live, unbounded external lead time |
| TD-2 / TD-18 | `mypy` advisory rather than blocking | **Missed at M5, M6 and now M7 — a third miss.** §11 predicted exactly this and kept it out anyway, which was the right call and did not help |
| TD-23 | `billing/selectors.py` scoping branches | Unconfirmed, see above |
| TD-26 | `_walk` guards covered only by the property test | Untouched |
| TD-14 | `Product._has_history()` inert | Overdue since M3 |
| TD-22 / TD-25 | Advisory `mypy` diagnostics | Untouched |
| TD-24 | Move `_ImmutableDocument` to `core` | M10 |
| TD-15 | `offer` has no milestone | Product Architect |

> **TD-2/TD-18 has now been missed three times.** M7 §11 argued it needed its own change
> rather than a third ride on someone else's milestone, and kept it out on that basis. The
> argument was correct and the item still did not get done. **The next milestone that
> "keeps it out for good reasons" should instead be the one that schedules it.**

---

## 8. Readiness for M8 — Mobile app

| Item | State |
| --- | --- |
| Edition 1a back end | **Feature-complete.** M0–M7 deliver every server-side capability Edition 1a requires |
| API surface | 8 report endpoints added; `05` §9.11 amended, additively |
| **TD-27 — FR-RPT-015** | **Blocking a claim of completeness, not blocking M8.** M8 changes language and platform; running the harness after that switch conflates two variables |
| TD-21 — reproducible build | **Should be closed before M8.** M8 adds a second toolchain; an unpinned Python build plus a new Dart build is two unpinned builds |
| CF-1 — statutory e-invoicing | Still unanswered, and more expensive with every invoice issued |

**Recommendation: run the performance harness and close TD-21 before M8 begins.** Both are
cheap now and become entangled the moment a second platform enters the repository.

---

## 9. Lessons

**1. A design review cannot find a framework-integration defect.** Both cycle-1 root causes
lived in the seam between our code and a library's conventions — how `csv.writer` quotes,
how DRF negotiates `format`. This design had two reviews, one independent, and neither could
have caught either. N-12 is not bureaucracy; it is the only stage that looks at that seam.

**2. A checklist finds what it names.** §4.3's audit asked "does this figure have an owner?"
and answered correctly for every figure — while missing two *predicates*. C-7 was found the
same way at review time: by asking a question the corpus had not been asked. Both are the
same failure at different scales.

**3. Tests that cannot fail are the expensive kind.** The vacuous scoping test would have
shipped a green suite that proved nothing about the one risk M7 rated High (AR-5). Every
scoping test now asserts the *positive* case first — that the data is visible to someone —
before asserting it is invisible to the salesman.

**4. The cheapest milestone to verify was the one that stores nothing.** Two cycles, no
migration, no lock, no rule. That is a property of read-only design, and it is worth
remembering when the pressure to materialise an aggregate arrives.

**5. What this run does not prove.** 665 green tests say the reports are correct at ten
rows. **They say nothing about ten seconds at five years**, and the design said so before
the code was written. Recording that here, rather than letting a green run imply it, is the
whole point of §6.1.

---

## 10. Addendum — the identity phone defect, verified 2026-08-08

Found after M7 was committed, while preparing to run the FR-RPT-015 harness: a freshly
created superuser could not log in.

**Root cause: the write path did not normalise, the read path did.** `UserManager._create`
stored the phone verbatim; `authenticate_password` normalised before looking it up. A user
created as `7903324153` was stored as `7903324153` and searched for as `+917903324153`. The
`user is None or not user.check_password(...)` test short-circuits, so `check_password` was
never reached — which is why the password verified in a shell and failed in a browser, and
why the message said "Incorrect phone number or password" while both were correct.

This is the same class as the canonical-decimal defect M1 fixed: **a canonical
representation enforced on read and not on write.** `core.fields.to_money` exists for
exactly that reason on the money side; `identity/phone.py` now does the same for the login
identity, below both the reader and the writer so neither has to reach across the layering.

### 10.1 Verified run

| Metric | M7 | **With the fix** |
| --- | --: | --: |
| Stages | 8/8 | **8/8** |
| Tests | 665 | **685** (+20) |
| Coverage | 94.47% | **94.78%** |
| Import contracts | 3 kept | **3 kept, 0 broken** — 139 files, 268 dependencies |
| Missing migrations | none | **none** — `0004` is hand-written and alters no model |

### 10.2 Why 665 green tests did not catch it

**`UserFactory` never calls `UserManager._create`.** `factory.django.DjangoModelFactory`
goes through `Manager.create()`, so no factory-built user has ever exercised the write-path
rules. The factory's own numbers happen to be canonical (`+9198765…`), so nothing failed
and nothing warned.

Every prior milestone's authentication tests were therefore testing a code path that
production does not use for user creation. Recorded as **TD-30**; the new regression tests
build their users through `create_user` deliberately.

### 10.3 What the migration does, and what it refuses to do

`0004_normalise_user_phone` normalises existing rows. It **copies** the rule rather than
importing it, so a later change to the canonical form cannot silently rewrite history — the
same reason `0002_seed_roles` inlines its data.

**It refuses rather than merges.** If two rows would collide on one canonical number it
raises with both user IDs and both raw values and stops. `phone` is `UNIQUE` and is the
login identity (`04` T-01), so choosing a winner would orphan a real account and its audit
trail. That is a business decision, not a migration's.

### 10.4 Advisory `mypy` grew

24 errors in 7 files, of which **6 are new in `backend/reporting/selectors.py`** —
annotation gaps around Django's `values()`/`annotate()` return types. Advisory only
(stage 6 runs under `|| true`), and folded into TD-25.

**This is the fourth consecutive milestone in which the `mypy` gate was not made blocking**
and the second in which the untyped surface grew while it stayed advisory.
