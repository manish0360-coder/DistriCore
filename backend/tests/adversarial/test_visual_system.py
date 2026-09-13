"""**The design system is a set of constraints, and constraints decay silently** (M11.4).

Before M11.4 the product had 71 lines of CSS spread over four `<style>` blocks, zero static
files, zero media queries and **zero focus rules**. `order_detail.html` shipped two classes
(`.note`, `.tot`) that were defined nowhere — the fragmentation already failing in
production. Nothing noticed, because nothing was watching.

These contracts watch the four things that would quietly come back:

1. **A second stylesheet.** The next screen with a special need adds a private `<style>`
   block, and the system is a suggestion again.
2. **A script tag.** ADR-003 chose server-rendered HTML to avoid a second pipeline and
   FD-05 exists to keep Node out of the backend. One CDN `<script>` is how that erodes.
3. **The focus ring.** It is invisible when it works, so it is the first thing removed by
   someone who finds the outline ugly. Its absence is a WCAG 2.4.7 failure and it makes
   keyboard order entry — the fast way to work these screens — unusable.
4. **Decorative colour.** Colour in this product means *state*: settled, pending, breach.
   The moment a hue is spent on decoration, the hue that means "overdue" is just one of
   many, and the receivables screen stops being readable at a glance.

Read from the mounted repository, and asserted on *mechanism* where possible rather than on
prose — the contrast contract below recomputes WCAG ratios from the tokens rather than
trusting a comment that says they pass.
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.adversarial

ROOT = Path(__file__).resolve().parents[3]

CSS = ROOT / "backend" / "webadmin" / "static" / "webadmin" / "districore.css"
TEMPLATES = ROOT / "backend" / "webadmin" / "templates" / "webadmin"
BASE = TEMPLATES / "base.html"
LIST = TEMPLATES / "_list.html"
PDF = ROOT / "backend" / "billing" / "templates" / "billing" / "invoice_document.html"
TEST_SETTINGS = ROOT / "backend" / "config" / "settings" / "test.py"

#: `backend/` is bind-mounted (`docker/compose.dev.yml`), so these are visible in stage 7.
REQUIRED_PATHS = (
    "backend/webadmin/static/webadmin/districore.css",
    "backend/webadmin/templates/webadmin/base.html",
    "backend/webadmin/templates/webadmin/_list.html",
    "backend/billing/templates/billing/invoice_document.html",
    "backend/config/settings/test.py",
)

#: Budget for the screen stylesheet's *rules*. Not a guess: the whole point of a no-build,
#: no-framework front end is that it stays small enough to read in one sitting.
CSS_BUDGET_BYTES = 12 * 1024
#: And what a browser actually downloads, which is the number the budget is a proxy for.
CSS_WIRE_BUDGET_BYTES = 6 * 1024

#: Three `onchange="this.form.submit()"` filter selects predate M11.4 and are progressive
#: enhancement on a GET form that works without them. Changing them is view behaviour and
#: out of this milestone's scope — but the set is pinned, so a fourth fails here.
HANDLER = r"\son(click|change|submit|load|input)\s*="
KNOWN_INLINE_HANDLERS = {
    "backend/webadmin/templates/webadmin/delivery_list.html",
    "backend/webadmin/templates/webadmin/order_list.html",
    "backend/webadmin/templates/webadmin/payment_list.html",
}

#: The four groups `base.html` must express, and every destination each must reach.
NAV_GROUPS = {
    "sell": ["order-list", "delivery-list", "invoice-list", "payment-list",
             "receivables-position", "customer-list", "zone-list"],
    "buy": ["supplier-list", "purchase-order-list", "goods-receipt-list",
            "supplier-payment-list"],
    "hold": ["product-list", "stock-list"],
    "config": ["dashboard", "report-sales", "reason-code-list", "business-profile"],
}


def test_every_path_this_suite_reads_is_visible_from_inside_the_container():
    """Fail on the plumbing *as* plumbing, before any contract is evaluated."""
    missing = [p for p in REQUIRED_PATHS if not (ROOT / p).exists()]
    assert not missing, (
        f"not visible at {ROOT}: {missing}. `backend/` arrives by bind-mount — see the "
        "`app` service volumes in `docker/compose.dev.yml`."
    )


# ───────────────────────────────────────────────── one stylesheet, and only one
def test_the_screen_stylesheet_is_the_only_one_and_is_linked_through_the_static_pipeline():
    """`{% static %}`, not a hardcoded path — production cache-busting depends on it.

    The file sits in an app static directory, so Django's `AppDirectoriesFinder` collects
    it with no configuration and no build step.
    """
    base = BASE.read_text(encoding="utf-8")
    assert "{% load static %}" in base, "`base.html` no longer loads the static tag library"
    assert re.search(r"{%\s*static\s+'webadmin/districore\.css'\s*%}", base), (
        "the stylesheet is not linked through `{% static %}`. A hardcoded `/static/...` "
        "path works, but forfeits the hashed filename production relies on for cache "
        "invalidation after a deploy."
    )
    assert CSS.parent.name == "webadmin" and CSS.parent.parent.name == "static", (
        "the stylesheet is not in an app static directory, so `AppDirectoriesFinder` will "
        "not collect it"
    )


def test_no_screen_template_keeps_a_private_style_block():
    """The failure this system exists to end.

    Four private blocks is how `order_detail.html` came to use `.note` and `.tot` with no
    rule behind them anywhere. The invoice PDF is the one legitimate exception — a printed
    document is not a screen, WeasyPrint renders it without the stylesheet, and its rules
    are page-box and print-specific.
    """
    offenders = [
        p.relative_to(ROOT).as_posix()
        for p in sorted((ROOT / "backend").rglob("*.html"))
        if "<style" in p.read_text(encoding="utf-8") and p != PDF
    ]
    assert not offenders, (
        f"private `<style>` blocks outside the PDF template: {offenders}. Screen styling "
        "belongs in `districore.css`; a second stylesheet is how the first one stops being "
        "the system."
    )


def test_the_invoice_pdf_stylesheet_stays_independent():
    """Anti-vacuity for the contract above, and a real constraint.

    WeasyPrint renders this template outside the browser and never loads
    `districore.css`. If it ever started depending on the screen system, a change made for
    a table hover would alter a statutory document.
    """
    pdf = PDF.read_text(encoding="utf-8")
    assert "<style" in pdf, "the invoice template lost its own print styling"
    assert "districore.css" not in pdf, (
        "the invoice PDF now depends on the screen stylesheet. A printed statutory document "
        "must not change because a screen rule changed."
    )


# ─────────────────────────────────────────────────────────── no second pipeline
def test_no_javascript_was_introduced_anywhere_in_the_web_admin():
    """ADR-003 and FD-05, as a gate rather than an intention.

    The narrow-screen menu is `<details>`/`<summary>` precisely so that this can stay true:
    native semantics, keyboard operable, announced by assistive technology, zero script.
    """
    scripts = [
        p.relative_to(ROOT).as_posix()
        for p in sorted((ROOT / "backend").rglob("*.html"))
        if re.search(r"<script\b", p.read_text(encoding="utf-8"), re.I)
    ]
    assert not scripts, f"`<script>` appeared in: {scripts}"

    js = [p.relative_to(ROOT).as_posix() for p in (ROOT / "backend").rglob("*.js")]
    assert not js, f"JavaScript files appeared in the backend: {js}"

    inline = {
        p.relative_to(ROOT).as_posix()
        for p in sorted((ROOT / "backend").rglob("*.html"))
        if re.search(HANDLER, p.read_text(encoding="utf-8"), re.I)
    }
    assert inline == KNOWN_INLINE_HANDLERS, (
        f"the inline-handler set changed. New: {sorted(inline - KNOWN_INLINE_HANDLERS)}. "
        f"Gone: {sorted(KNOWN_INLINE_HANDLERS - inline)}. The three known ones predate "
        "M11.4 and are a GET form's progressive enhancement; a fourth is a script by "
        "another name."
    )


def test_no_frontend_framework_or_external_dependency_was_introduced():
    """The documentation named Tailwind and HTMX for years and neither was ever built.

    M11.4 corrected the documentation to describe what exists. This stops the correction
    from being undone by a convenient CDN tag.
    """
    html = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "backend").rglob("*.html"))
    for banned in ("tailwind", "htmx", "react", "vue", "svelte", "three.js", "bootstrap",
                   "alpine", "jquery"):
        assert banned not in html.lower(), f"`{banned}` appeared in a template"

    external = re.findall(r'(?:href|src)="(https?://[^"]+)"', html)
    assert not external, (
        f"external front-end dependencies appeared: {external}. The admin must render with "
        "no third-party origin — that is an availability and a privacy property, not only "
        "an architectural one."
    )


def test_tests_run_against_static_storage_that_needs_no_build_artefact():
    """The landmine M11.4 found before it went off.

    `base.STATICFILES_STORAGE` is whitenoise's manifest storage. Its `url()` reads a
    manifest that only `collectstatic` writes, and skips it entirely when `DEBUG` is true —
    so dev and production are both fine. Tests are neither: `DEBUG = False` and no
    collectstatic. Without this override, every test that renders a web-admin page dies on
    `Missing staticfiles manifest entry`, and the failure looks like a template bug.
    """
    settings = TEST_SETTINGS.read_text(encoding="utf-8")
    assert re.search(
        r'STATICFILES_STORAGE\s*=\s*"django\.contrib\.staticfiles\.storage\.StaticFilesStorage"',
        settings,
    ), (
        "test settings no longer override the manifest storage. Restore it rather than "
        "dropping `{% static %}`: production cache-busting depends on the tag."
    )


# ────────────────────────────────────────────────────────── the system's shape
def _tokens() -> dict[str, str]:
    text = CSS.read_text(encoding="utf-8")
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6});", text))


def test_the_token_layer_covers_every_part_of_the_system():
    """Tokens are what make this a system rather than 400 lines of rules."""
    tokens = _tokens()
    required = ["command", "work", "field", "ink", "muted", "line",
                "ok", "attn", "bad", "focus",
                "g-sell", "g-buy", "g-hold", "g-config"]
    missing = [t for t in required if t not in tokens]
    assert not missing, f"design tokens missing from `districore.css`: {missing}"

    # The *declaration*, not the name. The first draft searched for `--s1` and passed on a
    # mutation that deleted the definition, because `var(--s1)` still appeared in 40 rules:
    # it was checking that the token is used, not that it exists.
    css = CSS.read_text(encoding="utf-8")
    for group in ("--s1", "--s4", "--r", "--lift", "--t", "--ease", "--fs-page", "--fs-cell"):
        assert re.search(rf"{re.escape(group)}:\s*\S", css), (
            f"`{group}` is no longer declared — spacing/type/motion is ad hoc again"
        )


def test_colour_is_spent_on_state_not_decoration():
    """**The discipline that keeps receivables readable.**

    If every screen has a hue, the hue that means *overdue* is just one of many. The budget
    is deliberately tight: two surfaces, text, rules, three states, a focus ring, and four
    matched navigation accents. A palette that grows past this has started decorating.
    """
    colours = set(re.findall(r"#[0-9a-fA-F]{6}", CSS.read_text(encoding="utf-8")))
    assert len(colours) <= 24, (
        f"{len(colours)} distinct colours in the stylesheet. Colour means state here; a "
        f"growing palette means it has started meaning decoration too. Found: "
        f"{sorted(colours)}"
    )


# ───────────────────────────────────────────────── accessibility, measured not claimed
def _contrast(fg: str, bg: str) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    def luminance(h: str) -> float:
        h = h.lstrip("#")
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def test_the_contrast_ratios_are_recomputed_rather_than_asserted_in_a_comment():
    """WCAG AA as a gate. `02` has no web accessibility NFR — this is the substitute.

    Recomputed from the tokens on every run, so changing a colour cannot quietly drop a
    pair below threshold. 4.5:1 for body text, 3.0:1 for large text and non-text indicators
    (the focus ring, the navigation accents), per WCAG 2.1 §1.4.3 and §1.4.11.
    """
    t = _tokens()
    text_pairs = [("ink", "work"), ("ink", "field"), ("muted", "work"), ("muted", "field"),
                  ("bad", "bad-bg"), ("attn", "attn-bg"), ("ok", "work"),
                  ("command-ink", "command"), ("command-dim", "command")]
    ui_pairs = [("focus", "work"), ("focus", "field"), ("navy", "work"),
                ("g-sell", "command"), ("g-buy", "command"),
                ("g-hold", "command"), ("g-config", "command")]

    failures = []
    for fg, bg in text_pairs:
        r = _contrast(t[fg], t[bg])
        if r < 4.5:
            failures.append(f"text --{fg} on --{bg}: {r:.2f} < 4.5")
    for fg, bg in ui_pairs:
        r = _contrast(t[fg], t[bg])
        if r < 3.0:
            failures.append(f"ui --{fg} on --{bg}: {r:.2f} < 3.0")
    assert not failures, "WCAG AA contrast failures: " + "; ".join(failures)


def test_every_interactive_control_gets_a_visible_focus_ring():
    """Zero focus rules existed before M11.4. This is the regression that matters most.

    Asserted as the *rule set*, because a focus style that covers only buttons is the same
    defect with better manners.
    """
    css = CSS.read_text(encoding="utf-8")
    assert ":focus-visible" in css, "the focus ring is gone (WCAG 2.4.7)"
    match = re.search(r":where\(([^)]*)\):focus-visible", css)
    assert match, "the focus rule no longer applies to a set of controls"
    covered = match.group(1)
    for control in ("a", "button", "input", "select", "summary"):
        assert re.search(rf"\b{control}\b", covered), (
            f"`{control}` is not covered by the focus rule; keyboard users lose it there"
        )
    assert "outline: 2px solid" in css, "the ring is thinner than 2px or no longer an outline"


def test_motion_is_bounded_and_can_be_switched_off():
    """Four transitions, all short, all escapable.

    `prefers-reduced-motion` is not optional courtesy — vestibular disorders make
    unrequested motion genuinely harmful, and an operations tool is used all day.
    """
    css = CSS.read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in css, "motion cannot be switched off"

    # Comments stripped first, the lesson `test_deployment_readiness` records: this
    # stylesheet *explains* that it has no parallax, and a plain substring search read the
    # explanation as the thing it forbids.
    code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

    durations = [int(d) for d in re.findall(r"--t(?:-fast)?:\s*(\d+)ms", css)]
    assert durations, "no motion tokens found"
    assert max(durations) <= 200, f"a transition exceeds 200 ms: {durations}"

    assert "infinite" not in code, "an infinite animation appeared"
    assert "parallax" not in code.lower(), "a parallax effect appeared"
    assert "translateZ" not in code and "rotate3d" not in code, "decorative 3D appeared"


def test_the_layout_is_responsive_and_tables_stay_tables():
    """A ledger reflowed into cards is unreadable. It scrolls, with the row identity pinned."""
    css = CSS.read_text(encoding="utf-8")
    queries = re.findall(r"@media\s*\(([^)]+)\)", css)
    widths = [q for q in queries if "width" in q]
    assert len(widths) >= 2, f"fewer than two width breakpoints: {queries}"
    assert "min(96vw, 1440px)" in css or "min(96vw,1440px)" in css, (
        "the fixed 960px measure is back; operational tables need the width"
    )
    assert "position: sticky" in css, (
        "nothing is pinned — on a narrow screen a scrolled row loses the column that "
        "identifies it"
    )


def test_the_stylesheet_stays_within_its_budget():
    """Two budgets, because the first draft of this contract measured the wrong thing.

    It used `stat().st_size`, which on a Windows development mount counts CRLF pairs and
    counts every comment — so it failed at 16 KB while the actual design was 10.4 KB of
    rules that gzip to 4.4 KB. **The criterion was mine and I amended it rather than
    trimming the reasoning out of the stylesheet**, because in this repository the argument
    lives next to the code.

    So: the stated 12 KB budget is applied to the rules it was always about, and a second,
    *stricter* check is added on the bytes actually sent over the wire — which is the number
    the budget was a proxy for.
    """
    text = CSS.read_text(encoding="utf-8")
    rules = re.sub(r"/\*.*?\*/", "", text, flags=re.S).encode("utf-8")
    assert len(rules) <= CSS_BUDGET_BYTES, (
        f"{len(rules)} bytes of CSS rules, over the {CSS_BUDGET_BYTES}-byte budget. The "
        "budget is the point of a no-build front end: it stays readable in one sitting."
    )

    shipped = len(gzip.compress(text.encode("utf-8"), 9))
    assert shipped <= CSS_WIRE_BUDGET_BYTES, (
        f"{shipped} compressed bytes, over the {CSS_WIRE_BUDGET_BYTES}-byte wire budget. "
        "Caddy and whitenoise both compress; this is what a browser actually downloads."
    )


# ──────────────────────────────────────────────────────────────── navigation
def test_the_navigation_expresses_four_groups_and_reaches_every_destination():
    """18 peer links is a list, not a menu.

    Orders → Invoices → Payments → Receivables is one workflow and the flat bar said all
    eighteen were the same thing. The groups are structure; they carry a 2px accent for
    orientation and never colour any data.
    """
    base = BASE.read_text(encoding="utf-8")
    for group, destinations in NAV_GROUPS.items():
        assert f'data-group="{group}"' in base, f"navigation group `{group}` is gone"
        for dest in destinations:
            assert f"webadmin:{dest}" in base, f"`{dest}` is unreachable from the navigation"

    # **Django template comments stripped first**, and the mutation that forced this is the
    # third of its kind in the repository (`backup.sh` in M11.2, the parallax check above).
    # `base.html` *explains* that the menu is `<details>`/`<summary>`, and the first draft
    # of this assertion was satisfied by that sentence after the real markup was replaced
    # with a `<div>`. A contract that cannot tell markup from prose checks spelling.
    markup = re.sub(r"{#.*?#}", "", base, flags=re.S)
    assert "<details" in markup and "<summary" in markup, (
        "the narrow-screen menu no longer uses `<details>`/`<summary>` — the only collapse "
        "that needs no JavaScript"
    )
    assert 'aria-label="Sections"' in base, "the navigation landmark lost its label"


def test_the_empty_state_is_text_first_and_has_its_own_hierarchy():
    """No illustrations. Say what the page holds; the action that fills it is in the toolbar."""
    assert 'class="empty"' in LIST.read_text(encoding="utf-8"), (
        "the shared list template no longer marks its empty state, so it renders as body "
        "copy indistinguishable from data"
    )
    assert ".empty" in CSS.read_text(encoding="utf-8"), "`.empty` has no rule behind it"


def test_the_orphaned_order_detail_classes_now_have_rules():
    """`.note` and `.tot` shipped with no rule anywhere — the fragmentation, caught."""
    css = CSS.read_text(encoding="utf-8")
    for orphan in (".note", ".tot"):
        assert orphan in css, f"`{orphan}` is used by order_detail.html and defined nowhere"
