"""**The performance harness must measure the requirement, not a comfortable subset.**

`02` §21 opens with the sentence these contracts exist to keep true:

> *"A non-functional goal without a measurement method is not a requirement."*

M10 gave the eleven NFR-SEC requirements a traceable measurement. The performance and
scalability families had none: before this pass, ``grep -r "NFR-PER" backend/tests/``
returned nothing at all, and the only measurement anyone had taken was M7's, against a
dataset **a tenth of the DR-8 retailer ceiling**.

**Three failure modes, and each has a contract below.**

1. **A threshold drifts from the document.** A budget written as a literal in a script is a
   requirement copy nobody reviews. Every threshold is read back out of `02` and `01` and
   compared, so raising one fails here rather than turning red into green.
2. **A report is added and never timed.** `sync_health` and the customer statement both
   post-date M7 and were absent from the harness for four milestones. A budget that skips a
   report is a budget the newest report is exempt from.
3. **A below-envelope run is reported as envelope evidence.** NFR-PER-001 and NFR-SCA-001
   both say *"at the envelope"*. The `m7` profile exists for comparison with history and
   must never be able to claim them.

Read from the mounted repository, because `ops/` is where the measurement gets quietly
narrowed — the same reasoning `test_mobile_boundary` uses for `|| true`, and
`test_restore_rehearsal` for a fabricated PASS. **Text and AST, never import**: this is a
repository-level contract, and importing the harness would run `django.setup()` and a
`sys.path` mutation inside the suite. Every earlier attempt to write one of these as an
application-runtime test failed on the plumbing rather than on its subject.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.adversarial

ROOT = Path(__file__).resolve().parents[3]

HARNESS = ROOT / "ops" / "report_performance.py"
REQUIREMENTS = ROOT / "docs" / "02_Requirements_Specification.md"
VISION = ROOT / "docs" / "01_Project_Vision.md"
SELECTORS = ROOT / "backend" / "reporting" / "selectors.py"
MAKEFILE = ROOT / "Makefile"
COMPOSE = ROOT / "docker" / "compose.yml"

#: Read from outside `backend/`; they arrive by bind-mount (`docker/compose.dev.yml`).
REQUIRED_PATHS = (
    "ops/report_performance.py",
    "docs/02_Requirements_Specification.md",
    "docs/01_Project_Vision.md",
    "Makefile",
    "docker/compose.yml",
)

#: Databases the corpus must never be written into. `districore` is the working development
#: database; `districore_prod` is the live one. Same list `ops/restore.sh` refuses.
WORKING_DATABASES = ("districore", "districore_prod")


def _verdicts_module():
    """Load `ops/perf_verdicts.py` **by path**, and assert it stayed importable.

    It imports nothing but the standard library, which is the property that lets these
    contracts test *behaviour* instead of grepping source. `report_performance.py` calls
    `django.setup()` at import and can never be loaded here — which is precisely how a
    verdict function that reported a hard failure as `NOT MEASURED` survived review.
    """
    path = ROOT / "ops" / "perf_verdicts.py"
    assert path.exists(), f"{path} is missing; the verdict mapping has no testable home"
    name = "perf_verdicts_under_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution, as importlib documents. `@dataclass` resolves string
    # annotations through `sys.modules[cls.__module__]`, so a module executed while absent
    # from it raises inside `dataclasses` rather than anywhere near the subject.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)  # raises if it ever acquires a Django import
    finally:
        sys.modules.pop(name, None)
    return module


def _make_recipe(target: str) -> str:
    """One target's recipe, tab-indented lines only."""
    makefile = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(
        rf"^{re.escape(target)}:[^\n]*\n(?P<body>(?:\t[^\n]*\n|\n(?=\t))*)",
        makefile,
        re.MULTILINE,
    )
    assert match, f"the `{target}` target is gone from the Makefile"
    return match.group("body")


def test_every_path_this_suite_reads_is_visible_from_inside_the_container():
    """Fail on the plumbing *as* plumbing, before any contract is evaluated."""
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    assert not missing, (
        f"not visible at {ROOT}: {missing}. These arrive by bind-mount — add them to the "
        "`app` service volumes in `docker/compose.dev.yml`."
    )


def _harness_constants() -> dict[str, object]:
    """Module-level literal constants, by AST. No import, no `django.setup()`."""
    tree = ast.parse(HARNESS.read_text(encoding="utf-8"))
    found: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name):
            try:
                found[target.id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return found


def _profile_field(profile: str, name: str) -> object:
    """One keyword argument of one `Profile(...)` call inside the `PROFILES` literal."""
    tree = ast.parse(HARNESS.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or getattr(node.func, "id", None) != "Profile":
            continue
        keywords = {kw.arg: kw.value for kw in node.keywords}
        name_node = keywords.get("name")
        if not isinstance(name_node, ast.Constant) or name_node.value != profile:
            continue
        wanted = keywords.get(name)
        assert wanted is not None, f"profile `{profile}` has no `{name}`"
        try:
            return ast.literal_eval(wanted)
        except ValueError:
            # A name reference such as DR8_MAX_RETAILERS — resolve it from the constants.
            assert isinstance(wanted, ast.Name), f"cannot resolve `{name}` for `{profile}`"
            return _harness_constants()[wanted.id]
    raise AssertionError(f"no `{profile}` profile in {HARNESS.name}")


# ------------------------------------------------- the thresholds must be the frozen ones
def test_the_report_budget_is_the_one_the_requirement_states():
    """NFR-PER-003 / FR-RPT-015 — *"within 10 seconds"*.

    Read back out of `02` rather than restated here, so the document and the instrument
    cannot drift apart without one of them failing.
    """
    text = REQUIREMENTS.read_text(encoding="utf-8")
    row = re.search(r"\|\s*NFR-PER-003\s*\|([^|]*)\|", text)
    assert row, "NFR-PER-003 is no longer in `02` §21.3"

    stated = re.search(r"within\s+(\d+)\s+seconds", row.group(1))
    assert stated, f"NFR-PER-003 no longer states a second budget: {row.group(1).strip()}"
    assert _harness_constants()["REPORT_BUDGET_SECONDS"] == float(stated.group(1)), (
        f"the harness budget is not `02`'s {stated.group(1)}s. A threshold that drifts from "
        "the requirement measures nothing the requirement asked for."
    )


def test_the_interactive_budget_and_percentile_are_the_ones_the_requirement_states():
    """NFR-PER-001 — *"within 2 seconds at the 95th percentile"*."""
    text = REQUIREMENTS.read_text(encoding="utf-8")
    row = re.search(r"\|\s*NFR-PER-001\s*\|([^|]*)\|", text)
    assert row, "NFR-PER-001 is no longer in `02` §21.3"

    seconds = re.search(r"within\s+(\d+)\s+seconds", row.group(1))
    percentile = re.search(r"(\d+)(?:st|th|nd|rd)\s+percentile", row.group(1))
    assert seconds and percentile, f"NFR-PER-001 lost its budget or its percentile: {row.group(1)}"

    constants = _harness_constants()
    assert constants["INTERACTIVE_BUDGET_SECONDS"] == float(seconds.group(1))
    assert constants["INTERACTIVE_PERCENTILE"] == int(percentile.group(1))


def test_the_linearity_line_is_exactly_linear():
    """NFR-SCA-003 — *"no query may degrade worse than linearly"*.

    Linear is an exponent of exactly 1.0 in ``time ~ history ** k``. The noise allowance is
    a separate constant on purpose: it may soften what *fails the stage*, but it must never
    become the line the report prints as the requirement.
    """
    constants = _harness_constants()
    assert constants["LINEAR_EXPONENT"] == 1.0, (
        "the linear exponent is no longer 1.0. Worse-than-linear growth would now be "
        "reported as compliant, which is the whole of NFR-SCA-003."
    )
    allowance = constants["LINEARITY_NOISE_ALLOWANCE"]
    assert isinstance(allowance, float) and 0 < allowance <= 0.25, (
        f"the measurement-noise allowance is {allowance}. Above a quarter it stops being "
        "noise and starts being a second, softer requirement."
    )


def test_the_dr8_profile_is_the_envelope_the_vision_states():
    """`01` NFR-4's ceilings — ≤10,000 SKUs, ≤10,000 retailers, ≤5 years.

    NFR-PER-001 and NFR-SCA-001 are both *"at the envelope"*. M7's dataset held 1,000
    customers and 500 products — 10% and 5% — which is why its numbers cannot evidence
    either, and why this contract reads the ceilings from `01` instead of trusting a literal.
    """
    vision = VISION.read_text(encoding="utf-8")
    envelope = re.search(r"NFR-4[^|]*\|[^|]*\|([^|]*)\|", vision) or re.search(
        r"DR-8 three-year design envelope[^\n]*", vision
    )
    assert envelope, "`01` NFR-4's DR-8 envelope is gone"
    stated = envelope.group(0)

    skus = re.search(r"≤\s*([\d,]+)\s+active SKUs", stated)
    retailers = re.search(r"≤\s*([\d,]+)\s+retailers", stated)
    years = re.search(r"≤\s*(\d+)\s+years of transaction history", stated)
    assert skus and retailers and years, f"`01` NFR-4 no longer states the ceilings: {stated}"

    constants = _harness_constants()
    assert constants["DR8_MAX_SKUS"] == int(skus.group(1).replace(",", ""))
    assert constants["DR8_MAX_RETAILERS"] == int(retailers.group(1).replace(",", ""))
    assert constants["DR8_YEARS_RETAINED"] == int(years.group(1))

    assert _profile_field("dr8", "products") == constants["DR8_MAX_SKUS"], (
        "the `dr8` profile no longer builds SKUs to the envelope ceiling, so a PASS from it "
        "would not be evidence for NFR-SCA-001"
    )
    assert _profile_field("dr8", "customers") == constants["DR8_MAX_RETAILERS"], (
        "the `dr8` profile no longer builds retailers to the envelope ceiling. "
        "`receivables_ageing` is a per-customer walk — this is the dimension that report "
        "is linear in, and the one that breached at M7"
    )


def test_the_m7_profile_stays_below_the_envelope_and_says_so():
    """**Anti-vacuity, and the honesty contract.**

    `m7` exists to keep 2026-08-09's numbers comparable. If it ever grew to the ceilings it
    would stop being the historical shape *and* the harness would lose the only profile that
    can distinguish a regression from a re-scaling. It must also carry the warning, because
    a profile that is quietly below envelope is how a below-envelope run gets read as one.
    """
    constants = _harness_constants()
    assert _profile_field("m7", "customers") < constants["DR8_MAX_RETAILERS"]
    assert _profile_field("m7", "products") < constants["DR8_MAX_SKUS"]

    note = _profile_field("m7", "note")
    assert isinstance(note, str) and "not sufficient to evidence NFR-SCA-001" in note, (
        "the `m7` profile no longer declares that it cannot evidence NFR-SCA-001"
    )

    source = HARNESS.read_text(encoding="utf-8")
    assert re.search(r'!=\s*"dr8"', source) and "below the DR-8 ceilings" in source, (
        "the harness no longer warns when it runs below the envelope"
    )


# ---------------------------------------------------- every report must actually be timed
def test_every_public_report_selector_is_timed():
    """**The defect that hid for four milestones.**

    `sync_health` (FR-RPT-009, added at M9.4) and `statement_table` were both absent from
    the harness's case list. Eleven reports were timed and the two newest were not, so the
    only two reports whose performance nobody had ever measured were the two most recently
    written.

    The public surface of `reporting.selectors` *is* the set of reports, so it is read
    rather than restated — a hand-maintained list is how the gap opened.
    """
    tree = ast.parse(SELECTORS.read_text(encoding="utf-8"))
    public = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    assert public, "no public selectors found — this contract would be vacuous"

    harness = HARNESS.read_text(encoding="utf-8")
    untimed = sorted(name for name in public if f"reports.{name}(" not in harness)
    assert not untimed, (
        f"these reports are never timed by the harness: {untimed}. NFR-PER-003 applies to "
        "every report, and a report added after the last measurement is exactly the one "
        "most likely to breach."
    )


def test_the_harness_refuses_a_dataset_built_for_another_profile():
    """A 1,000-customer dataset must not be measured as if it were the envelope.

    The profiles share the `PERF-` prefixes, so a presence check alone would reuse whichever
    dataset happened to be in the database and report it under whatever profile was asked
    for — a below-envelope run wearing an envelope label.
    """
    source = HARNESS.read_text(encoding="utf-8")
    match = re.search(r"def _dataset_matches\(.*?\n(?:.*?\n)*?\n\n", source)
    assert match, "`_dataset_matches` is gone; the harness cannot detect a profile mismatch"

    body = match.group(0)
    for dimension in ("invoices", "customers", "products"):
        assert f"profile.{dimension}" in body, (
            f"`_dataset_matches` no longer compares `{dimension}`, so a dataset differing "
            "only in that dimension would be silently reused"
        )


def test_a_breach_cannot_be_reported_as_a_pass():
    """**The B-3 lesson, in a second place.**

    A gate that manufactures its own evidence is worse than no gate. The harness must derive
    each verdict from the measurements and exit non-zero when anything breached — not print
    a template and return 0, which is exactly how a failed restore rehearsal was once
    recorded as a passed one.
    """
    source = HARNESS.read_text(encoding="utf-8")

    assert re.search(r"verdicts\s*=\s*evaluate\(", source), (
        "the harness no longer derives its verdicts from `perf_verdicts.evaluate`, so the "
        "mapping the contracts above test is not the mapping it runs"
    )
    assert re.search(r"blocking\s*=\s*failing\(verdicts\)", source), (
        "nothing computes the failing requirements, so nothing can gate on them"
    )
    assert re.search(r"return\s+1\s+if\s+blocking\s+else\s+0", source), (
        "the exit status is no longer driven by the requirement verdicts. Driving it from a "
        "breach counter is how PARTIAL and NOT MEASURED became indistinguishable from FAIL."
    )
    assert not re.search(r"if\s+total\s+and\s+verdict", source), (
        "the global breach counter is back in the verdict path. One requirement's breach "
        "must never alter another's verdict."
    )


# --------------------------------------------- the corpus must never reach a real database
def test_the_harness_refuses_every_database_but_the_disposable_one():
    """**Fail closed, by allow-list.**

    The corpus is roughly three-quarters of a million synthetic financial documents written
    without their services, and nothing undoes it. A deny-list would protect the two names
    someone thought of and let the harness fill a staging copy, a colleague's restore, or
    `districore_restore_test` itself.

    So the guard admits exactly one name and refuses everything else — which also means a
    forgotten `DATABASE_URL` override kills the run rather than the database.
    """
    constants = _harness_constants()
    perf = constants["PERF_DATABASE"]
    assert isinstance(perf, str) and perf, "the harness no longer names a disposable database"
    assert perf not in WORKING_DATABASES, (
        f"the disposable database is `{perf}`, which is a working database. That is the "
        "one value this whole guard exists to make impossible."
    )

    source = HARNESS.read_text(encoding="utf-8")
    guard = re.search(r"def guard_database\(\).*?(?=\n@|\ndef |\nclass )", source, re.DOTALL)
    assert guard, "`guard_database` is gone; nothing checks which database is about to be filled"
    body = guard.group(0)

    assert re.search(r"if\s+name\s*==\s*PERF_DATABASE:\s*\n\s*return name", body), (
        "the guard is no longer an allow-list. A deny-list admits every database nobody "
        "remembered to name."
    )
    assert "raise SystemExit(" in body, (
        "the guard no longer terminates the run; a warning does not stop 750,000 inserts"
    )


def test_the_guard_runs_before_anything_is_written():
    """A guard the writer does not consult is a guard that can be routed around.

    `synthesise` is what writes. It must call the guard itself, not merely trust that `main`
    did — the same reasoning that puts the live-database refusal inside `ops/restore.sh` as
    well as in the `restore-rehearsal` recipe.
    """
    tree = ast.parse(HARNESS.read_text(encoding="utf-8"))
    callers = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(inner, ast.Call) and getattr(inner.func, "id", None) == "guard_database"
            for inner in ast.walk(node)
        )
    }
    assert {"synthesise", "main"} <= callers, (
        f"`guard_database` is called from {sorted(callers)}. It must be called from both "
        "`synthesise` (which writes) and `main` (which measures)."
    )


def test_make_perf_recreates_the_disposable_database_and_never_the_development_one():
    """`make perf` must build its own target, not borrow whatever `DATABASE_URL` points at.

    Three properties, and all three are needed. The recipe must **redirect the connection**
    — otherwise the harness inherits `.env` and the guard turns a measurement into a
    refusal every time. It must **create the database it is about to fill**, so a run starts
    from a known empty schema rather than whatever the last one left. And `perf-db` must
    **refuse the working names outright**, because the drop happens there.
    """
    perf = _make_recipe("perf")
    perf_db = _make_recipe("perf-db")

    assert "PERF_URL" in perf, (
        "`make perf` no longer overrides DATABASE_URL, so it would run against whatever "
        "`.env` configures — the development database"
    )
    assert "DROP DATABASE IF EXISTS" in perf_db and "CREATE DATABASE" in perf_db, (
        "`perf-db` no longer recreates the disposable database, so a run would measure "
        "whatever the previous one left behind"
    )
    assert "migrate" in perf_db, (
        "`perf-db` no longer migrates, so the corpus would be measured against a schema "
        "that is not the application's"
    )
    for database in WORKING_DATABASES:
        assert database in perf_db, f"`{database}` is no longer refused as a perf target"
    assert re.search(r"REFUSED[^\n]*working database", perf_db), "the refusal message is gone"
    assert "exit 2" in perf_db, "the guard does not exit non-zero"

    makefile = MAKEFILE.read_text(encoding="utf-8")
    declared = re.search(r"^PERF_DB\s*:?=\s*(\S+)", makefile, re.MULTILINE)
    assert declared, "PERF_DB is no longer declared"
    assert declared.group(1) == _harness_constants()["PERF_DATABASE"], (
        f"the Makefile targets `{declared.group(1)}` and the harness admits "
        f"`{_harness_constants()['PERF_DATABASE']}`. They must be one name, or every run "
        "is refused and someone 'fixes' it by widening the guard."
    )


def test_the_disposable_database_is_not_the_configured_default():
    """Anti-vacuity, read from the compose file rather than from this test's memory.

    If `PERF_DB` ever became the value `docker/compose.yml` defaults `POSTGRES_DB` to, every
    guard above would still pass while pointing at the working database.
    """
    compose = COMPOSE.read_text(encoding="utf-8")
    default = re.search(r"POSTGRES_DB:\s*\$\{POSTGRES_DB:-([^}]+)\}", compose)
    assert default, "`docker/compose.yml` no longer declares a default POSTGRES_DB"
    assert default.group(1) not in ("", None)
    assert _harness_constants()["PERF_DATABASE"] != default.group(1), (
        f"the disposable database is the compose default `{default.group(1)}` — the "
        "development database wearing a different variable name"
    )


# ============================================ the verdict mapping, tested as behaviour
def _stages(module, **overrides):
    """Three healthy stages, so each contract below perturbs exactly one thing."""
    base = {
        "reports": module.StageResult(ran=True, total=13, worst_label="r", worst_seconds=1.0),
        "interactive": module.StageResult(ran=True, total=11, worst_label="i", worst_seconds=0.2),
        "linearity": module.StageResult(ran=True, total=6),
    }
    base.update(overrides)
    return base


def _evaluate(module, *, at_envelope=True, **overrides) -> dict[str, object]:
    verdicts = module.evaluate(
        **_stages(module, **overrides),
        at_envelope=at_envelope,
        report_budget_seconds=10.0,
        interactive_budget_seconds=2.0,
        interactive_percentile=95,
    )
    return {verdict.requirement: verdict for verdict in verdicts}


def test_a_measured_breach_can_never_be_reported_as_not_measured():
    """**The defect the first DR-8 run shipped.**

    Thirteen reports ran, `receivables ageing` took 17.139s and `dashboard` 16.874s against
    a ten-second requirement, and the release gate printed `NFR-PER-003  NOT MEASURED`. The
    original mapping used `NOT MEASURED` as the else-branch of a PASS test, so *measured and
    failing* and *never measured* came out of the same expression.

    **Absence of a measurement is not evidence of compliance, and a failure is not an
    absence.** The second half of that sentence is the one that was missing.
    """
    module = _verdicts_module()
    breached = module.StageResult(
        ran=True, total=13, breached=("receivables ageing", "dashboard"), worst_seconds=17.139
    )
    verdicts = _evaluate(module, reports=breached)

    assert verdicts["NFR-PER-003"].state == module.FAIL, (
        "a report that exceeded the budget is reported as something other than FAIL"
    )
    assert verdicts["NFR-PER-003"].state != module.NOT_MEASURED
    assert "receivables ageing" in verdicts["NFR-PER-003"].detail, (
        "the verdict does not name what breached, so the record cannot be acted on"
    )
    assert verdicts["NFR-SCA-001"].state == module.FAIL, (
        "the envelope was not sustained; SCA-001 must not report the absence of a measurement"
    )


def test_a_measured_breach_can_never_be_reported_as_pass():
    """The other direction, held for every requirement that has a threshold."""
    module = _verdicts_module()
    cases = {
        "NFR-PER-003": {"reports": module.StageResult(ran=True, total=13, breached=("r",))},
        "NFR-PER-001": {"interactive": module.StageResult(ran=True, total=11, breached=("i",))},
        "NFR-SCA-003": {"linearity": module.StageResult(ran=True, total=6, breached=("q",))},
    }
    for requirement, override in cases.items():
        verdicts = _evaluate(module, **override)
        assert verdicts[requirement].state == module.FAIL, (
            f"{requirement} reported {verdicts[requirement].state} over a measured breach"
        )


def test_one_requirements_breach_cannot_alter_another_requirements_verdict():
    """**No global counter. Ever.**

    The original mapping ended in `"FAIL" if total and verdict.startswith("PASS")`, so a
    report breach turned NFR-PER-001 and NFR-SCA-003 into failures although every one of
    their own measurements passed — eleven S1 operations at seven times inside budget, and
    two sub-linear queries. A verdict must be a function of its own requirement's evidence.
    """
    module = _verdicts_module()
    clean = _evaluate(module)
    with_report_breach = _evaluate(
        module, reports=module.StageResult(ran=True, total=13, breached=("receivables ageing",))
    )

    for requirement in ("NFR-PER-001", "NFR-SCA-003"):
        assert with_report_breach[requirement].state == clean[requirement].state, (
            f"a NFR-PER-003 breach changed {requirement} from "
            f"{clean[requirement].state} to {with_report_breach[requirement].state}. "
            "Neither requirement describes the reports stage."
        )


def test_per_001_can_never_report_an_unqualified_pass_while_s4_does_not_exist():
    """NFR-PER-001 names **`S1` and `S4`**; `S4` is Edition 1b (`00` §19.1, M12).

    A bare PASS would tell a reader the requirement is discharged when one of its two
    surfaces has never been looked at. PARTIAL says what is true: favourable evidence,
    incomplete coverage. A breach on `S1` is still FAIL — an unmeasurable second surface
    does not soften a violation on the first.
    """
    module = _verdicts_module()
    verdict = _evaluate(module)["NFR-PER-001"]

    assert verdict.state == module.PARTIAL, (
        f"NFR-PER-001 reported {verdict.state} with S4 unmeasurable. Only PARTIAL, FAIL or "
        "NOT MEASURED are honest here."
    )
    assert verdict.state != module.PASS
    assert module.BLOCKED in verdict.detail and "S4" in verdict.detail, (
        "the verdict no longer says which surface is unavailable or why"
    )
    breached = _evaluate(
        module, interactive=module.StageResult(ran=True, total=11, breached=("S1 stock list",))
    )["NFR-PER-001"]
    assert breached.state == module.FAIL, "an S1 breach was softened by S4's absence"


def test_sca_003_reports_partial_assessability_rather_than_claiming_coverage():
    """Four of six queries take no date range, so history cannot be scaled for them.

    Reporting PASS over a sample that excluded two thirds of the queries would be the
    report claiming coverage the instrument does not have.
    """
    module = _verdicts_module()
    partial = _evaluate(
        module,
        linearity=module.StageResult(
            ran=True, total=6, not_assessable=("sales (day)", "returns", "pipeline", "variance")
        ),
    )["NFR-SCA-003"]
    assert partial.state == module.PARTIAL
    assert "NOT ASSESSABLE" in partial.detail and "sales (day)" in partial.detail

    everything = _evaluate(module, linearity=module.StageResult(ran=True, total=6))["NFR-SCA-003"]
    assert everything.state == module.PASS, (
        "with every query assessable and sub-linear the verdict must be a full PASS, or "
        "PARTIAL stops meaning anything"
    )
    nothing = _evaluate(
        module, linearity=module.StageResult(ran=True, total=4, not_assessable=("a", "b", "c", "d"))
    )["NFR-SCA-003"]
    assert nothing.state == module.NOT_MEASURED, (
        "with nothing assessable the instrument measured nothing and must say so"
    )


def test_per_005_is_a_process_requirement_and_is_independent_of_latency():
    """*"Performance MUST be re-measured ... before each release"*, verified by Release gate.

    It states no latency of its own. A breach elsewhere is the *product* of the
    re-measurement, not evidence that it failed to happen — the original mapping reported
    `NOT MEASURED` for a run that plainly occurred and produced 30 timings.
    """
    module = _verdicts_module()
    clean = _evaluate(module)["NFR-PER-005"]
    breached = _evaluate(
        module,
        reports=module.StageResult(
            ran=True, total=13, breached=("receivables ageing", "dashboard")
        ),
    )["NFR-PER-005"]

    assert clean.state == module.MET
    assert breached.state == module.MET, (
        f"a latency breach turned the re-measurement obligation into {breached.state}. The "
        "measurement happened; NFR-PER-003 and NFR-SCA-001 carry the failure."
    )
    assert "blocked" in breached.detail.lower(), (
        "MET no longer says the release is blocked, so a reader could take it for shippable"
    )

    partial_run = _evaluate(module, linearity=module.StageResult(ran=False))["NFR-PER-005"]
    assert partial_run.state == module.NOT_MEASURED, (
        "a partial run must not discharge a release gate that asks for the whole measurement"
    )


def test_only_a_violation_stops_the_release():
    """PARTIAL, BLOCKED and NOT MEASURED are gaps in evidence, not requirement violations.

    They must not be silently exit-code-equivalent to a breach, or the harness cannot
    distinguish "we have not looked" from "we looked and it is broken".
    """
    module = _verdicts_module()
    assert module.FAILING_STATES == (module.FAIL,)

    verdicts = list(_evaluate(module).values())
    assert not module.failing(verdicts), "a clean run reports a failing requirement"

    breached = list(
        _evaluate(module, reports=module.StageResult(ran=True, total=13, breached=("r",))).values()
    )
    failing = {verdict.requirement for verdict in module.failing(breached)}
    assert failing == {"NFR-PER-003", "NFR-SCA-001"}, (
        f"the failing set is {failing}; a report breach violates exactly PER-003 and the "
        "envelope requirement that contains it"
    )


def test_the_recorded_dr8_evidence_recomputes_to_the_verdicts_it_carries():
    """**The writer and the reader must agree about the run that actually happened.**

    `evaluate_document` re-derives verdicts from saved timings, which is what made
    correcting the M10.6a mapping cheap: the DR-8 corpus costs minutes to synthesise and
    would measure differently the second time, so a verdict is fixed by re-reading the
    artefact, never by re-running the benchmark.

    **This asserts an invariant, not a dated result.** It compares the recomputed verdicts
    against the `verdicts` block the harness itself wrote into the artefact. That holds for
    every run — the 2026-09-07 FAIL and the 2026-09-08 PASS alike — and it catches something
    the previous spelling could not: a drift between what `report_performance` records and
    what `perf_verdicts` computes. The earlier version hard-coded the 2026-09-07 verdicts, so
    it began failing the moment a *successful* run replaced the artefact — a test of one
    day's result wearing the name of a contract.

    **The historical failure is not lost, and was never held here.**

    * The **artefact** is immutable in history: ``git show 3b75aa7:ops/perf-latest.json``
      still carries `"NFR-PER-003": "NOT MEASURED"` and the 17.139 s timing, and
      `docs/M10.6_Performance_Report.md` §3 and §9 record both runs side by side.
      A test cannot read it — **the backend image contains no git** (`M10_Security_Review`
      §NFR-SEC-007, where this project already made that mistake once) — so reaching for a
      git object here would reproduce a defect the corpus has recorded.
    * The **mapping** that produced those verdicts is held by behaviour, where it belongs:
      `test_a_measured_breach_can_never_be_reported_as_not_measured` and
      `test_only_a_violation_stops_the_release` (PER-003 and SCA-001 → FAIL),
      `test_per_001_can_never_report_an_unqualified_pass_while_s4_does_not_exist` (PARTIAL),
      `test_sca_003_reports_partial_assessability_rather_than_claiming_coverage` (PARTIAL)
      and `test_per_005_is_a_process_requirement_and_is_independent_of_latency` (MET). Those
      feed the mapping synthetic breaches and cannot go stale.

    Skipped rather than failed when the file is absent: the evidence is an artefact of a run,
    not of the repository, and a contract that demands it would fail on a fresh clone.
    """
    evidence = ROOT / "ops" / "perf-latest.json"
    if not evidence.exists():
        pytest.skip("no recorded run in this tree")

    import json

    raw = evidence.read_text(encoding="utf-8")
    document = json.loads(raw[raw.index("{") :])
    module = _verdicts_module()

    recorded = {entry["requirement"]: entry["state"] for entry in document["verdicts"]}
    assert set(recorded) == {
        "NFR-PER-003",
        "NFR-PER-001",
        "NFR-SCA-001",
        "NFR-SCA-003",
        "NFR-PER-005",
    }, f"the artefact does not carry all five requirements: {sorted(recorded)}"

    recomputed = {
        verdict.requirement: verdict.state for verdict in module.evaluate_document(document)
    }
    assert recomputed == recorded, (
        f"the recorded run no longer recomputes to the verdicts it carries.\n"
        f"    recorded   ({document['measured_at']}): {recorded}\n"
        f"    recomputed (perf_verdicts today)      : {recomputed}\n"
        "The harness and the mapping disagree about a run that already happened."
    )


def test_only_the_evidence_document_reaches_stdout():
    """`config/logging.py` sends application logs to **stdout** by design (`00` §12).

    Right for a container, wrong for a script whose stdout is a machine-readable document:
    the first DR-8 run put `INFO axes.apps: AXES: BEGIN ...` above the opening brace and
    `json.load` refused the file. The swap has to happen **before** `django.setup()`,
    because `LOGGING` is applied during setup and `axes` logs from `AppConfig.ready()`.
    """
    source = HARNESS.read_text(encoding="utf-8")
    swap = source.index("sys.stdout = sys.stderr")
    # The *statement*, at column zero — `django.setup()` also appears in the comment that
    # explains this ordering, and matching that would compare the rule to its own prose.
    call = re.search(r"^django\.setup\(\)", source, re.MULTILINE)
    assert call, "`django.setup()` is no longer called at module level"
    setup = call.start()
    assert swap < setup, (
        "stdout is redirected after `django.setup()`, so anything logged during setup still "
        "lands in the evidence document"
    )
    assert "_EVIDENCE_STREAM = sys.stdout" in source, "the real stdout is no longer captured"
    assert re.search(r"print\(document, file=_EVIDENCE_STREAM", source), (
        "the document is no longer written to the saved stdout, so `--json -` would emit it "
        "into the log stream"
    )


def test_s4_is_recorded_as_unmeasurable_rather_than_assumed_to_pass():
    """NFR-PER-001 names **`S1` and `S4`**. `S4` is the retailer portal — Edition 1b, M12.

    It does not exist in this tree, so half of NFR-PER-001 cannot be measured at V1. That
    has to be stated in the output: a requirement measured on one of its two surfaces and
    reported as PASS is the quiet kind of false evidence.
    """
    assert "NOT MEASURABLE at V1" in HARNESS.read_text(encoding="utf-8"), (
        "the harness's interactive stage no longer declares the S4 gap in its own output"
    )
    module = _verdicts_module()
    detail = _evaluate(module)["NFR-PER-001"].detail
    assert "S4" in detail and module.BLOCKED in detail and "Edition 1b" in detail, (
        "NFR-PER-001's verdict no longer carries its own scope limit, so a reader sees a "
        f"verdict for a requirement measured on one surface of two: {detail!r}"
    )
