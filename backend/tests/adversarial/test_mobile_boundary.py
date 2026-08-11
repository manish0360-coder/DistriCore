"""**The M8 mobile boundary, proven rather than trusted** (M8 §2.1, §8.5, §10 task 1).

`make verify` is the only authority (N-12), and its eight stages are Python. A layering
rule that lives only in `analysis_options.yaml` runs where the gate cannot see it — which
is precisely the status `mypy` held for six milestones before TD-2, and the status
`M8_Design_Review` §12.7 warned P-1…P-10 were starting in.

So the contracts that must not be broken are asserted **here**, from stage 7, over the Dart
sources. They are structural properties of imports and literals: they need a parser, not a
compiler. `flutter analyze` (`make mobile-verify`) is the developer-facing half and catches
what a compiler must; it is not yet in the gate, recorded as TD-37.

This is `test_reporting_boundary.py`'s shape applied to a second language. The lesson it
encodes is TD-36's: **the seven report endpoints violated a frozen clause for a whole
milestone because no test could fail.** These are written before the first feature for that
reason, not after.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

import pytest

pytestmark = pytest.mark.adversarial

ROOT = Path(__file__).resolve().parents[3]
MOBILE = ROOT / "mobile"
LIB = MOBILE / "lib"

#: Everything this module reads from the repository. The backend image contains only
#: `backend/`; these arrive by bind-mount from `docker/compose.dev.yml`, and a path that is
#: not mounted fails here as a `FileNotFoundError` deep inside an unrelated assertion.
#: `docker/` was added to that mount list a commit *after* the test that reads it, which is
#: exactly how stage 7 came to fail on plumbing while reporting a mobile contract.
REQUIRED_PATHS = (
    "Makefile",
    "mobile/.flutter-version",
    "mobile/pubspec.yaml",
    "mobile/lib",
    "docker/flutter.Dockerfile",
    "docker/compose.dev.yml",
)

#: The §9 layers, in the order dependencies are allowed to point.
LAYERS = ("app", "features", "data", "domain", "core")

#: Who may import whom. `app` is the composition root and may see everything — it is the
#: one place an interface is bound to an implementation, which is what buys `features`
#: the right never to see `data` (M8 §2.2).
ALLOWED: dict[str, frozenset[str]] = {
    "app": frozenset(LAYERS),
    "features": frozenset({"features", "domain", "core"}),
    "data": frozenset({"data", "domain", "core"}),
    "domain": frozenset({"domain", "core"}),
    "core": frozenset({"core"}),
}

#: Packages that make a layer untestable without a device. `domain` and `core` must compile
#: and run on a laptop — that is the whole reason the outbox can be tested at all (§2.1).
DEVICE_PACKAGES = ("flutter", "flutter_riverpod", "go_router", "dio", "drift", "sqlite3")
PURE_LAYERS = ("domain", "core")


# ------------------------------------------------------------------------- preconditions
def test_every_path_this_suite_reads_is_visible_from_inside_the_container():
    """Fail on the plumbing *as* plumbing, before any contract is evaluated.

    Without this, an unmounted path surfaces as a `FileNotFoundError` in the middle of
    whichever assertion happened to touch it first — so the gate reports "the Flutter pin is
    not stated exactly once" when the truth is "the container cannot see the file". A
    diagnosis that points at the wrong layer costs more than the failure it describes.

    Named first in the file so it is the first thing that fails and the first thing read.
    """
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    assert not missing, (
        f"not visible at {ROOT}: {missing}. The backend image contains only `backend/`; "
        "these arrive by bind-mount. Add them to the `app` service volumes in "
        "`docker/compose.dev.yml`."
    )


# --------------------------------------------------------------------------- source set
def dart_files() -> list[Path]:
    files = sorted(LIB.rglob("*.dart"))
    assert files, "mobile/lib holds no Dart files — this suite would pass vacuously"
    return files


def test_the_layer_folders_exist_and_are_populated():
    """Anti-vacuity. Every rule below is quantified over files; empty folders prove nothing.

    `reporting`'s boundary suite carries the same assertion for the same reason: a contract
    that holds because there is nothing to check is not a contract.
    """
    empty = [name for name in LAYERS if not list((LIB / name).rglob("*.dart"))]
    assert not empty, f"M8 §9 layers exist but hold no Dart: {empty}"


# --------------------------------------------------------------------------- the parser
#: `import 'x';` / `export 'x';`. Dart also allows `show`, `hide` and `as` suffixes, which
#: do not change *what* is imported and are therefore ignored.
_DIRECTIVE = re.compile(r"^\s*(?:import|export)\s+'([^']+)'", re.MULTILINE)
#: A conditional import resolves differently per platform. This parser reads one branch, so
#: rather than silently checking the wrong one it refuses.
_CONDITIONAL = re.compile(r"^\s*(?:import|export)\s+'[^']+'\s+if\s*\(", re.MULTILINE)


def test_every_import_in_the_tree_is_one_this_parser_understands():
    """**Fail loudly, not silently.**

    A regex over another language's grammar is a second implementation of that grammar, and
    the dangerous failure is not a crash — it is a construct this parser skips, leaving a
    layering violation unasserted while the suite stays green.
    """
    offenders = {
        path.name: _CONDITIONAL.findall(path.read_text(encoding="utf-8"))
        for path in dart_files()
    }
    assert not any(offenders.values()), (
        "conditional imports found; this parser reads a single branch and would check the "
        f"wrong one: {offenders}"
    )


def layer_of(path: Path) -> str:
    """The §9 layer a file belongs to, from its first segment under `lib/`."""
    relative = path.relative_to(LIB)
    return relative.parts[0] if len(relative.parts) > 1 else "root"


def imports_of(path: Path) -> list[str]:
    return _DIRECTIVE.findall(path.read_text(encoding="utf-8"))


def imported_layer(path: Path, target: str) -> str | None:
    """The layer a single import points at, or `None` for `dart:`/`package:` imports."""
    if target.startswith(("dart:", "package:")):
        # A self-import by package name is a relative import spelled the long way.
        if target.startswith("package:districore/"):
            inside = Path(target.removeprefix("package:districore/"))
            return inside.parts[0] if len(inside.parts) > 1 else "root"
        return None
    resolved = (path.parent / target).resolve()
    try:
        relative = resolved.relative_to(LIB)
    except ValueError:
        pytest.fail(f"{path.name} imports outside lib/: {target}")
    return relative.parts[0] if len(relative.parts) > 1 else "root"


# ----------------------------------------------------------------------------- layering
def test_dependencies_point_downward_only():
    """M8 §2.1. The mobile form of the N-01 violation the backend has refused for seven
    milestones: a lower layer reaching up, or presentation reaching past the interface it
    was given.
    """
    violations: list[str] = []
    for path in dart_files():
        source = layer_of(path)
        if source not in ALLOWED:
            continue
        for target in imports_of(path):
            destination = imported_layer(path, target)
            if destination in (None, "root"):
                continue
            if destination not in ALLOWED[source]:
                violations.append(f"{source}/{path.name} -> {destination} ({target})")
    assert not violations, "layering violated: " + "; ".join(violations)


def test_the_presentation_layer_cannot_see_an_implementation():
    """M8 §2.2, stated separately from the table because it is the rule most likely to be
    argued away by someone in a hurry.

    A screen asks for a repository *interface* and the composition root decides which
    implementation it gets. The moment a feature imports `data/`, task 4's swap of the stub
    session repository for the real one stops being a one-line change.
    """
    offenders = [
        f"features/{path.relative_to(LIB / 'features')}"
        for path in (LIB / "features").rglob("*.dart")
        if any(imported_layer(path, target) == "data" for target in imports_of(path))
    ]
    assert not offenders, (
        f"a screen imported an implementation instead of an interface: {offenders}"
    )


@pytest.mark.parametrize("layer", PURE_LAYERS)
def test_the_pure_layers_import_no_device_package(layer):
    """`domain` and `core` must run on a laptop with no Flutter, no emulator, no network.

    This is what makes the outbox testable at all — and the outbox is the milestone (§10.1).
    """
    offenders: dict[str, list[str]] = {}
    for path in (LIB / layer).rglob("*.dart"):
        bad = [
            target
            for target in imports_of(path)
            if target.startswith("package:")
            and target.removeprefix("package:").split("/")[0] in DEVICE_PACKAGES
        ]
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"{layer}/ imported a device package: {offenders}"


# ------------------------------------------------------------------------- P-9 secrets
#: A literal assigned to a secret-shaped name. Targeted at the *assignment*, not the word:
#: a login screen legitimately contains the string "Password", and a rule that fired on
#: that would be turned off within a week.
_SECRET_ASSIGNMENT = re.compile(
    r"""(?:const|final|var|String|static)\s+\w*
        (?:secret|api_?key|token|password|passwd|credential|private_?key|client_?secret)
        \w*\s*=\s*(['"])(?P<value>[^'"]{4,})\1""",
    re.IGNORECASE | re.VERBOSE,
)
#: An internal surface `02A` §9.3 says must not be discoverable by decompiling the binary.
_INTERNAL_SURFACE = re.compile(
    r"""(['"])(?P<value>
        (?:https?://)?(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)
        [^'"]*
        |/(?:admin|internal|debug)/[^'"]*
    )\1""",
    re.IGNORECASE | re.VERBOSE,
)


def _shannon_entropy(text: str) -> float:
    counts = Counter(text)
    length = len(text)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def test_no_secret_shaped_constant_ships_in_the_binary():
    """P-9 / `02A` §9.3 / DV-4 — **the condition the one-binary decision is accepted on.**

    > *The binary contains no API key, secret, internal endpoint or business rule whose
    > confidentiality matters.*

    The binary is publicly downloadable and must be assumed fully decompiled. `gitleaks`
    already scans the repository in CI, but it looks for *known* credential formats; this
    looks for the shape — a literal bound to a name that says it is a secret.
    """
    offenders: dict[str, list[str]] = {}
    for path in dart_files():
        text = path.read_text(encoding="utf-8")
        found = [m.group("value") for m in _SECRET_ASSIGNMENT.finditer(text)]
        found += [m.group("value") for m in _INTERNAL_SURFACE.finditer(text)]
        if found:
            offenders[str(path.relative_to(LIB))] = found
    assert not offenders, f"secret-shaped constant or internal surface in the binary: {offenders}"


def test_no_high_entropy_literal_ships_in_the_binary():
    """The other half of P-9: a key does not have to be *named* like one.

    Entropy over length is the cheapest signal that a string is a credential rather than
    prose. Deliberately conservative — 32+ characters at >4.2 bits/char is far above English
    text or a route path, so a false positive is rare and a real key is not.
    """
    candidate = re.compile(r"""(['"])(?P<value>[A-Za-z0-9+/=_-]{32,})\1""")
    offenders: dict[str, list[str]] = {}
    for path in dart_files():
        found = [
            value
            for match in candidate.finditer(path.read_text(encoding="utf-8"))
            if _shannon_entropy(value := match.group("value")) > 4.2
        ]
        if found:
            offenders[str(path.relative_to(LIB))] = found
    assert not offenders, f"high-entropy literal in the binary: {offenders}"


# --------------------------------------------------------------------- P-3 and P-6
#: Money-shaped identifiers. `double width` is legitimate Flutter; `double amount` is not.
_MONEY_WORDS = (
    "amount|price|total|balance|outstanding|quantity|qty|rate|tax|discount|paid|due|value"
)
_DOUBLE_MONEY = re.compile(rf"\bdouble\s+\w*(?:{_MONEY_WORDS})\w*\b", re.IGNORECASE)
_DOUBLE_COERCION = re.compile(r"\bas\s+double\b|\bdouble\.parse\s*\(|\.toDouble\s*\(\s*\)")


def test_money_never_becomes_a_double():
    """**P-3 / `05` AD-02 / C-1.** Dart has no `Decimal`, and `jsonDecode` yields `double`
    for any unquoted number.

    This is not hypothetical on this project. TD-36 is the *server* side of the same
    defect, found three days ago: the seven report endpoints emit money as JSON floats
    because `_as_json` bypasses the serializer that would have made them strings. One
    `as double` here reintroduces it on the client, where no database constraint can see
    it and no test on the other side can fail.

    **Currently vacuous by construction** — task 1 has no money. It is written now because
    task 2 introduces the codec, and a rule added after the code it governs is a rule
    written to fit what already exists.
    """
    offenders: dict[str, list[str]] = {}
    for path in dart_files():
        text = path.read_text(encoding="utf-8")
        found = _DOUBLE_MONEY.findall(text) + _DOUBLE_COERCION.findall(text)
        if found:
            offenders[str(path.relative_to(LIB))] = found
    assert not offenders, f"a money path touched `double`: {offenders}"


#: Where a v4 UUID may legitimately be minted. Task 3 adds the outbox; until then, nowhere.
_UUID_GENERATION = re.compile(r"\bUuid\s*\(\s*\)\s*\.\s*v4\s*\(|\bconst\s+Uuid\s*\(\)")
_UUID_ALLOWED = ("data/outbox",)


def test_a_client_uuid_is_minted_only_where_the_outbox_owns_it():
    """**P-6 / `05` C-2.** `client_uuid` is generated *before* the first attempt and reused
    on every retry; regenerating it on retry defeats the server's `uq_*_client_uuid`
    idempotency and produces duplicate orders and duplicate payments.

    Confining minting to the outbox is the mechanism: a retry path that cannot reach a UUID
    generator cannot mint a second one. **Vacuous until task 3**, and written now for the
    same reason as P-3 above.
    """
    offenders = {
        str(path.relative_to(LIB)): _UUID_GENERATION.findall(path.read_text(encoding="utf-8"))
        for path in dart_files()
        if not str(path.relative_to(LIB)).startswith(_UUID_ALLOWED)
    }
    assert not any(offenders.values()), (
        f"a UUID is minted outside {_UUID_ALLOWED}; a retry could regenerate it: "
        f"{ {k: v for k, v in offenders.items() if v} }"
    )


# ------------------------------------------------------------------------- the toolchain
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def test_the_flutter_pin_is_stated_exactly_once():
    """TD-21's lesson, applied to the second toolchain — **as a mechanism, not a check.**

    The first draft of this task hard-coded the version in the Makefile *and* in
    `.flutter-version`, then asserted the two agreed. Two consumers of one fact is the shape
    that drifts, and a test that watches for drift is a worse answer than not having two
    copies: the Makefile now reads the file. This asserts only that nobody restores the
    duplicate.

    Same move as `identity/phone.py` — one canonical definition that the write path and the
    read path both use, rather than two implementations kept in step by discipline.
    """
    pinned = (MOBILE / ".flutter-version").read_text(encoding="utf-8").strip()
    assert _SEMVER.match(pinned), f".flutter-version is not an exact version: {pinned!r}"

    declaration = re.search(
        r"^FLUTTER_VERSION\s*:=\s*(.+)$", (ROOT / "Makefile").read_text(encoding="utf-8"), re.M
    )
    assert declaration, "FLUTTER_VERSION is not declared in the Makefile"
    assert ".flutter-version" in declaration.group(1), (
        "FLUTTER_VERSION restates the version instead of reading `.flutter-version`: "
        f"{declaration.group(1).strip()!r}"
    )

    # The toolchain image is now built here rather than pulled, which added a third place
    # the version could be written down. It takes the pin as a build-arg with no default.
    dockerfile = (ROOT / "docker" / "flutter.Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^ARG FLUTTER_VERSION\s*$", dockerfile, re.M), (
        "docker/flutter.Dockerfile must take FLUTTER_VERSION as a build-arg with no default"
    )
    assert pinned not in dockerfile, (
        f"docker/flutter.Dockerfile hard-codes {pinned}; it must receive the pin, not restate it"
    )


def test_the_toolchain_image_is_built_not_borrowed():
    """The defect that produced this file.

    `ghcr.io/cirruslabs/flutter:3.44.7` was written into the Makefile without checking that
    the tag existed. It did not, and could not: cirruslabs stopped publishing on
    **2026-05-01**, and Flutter 3.44.0 shipped on **2026-05-18**. Their Docker Hub
    predecessor `cirrusci/flutter` stopped at 3.7.7 in March 2023.

    **A pinned toolchain that depends on a third party continuing to publish is borrowed,
    not pinned.** This asserts the Makefile builds the image from a Dockerfile we own.
    """
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    image = re.search(r"^FLUTTER_IMAGE\s*:=\s*(.+)$", makefile, re.M)
    assert image, "FLUTTER_IMAGE is not declared"
    assert "cirruslabs" not in image.group(1) and "cirrusci" not in image.group(1), (
        "the Flutter toolchain points at a registry that stopped publishing in May 2026"
    )
    assert (ROOT / "docker" / "flutter.Dockerfile").exists(), (
        "FLUTTER_IMAGE names an image with no Dockerfile to build it from"
    )


def test_no_flutter_command_is_separated_from_its_pub_get():
    """The second defect this infrastructure produced, and the more insidious one.

    `PUB_CACHE` is `/tmp` inside a `--rm` container, but `.dart_tool/package_config.json`
    is written into the **mounted** tree and records absolute paths into that cache. Running
    `pub get` in one `docker run` and `flutter analyze` in the next therefore leaves the
    second container holding a package map that points at files which no longer exist.

    **It fails as 51 compile errors, not as a cache miss** — `Got dependencies!` immediately
    followed by every import reported as `uri_does_not_exist`, which reads like broken source
    rather than broken plumbing. Chaining them in one container is the fix; this asserts
    nobody unchains them.
    """
    recipes = [
        line
        for line in (ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
        if line.startswith("\t") and re.search(r"flutter\s+(analyze|test)\b", line)
    ]
    assert recipes, "no mobile analyze/test recipe found — this test would pass vacuously"
    offenders = [line.strip() for line in recipes if "pub get" not in line]
    assert not offenders, (
        "a flutter command runs in a different container from its `pub get`; the packages "
        f"will be invisible to it: {offenders}"
    )


def test_the_refresh_client_carries_no_interceptors():
    """**D-B2** — isolation is structural, not a re-entrancy flag.

    `/auth/refresh` runs on a `Dio` that carries neither `AuthInterceptor` nor
    `RefreshInterceptor`. A refresh call able to trigger the refresh interceptor is an
    infinite loop reachable from one expired token, and a flag guarding it is a rule someone
    deletes while adding a feature. An interceptor that was never added cannot be re-entered.

    Asserted here rather than only in Dart because `make verify` is the only authority and
    it does not run `flutter test` (TD-37).
    """
    client = LIB / "data" / "api" / "api_client.dart"
    assert client.exists(), "api_client.dart is missing — this test would pass vacuously"
    source = client.read_text(encoding="utf-8")

    assert "_refreshDio.interceptors" not in source, (
        "the refresh client was given interceptors; D-B2 requires it to carry none"
    )
    added = re.findall(r"(\w+)\.interceptors\s*\.\s*add", source)
    assert set(added) <= {"_dio"}, (
        f"only the main client may receive interceptors, found: {sorted(set(added))}"
    )


def test_no_mobile_check_is_silenced():
    """`|| true` is how a gate stops being one.

    This project has the receipts: `mypy` carried it for six milestones (TD-2, closed at the
    fourth attempt, 24 real errors behind it) and `pip-audit` still does (TD-35). The mobile
    checks are new and noisy, which is exactly when someone reaches for it.

    Softening *severity* is a decision — `--no-fatal-infos` says infos are not defects.
    Softening the *exit code* is a way of not making one.
    """
    recipes = [
        line
        for line in (ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
        if line.startswith("\t") and "flutter" in line
    ]
    assert recipes, "no mobile recipes found — this test would pass vacuously"
    offenders = [
        line.strip()
        for line in recipes
        # `|| true` discards the exit code; a leading `-` tells make to ignore it. The
        # dash must be tested against the *recipe* prefix (one tab, then `-`), not against
        # the stripped line: continuation lines like `\t\t-f docker/flutter.Dockerfile`
        # are docker flags, and an earlier draft of this test flagged one of them.
        if "|| true" in line or line.startswith("\t-")
    ]
    assert not offenders, f"a mobile check cannot fail the build: {offenders}"


def test_the_mobile_package_declares_no_floating_git_or_path_dependency():
    """A `git:` or `path:` dependency is not reproducible from the lock alone. `uv.lock`
    pins 91 packages precisely so a clean machine builds what the gate built; the mobile
    package must not open a door beside it (TD-21).
    """
    pubspec = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in pubspec.splitlines()
        if re.match(r"^\s+(git|path):\s*\S", line) and "sdk: flutter" not in line
    ]
    assert not offenders, f"non-reproducible dependency source: {offenders}"
