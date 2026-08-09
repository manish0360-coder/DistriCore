# Design Note — TD-2 / TD-18: make the `mypy` gate blocking

| Field | Value |
| --- | --- |
| Document ID | `TD-2_Mypy_Blocking_Design_Note` |
| Version | **1.1.0** |
| Status | **IMPLEMENTED AND VERIFIED — TD-2 / TD-18 closed.** See §8 |
| Date | 2026-08-09 |
| Closes | **TD-2 / TD-18** (missed at M5, M6, M7) |
| Independent review | Gemini, responded to in §2 |
| ADR required | **No** — see §7 |

---

## 1. What the 24 errors actually are

Gemini opens with:

> *"They do not indicate architectural flaws but rather represent the known friction
> between Python's dynamic heritage … and the discipline of static analysis."*

**That is true of most of them and false of the most valuable ones.** Read against the
source, the 24 errors fall into five groups, not four — and the group Gemini does not have
is the one worth doing first.

| # | Group | Count | Nature |
| --: | --- | --: | --- |
| **A** | **Signatures that are false** | **8** | The declared type is not what the function returns. mypy is right and the code is wrong |
| B | Narrowing mypy cannot perform | 5 | Runtime-safe; the guard is real but not provable |
| C | Expression helpers with a heterogeneous kwargs dict | 4 | Plain Python typing, **not ORM dynamism** |
| D | Annotated fields (`.annotate()`) | 2 | Genuine ORM friction |
| E | Third-party stubs + a coupled unused-ignore | 3 | Configuration |
| — | Missing return annotations | 2 | Trivial |

### 1.1 Group A — three lying signatures, eight errors

```python
def variance_by_reason(...) -> QuerySet[StockMovement]:      # inventory/selectors.py:82
    return queryset.values(...).annotate(...).order_by(...)  # returns DICTS, not movements
```

This single wrong annotation causes **five** errors: `inventory:97` plus
`reporting:396,397,398,401` (*"Value of type StockMovement is not indexable"* — the report
iterates dicts that the signature says are models).

```python
def settled_order_ids(customer) -> QuerySet[int]:            # ledger/selectors.py:75
    return CustomerLedgerEntry.objects.filter(...).values_list(...)   # QuerySet[CLE, int]
```

Two more errors. `QuerySet`'s first parameter must be a `Model`.

```python
def invoice_pdf(request, pk) -> HttpResponse:                # webadmin/fulfilment_views.py:130
    return FileResponse(...)                                 # FileResponse is NOT an HttpResponse
```

`FileResponse` descends from `StreamingHttpResponse`, a **sibling** of `HttpResponse` under
`HttpResponseBase`. Any caller trusting the annotation and touching `.content` would fail at
runtime.

> **These are documentation-as-code that lies.** They are the same class as the phone
> number that was canonical on read and not on write, and the walk whose cost was invariant
> but evaluated as though it were not: **a statement that is not true of the thing it
> describes.** They are worth fixing whether or not mypy ever becomes blocking, and
> classifying them as "friction with Python's dynamic heritage" invites silencing them.

### 1.2 Group C is not what Gemini says it is

Gemini files `Sum(**kwargs)` and the `Q` assignment under *"Friction with Django's Dynamic
ORM"* and predicts they *"will likely be resolved by … ensuring the containing function has
a fully annotated signature"*.

```python
kwargs = {"output_field": QuantityField()}      # mypy infers dict[str, QuantityField]
if as_of is not None:
    kwargs["filter"] = Q(...)                   # <- error. Nothing to do with the ORM
```

This is a **heterogeneous dict inferred from its first assignment** — ordinary Python. A
return annotation does not touch it. The correct fix removes the dict:

```python
def _on_hand_expression(*, as_of: datetime | None = None) -> Coalesce:
    movement_filter = Q(movements__occurred_at__lte=as_of) if as_of is not None else None
    return Coalesce(
        Sum("movements__quantity", filter=movement_filter, output_field=QuantityField()),
        ZERO,
    )
```

`filter=None` is already `Sum`'s default, so this is behaviour-identical, shorter, and the
error disappears because the shape was clarified rather than annotated around.

### 1.3 Group B is safe, and Gemini's claim about it is overstated

Gemini says Category 1 *"fixes potential bugs (like the `int` vs `None` comparison)"*.

```python
if (base is None) == (packs is None):        # exactly one must be given
    raise serializers.ValidationError(...)
if (base if base is not None else packs) <= 0:      # <- mypy: int vs None
```

The guard two lines above **proves** the expression is never `None`. mypy cannot follow it
because the condition is on a derived boolean. **This is not a latent bug**, and describing
it as one would misrepresent the value of the milestone. The fix is to restructure so the
narrowing is visible — worth doing for readability, not for correctness.

---

## 2. Response to the independent review

### 2.1 Agreed, without reservation

| Gemini's point | Why it is right |
| --- | --- |
| **Risk 1 — the `Any` escape hatch is Severe** | Correct, and it is the principal risk. Silencing with `Any` would make this milestone cosmetic. Adopted as a hard rule in §4 |
| **Risk 2 — do not replace `.values()` with full model fetches** | Correct and important. `variance_by_reason` and `collections_by_user` are on the FR-RPT-015 path; M7 §13 has just shown what a careless change there costs. **`TypedDict`, never a model fetch** |
| **Risk 3 — "least possible silence"** | Correct. `warn_unused_ignores = true` is already set, which enforces it mechanically: an unnecessary ignore becomes an error |
| **`weasyprint` → `ignore_missing_imports`** | Correct. It ships no `py.typed`, and it is a native-library wrapper we call in one place |
| **Two sequential phases, not one push** | Agreed in principle, disagreed on the grouping criterion — §2.2 |

### 2.2 Disagreed

**(a) Grouping by technique puts the highest-value fixes in the cheapest bucket.**
Gemini's Phase 1 is *"routine annotations"* and includes the three false signatures of §1.1
alongside cosmetic work. Those three are the only errors here that describe a real defect.
**§5 sequences by value and risk instead.**

**(b) `disallow_untyped_defs = true` globally is a different milestone.**
Gemini's step 4 proposes turning it on repository-wide and notes it *"will likely reveal a
new set of errors in files that were not in the initial report."* That is an **unbounded
task presented as a step.** It is currently scoped to `*.services` and `*.selectors`, which
is where the business rules live — deliberately. Expanding to `api/v1`, `webadmin`, `core`
and every model is a second, larger change.

> **TD-2/TD-18 is "make the gate blocking". It is not "make mypy strict everywhere."**
> Conflating them is how a milestone that has already slipped three times slips a fourth.

**(c) A hand-rolled stub class for annotated fields would assert something false.**
Gemini recommends *"a TYPE_CHECKING block to create a protocol or stub class that includes
the annotated field (`on_hand`)"*. A class declaring that `Product` has `on_hand` makes the
type system believe it **everywhere** — including the many paths where it does not. That is
worse than a narrow ignore: it is a mechanism that appears to guarantee something it does
not.

django-stubs ships the correct primitive: **`django_stubs_ext.WithAnnotations[Product, …]`**,
used under `if TYPE_CHECKING:` so it costs nothing at runtime. Same intent, no falsehood.

**(d) `Sum(**kwargs)` is miscategorised** — §1.2. The proposed remedy would not have worked.

**(e) The claim that Category 1 "fixes potential bugs"** — §1.3. One of the two cited is
provably safe.

### 2.3 Risks Gemini did not identify

| # | Risk | Why it matters |
| --: | --- | --- |
| **R1** | **The gate is advisory in *two* places.** `Makefile` stage 6 (`mypy backend/ \|\| true`) **and** `.github/workflows/ci.yml`, whose comment still reads *"advisory until M2; hard gate from M3"* — stale since M3 | Closing one and not the other leaves the gate open where most changes are first seen |
| **R2** | **`ops/` is outside `mypy backend/`.** `ops/report_performance.py` imports eight model modules and every report selector | A blocking gate that does not see the harness will not notice when a selector signature changes under it |
| **R3** | **`billing/pdf.py:55` and `:57` are inversely coupled.** Adding the `weasyprint` override makes `HTML` return `Any`, which may make the currently-unused `# type: ignore[no-any-return]` **necessary again** | Fixing them in the wrong order produces a new error. They must be changed together and re-run |
| **R4** | **A blocking gate makes `make lock` a gate-breaking operation.** A refresh that moves `mypy` or `django-stubs` can fail stage 6 under unchanged source — **the pytest-django failure mode, one gate over** | Argues that `mypy` and `django-stubs` keep `==` pins even when TD-32 retires the others, and that a lock refresh becomes its own change with its own verify run |
| **R5** | **Two of the fixes land in `receivables/selectors.py`'s §5A walk** — the code that took two verify cycles to get right at M6 and hid a quadratic until M7 §13 | A "type fix" there must not alter walk semantics. The five-seed property test is the guard, and must be run, not assumed |
| **R6** | **`warn_unused_ignores = true` makes ordering matter.** Every ignore added must be necessary *at the moment the suite runs* | Self-tightening and good — but it means fixes cannot be batched blindly |

R4 is the one I would raise first in a review of this note.

---

## 3. `djangorestframework-stubs` — **defer**

Gemini recommends adopting now. **Disagreed, on three grounds.**

**It does not engage the recorded reason for deferral.** `pyproject.toml` says, and
`M0_Completion_Report` §5 records: *"djangorestframework-stubs exists but pins mypy and
django-stubs versions tightly."* A review that recommends reversing a recorded decision
should address the reason it was made.

**It moves two variables at once.** Adopting DRF stubs means removing `rest_framework.*`
from `ignore_missing_imports`, which will surface a fresh error wave across ~10 files in
`api/v1`. Doing that **in the same change that closes the gate** risks the gate never
closing — which is precisely how this item has been missed three times.

**It sharpens R4 before the gate has ever held once.** DRF-stubs pins `mypy` and
`django-stubs` narrowly. Introducing that constraint in the same change that makes mypy
blocking means the first thing the new gate does is depend on a three-way version pin nobody
has exercised.

> **One genuinely new argument in Gemini's favour, which I record because it will be right
> later:** TD-21 closed two days ago. Tight version pins are now *managed* — `uv.lock`
> records exactly what resolves, and `--frozen` refuses to drift. The original objection is
> materially weaker than when it was written.
>
> **So: defer, but not indefinitely.** Adopt DRF stubs as its own change once the gate has
> held through one full milestone. Recorded as **TD-33**.

---

## 4. Hard rules for the implementation

1. **`Any` may not be used to silence a Group A, C or D error.** If a type cannot be
   expressed, the fix is a narrower `# type: ignore[code]` with a comment naming why —
   never a widened annotation.
2. **`.values()` stays.** No error is fixed by fetching model instances instead. `TypedDict`
   or nothing.
3. **No behaviour change.** This milestone alters annotations, expression shape and
   configuration. If a fix requires changing what a function *does*, it stops and is raised.
4. **No new `ignore_errors`, and no module-wide silencing.** `ignore_missing_imports` for a
   genuinely stub-less package only.
5. **The §5A walk is touched under the property test**, not under review alone.

---

## 5. Implementation plan

**Not a milestone.** A maintenance change between M7 and M8, sequenced by value and risk.

| Phase | Content | Errors | Why here |
| :-: | --- | :-: | --- |
| **1** | **The three false signatures** — `variance_by_reason`, `settled_order_ids`, `invoice_pdf` | **8** | The only errors describing a real defect. Worth doing if mypy vanished tomorrow. `variance_by_reason` alone clears five |
| **2** | **Expression helpers** — remove the heterogeneous kwargs dict in `_on_hand_expression` and `_balance_expression`; add their return types | **6** | Self-contained, behaviour-identical, and clarifies two functions that are read often |
| **3** | **Narrowing** — `order_serializers` validate, `receivables` key construction, `pdf.py` `pdf_media` | **5** | Touches §5A (R5). Property test is the gate |
| **4** | **Third-party and annotated fields** — `weasyprint` override; `WithAnnotations` for `on_hand`; resolve the `pdf.py` 55↔57 coupling | **5** | Must be one step (R3) |
| **5** | **Close the gate** — remove `\|\| true` from `Makefile` **and** `ci.yml`; delete the stale *"advisory until M2"* comment | 0 | Only meaningful at zero errors |

**Explicitly out of scope**, so it is not smuggled in: global `disallow_untyped_defs`
(§2.2b), `djangorestframework-stubs` (§3), and adding `ops/` to mypy's path (R2 — recorded
as **TD-34**, not fixed here; the harness is a measurement script and widening the gate and
closing it in one change is the same mistake twice).

### 5.1 Verification strategy

- **Phases 1–4**: iterate locally against `mypy backend/`, then **one `make verify`** when
  the count reaches zero. Stage 6 is still advisory, so this run proves the suite still
  passes — not that the gate holds.
- **Phase 5**: a **second `make verify`**. This is the one that matters: with `|| true`
  removed, stage 6 can now fail, so a green run is the first evidence the gate holds.
- **The §5A property test is a named check**, not an incidental one — R5.
- **Success criterion:** `mypy backend/` reports *Success: no issues found*, `make verify`
  is 8/8 with stage 6 blocking, 712/712 tests, contracts 3 kept.

Two verify runs, not five. Running one per phase would cost ~20 minutes to prove something
only the last run can establish.

---

## 6. What this milestone is worth, stated honestly

Of 24 errors: **3 describe real defects** (§1.1), **6 improve readability** (§1.2–1.3), and
**15 are the tax of static analysis** on a dynamic ORM.

That is a modest direct yield, and it would be dishonest to sell it as more. **The value is
not in the 24 — it is in the 25th**, the one a blocking gate catches next year in code
nobody has written yet. Three of the four defects found since M7 shipped were caught by
running the real thing, and none by review; a blocking type gate is one of the few
mechanisms that catches a defect *before* it runs.

---

## 7. ADR or design note

**Design note.** No milestone boundary moves, no table is added, no architectural decision
is amended. FD-03 and `00` §6.3 already require the type check; this makes an existing gate
enforce what it already reports.

The one decision worth recording is the *scope*: **blocking the gate at its current strictness,
not raising the strictness.** That is stated in §2.2b and §5.

---

---

## 8. Closing evidence — TD-2 / TD-18 closed 2026-08-09

### 8.1 Verified

| Gate | Result |
| --- | --- |
| `make verify` | **8/8**, clean Docker build |
| **`mypy`** | **Success: no issues found in 115 source files** |
| Tests | **712/712** |
| Coverage | **94.83%** |
| Import contracts | **3 kept, 0 broken** |

### 8.2 The count, phase by phase — every prediction held

| Phase | Predicted | Actual | Remaining |
| :-: | :-: | :-: | :-: |
| — baseline | — | 24 | 24 |
| 1 — false signatures | 8 | **8** | 16 |
| 2 — expression helpers | 6 | **6** | 10 |
| 3 — narrowing | 4 | **4** | 6 |
| 4 — third-party, annotated fields, return types | 6 | **6** | **0** |

Every phase cleared exactly what §5 said it would, and nothing else moved. The container
independently confirmed 16 and 0.

### 8.3 The gate was proved to fail, not merely to pass

A green run cannot distinguish *blocking and passing* from *still advisory*. So a deliberate
type error was injected before the final run:

```
def _td2_probe(x: int) -> str:
    return x
→ mypy exit code 1
```

`|| true` is gone from both the Makefile and CI, so a non-zero exit now stops the run. The
probe was reverted before verification.

### 8.4 Three things the review got wrong, recorded

The independent review is responded to in §2; these are the three that the code contradicted:

1. **"Not architectural flaws, just friction with Python's dynamic heritage."** Three of the
   24 were **false signatures**. One of them produced five errors, four in a module it did
   not live in.
2. **`Sum(**kwargs)` filed under ORM dynamism.** It was an ordinary heterogeneous dict; the
   proposed remedy — a fuller function signature — would not have touched it.
3. **"Fixes potential bugs (like the int vs None comparison)."** That one is provably safe:
   the guard two lines above proves the value is never `None`.

**And one it got right that mattered most:** forbidding `Any` as the escape hatch. Not one
of the 24 was silenced that way.

### 8.5 R3 resolved, and the direction was not predictable

§2.3 flagged `pdf.py:55` and `:57` as *inversely* coupled — adding the `weasyprint` override
might make the unused `# type: ignore` **necessary again**. It does not: `warn_return_any`
is not enabled, so `HTML` being `Any` never triggers `no-any-return`. Both cleared by adding
the override **and deleting the ignore**.

Handling them as one step was right. Guessing the direction would have been a coin flip.

### 8.6 A finding worth carrying: mypy's cache hid a config change

The first run after adding the `weasyprint` override still reported the error. Only a **cold
cache** showed the truth. `make verify` builds `--no-cache` so the gate is unaffected — but
now that mypy is blocking, a stale local `.mypy_cache` can make a developer believe the gate
is green when it is not.

### 8.7 Scope held

**`disallow_untyped_defs` was not turned on globally** (§2.2b) and
**`djangorestframework-stubs` was not adopted** (§3, now TD-33). Both were recommended by
the review and both would have expanded an item that had already slipped three times.

Two items were discovered while closing this one and recorded rather than absorbed:
**TD-34** (`ops/` sits outside `mypy backend/`) and **TD-35** (`pip-audit --strict || true`
is still advisory — the same pattern, a different scan).

### 8.8 What it cost, and what it is worth

§6 predicted 3 real defects, 6 readability improvements, 15 tax. That is what it was.
Coverage fell 0.02 points, permanently, because the `TYPE_CHECKING` block can never execute.

**The value remains the 25th error** — the one this gate catches next year in code nobody
has written. Four defects have been found since M7 shipped, all by running the real thing
and none by review. A blocking type gate is one of the few mechanisms that catches a defect
*before* it runs.

---

*Implemented and verified. TD-2 / TD-18 closed.*
