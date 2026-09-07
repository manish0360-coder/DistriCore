"""**NFR-SEC-001…011, traced to an assertion each** (`02` §21.4, M10 → M11 gate).

`00` §19.2's gate is *"Restore rehearsed and recorded (B-3); **security review complete**"*,
and `02` §21 opens with the reason this file exists:

> *"A non-functional goal without a measurement method is not a requirement."*

Before M10, `grep NFR-SEC-0` over `tests/` found **two** of the eleven. The mechanisms mostly
existed — `prod.py` sets HSTS and secure cookies, the exception handler emits problem+json,
`test_authorization_matrix.py` issues the role grid directly at the API — but nothing tied a
requirement to the thing that proves it, so the review could not be completed whatever the
code did.

**What this file will not do.** `02` §21.4 names verification methods that are external to a
test run: *"downgrade attempt"* against a live TLS endpoint, *"automated scan"*,
*"repository scanning in CI"*, *"device inspection"*. Those are recorded in
`docs/M10_Security_Review.md` as **manual or external evidence** and are not simulated here.
A test that pretended to perform a TLS downgrade would be worse than an honest gap.

**Where a rule depends on authorisation, both sides are asserted** — the allowed case and the
forbidden one. A refusal test that never proves the allowed case can be satisfied by an
endpoint that refuses everybody.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest
from django.test import Client
from django.urls import NoReverseMatch, get_resolver, resolve, reverse
from rest_framework.permissions import AllowAny

from tests.factories import CustomerFactory

pytestmark = pytest.mark.adversarial

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"

#: Everything this module reads from **outside** `backend/`. The backend image contains only
#: `backend/`; these arrive by bind-mount from `docker/compose.dev.yml`.
#:
#: Copied deliberately from `test_mobile_boundary.py`, which learned it the same way: the
#: first authoritative run of this suite failed on missing mounts, and the failure said
#: "no such file" rather than anything about security. A diagnosis that points at the wrong
#: layer costs more than the failure it describes.
REQUIRED_PATHS = (
    ".github/workflows/ci.yml",
    "docs/M10_Security_Review.md",
    ".gitignore",
    # Added after the lock contract shipped without it and failed as a bare
    # `FileNotFoundError: /app/uv.lock` instead of as the mount problem it was — the third
    # time this suite made that mistake. `uv.lock` is COPYed into the *builder* stage only.
    "uv.lock",
    # `make audit` is NFR-SEC-009's local half; the Makefile is where it can be neutered.
    "Makefile",
)


def test_every_path_this_suite_reads_is_visible_from_inside_the_container():
    """Fail on the plumbing *as* plumbing, before any requirement is evaluated.

    Named first so it is the first thing that fails and the first thing read.
    """
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    assert not missing, (
        f"not visible at {ROOT}: {missing}. The backend image contains only `backend/`; "
        "these arrive by bind-mount. Add them to the `app` service volumes in "
        "`docker/compose.dev.yml`."
    )


# ---------------------------------------------------------- NFR-SEC-001 — transport
#: The production settings module, parsed rather than imported. See `_prod_setting`.
PROD_SETTINGS = BACKEND / "config" / "settings" / "prod.py"


def _prod_setting(name: str) -> Any:
    """One module-level setting from `prod.py`, read **statically**.

    **`prod.py` cannot be imported from a test run, and that is the point of `prod.py`.**
    It raises at import unless the process holds a real 50-character secret, an explicit
    `ALLOWED_HOSTS`, a real SMS provider and JSON logging — `00` §10.1: *"a misconfigured
    production instance must refuse to start rather than run insecurely."* Importing it here
    would mean supplying those, i.e. making the test runtime claim to be a production
    runtime, which is exactly the property the module exists to deny.

    So the configuration is read from source. That is the technique `test_mobile_boundary`
    uses for Dart and `test_production_refuses_to_start_on_a_development_secret` already uses
    for this very file — and it is **stronger than importing** in one respect: it proves the
    value is a literal in the production module, not something an environment variable could
    weaken at deploy time.
    """
    tree = ast.parse(PROD_SETTINGS.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"prod.py does not set {name} at module level")


def test_production_settings_reject_plaintext_transport():
    """*"All network traffic MUST use current TLS. Plaintext transport MUST be rejected,
    not merely discouraged."*

    The **live** downgrade attempt is external evidence (`M10_Security_Review` §2). What is
    assertable here is the configuration that produces the rejection, read from the real
    production settings module rather than described.
    """
    assert _prod_setting("SECURE_SSL_REDIRECT") is True, "plaintext is only discouraged"
    assert _prod_setting("SESSION_COOKIE_SECURE") is True
    assert _prod_setting("CSRF_COOKIE_SECURE") is True
    # One year, preloadable: a downgrade must fail at the browser too, not only at the proxy.
    assert _prod_setting("SECURE_HSTS_SECONDS") >= 31_536_000
    assert _prod_setting("SECURE_HSTS_INCLUDE_SUBDOMAINS") is True
    assert _prod_setting("SECURE_HSTS_PRELOAD") is True


def test_that_settings_reader_fails_on_a_setting_that_is_absent():
    """Anti-vacuity for `_prod_setting`. A reader that returned `None` for everything would
    make every assertion above pass against an empty file."""
    with pytest.raises(AssertionError):
        _prod_setting("SECURE_SSL_REDIRECT_TYPO")


def test_production_refuses_to_start_on_a_development_secret():
    """The same clause, at the other end: a production process that boots with a dev key.

    `prod.py` collects `_errors` and raises. This asserts the check exists and is fatal
    rather than advisory — a warning at boot is read once and never again.
    """
    source = (BACKEND / "config" / "settings" / "prod.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    raises = [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]
    assert raises, "prod.py collects configuration errors and never raises them"


# ------------------------------------------------------- NFR-SEC-002 — SQL injection
@pytest.mark.django_db
def test_a_sql_payload_in_a_query_parameter_changes_nothing(auth, owner):
    """*"All data access MUST be parameterised. String-concatenated queries MUST NOT exist."*

    A real payload through a real filter. The assertion is not "no 500" — a 500 would also be
    a pass for a query that dropped the table first. It is that the table is **still there**
    and still holds the row.
    """
    CustomerFactory(code="C-SEC-002", shop_name="Injection Probe")
    payload = "'); DROP TABLE customer; --"

    response = auth(owner).get(reverse("v1:customer-list"), {"search": payload})

    assert response.status_code in (200, 400), f"unexpected {response.status_code}"
    from customers.models import Customer

    assert Customer.objects.filter(code="C-SEC-002").exists(), "the probe row is gone"


def _module_constants(tree: ast.Module) -> set[str]:
    """Module-level ``UPPER_CASE`` names — values fixed at import, never caller input.

    **Imports count, and missing them was the first draft's second defect.** The four sequence
    names live in `models.py` and are *imported* into `services.py`, so a collector that read
    only assignments found none of them and flagged all four sites. An imported upper-case
    name is no more reachable by a caller than a locally assigned one; both are bound once, at
    import, before any request exists.
    """
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names |= {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name) and target.id.isupper()
            }
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.isupper():
                names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {
                (alias.asname or alias.name).split(".")[0]
                for alias in node.names
                if (alias.asname or alias.name).isupper()
            }
    return names


def _interpolates_only_constants(sql: ast.JoinedStr, constants: set[str]) -> bool:
    return all(
        isinstance(part.value, ast.Name) and part.value.id in constants
        for part in sql.values
        if isinstance(part, ast.FormattedValue)
    )


def test_no_production_query_carries_a_value_into_its_sql():
    """The structural half, and it is scoped to what actually executes SQL.

    Raw SQL is legitimate here — `test_financial_immutability` and `test_stock_ledger_integrity`
    both issue it deliberately to prove a constraint bites. What must not exist is a
    `cursor.execute` whose SQL **carries a value into the query text**: that is the shape an
    attacker's input travels in.

    **A module-level constant is not a value in that sense**, and the first draft of this test
    could not tell the difference. It flagged four real sites —
    `purchasing.services._next_po_number` and `receivables.services._next_payment_number` —
    which read `f"SELECT nextval('{PAYMENT_NUMBER_SEQUENCE}')"`. The interpolated name is a
    sequence identifier fixed at import; no caller can reach it, and rewriting the two gapless
    numbering paths (M5-4, M6) to satisfy a rule that could not read them would have added
    risk to financial code to remove none. Recorded in `M10_Security_Review` §2, NFR-SEC-002.

    So the rule is stated as the property rather than as the syntax: **interpolation of
    anything that is not a module constant**, plus `%` and `+` in any form.
    """
    offenders: list[str] = []
    for path in sorted(BACKEND.rglob("*.py")):
        parts = path.relative_to(BACKEND).parts
        if parts[0] in {"tests", "ops"} or "migrations" in parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        constants = _module_constants(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "execute"):
                continue
            if not node.args:
                continue
            sql = node.args[0]
            flagged = (
                isinstance(sql, ast.JoinedStr) and not _interpolates_only_constants(sql, constants)
            ) or (isinstance(sql, ast.BinOp) and isinstance(sql.op, (ast.Mod, ast.Add)))
            if flagged:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, f"SQL built from a non-constant value: {offenders}"


def test_that_rule_still_catches_a_query_built_from_a_variable():
    """Mutation, on the pure predicate — the constant exemption must not have opened a hole.

    Without this, `_interpolates_only_constants` could return `True` unconditionally and the
    contract above would pass against any code at all.
    """
    hostile = ast.parse('cursor.execute(f"SELECT * FROM t WHERE c = {code}")').body[0].value.args[0]
    benign = ast.parse('cursor.execute(f"SELECT nextval(\'{SEQ}\')")').body[0].value.args[0]

    assert not _interpolates_only_constants(hostile, {"SEQ"}), "a bare variable was permitted"
    assert _interpolates_only_constants(benign, {"SEQ"})
    assert not _interpolates_only_constants(benign, set()), "the exemption is not name-checked"

    # The collector must see an imported constant, which is how all four real sites bind it.
    imported = ast.parse("from receivables.models import PAYMENT_NUMBER_SEQUENCE")
    assert "PAYMENT_NUMBER_SEQUENCE" in _module_constants(imported)
    assert "payment" not in _module_constants(ast.parse("from x import payment"))


# ----------------------------------------------------- NFR-SEC-003 — input validation
@pytest.mark.django_db
def test_malformed_input_is_refused_by_the_server_not_the_client(auth, owner):
    """*"All input MUST be validated server-side against an explicit schema, irrespective of
    client validation."*

    Three shapes a client could never send by accident, each to a real write endpoint.
    **400, never 500**: a 500 means the payload reached something that was not expecting it.
    """
    client = auth(owner)
    cases = [
        ("v1:order-list", {"customer_id": "not-an-integer", "lines": []}),
        ("v1:order-list", {"lines": [{"product_id": 1, "quantity": "-5"}]}),
        ("v1:payment-list", {"customer_id": 1, "amount": "abc", "method": "CASH"}),
    ]
    for name, body in cases:
        response = client.post(reverse(name), body, format="json")
        assert 400 <= response.status_code < 500, (
            f"{name} answered {response.status_code} to {body} — a 5xx means the payload "
            "reached code that assumed it was well formed"
        )


# ------------------------------------------------------------------ NFR-SEC-004 — XSS
@pytest.mark.django_db
def test_a_stored_script_payload_is_escaped_on_the_page(client, owner):
    """*"Output MUST be encoded contextually to prevent XSS."* A stored-payload test.

    `shop_name` is typed by a human and rendered on an owner screen, which is the shortest
    path from a customer record to someone else's browser.
    """
    CustomerFactory(code="C-SEC-004", shop_name="<script>alert('xss')</script>")
    client.force_login(owner)

    body = client.get(reverse("webadmin:customer-list")).content.decode()

    assert "<script>alert('xss')</script>" not in body, "the payload rendered as markup"
    assert "&lt;script&gt;" in body, (
        "the payload is absent entirely — this test would pass on a page that never rendered "
        "the customer at all, which proves nothing about encoding"
    )


# ----------------------------------------------------------------- NFR-SEC-005 — CSRF
@pytest.mark.django_db
def test_a_cookie_authenticated_post_without_a_csrf_token_is_refused(owner):
    """*"State-changing requests MUST carry CSRF protection where the surface is
    cookie-authenticated."*

    `enforce_csrf_checks=True` is the point: Django's test client disables the check by
    default, so a test written without it asserts nothing at all.

    **The API is deliberately out of scope** — it is `Authorization`-header authenticated, so
    no browser attaches credentials automatically and CSRF does not apply. That is the
    requirement's own *"where the surface is cookie-authenticated"* clause.
    """
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(owner)

    refused = csrf_client.post(
        reverse("webadmin:customer-new"), {"code": "C-CSRF", "shop_name": "X"}
    )
    assert refused.status_code == 403, f"a tokenless POST was accepted ({refused.status_code})"

    # The allowed case, so the test cannot pass against a form that refuses everything.
    page = csrf_client.get(reverse("webadmin:customer-new"))
    assert page.status_code == 200
    assert "csrfmiddlewaretoken" in page.content.decode(), "the form issues no token to send"


# --------------------------------------------------------------- NFR-SEC-007 — secrets
def test_the_secret_key_has_no_in_repository_default():
    """*"Secrets MUST NOT appear in source control. Configuration MUST be supplied by
    environment or a secret store."*

    CI's gitleaks scan is the repository-wide half (external evidence). This is the half a
    scanner cannot see: a `default=` on the key would be a secret in source control that no
    entropy check would flag, because a placeholder looks exactly like a placeholder until
    it reaches production.
    """
    source = (BACKEND / "config" / "settings" / "base.py").read_text(encoding="utf-8")
    match = re.search(r"SECRET_KEY\s*=\s*env\.str\((?P<args>[^)]*)\)", source)
    assert match, "SECRET_KEY is no longer read from the environment"
    assert "default" not in match.group("args"), (
        "SECRET_KEY has a default; a build with no key would boot on it silently"
    )


def test_an_env_file_cannot_be_committed():
    """The file that carries the key in every deployment must be uncommittable.

    **Two drafts were wrong before this one, in opposite directions.**
    The first used `rglob` and failed on the developer's own `.env` — which is exactly where
    a secret is *supposed* to live; the requirement says *"MUST NOT appear in **source
    control**"*, not "must not exist". The second asked `git ls-files`, which is the right
    question and the wrong place: **the backend image contains no git**, so it failed in the
    authoritative environment while passing everywhere it did not matter.

    So the assertion is on the mechanism that *prevents the commit*, which is a file in
    source control and therefore readable anywhere the repository is: `.gitignore`. gitleaks
    — CI's first step — is the backstop for a forced `git add -f`, and is external evidence
    in `M10_Security_Review` §2 rather than something a test run can perform.
    """
    rules = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert rules, ".gitignore is empty — this check would be vacuous"

    assert ".env" in rules, "`.env` is not ignored; the deployment secret is one `git add` away"
    assert ".env.*" in rules, (
        "`.env.*` is not ignored, so `.env.production` and `.env.local` are committable"
    )


# ------------------------------------------------------- NFR-SEC-009 — dependency gate
def test_the_dependency_audit_cannot_be_silenced():
    """*"Dependencies MUST be scanned for known vulnerabilities in CI; a critical finding
    MUST block release."*

    **The workflow step is the mechanism**, so the workflow is what is asserted — the same
    reasoning as *"no mobile check can be silenced"*, which reads the Makefile because the
    Makefile is where a check gets neutered.

    This step carried `|| true` from P0 until M10 (TD-35). `mypy` carried the same suffix for
    six milestones with 24 real errors behind it, so the pattern is not hypothetical.
    """
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    command = _audit_command(workflow)

    assert "|| true" not in command, "the audit cannot fail, so it blocks nothing"
    assert "--strict" in command, "a dependency that cannot be audited would pass silently"
    assert "continue-on-error" not in workflow, "a step is allowed to fail without failing CI"


def _audit_command(workflow: str) -> str:
    """The audit step's command, folded to one line.

    `>-` block scalars are how the step spells a multi-line command, so a single-line regex
    would read only `pip-audit --strict` and miss every flag under it — passing while the
    thing it checks was invisible.
    """
    step = re.search(
        r"- name: Dependency audit\n(?P<body>(?:\s+.*\n)+?)(?=\s*- name:|\Z)", workflow
    )
    assert step, "the dependency audit step is gone"
    return " ".join(step.group("body").split())


def test_every_ignored_vulnerability_is_a_recorded_decision():
    """**An exemption is a decision, and a decision has a record and a date.**

    The stronger form of the rule this replaced. That one banned `--ignore-vuln` outright,
    which is right until the day a finding has **no published fix in any version** — and then
    a blanket ban leaves only two moves, both bad: keep the pipeline red for ever, or delete
    the gate. M10.5 met exactly that case (`M10_Security_Review` §3.2).

    So the ban becomes a **traceability requirement**: every ignored identifier must appear in
    the review document, which is where the reasoning, the date and the review date live. An
    undocumented ignore still fails, and that is the failure the old rule was really for.
    """
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    ignored = set(re.findall(r"--ignore-vuln\s+(\S+)", _audit_command(workflow)))
    review = (ROOT / "docs" / "M10_Security_Review.md").read_text(encoding="utf-8")

    undocumented = sorted(identifier for identifier in ignored if identifier not in review)
    assert not undocumented, (
        f"these identifiers are silenced in CI and appear nowhere in the security review: "
        f"{undocumented}. An exemption with no record is how a finding disappears."
    )

    if ignored:
        assert "Review by" in review, (
            "an exemption is recorded but the review carries no review date; a permanent "
            "exception is an accepted vulnerability wearing a temporary label"
        )


def test_weasyprint_presentational_hints_are_never_enabled():
    """**The code property the §3.2 exemption rests on.**

    CVE-2026-49452 has no fix in any published WeasyPrint version. It is reachable only
    through `presentational_hints=True`: WeasyPrint's `css.find_style_attributes` guards the
    entire vulnerable block with

        if not presentational_hints:
            continue

    immediately above the interpolations the advisory names — `f'background-color:{...}'` and
    its siblings. The default is `False` and this application never passes it.

    **That makes the exemption conditional on our own code, so a test holds it.** Without
    this, enabling one keyword argument in `billing/pdf.py` would silently turn a documented
    non-issue into a live CSS-injection path, and the CI ignore would hide it.
    """
    offenders = []
    for path in sorted(BACKEND.rglob("*.py")):
        if "tests" in path.relative_to(BACKEND).parts:
            continue
        source = path.read_text(encoding="utf-8")
        if "presentational_hints" in source:
            offenders.append(str(path.relative_to(ROOT)))

    assert not offenders, (
        f"presentational hints are referenced in {offenders}. If they were enabled, "
        "CVE-2026-49452 becomes reachable and the `--ignore-vuln` in CI is no longer honest — "
        "remove the exemption before enabling them."
    )

    # Anti-vacuity: the renderer this reasons about must still exist and still be the one
    # call site, or the argument above is about code that is no longer there.
    pdf = (BACKEND / "billing" / "pdf.py").read_text(encoding="utf-8")
    assert "write_pdf()" in pdf, "the PDF call site changed; re-check §3.2's reachability"


# --------------------------------------------------------- NFR-SEC-010 — error hygiene
@pytest.mark.django_db
def test_an_error_response_discloses_nothing_internal(auth, salesman):
    """*"Error responses MUST NOT disclose stack traces, query text, or internal identifiers
    to any client."*

    A **real refusal**, not a synthetic one: a salesman reaching an owner-only report. The
    body must be problem+json and must carry no traceback, no SQL and no file path.
    """
    response = auth(salesman).post(reverse("v1:report-sales"))
    assert response.status_code in (403, 405), f"unexpected {response.status_code}"

    body = response.content.decode()
    for leak in ("Traceback", "SELECT ", "INSERT ", 'File "', "/backend/", "django.db"):
        assert leak not in body, f"the error body disclosed {leak!r}"


def test_production_never_runs_with_debug_enabled():
    """The single setting that turns every 500 into a stack trace with source and locals.

    Read statically, for the reason `_prod_setting` gives: importing `prod.py` would require
    the test process to hold production credentials.
    """
    assert _prod_setting("DEBUG") is False


# ------------------------------------------------------- NFR-SEC-011 — every endpoint
#: Endpoints that are deliberately reachable without a token, and the reason each one is.
#: **A list, so adding a public endpoint is an edit somebody reviews** rather than a default
#: nobody notices.
#:
#: **Bare route names, not `v1:`-prefixed.** `reverse_dict`'s keys carry no namespace, and
#: the first draft compared prefixed strings against unprefixed ones — so all four looked
#: simultaneously unrecorded *and* stale. The failure read like a short allowlist; it was a
#: key-format mismatch, which is why both directions are asserted below.
PUBLIC_BY_DESIGN = {
    "otp-request": "the field login path — the caller has no token yet",
    "otp-verify": "exchanges the code for the first token",
    "login": "the internal password fallback",
    "refresh": "presents a refresh token, which is not an access token",
}


def _api_view_classes() -> dict[str, Any]:
    """Every `v1:` route, resolved to its view class through the live URL conf.

    Read from the resolver rather than by parsing `urls.py`, so a route that exists but is
    unreachable does not count — the same construction `test_report_registration` uses.

    Arity is discovered by **trying**, not by reading `reverse_dict`'s internals: a route
    either reverses with no argument or with one `pk`, and asking the resolver is stabler than
    indexing a private structure four levels deep.
    """
    _prefix, sub_resolver = get_resolver().namespace_dict["v1"]
    found: dict[str, Any] = {}
    for name in (key for key in sub_resolver.reverse_dict if isinstance(key, str)):
        for args in ([], [1]):
            try:
                view = resolve(reverse(f"v1:{name}", args=args)).func
            except NoReverseMatch:
                continue
            found[name] = getattr(view, "view_class", None)
            break
    return found


def test_every_api_endpoint_requires_authentication_unless_listed():
    """*"Authorisation MUST be verified at the API boundary for every request, tested
    independently of any client."*

    `test_authorization_matrix` proves the **role grid** for the endpoints it names. This
    proves the *set* — that no endpoint has quietly become anonymous. The two are different
    failures: the grid catches a wrong rule, this catches a missing one.

    `DEFAULT_PERMISSION_CLASSES` is `IsAuthenticated`, so the dangerous edit is not forgetting
    a permission but **overriding one to `AllowAny`**, which reads as deliberate.
    """
    anonymous = {
        name
        for name, view_class in _api_view_classes().items()
        if view_class is not None and AllowAny in getattr(view_class, "permission_classes", ())
    }

    assert anonymous, "no public endpoint found at all — the resolver walk has drifted"
    unexpected = anonymous - set(PUBLIC_BY_DESIGN)
    assert not unexpected, (
        f"these endpoints are reachable without a token and are not recorded as public: "
        f"{sorted(unexpected)}. If that is intended, add each to PUBLIC_BY_DESIGN with the "
        "reason; if it is not, it is an authorisation hole."
    )

    stale = set(PUBLIC_BY_DESIGN) - anonymous
    assert not stale, f"PUBLIC_BY_DESIGN names endpoints that are no longer public: {sorted(stale)}"


@pytest.mark.django_db
def test_a_protected_endpoint_refuses_an_anonymous_caller(api):
    """The behavioural half of the same claim, and the anti-vacuity guard for the set test.

    A resolver walk that returned nothing would satisfy every assertion above. This issues a
    real anonymous request at a real protected route and requires a real 401.
    """
    assert api.get(reverse("v1:customer-list")).status_code == 401
    assert api.get(reverse("v1:report-sales")).status_code == 401


# ------------------------------------------------------------------- the review itself
#: The requirements this suite asserts in-process. The rest are recorded in
#: `docs/M10_Security_Review.md` against evidence that a test run cannot produce.
AUTOMATED_HERE = {
    "NFR-SEC-001", "NFR-SEC-002", "NFR-SEC-003", "NFR-SEC-004",
    "NFR-SEC-005", "NFR-SEC-007", "NFR-SEC-009", "NFR-SEC-010", "NFR-SEC-011",
}
#: Covered by an existing suite, and deliberately not duplicated here.
ELSEWHERE = {
    "NFR-SEC-006": "tests/unit/test_media.py, tests/adversarial/test_master_data_authorization.py",
    "NFR-SEC-008": "tests/adversarial/test_mobile_boundary.py + the device gate (D-M9-8)",
}


def test_the_review_document_accounts_for_all_eleven_requirements():
    """**The review is only complete if every requirement is named.**

    The gate condition is *"security review complete"*, and the way a review quietly becomes
    incomplete is that a requirement is never mentioned — not that it is mentioned and marked
    open. So this asserts coverage of the **set**, and says nothing about the verdicts, which
    are a reader's judgement rather than a test's.
    """
    review = (ROOT / "docs" / "M10_Security_Review.md").read_text(encoding="utf-8")
    assert review, "the review document is empty"
    expected = {f"NFR-SEC-{index:03d}" for index in range(1, 12)}

    missing = sorted(requirement for requirement in expected if requirement not in review)
    assert not missing, f"the review does not mention: {missing}"

    assert AUTOMATED_HERE | set(ELSEWHERE) == expected, (
        "this file's own accounting has drifted from the eleven requirements"
    )


# ------------------------------------------- NFR-SEC-009 — the lock must match the record
#: Floors the security review claims were applied, as `package -> minimum version`.
#:
#: **Read from the review, not restated here**, so the document and the check cannot drift.
_FLOOR_ROW = re.compile(
    r"^\|\s*`(?P<package>[a-z0-9_.-]+)`\s*\|[^|]*\|\s*\*\*(?P<version>[0-9][0-9a-z.]*)\*\*\s*\|",
    re.MULTILINE,
)


def _claimed_floors() -> dict[str, str]:
    review = (ROOT / "docs" / "M10_Security_Review.md").read_text(encoding="utf-8")
    return {m.group("package"): m.group("version") for m in _FLOOR_ROW.finditer(review)}


def _locked_versions() -> dict[str, str]:
    """`uv.lock`, parsed. **Fails closed and says why**, rather than raising an OSError.

    The first run of this contract died on `FileNotFoundError: /app/uv.lock` — the lock is
    COPYed into the *builder* stage and never into the runtime one, so it arrives only by
    bind-mount. An unreadable lock must never be mistaken for a satisfied lock, and the
    message has to name the layer or the next reader debugs the wrong one.
    """
    path = ROOT / "uv.lock"
    assert path.is_file(), (
        f"{path} is not readable. `uv.lock` is COPYed into the builder stage at /build, not "
        "into the runtime image; it arrives by bind-mount. Add it to the `app` service "
        "volumes in `docker/compose.dev.yml`."
    )
    locked = dict(
        re.findall(
            r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"',
            path.read_text(encoding="utf-8"),
        )
    )
    assert locked, "uv.lock parsed to nothing — the lock format this reader expects has moved"
    return locked


def _as_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def test_the_lock_contains_the_versions_the_security_review_claims():
    """**The defect this exists for, and it cost a full verification cycle.**

    M10.5 raised Django's floor to 5.2.17 and recorded that `sqlparse` moved to 0.6.0 with it.
    It did not. Django requires only `sqlparse>=0.3.1`, so `uv lock` kept the locked 0.5.5 —
    correct behaviour, minimal churn — and five advisories stayed in the lock while three
    documents said they were fixed.

    **`make verify` could not catch it**: the dependency audit is `make audit` and a CI step,
    not one of the eight stages (a recorded gap, not an omission — see `M10_Security_Review`
    §3.5). So the only authority had no view of the thing the milestone was about.

    This closes that specific hole without moving the gate: **a remediation the review claims
    must be present in the lock the build actually installs.** It is not a substitute for the
    audit — a new advisory against a locked version still needs `pip-audit` — but a documented
    fix that never reached the lock now fails inside `make verify`.
    """
    claimed = _claimed_floors()
    assert claimed, "no version floors parsed from the review — this check would be vacuous"

    locked = _locked_versions()
    behind = {
        package: (locked.get(package), floor)
        for package, floor in claimed.items()
        if package not in locked or _as_tuple(locked[package]) < _as_tuple(floor)
    }
    assert not behind, (
        f"the security review claims these versions and the lock does not contain them: "
        f"{behind}. Either `uv lock` has not been run since the constraint changed, or a "
        "transitive floor needs `[tool.uv] constraint-dependencies`."
    )


def test_that_lock_check_can_actually_fail():
    """Mutation, on the comparison rather than on a file.

    Without this, `_as_tuple` could return `()` for everything and the contract above would
    pass against any lock at all.
    """
    assert _as_tuple("0.5.5") < _as_tuple("0.6.0")
    assert _as_tuple("5.1.15") < _as_tuple("5.2.17")
    assert not _as_tuple("68.1") < _as_tuple("68.0")
    assert "sqlparse" in _claimed_floors(), (
        "the review no longer names a sqlparse floor; the row format this parses has changed"
    )


# ---------------------------------------- NFR-SEC-009 — the audit must be runnable at all
def _make_recipe(target: str) -> str:
    """One target's **executable** lines from the Makefile, folded to a single line.

    Recipe lines are the tab-indented ones under `target:`; a blank line or a new rule ends
    it. Read from the mounted Makefile because that is where a command gets neutered — the
    same reasoning as *"no mobile check can be silenced"*, which reads it for `|| true`.

    **`@echo` lines are dropped, and the reason is a defect this test had.** The `audit`
    recipe prints a banner that names the flags it is about to use, so a search over the whole
    recipe found `--strict` in the *message* after it had been removed from the *command* —
    the contract passed against precisely the change it exists to catch. Prose that describes
    a command is not the command.
    """
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(
        rf"^{re.escape(target)}:[^\n]*\n(?P<body>(?:\t[^\n]*\n|\n(?=\t))*)",
        makefile,
        re.MULTILINE,
    )
    assert match, f"the `{target}` target is gone from the Makefile"

    commands = [
        line
        for line in match.group("body").splitlines()
        if line.strip() and not re.match(r"^\s*[@-]*echo\b", line)
    ]
    return " ".join(" ".join(commands).split())


def test_the_audit_target_does_not_require_a_running_stack():
    """**The verify -> audit sequencing failure, made impossible.**

    `make verify` ends with `$(DC) down -v`. `make audit` used `$(TOOLS)`, which is `exec`
    into a running container, so the natural sequence — verify, then audit — died with
    `service "app" is not running`. The audit did not run, and a security gate that did not
    run is indistinguishable from one that passed unless somebody reads the output carefully.

    So the recipe must be **one-shot**: `run --rm`, the pattern `make lock` and `FLUTTER_RUN`
    already use for work that needs an image but not a session.

    **And it must not depend on the database, in either of the two ways it can.** `--no-deps`
    stops Postgres being *started*. It does not stop the image's ENTRYPOINT —
    `docker/entrypoint.sh` — from *waiting* for it: the first run with `--no-deps` alone
    blocked for 60 seconds on `waiting for database...` and exited without ever reaching
    `pip-audit`. Both flags are asserted because removing either reproduces a different half
    of the same failure.
    """
    recipe = _expand_make_variables(_make_recipe("audit"))

    assert "pip-audit" in recipe, "the audit target no longer runs pip-audit"
    assert "exec" not in recipe, (
        "`make audit` execs into a running container, so `make verify && make audit` cannot "
        "work — verify's last act is `down -v`. Use the one-shot `$(AUDIT)` runner."
    )
    assert "run --rm" in recipe, "the audit does not run in a one-shot container"
    assert "--no-deps" in recipe, (
        "the audit starts the database; pip-audit reads a virtualenv, and a scan that fails "
        "when Postgres is unhealthy is not a dependency gate"
    )
    assert "--entrypoint" in recipe, (
        "the audit runs through `docker/entrypoint.sh`, which waits 60s for the database and "
        "then migrates before exec'ing anything — the scan never runs"
    )
    assert "--strict" in recipe, "a dependency that cannot be audited would pass silently"
    assert "|| true" not in recipe, "the local audit cannot fail, so it proves nothing"


def _expand_make_variables(text: str, passes: int = 5) -> str:
    """Substitute `$(NAME)` from the Makefile's own definitions.

    **The first draft of this contract checked the raw recipe and could not fail.** Reverting
    the command to `$(TOOLS)` — the exact regression this test exists to prevent — left the
    literal `exec` inside a *variable definition*, so a substring search over the recipe saw
    only `$(TOOLS)` and passed. Expanding first is what makes the assertion about the command
    that actually runs rather than about how it happens to be spelled.

    Bounded passes rather than recursion: a self-referential variable would otherwise hang the
    suite, and five is far past this Makefile's nesting.
    """
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    definitions = dict(re.findall(r"^([A-Z_][A-Z0-9_]*)\s*:?=[ \t]*(.*)$", makefile, re.MULTILINE))
    assert definitions, "no Make variables parsed — this expansion would be a no-op"

    for _ in range(passes):
        expanded = re.sub(
            r"\$\((\w+)\)", lambda m: definitions.get(m.group(1), m.group(0)), text
        )
        if expanded == text:
            break
        text = expanded
    return " ".join(text.split())


def test_that_the_make_expander_actually_expands():
    """Anti-vacuity for the helper above — an expander that returned its input unchanged
    would make the contract pass against a recipe that execs."""
    assert "exec" in _expand_make_variables("$(TOOLS) pip-audit"), "TOOLS did not expand"
    assert "run --rm" in _expand_make_variables("$(AUDIT) pip-audit"), "AUDIT did not expand"


def _ignored_ids(command: str) -> set[str]:
    return set(re.findall(r"--ignore-vuln\s+(\S+)", command))


def test_the_local_audit_matches_the_ci_audit():
    """**Two copies of one fact, and this is the police the repository asked for.**

    `make audit` and the CI step both name the exemption. The Makefile's own comment on
    `FLUTTER_VERSION` records the preferred answer — *"deriving it deletes the class instead
    of policing it"* — and there is no derivation available here: a GitHub workflow cannot
    read a Make variable and CI does not run through the Makefile. So the two are asserted
    equal instead, which is the fallback that file also uses.

    The failure this prevents is silent and one-directional: CI green, local audit red, and
    a developer concluding the gate is broken rather than that the two disagree.
    """
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    local = _ignored_ids(" ".join(makefile.split()))
    ci = _ignored_ids(_audit_command(workflow))

    assert local == ci, (
        f"`make audit` and CI ignore different identifiers — local {sorted(local)}, "
        f"CI {sorted(ci)}. One of them is auditing something the other is not."
    )
