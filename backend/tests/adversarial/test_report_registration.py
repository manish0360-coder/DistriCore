"""**TD-29 — a report must be wired everywhere, or not at all** (D5 Stage 4, S4.0).

TD-29, recorded at M7 and carried since:

> *"Nothing asserts a **newly added** report is wired into `REPORT_MENU`, the API router and
> the CSV path. The eighth report will be added by someone who forgets one of the three."*

FR-PUR-015 is that eighth report — and the ninth, and the tenth. This contract is written
**before** the first procurement report exists, because a wiring test written afterwards
documents whatever was already forgotten instead of preventing it.

**The count that makes this necessary.** Adding one report today means editing **five**
places by hand, and nothing checks that all five happened:

1. `webadmin.report_views.REPORT_MENU`  — the navigation
2. `webadmin/urls.py`                   — the screen route
3. `api/v1/urls.py`                     — the API route
4. the CSV path on **both** surfaces
5. the hand-maintained report lists in the two integration suites

Miss (1) and the report exists but is unreachable. Miss (3) and the field app cannot fetch
it. Miss (4) and the export silently 404s under `?format=csv`. Miss (5) and it is wired but
untested. **None of those fail anything today.**

**No second registry is invented.** `REPORT_MENU` is the registry the repository already
has, and the join key is the URL name it already stores. The two routers and the CSV
capability are read from the **live URL conf and the live view classes** — not from a list
maintained here, which would be a sixth place to forget.

**How the anti-vacuity proofs work.** The rule is a pure function, `check_registration`,
over four sets of names. The live test feeds it the real wiring; the mutation tests feed it
deliberately broken copies. Both exercise **the same code**, so a mutation that passes is
proof the rule is inert — the construction `test_purchasing_boundary` uses for
`_transition`, applied to a set comparison instead of an AST walk.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.urls import get_resolver, resolve, reverse

pytestmark = pytest.mark.adversarial

BACKEND = Path(__file__).resolve().parents[2]

#: The prefix that makes a URL name a report. Both routers already follow it exactly, and
#: `api/v1/urls.py` records the one deliberate exclusion in a comment: the dashboard is
#: named `dashboard`, **not** `report-dashboard`, precisely so it never joins this set.
REPORT_PREFIX = "report-"

#: The helpers in `webadmin.report_views` through which a screen reaches the CSV branch.
#: `_respond` is the branch itself; `_report` wraps it. A view that reaches neither renders
#: HTML only, and `?format=csv` on it would return a page rather than a file.
WEB_CSV_HELPERS = frozenset({"_report", "_respond"})


# --------------------------------------------------------------------------- the rule


def check_registration(
    *,
    menu: set[str],
    web: set[str],
    api: set[str],
    web_csv: set[str],
    api_csv: set[str],
) -> list[str]:
    """The whole of TD-29, as a pure function. Returns failures; empty means complete.

    **Pure and total on purpose.** It reaches for nothing — no URL conf, no imports, no
    filesystem — so the mutation tests below can hand it any shape at all, including shapes
    that could not exist in a running system. A rule that could only be exercised against
    the live wiring could only ever be proven to pass.

    **Every comparison is bidirectional**, and that is the part that catches the real TD-29
    failure. Enumerating from the menu alone would miss the opposite mistake: a report added
    to a router and forgotten by the navigation is wired, reachable by URL, and invisible.
    """
    failures: list[str] = []

    if not menu:
        failures.append(
            "REPORT_MENU is empty. Either every report has been removed, or this contract "
            "is reading the wrong registry — both are failures."
        )

    for missing in sorted(menu - web):
        failures.append(f"{missing}: in REPORT_MENU, but no webadmin route is wired")
    for orphan in sorted(web - menu):
        failures.append(f"{orphan}: has a webadmin route, but is absent from REPORT_MENU")

    for missing in sorted(menu - api):
        failures.append(f"{missing}: in REPORT_MENU, but no API route is wired")
    for orphan in sorted(api - menu):
        failures.append(f"{orphan}: has an API route, but is absent from REPORT_MENU")

    for missing in sorted(menu - web_csv):
        failures.append(f"{missing}: webadmin view has no CSV export path")
    for missing in sorted(menu - api_csv):
        failures.append(f"{missing}: API view does not declare the CSV renderer")

    return failures


# ------------------------------------------------------------------- the live adapters


def _menu_names() -> set[str]:
    """The registry. `("webadmin:report-sales", "Sales")` -> `report-sales`."""
    from webadmin.report_views import REPORT_MENU

    return {name.split(":", 1)[-1] for name, _label in REPORT_MENU}


def _routed_names(namespace: str) -> set[str]:
    """Every `report-*` URL name actually registered under a namespace.

    Read from the resolver rather than by parsing `urls.py`, so a route that exists but is
    unreachable — shadowed, or in a module nobody includes — does not count as wired.
    """
    _prefix, sub_resolver = get_resolver().namespace_dict[namespace]
    return {
        key
        for key in sub_resolver.reverse_dict
        # `reverse_dict` is keyed by both name and view callable; only names matter here.
        if isinstance(key, str) and key.startswith(REPORT_PREFIX)
    }


def _api_csv_names(names: set[str]) -> set[str]:
    """Those whose API view declares a CSV renderer.

    **The renderer list is the mechanism, not a branch**, and `api/v1/report_views.py`
    explains why: DRF negotiates `?format=csv` against `renderer_classes` and raises
    `Http404` when nothing matches. So declaring the renderer *is* wiring the export, and
    its absence is what a forgotten CSV path actually looks like at runtime.
    """
    from api.v1.renderers import CsvRenderer

    capable = set()
    for name in names:
        view = resolve(reverse(f"v1:{name}")).func
        renderers = getattr(getattr(view, "view_class", None), "renderer_classes", ())
        if CsvRenderer in renderers:
            capable.add(name)
    return capable


def _web_view_function_names(names: set[str]) -> dict[str, str]:
    """`report-sales` -> the name of the function the route resolves to (`sales`).

    Taken from the resolved callable rather than derived from the URL name, because
    `login_required` preserves `__name__` and a naming convention is not a guarantee.
    """
    return {name: resolve(reverse(f"webadmin:{name}")).func.__name__ for name in names}


def _web_csv_names(names: set[str]) -> set[str]:
    """Those whose webadmin view reaches the shared CSV-capable responder.

    AST rather than an HTTP round trip, deliberately. `test_webadmin_reports.py` already
    asserts *functionally* that seven named screens export CSV; what has never been asserted
    is that **the set of screens is the right set**. Structure is the missing half, and it is
    the half that fails when a new report is added — which is precisely TD-29.
    """
    source = (BACKEND / "webadmin" / "report_views.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    capable = set()
    for name, function_name in _web_view_function_names(names).items():
        node = functions.get(function_name)
        if node is None:
            continue
        called = {
            inner.func.id
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
        }
        if called & WEB_CSV_HELPERS:
            capable.add(name)
    return capable


def live_wiring() -> dict[str, set[str]]:
    """Everything the rule needs, read from the running system."""
    menu = _menu_names()
    web = _routed_names("webadmin")
    api = _routed_names("v1")
    return {
        "menu": menu,
        "web": web,
        "api": api,
        "web_csv": _web_csv_names(web),
        "api_csv": _api_csv_names(api),
    }


# ------------------------------------------------------------------------ the contract


def test_every_report_is_wired_into_the_menu_both_routers_and_the_csv_path():
    """**TD-29, closed.** The four wirings, checked against each other, both directions."""
    failures = check_registration(**live_wiring())
    assert not failures, "report wiring is incomplete:\n  " + "\n  ".join(failures)


def test_the_registry_is_not_empty():
    """Anti-vacuity for the adapters themselves.

    Every assertion above is a set comparison, and comparisons over three empty sets all
    pass. If `REPORT_MENU` were renamed or the namespace lookup silently returned nothing,
    this suite would go green while checking nothing at all.
    """
    wiring = live_wiring()
    assert wiring["menu"], "REPORT_MENU is empty or unreadable — this suite would be vacuous"
    assert wiring["web"], "no webadmin report routes found — check the namespace lookup"
    assert wiring["api"], "no API report routes found — check the namespace lookup"


def test_the_dashboard_is_not_treated_as_a_report():
    """`api/v1/urls.py` states the intent; this makes it a contract.

    > *"Named `dashboard`, not `report-dashboard`: it returns no ReportTable and must never
    > join the list the FR-RPT-012 CSV suite is parametrised over."*

    A dashboard declares only `JSONRenderer`, so if it were ever renamed into the `report-*`
    family the CSV assertion would fail — correctly, but with a message about a missing
    export rather than about the real mistake. This says the real thing.
    """
    from api.v1.renderers import CsvRenderer

    wiring = live_wiring()
    assert "dashboard" not in wiring["menu"]
    assert not any(name.endswith("dashboard") for name in wiring["api"])

    view = resolve(reverse("v1:dashboard")).func
    assert CsvRenderer not in view.view_class.renderer_classes, (
        "the dashboard now declares a CSV renderer. M7 §8.2 withholds export from figures "
        "that describe *today* and are not reproducible — the refusal is the renderer list."
    )


def test_the_parametrised_report_suites_cover_every_registered_report():
    """The fifth place TD-29 predicted, and the one no other test can see.

    Both integration suites carry a **hand-maintained list** of report URL names and
    parametrise their status, authorisation and CSV checks over it. A report added to the
    menu and both routers but not to these lists is fully wired and **entirely untested** —
    green build, no coverage, discovered by a user.

    Asserting across suites is unusual and is justified here: those lists are not test data,
    they are a fourth and fifth copy of the registry.
    """
    from tests.integration.test_report_api import REPORTS
    from tests.integration.test_webadmin_reports import SCREENS

    menu = _menu_names()
    covered_api = {name.split(":", 1)[-1] for name in REPORTS}
    covered_web = {name.split(":", 1)[-1] for name in SCREENS}

    assert covered_api == menu, (
        "tests/integration/test_report_api.py::REPORTS has drifted from REPORT_MENU: "
        f"missing {sorted(menu - covered_api)}, stale {sorted(covered_api - menu)}"
    )
    assert covered_web == menu, (
        "tests/integration/test_webadmin_reports.py::SCREENS has drifted from REPORT_MENU: "
        f"missing {sorted(menu - covered_web)}, stale {sorted(covered_web - menu)}"
    )


# ------------------------------------------------------------ anti-vacuity: mutation
#
# Each test below breaks a **copy** of the live wiring and requires the rule to notice.
# Nothing here touches the repository; the mutations are dictionaries.
#
# Without these, `check_registration` could be `return []` and everything above would pass.


def _mutated(**overrides: set[str]) -> dict[str, set[str]]:
    """The live wiring with named sets replaced. The original is never modified."""
    wiring = {key: set(value) for key, value in live_wiring().items()}
    wiring.update(overrides)
    return wiring


def test_a_report_missing_from_the_menu_is_caught():
    wiring = _mutated()
    victim = sorted(wiring["menu"])[0]
    wiring["menu"].discard(victim)

    failures = check_registration(**wiring)
    assert any("absent from REPORT_MENU" in failure for failure in failures), (
        f"removing {victim} from the menu while leaving both routes did not fail: {failures}"
    )


def test_a_report_missing_from_the_webadmin_router_is_caught():
    wiring = _mutated()
    victim = sorted(wiring["menu"])[0]
    wiring["web"].discard(victim)
    wiring["web_csv"].discard(victim)

    failures = check_registration(**wiring)
    assert any("no webadmin route is wired" in failure for failure in failures), (
        f"removing the {victim} screen route did not fail: {failures}"
    )


def test_a_report_missing_from_the_api_router_is_caught():
    wiring = _mutated()
    victim = sorted(wiring["menu"])[0]
    wiring["api"].discard(victim)
    wiring["api_csv"].discard(victim)

    failures = check_registration(**wiring)
    assert any("no API route is wired" in failure for failure in failures), (
        f"removing the {victim} API route did not fail: {failures}"
    )


def test_a_report_with_no_csv_path_is_caught():
    """Both surfaces, separately: an export can be forgotten on either one alone."""
    victim = sorted(_menu_names())[0]

    web_broken = _mutated()
    web_broken["web_csv"].discard(victim)
    assert any(
        "no CSV export path" in failure for failure in check_registration(**web_broken)
    ), f"a {victim} screen that cannot export CSV was not caught"

    api_broken = _mutated()
    api_broken["api_csv"].discard(victim)
    assert any(
        "does not declare the CSV renderer" in failure
        for failure in check_registration(**api_broken)
    ), f"a {victim} API view with no CSV renderer was not caught"


def test_an_entire_report_family_dropped_from_the_menu_is_caught():
    """**The S4.4 rehearsal, run before S4.4 exists.**

    FR-PUR-015 adds a *family* of reports at once, and the plausible mistake at that scale
    is not forgetting one line — it is routing the whole family on both surfaces and never
    touching `REPORT_MENU`. Every one would be reachable by URL and none would appear in the
    navigation.

    The family here is **synthetic**. No procurement report exists yet and this test invents
    none in production; it proves the rule is sensitive to wholesale omission, so that when
    the real family lands the contract already covers it.
    """
    family = {"report-purchase-orders", "report-supplier-balances", "report-receipt-variance"}
    wiring = _mutated()
    # Wired on both surfaces, exportable on both, and absent from the registry.
    wiring["web"] |= family
    wiring["api"] |= family
    wiring["web_csv"] |= family
    wiring["api_csv"] |= family

    failures = check_registration(**wiring)
    unregistered = {
        name for name in family if any(name in failure for failure in failures)
    }
    assert unregistered == family, (
        "a whole family of reports was routed on both surfaces without reaching "
        f"REPORT_MENU and only {sorted(unregistered)} was caught"
    )


def test_removing_every_report_is_caught():
    """Wholesale deletion, the degenerate case every set comparison passes.

    `set() - set()` is empty six times over, so an emptied registry satisfies every
    bidirectional check above. Only the explicit non-empty guard refuses it.
    """
    failures = check_registration(**_mutated(menu=set(), web=set(), api=set()))
    assert any("REPORT_MENU is empty" in failure for failure in failures), (
        f"an empty registry passed the contract: {failures}"
    )


def test_the_live_wiring_still_passes_after_every_mutation_test():
    """The mutations must not have leaked. `_mutated` copies; this proves it copies.

    A mutation helper that modified the live sets in place would leave the earlier tests
    passing and this one failing — which is the right way round, and worth one assertion.
    """
    assert not check_registration(**live_wiring())
