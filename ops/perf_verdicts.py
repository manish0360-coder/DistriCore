"""Measurements to requirement verdicts — the mapping, and nothing else.

**Why this is its own module.** `report_performance.py` calls `django.setup()` at import,
so nothing in the test suite can import it and every contract over it has to assert on its
*source text*. Verdict semantics are the one part that must be asserted on its *behaviour*:
the first DR-8 run reported a hard NFR-PER-003 failure as **NOT MEASURED**, and no amount of
grepping the file would have caught that. This module imports nothing but the standard
library, so `backend/tests/adversarial/test_performance_harness.py` loads it directly and
feeds it measurements.

**The defect this exists to make impossible.** The original mapping was::

    "NFR-PER-003": "PASS" if reports and not report_breaches else "NOT MEASURED"
    ...
    for requirement, verdict in verdicts.items():
        verdicts[requirement] = "FAIL" if total and verdict.startswith("PASS") else verdict

Two failures, in opposite directions, and both were reported to the operator as fact:

* **A measured breach became `NOT MEASURED`.** Thirteen reports ran, two exceeded the
  ten-second budget, and the release gate printed the absence of evidence. *Absence of a
  measurement is not evidence of compliance — and a failure is not an absence.*
* **One requirement's breach contaminated every other.** All eleven `S1` operations passed
  at seven times inside budget and both assessable linearity queries were sub-linear; both
  requirements were flipped to FAIL by a breach in a stage neither of them describes.

**A verdict is a function of its own requirement's measurements.** There is no global
counter here and there must never be one again.

**Six states, because the requirements need six.** A four-state vocabulary is what forced
the original mapping to lie: with only PASS / FAIL / NOT MEASURED to reach for, a
requirement measured on one of its two surfaces has no honest home.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# =============================================================================== states
#: Measured, and within the frozen threshold.
PASS = "PASS"  # noqa: S105 — a verdict state, not a credential
#: Measured, and outside the frozen threshold. **The only state that fails the run.**
FAIL = "FAIL"
#: Measured on part of what the requirement names, and compliant on that part. Never a
#: substitute for PASS: it is a statement that the evidence is incomplete, not favourable.
PARTIAL = "PARTIAL"
#: Not measurable because the surface the requirement names does not exist yet. Distinct
#: from NOT MEASURED, which is about this run; BLOCKED is about the product.
BLOCKED = "BLOCKED"
#: The measurement did not happen. **Never used for a measurement that happened and failed.**
NOT_MEASURED = "NOT MEASURED"
#: A *process* requirement was satisfied. `02` verifies NFR-PER-005 by "Release gate" — it
#: asks whether the re-measurement was performed, not how fast anything was.
MET = "MET"

#: States that stop a release. `PARTIAL`, `BLOCKED` and `NOT MEASURED` are gaps in the
#: evidence, which is a different thing from a requirement being violated.
FAILING_STATES = (FAIL,)


@dataclass(frozen=True)
class RequirementVerdict:
    """One requirement's state and the sentence that justifies it."""

    requirement: str
    state: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"requirement": self.requirement, "state": self.state, "detail": self.detail}

    def __str__(self) -> str:
        return f"{self.requirement:<12} {self.state:<13} {self.detail}"


# ========================================================================== measurements
@dataclass(frozen=True)
class StageResult:
    """What one stage produced, reduced to what a verdict needs.

    `ran` is carried separately from `len(labels)`: a stage that executed and measured
    nothing is not the same as a stage that never executed, and only one of them may
    become NOT MEASURED for a reason the operator can act on.
    """

    ran: bool = False
    total: int = 0
    breached: tuple[str, ...] = ()
    #: Only linearity uses this: a query with no date parameter cannot be scaled by
    #: history, so the instrument has nothing to say about it.
    not_assessable: tuple[str, ...] = ()
    #: The worst observed value, for the sentence the verdict carries.
    worst_label: str = ""
    worst_seconds: float = 0.0

    @property
    def assessable(self) -> int:
        return self.total - len(self.not_assessable)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


# ============================================================================== the rules
def evaluate(
    *,
    reports: StageResult,
    interactive: StageResult,
    linearity: StageResult,
    at_envelope: bool,
    report_budget_seconds: float,
    interactive_budget_seconds: float,
    interactive_percentile: int,
) -> list[RequirementVerdict]:
    """Map measurements onto the five requirements. **Pure, and independent per requirement.**

    No argument is shared between two rules except `at_envelope`, which two requirements
    genuinely both depend on because both are written *"at the envelope"*.
    """
    return [
        _per_003(reports, report_budget_seconds),
        _per_001(interactive, at_envelope, interactive_budget_seconds, interactive_percentile),
        _sca_001(reports, interactive, at_envelope),
        _sca_003(linearity),
        _per_005(reports, interactive, linearity, at_envelope),
    ]


def _per_003(reports: StageResult, budget: float) -> RequirementVerdict:
    """*"Reports MUST return within 10 seconds over five years of history."* `02` §21.3.

    Report-level, so **one breach is a breach** — the requirement is not an average over
    thirteen reports and a mean would hide exactly the one the owner waits on.
    """
    if not reports.ran:
        return RequirementVerdict("NFR-PER-003", NOT_MEASURED, "the reports stage did not run")
    if not reports.total:
        return RequirementVerdict("NFR-PER-003", NOT_MEASURED, "no report was timed")
    if reports.breached:
        return RequirementVerdict(
            "NFR-PER-003",
            FAIL,
            f"{len(reports.breached)} of {reports.total} reports exceed the {budget:.0f}s "
            f"requirement: {', '.join(reports.breached)}",
        )
    return RequirementVerdict(
        "NFR-PER-003",
        PASS,
        f"{_plural(reports.total, 'report')} timed, all within {budget:.0f}s "
        f"(worst {reports.worst_label} {reports.worst_seconds:.3f}s)",
    )


def _per_001(
    interactive: StageResult, at_envelope: bool, budget: float, percentile: int
) -> RequirementVerdict:
    """*"Interactive `S1` **and** `S4` operations ... 2 seconds at the 95th percentile."*

    **`S4` is the retailer portal**, and `00` §19.1 places it at M12, Edition 1b. It does
    not exist in this tree, so half of what this requirement names cannot be measured at
    V1 — which means the requirement **can never return an unqualified PASS here**.

    A compliant `S1` is `PARTIAL`, not `PASS`: the evidence is favourable and incomplete,
    and a bare PASS would tell a reader the requirement is discharged when one of its two
    surfaces has never been looked at. A breach on `S1` is still `FAIL` — an unmeasurable
    second surface does not soften a violation on the first.
    """
    if not interactive.ran:
        return RequirementVerdict("NFR-PER-001", NOT_MEASURED, "the interactive stage did not run")
    if not at_envelope:
        return RequirementVerdict(
            "NFR-PER-001",
            NOT_MEASURED,
            "measured below the DR-8 envelope; the requirement is written 'under the DR-8 "
            "envelope' and a smaller dataset cannot evidence it",
        )
    if interactive.breached:
        return RequirementVerdict(
            "NFR-PER-001",
            FAIL,
            f"{len(interactive.breached)} of {interactive.total} S1 operations exceed "
            f"{budget:.0f}s at p{percentile}: {', '.join(interactive.breached)}",
        )
    return RequirementVerdict(
        "NFR-PER-001",
        PARTIAL,
        f"S1 PASS {interactive.total}/{interactive.total} within {budget:.0f}s at "
        f"p{percentile} (worst {interactive.worst_label} {interactive.worst_seconds:.3f}s); "
        f"S4 {BLOCKED} — the retailer portal is Edition 1b (00 §19.1, M12) and does not "
        "exist in V1",
    )


def _sca_001(
    reports: StageResult, interactive: StageResult, at_envelope: bool
) -> RequirementVerdict:
    """*"MUST sustain the DR-8 three-year envelope without architectural change."* `02` §21.4.

    Sustaining the envelope is the conjunction of the two things measured at it. Unlike
    NFR-PER-001 this requirement names no surface, so `S4`'s absence does not qualify it —
    it is a statement about the system under load, and the system was under load.
    """
    if not (reports.ran and interactive.ran):
        return RequirementVerdict(
            "NFR-SCA-001", NOT_MEASURED, "the envelope load test needs both reports and interactive"
        )
    if not at_envelope:
        return RequirementVerdict(
            "NFR-SCA-001", NOT_MEASURED, "the dataset was below the DR-8 master-data ceilings"
        )
    breached = (*reports.breached, *interactive.breached)
    if breached:
        return RequirementVerdict(
            "NFR-SCA-001",
            FAIL,
            f"measured at the DR-8 envelope and not sustained: {', '.join(breached)}",
        )
    return RequirementVerdict(
        "NFR-SCA-001", PASS, "sustained at the DR-8 envelope across reports and interactive S1"
    )


def _sca_003(linearity: StageResult) -> RequirementVerdict:
    """*"No query may degrade worse than linearly with retained history."* `02` §21.4.

    A query with no date parameter cannot be scaled by history, so this instrument has
    nothing to say about it — and saying PASS over a sample that excluded two-thirds of the
    queries would be the report claiming coverage it does not have.
    """
    if not linearity.ran:
        return RequirementVerdict("NFR-SCA-003", NOT_MEASURED, "the linearity stage did not run")
    if linearity.breached:
        return RequirementVerdict(
            "NFR-SCA-003",
            FAIL,
            f"{len(linearity.breached)} of {linearity.assessable} assessable queries grow "
            f"worse than linearly: {', '.join(linearity.breached)}",
        )
    if not linearity.assessable:
        return RequirementVerdict(
            "NFR-SCA-003",
            NOT_MEASURED,
            f"none of {linearity.total} queries is assessable by this instrument",
        )
    if linearity.not_assessable:
        return RequirementVerdict(
            "NFR-SCA-003",
            PARTIAL,
            f"{linearity.assessable} of {linearity.total} queries are assessable and all are "
            f"sub-linear; {len(linearity.not_assessable)} NOT ASSESSABLE (no history "
            f"parameter): {', '.join(linearity.not_assessable)}",
        )
    return RequirementVerdict(
        "NFR-SCA-003",
        PASS,
        f"all {linearity.total} queries grow no worse than linearly with retained history",
    )


def _per_005(
    reports: StageResult, interactive: StageResult, linearity: StageResult, at_envelope: bool
) -> RequirementVerdict:
    """*"Performance MUST be re-measured against the five-year projected dataset before each
    release, not only against a fresh database."* `02` §21.3, verified by **Release gate**.

    **This is a process requirement, and it is the one the original mapping mangled worst.**
    It asks whether the re-measurement happened. It states no latency of its own, so a
    breach elsewhere cannot make it `NOT MEASURED` — the measurement plainly occurred, and
    a breach is its *product*, not its absence.

    `MET` rather than `PASS`, because what is satisfied is an obligation to measure, not a
    threshold. The release still stops: NFR-PER-003 and NFR-SCA-001 carry that, and the
    detail below says so rather than leaving a reader to infer that MET means shippable.
    """
    if not (reports.ran and interactive.ran and linearity.ran):
        return RequirementVerdict(
            "NFR-PER-005",
            NOT_MEASURED,
            "a partial run does not discharge the release gate; all stages must run",
        )
    if not at_envelope:
        return RequirementVerdict(
            "NFR-PER-005",
            NOT_MEASURED,
            "re-measured below the envelope; the requirement names the five-year projected dataset",
        )
    breached = (*reports.breached, *interactive.breached, *linearity.breached)
    outcome = (
        "the release is blocked by the breaches this run recorded"
        if breached
        else "no breach recorded"
    )
    return RequirementVerdict(
        "NFR-PER-005",
        MET,
        f"the five-year re-measurement was performed against the DR-8 dataset; {outcome}",
    )


# ================================================== recomputing from a preserved document
def stages_from_document(document: Mapping[str, Any]) -> dict[str, StageResult]:
    """Rebuild the stage results from a saved evidence document.

    **This is how a verdict is corrected without rebuilding the dataset.** The DR-8 corpus
    costs 791 seconds to synthesise; re-running it to re-derive a mapping over timings that
    are already recorded would be paying for the measurement twice and getting a *different*
    measurement the second time.
    """

    def stage(rows: Sequence[Mapping[str, Any]], breach_states: tuple[str, ...]) -> StageResult:
        if not rows:
            return StageResult(ran=False)
        breached = tuple(r["label"] for r in rows if r.get("verdict") in breach_states)
        assessable = [r for r in rows if r.get("verdict") != "NOT ASSESSABLE"]
        timed = [r for r in assessable if r.get("seconds") is not None]
        worst = max(timed, key=lambda r: r["seconds"]) if timed else None
        return StageResult(
            ran=True,
            total=len(rows),
            breached=breached,
            not_assessable=tuple(r["label"] for r in rows if r.get("verdict") == "NOT ASSESSABLE"),
            worst_label=worst["label"] if worst else "",
            worst_seconds=float(worst["seconds"]) if worst else 0.0,
        )

    return {
        "reports": stage(document.get("reports", ()), ("BREACH",)),
        "interactive": stage(document.get("interactive", ()), ("BREACH",)),
        "linearity": stage(document.get("linearity", ()), ("BREACH",)),
    }


def evaluate_document(document: Mapping[str, Any]) -> list[RequirementVerdict]:
    """`evaluate` applied to a saved evidence document, thresholds and all."""
    stages = stages_from_document(document)
    thresholds = document.get("thresholds", {})
    return evaluate(
        reports=stages["reports"],
        interactive=stages["interactive"],
        linearity=stages["linearity"],
        at_envelope=bool(document.get("profile", {}).get("at_dr8_envelope")),
        report_budget_seconds=float(thresholds.get("report_budget_seconds", 0.0)),
        interactive_budget_seconds=float(thresholds.get("interactive_budget_seconds", 0.0)),
        interactive_percentile=int(thresholds.get("interactive_percentile", 95)),
    )


def failing(verdicts: Sequence[RequirementVerdict]) -> list[RequirementVerdict]:
    """The requirements that stop a release. Gaps in evidence are not violations."""
    return [verdict for verdict in verdicts if verdict.state in FAILING_STATES]
