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
    "scripts/win-flutter.sh",
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


#: How a Flutter invocation is spelled in a recipe. Two spellings are legitimate and mean
#: different toolchains: bare `flutter` inside `$(FLUTTER_SH) '…'` is the pinned container,
#: `$(FLUTTER_HOST)` is the workstation launcher the device gates need. **Both are matched
#: here.** Matching only the bare word is how the `flutter drive` contracts below silently
#: went vacuous the moment the device gates were switched to `$(FLUTTER_HOST)` — they kept
#: passing while guarding nothing, which is worse than failing.
_FLUTTER_CMD = r"(?:\bflutter|\$\(FLUTTER_HOST(?:_RUN)?\))\s+"


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
        if line.startswith("\t") and re.search(_FLUTTER_CMD + r"(analyze|test|drive)\b", line)
    ]
    assert recipes, "no mobile analyze/test recipe found — this test would pass vacuously"
    offenders = [line.strip() for line in recipes if "pub get" not in line]
    assert not offenders, (
        "a flutter command runs in a different container from its `pub get`; the packages "
        f"will be invisible to it: {offenders}"
    )


#: Every `flutter drive` in a recipe must name its device. `MOBILE_DEVICE_ID` is the
#: Makefile variable that supplies it; naming it here rather than matching any `-d` means a
#: hard-coded serial fails this test too, which is the point — the value is a property of
#: the machine, not of the project.
DEVICE_SELECTOR = "-d $(MOBILE_DEVICE_ID)"


def _drive_recipes() -> list[str]:
    """Every Makefile recipe line that invokes `flutter drive`, joined across continuations.

    Two of the four device-gate invocations are written across three physical lines with
    trailing backslashes, so a per-line scan would see `flutter drive` on one line and its
    `-d` on another and report a false offender. Joining first is what makes this contract
    describe commands rather than lines.
    """
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    joined = re.sub(r"\\\n\s*", " ", text)
    return [
        line
        for line in joined.splitlines()
        if line.startswith("\t") and re.search(_FLUTTER_CMD + r"drive\b", line)
    ]


def test_every_device_gate_names_the_device_it_drives():
    """**A gate that can stop and ask a question is not a gate.**

    `flutter drive` with no `-d` and more than one visible device does not fail — it prompts
    and then waits. On Windows the visible set routinely includes the desktop, Chrome and
    Edge beside the emulator, so the run produces no further output and is indistinguishable
    from a hang. Measured 2026-08-30: a host `flutter drive` sat for thirty minutes emitting
    nothing, and was killed rather than completing.

    `flutter test integration_test/...` — which the encryption gate uses — does **not** have
    this failure mode: it requires exactly one device and errors out rather than asking. That
    asymmetry is why this contract is scoped to `drive`, and why the one device gate that has
    ever run successfully never exposed the defect.
    """
    recipes = _drive_recipes()
    assert recipes, "no `flutter drive` recipe found — this test would pass vacuously"

    offenders = [line.strip()[:110] for line in recipes if DEVICE_SELECTOR not in line]
    assert not offenders, (
        f"a device gate invokes `flutter drive` without `{DEVICE_SELECTOR}` and can therefore "
        f"block on an interactive device prompt: {offenders}"
    )


def test_the_device_id_is_overridable_and_defaulted():
    """`?=`, not `:=`, and that distinction is the whole configurability.

    The device serial is a property of the *machine*, so an environment variable must be able
    to win. Every other variable in the Makefile is `:=` because it is a property of the
    project; this is the deliberate exception, and pinning it to `:=` would silently ignore
    an exported `MOBILE_DEVICE_ID`.
    """
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^MOBILE_DEVICE_ID\s*\?=\s*\S+", text, re.MULTILINE), (
        "MOBILE_DEVICE_ID must be declared with `?=` so an environment variable or a "
        "command-line override can select a different device"
    )
    assert not re.search(r"^MOBILE_DEVICE_ID\s*:=", text, re.MULTILINE), (
        "MOBILE_DEVICE_ID is `:=`, which ignores the environment"
    )


def test_no_device_serial_is_hard_coded_in_a_recipe():
    """The device must be named through the variable, never inline.

    A literal `emulator-5554` in a recipe works on exactly one machine and fails silently
    everywhere else — it would select nothing, and `flutter drive` would go back to asking.
    """
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    joined = re.sub(r"\\\n\s*", " ", text)
    offenders = [
        line.strip()[:110]
        for line in joined.splitlines()
        if line.startswith("\t") and re.search(r"-d\s+emulator-\d+", line)
    ]
    assert not offenders, (
        f"a recipe hard-codes a device serial instead of using {DEVICE_SELECTOR}: {offenders}"
    )


#: Everything that touches a **real device**: the three gates and the preflight they share.
#: `emulator-trust-ca` is deliberately absent — it is a developer convenience, not a gate,
#: and its `adb push build/$(CA_HASH).0` passes a *host* path across the WSL boundary, a
#: different problem with a different fix, which these contracts would misreport if they
#: claimed it. `device-gate-preflight` must stay in this list: the guards moved there out of
#: the gates, and omitting it would quietly stop checking them.
DEVICE_GATES = (
    "device-gate-preflight",
    "mobile-device-kill",
    "mobile-device-storage",
    "mobile-device-encryption",
)

#: Shell string literals. `echo "…the adb server is Windows-side…"` is prose about adb, not
#: an invocation of it, and the guards below are written to be read by a human at 2am — so
#: the scanners strip quoted text first and then look at what is left, which is commands.
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def _gate_recipe_lines() -> list[str]:
    """Every recipe line of the three device gates, continuations joined, quotes stripped."""
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    joined = re.sub(r"\\\n\s*", " ", text)

    collected: list[str] = []
    current: str | None = None
    for line in joined.splitlines():
        if line.startswith("\t"):
            if current is not None:
                collected.append(_QUOTED.sub(" ", line))
            continue
        target = line.split(":", 1)[0].strip()
        current = target if target in DEVICE_GATES else None
    return collected


def test_no_device_gate_invokes_a_bare_adb():
    """**`make` runs in WSL2; the adb server does not.**

    WSL2 is a separate VM with its own network namespace, so a Linux `adb` started inside it
    talks to a Linux adb server on the WSL2 loopback — which no Windows emulator has ever
    registered with. It answers `List of devices attached` with nothing and exits 0, so a
    bare `adb devices` guard passes *because* it saw no device, and the gate then drives
    nothing while reporting success. Naming the Windows binary is what makes the boundary
    explicit; installing a Linux adb would be selecting the one that cannot see the device.
    """
    lines = _gate_recipe_lines()
    assert lines, "no device-gate recipe found — this test would pass vacuously"

    offenders = [line.strip()[:110] for line in lines if re.search(r"(?<![-\w$/.)])adb\b", line)]
    assert not offenders, (
        "a device gate invokes a bare `adb`, which in WSL resolves to a Linux adb server that "
        f"cannot see a Windows emulator; use $(ADB): {offenders}"
    )


def test_no_device_gate_invokes_a_bare_flutter():
    """The device gates need a **host** Flutter, and `flutter` on PATH is not it.

    `docker/flutter.Dockerfile` carries no Android SDK, no JDK and no adb, so the container
    that runs every other mobile target cannot drive a device at all. A bare `flutter` here
    resolves to whatever the shell finds — often nothing in WSL, occasionally the container
    wrapper — and the failure surfaces as a missing device rather than a missing toolchain.
    """
    lines = _gate_recipe_lines()
    assert lines, "no device-gate recipe found — this test would pass vacuously"

    offenders = [
        line.strip()[:110] for line in lines if re.search(r"(?<![-\w$/.)])flutter\b", line)
    ]
    assert not offenders, (
        "a device gate invokes a bare `flutter`; the pinned container has no Android SDK, so "
        f"the host launcher must be named through $(FLUTTER_HOST): {offenders}"
    )


#: The wrapper every host-Flutter call must go through.
WIN_FLUTTER = ROOT / "scripts" / "win-flutter.sh"

#: Stub `wslpath -w` bodies. Raw strings on purpose: the corruption under test *is*
#: backslashes, and re-escaping them through Python, sh and sed is how the first draft of
#: these stubs silently produced a healthy path and passed while proving nothing.
_WSLPATH_OK = r"""printf 'D:%s\n' "$(printf '%s' "$2" | tr '/' '\\')""" '"'
#: The 2026-08-31 defect, byte for byte: `…-stable\flutter\bin` -> `…-stableflutter\bin`.
_WSLPATH_DROPS_A_SEPARATOR = (
    r"""printf 'D:%s\n' "$(printf '%s' "$2" | tr '/' '\\' """
    r"""| sed 's|\\flutter\\bin|flutter\\bin|')""" '"'
)
#: `\f` decoded as formfeed. Renders as nothing, so the path looks correct in every log.
_WSLPATH_INJECTS_A_CONTROL_CHARACTER = (
    r"""printf 'D:%s\n' "$(printf '%s' "$2" | tr '/' '\\' """
    r"""| sed 's|\\flutter\\bin|\x0clutter\\bin|')""" '"'
)

#: Stub `cmd.exe`. Answers the wrapper's `if exist` probe by translating the Windows path
#: back and testing it — what a correct Windows does. With `STUB_CMD_LOSES_A_SEPARATOR` it
#: mangles the path *it* received, which is the only faithful model of a corruption that
#: happens after bash: `wslpath` is healthy, the Makefile expansion is byte-exact, and the
#: loss is in interop's command-line construction or cmd's parsing.
_CMD_STUB = r"""#!/bin/sh
if [ "$3" = "if" ] && [ "$4" = "exist" ]; then
  p=$5
  if [ "${STUB_CMD_LOSES_A_SEPARATOR:-}" = 1 ]; then
    p=$(printf '%s' "$p" | sed 's|\\flutter\\bin|flutter\\bin|')
  fi
  real=$(printf '%s' "$p" | sed -E 's|^D:||' | tr '\\' '/')
  [ -f "$real" ] && printf 'PATH_OK\r\n'
  exit 0
fi
printf 'LAUNCH'; for a in "$@"; do printf ' [%s]' "$a"; done; printf '\n'
"""


def _run_wrapper(
    tmp_path, wslpath_body: str, flutter_host: str | None = None, lossy_cmd: bool = False
):
    """Run `win-flutter.sh` with `wslpath` and `cmd.exe` stubbed onto PATH.

    The stub `cmd.exe` answers the `if exist` probe by translating the Windows path back and
    testing it, which is what a correct Windows would do — so a corrupted path fails the
    probe here for the same reason it fails there.
    """
    import os
    import subprocess

    stub = tmp_path / "stub"
    stub.mkdir()
    launcher = tmp_path / "d" / "flutter_windows_3.44.7-stable" / "flutter" / "bin"
    launcher.mkdir(parents=True, exist_ok=True)
    (launcher / "flutter.bat").write_text("@ECHO OFF\r\n", encoding="utf-8")

    (stub / "wslpath").write_text(f"#!/bin/sh\n{wslpath_body}\n", encoding="utf-8")
    (stub / "cmd.exe").write_text(_CMD_STUB, encoding="utf-8")
    for name in ("wslpath", "cmd.exe"):
        (stub / name).chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{stub}:{env['PATH']}"
    if lossy_cmd:
        env["STUB_CMD_LOSES_A_SEPARATOR"] = "1"
    env["FLUTTER_HOST"] = flutter_host or str(launcher / "flutter.bat")
    return subprocess.run(  # noqa: S603
        ["/bin/sh", str(WIN_FLUTTER), "drive", "-d", "emulator-5554"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_the_wrapper_launches_when_the_windows_path_is_intact(tmp_path):
    """Anti-vacuity for the two rejection tests below: the healthy path must still run.

    A guard that rejects everything is not a guard, and the failure mode being defended
    against here — a gate that cannot start — is the same one the guard exists to prevent.
    """
    result = _run_wrapper(tmp_path, _WSLPATH_OK)
    assert result.returncode == 0, f"the wrapper refused a healthy path:\n{result.stderr}"
    assert "LAUNCH" in result.stdout, result.stdout
    assert "call" in result.stdout, (
        f"a batch file must be launched with `call`, or cmd need not return its errorlevel — "
        f"and mobile-device-kill phase 1 asserts on an inverted exit code: {result.stdout}"
    )
    assert "flutter_windows_3.44.7-stable\\flutter\\bin\\flutter.bat" in result.stdout, (
        f"the launched path lost a component: {result.stdout}"
    )


def test_the_wrapper_refuses_a_windows_path_that_lost_a_separator(tmp_path):
    """**The 2026-08-31 defect, as an executable regression.**

    A gate run reached cmd.exe as `…flutter_windows_3.44.7-stableflutter\\bin\\flutter.bat`,
    the separator before `flutter` gone. cmd cannot resolve that, and the way it failed was
    a thirty-minute apparent hang rather than an error — the expensive failure mode, because
    nothing named the cause.

    Reproducing the make expansion under instrumented stubs proved it byte-exact, so the
    loss happens downstream of bash and no static check over the Makefile can ever see it.
    This asserts the wrapper catches it at runtime instead, before Flutter is launched.
    """
    result = _run_wrapper(tmp_path, _WSLPATH_DROPS_A_SEPARATOR)
    assert result.returncode != 0, (
        f"the wrapper launched Flutter with a path missing a separator:\n{result.stdout}"
    )
    assert "LAUNCH" not in result.stdout, "cmd.exe was reached despite the corrupt path"
    assert "stableflutter" in result.stderr, (
        f"the diagnostic must show the corrupted path so the guilty layer is identifiable:"
        f"\n{result.stderr}"
    )
    assert "expected components" in result.stderr, (
        "the component-by-component comparison must be what reports this. The cmd.exe probe "
        "would also refuse the path, but only says the file is not there; naming the "
        "differing component is what turns a thirty-minute hang into a two-line diagnosis."
        f"\n{result.stderr}"
    )


def test_the_wrapper_refuses_when_windows_cannot_see_the_path_it_was_handed(tmp_path):
    """**The case no Linux-side check can observe, and the one that actually happened.**

    Reproducing the make expansion under instrumented stubs proved argv byte-exact, and
    `wslpath` output is checked component-by-component above. So if the path still arrives
    corrupted, the loss is in WSL interop's command-line construction or in cmd's own
    parsing — *after* everything this script can inspect. Here `wslpath` is healthy and the
    stub cmd.exe is the layer that drops the separator, which is the only faithful model of
    that failure.

    The probe is what makes it observable: the wrapper asks Windows whether the file exists
    at the path Windows was handed, over the same boundary the real call crosses.
    """
    result = _run_wrapper(tmp_path, _WSLPATH_OK, lossy_cmd=True)
    assert result.returncode != 0, (
        f"the wrapper launched Flutter although Windows could not resolve the path:"
        f"\n{result.stdout}"
    )
    assert "cmd.exe cannot see the launcher" in result.stderr, (
        f"the diagnostic must name the Windows side as the layer that lost it, or the next "
        f"investigation starts again at the Makefile:\n{result.stderr}"
    )


def test_the_wrapper_refuses_a_flutter_host_carrying_a_control_character(tmp_path):
    """A control character in the OVERRIDE, which the component comparison cannot see.

    `\f` decoded as a formfeed renders as nothing, so a mangled `FLUTTER_HOST=` on the
    command line looks correct in the shell, in `ps` and in every log. It also survives
    translation into the Windows path — so it lands on *both* sides of the component
    comparison, which then finds two equal strings and passes it through. Checking the input
    is what makes this detectable, and it is the only corruption that check uniquely owns.
    """
    # The file must EXIST, or the `-f` guard fires first and the test passes for the wrong
    # reason — proving nothing about the check it is named for.
    odd = tmp_path / "d" / "flutter_windows_3.44.7-stable" / "flutter" / "bin" / "flut\x0cer.bat"
    odd.parent.mkdir(parents=True, exist_ok=True)
    odd.write_text("@ECHO OFF\r\n", encoding="utf-8")

    result = _run_wrapper(tmp_path, _WSLPATH_OK, flutter_host=str(odd))
    assert result.returncode != 0, f"a control character reached cmd.exe:\n{result.stdout}"
    assert "non-printing" in result.stderr, (
        f"the control-character check must be what refuses this — not the existence guard, "
        f"and not a downstream failure:\n{result.stderr}"
    )


def test_the_wrapper_refuses_a_windows_path_carrying_a_control_character(tmp_path):
    """`\\f` decoded as a formfeed renders as *nothing*, so the path looks right in every log.

    This is the sibling of the defect above and the more dangerous of the two: a lost
    separator is at least visible on close reading, whereas a 0x0C is not visible at all.
    """
    result = _run_wrapper(tmp_path, _WSLPATH_INJECTS_A_CONTROL_CHARACTER)
    assert result.returncode != 0, (
        f"the wrapper launched Flutter with a non-printing character in the path:"
        f"\n{result.stdout}"
    )


def test_the_wrapper_never_prints_a_windows_path_with_echo():
    """POSIX `echo` interprets backslash escapes, and every path this script reports has them.

    `\\c` truncates the line outright, `\\f` becomes an invisible formfeed, `\\b` a backspace
    that eats the character before it. The first draft of this wrapper used `echo` and its
    own diagnostic printed `D:` and stopped — a message about a corrupted path, corrupted
    while being printed. `printf '%s'` is the only safe form.
    """
    body = WIN_FLUTTER.read_text(encoding="utf-8")
    code = [
        line
        for line in body.splitlines()
        if not line.lstrip().startswith("#") and re.search(r"(?<![-\w.])echo\s", line)
    ]
    offenders = [line.strip()[:100] for line in code if "cmd.exe" not in line]
    assert not offenders, (
        f"win-flutter.sh uses `echo` on a string that may contain backslashes: {offenders}"
    )


def test_the_host_flutter_is_invoked_through_the_windows_interpreter():
    """**A `.bat` is not executable by anything in Linux, and the failure does not say so.**

    WSL's binfmt_misc interop recognises PE binaries, which is why `$(ADB)` can name
    `adb.exe` directly and simply work. A batch file has no PE header, so the kernel falls
    through to the shell and **bash reads the batch script as shell**. Measured 2026-08-31:
    `@ECHO: command not found`, `$'\\r': command not found` (one per CRLF line ending) and a
    syntax error at `FOR %%i IN` — three messages that name bash's confusion and never
    mention that the wrong interpreter was chosen.

    Flutter ships no `flutter.exe`, only `flutter.bat` beside a `flutter` bash script meant
    for a POSIX install — and that script is the more dangerous of the two, because it is
    executable from WSL and would drive a *Windows* SDK from Linux. So the wrapper is not a
    workstation preference; it is the only correct way to reach host Flutter from `make`.
    """
    text = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert re.search(
        r"^FLUTTER_HOST_RUN\s*=\s*FLUTTER_HOST='\$\(FLUTTER_HOST\)'\s+"
        r"\$\(CURDIR\)/scripts/win-flutter\.sh\s*$",
        text,
        re.MULTILINE,
    ), (
        "FLUTTER_HOST_RUN must route through scripts/win-flutter.sh, passing FLUTTER_HOST in "
        "the environment rather than as an argument, and using $(CURDIR) because the recipes "
        "`cd mobile` first"
    )

    wrapper = WIN_FLUTTER.read_text(encoding="utf-8")
    assert re.search(r"^exec cmd\.exe /D /C call \"\$WIN_FLUTTER\" \"\$@\"", wrapper, re.M), (
        "the wrapper must launch through `cmd.exe /D /C call`: /D suppresses AutoRun, whose "
        "exit status could otherwise become cmd's, and `call` is what returns the batch "
        "errorlevel that mobile-device-kill phase 1 asserts on — inverted"
    )
    assert 'cmd.exe /D /C if exist "$WIN_FLUTTER"' in wrapper, (
        "the wrapper must ask cmd.exe whether the launcher exists at the path it was handed; "
        "that probe is the only check positioned to see a corruption that happens on the "
        "Windows side of the boundary"
    )

    # The bypass this contract exists to reject: naming the launcher without the interpreter.
    offenders = [
        line.strip()[:110]
        for line in _gate_recipe_lines()
        if re.search(r"\$\(FLUTTER_HOST\)(?!_)", line) or ".bat" in line
    ]
    assert not offenders, (
        "a device gate invokes the Windows launcher directly instead of through "
        f"$(FLUTTER_HOST_RUN); bash will read the batch file as shell: {offenders}"
    )


def test_every_host_flutter_invocation_uses_the_wrapper():
    """The gates must all reach Flutter the same way — one of three is not a fix.

    Scoped to the *host* gates on purpose. `mobile-verify` and friends run bare `flutter`
    inside `$(FLUTTER_SH) '…'`, which is the pinned container and correct there; conflating
    the two toolchains is what this whole variable split exists to prevent.
    """
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    joined = re.sub(r"\\\n\s*", " ", text)

    invocations = [
        line
        for line in joined.splitlines()
        if line.startswith("\t") and "$(FLUTTER_HOST_RUN)" in line
    ]
    assert invocations, "no wrapped host-Flutter invocation found — this would pass vacuously"

    verbs = {"pub", "drive", "build", "test"}
    seen = {
        match
        for line in invocations
        for match in re.findall(r"\$\(FLUTTER_HOST_RUN\)\s+(\w+)", line)
    }
    assert verbs <= seen, (
        f"a host-Flutter verb is no longer wrapped; expected all of {sorted(verbs)}, the "
        f"wrapper carries {sorted(seen)}"
    )


#: The storage gate's two halves: the helper that fills the disk, and the phase that uses it.
_STORAGE_SUPPORT = MOBILE / "integration_test" / "support" / "device_outbox.dart"
_STORAGE_TEST = MOBILE / "integration_test" / "outbox_storage_full_test.dart"


def test_the_storage_gate_fills_its_own_disk_and_always_releases_it():
    """**`flutter drive` always installs the APK, so the disk cannot be full beforehand.**

    Measured 2026-09-04 across three runs: plain `drive` builds and installs; `--no-build` is
    ignored and it rebuilds, which rewrites the APK and forces a reinstall; and
    `--use-application-binary` skips the build but installs anyway. Every one of them died on
    `PackageInstallerService`'s *"Requested internal only, but not enough space"* before a
    line of Dart ran. An externally placed ballast — `adb shell dd` in the Makefile — cannot
    work, and no arrangement of the recipe can make it work.

    So the app fills its own filesystem, after it is running. Two properties must hold and
    neither is visible to a reader skimming the test:

    1. **The fill happens**, or the loop runs on an empty disk, nothing is refused, and the
       gate reports a setup error rather than a durability result.
    2. **The release is in a `finally`**, or a failed expectation leaves the device full — and
       the *next* run then cannot install the APK either. That is precisely the state the old
       external ballast left behind whenever a run aborted between the `dd` and the `rm`.
    """
    assert _STORAGE_SUPPORT.exists(), f"{_STORAGE_SUPPORT} missing — would pass vacuously"
    assert _STORAGE_TEST.exists(), f"{_STORAGE_TEST} missing — would pass vacuously"

    support = _STORAGE_SUPPORT.read_text(encoding="utf-8")
    for symbol in ("Future<int> fillDeviceStorage(", "Future<void> releaseDeviceStorage("):
        assert symbol in support, f"device_outbox.dart no longer defines `{symbol}`"

    # **The slack must be measured, not counted.** The write that hits `ENOSPC` can land part
    # of its chunk before throwing; a per-chunk counter cannot see those bytes, so truncating
    # relative to it releases the partial remainder as well as the slack — up to a whole chunk
    # too much. Measured 2026-09-04: a 2 MiB slack left under 34 MiB, all 2000 appends
    # committed, and the gate reported a setup error instead of a durability result.
    assert re.search(r"final \w+ = handle\.lengthSync\(\);\s*\n\s*final \w+ = \w+ - slackBytes",
                     support), (
        "the ballast is truncated relative to a counter rather than the file's real length. "
        "A partially written final chunk then frees more than the slack, and the append loop "
        "never exhausts the disk"
    )

    test = _STORAGE_TEST.read_text(encoding="utf-8")
    assert re.search(r"await fillDeviceStorage\(", test), (
        "the storage phase does not fill the disk; the append loop would run with free space "
        "and the gate would prove nothing"
    )
    assert re.search(
        r"\}\s*finally\s*\{[^}]*await releaseDeviceStorage\(\)", test, re.DOTALL
    ), (
        "releaseDeviceStorage() is not inside a `finally`. A phase that fails must still hand "
        "the space back, or the next run cannot install the APK"
    )


def test_the_storage_gate_places_no_ballast_from_the_runner():
    """The Makefile must not fill the disk — it is the one actor that provably cannot.

    Kept as a separate contract from the one above because they fail for opposite reasons: a
    reader who reintroduces `dd` has not broken the test, they have broken the *ordering*, and
    the message needs to say so.
    """
    joined = re.sub(r"\\\n\s*", " ", (ROOT / "Makefile").read_text(encoding="utf-8"))
    offenders = [
        line.strip()[:110]
        for line in joined.splitlines()
        if line.startswith("\t")
        and re.search(r"dd\s+if=/dev/zero|BALLAST_MB", _QUOTED.sub(" ", line))
    ]
    assert not offenders, (
        "the runner places a ballast again. An APK cannot be installed onto a full disk and "
        f"`flutter drive` always installs, so this can only ever fail: {offenders}"
    )


def test_the_adb_binary_is_derived_from_one_sdk_root():
    """One canonical SDK variable, and `ADB` computed from it — never a second literal.

    A repository that spells `platform-tools/adb.exe` twice has two facts where there is one,
    and they drift the first time somebody moves the SDK: the guard reads one path and the
    command runs the other, so the gate passes its precondition and then fails to execute.
    Deriving it means overriding `MOBILE_ANDROID_SDK` alone relocates every consumer.
    """
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(
        r"^ADB\s*\?=\s*\$\(MOBILE_ANDROID_SDK\)/platform-tools/adb(\.exe)?\s*$",
        text,
        re.MULTILINE,
    ), "ADB must be derived from $(MOBILE_ANDROID_SDK), not stated independently"

    joined = re.sub(r"\\\n\s*", " ", text)
    offenders = [
        line.strip()[:110]
        for line in joined.splitlines()
        if line.startswith("\t") and "platform-tools" in _QUOTED.sub(" ", line)
    ]
    assert not offenders, (
        f"a recipe restates the platform-tools path instead of using $(ADB): {offenders}"
    )


def test_the_host_toolchain_variables_are_overridable():
    """`?=` for all three, for the same reason `MOBILE_DEVICE_ID` has it.

    The SDK root, the adb binary and the host Flutter launcher are properties of the
    *workstation*, not of the project — a second machine, a second emulator or a Flutter
    installed somewhere else must be selectable without editing a tracked file. `:=` would
    ignore both the environment and the command line and hard-code this workstation.

    `FLUTTER_HOST` is deliberately not named `FLUTTER`: four `FLUTTER_*` variables above it
    already denote the **container** toolchain, and a bare `FLUTTER` beside them would read
    as the same thing.
    """
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    for name in ("MOBILE_ANDROID_SDK", "ADB", "FLUTTER_HOST", "MOBILE_DEVICE_ID"):
        assert re.search(rf"^{name}\s*\?=\s*\S+", text, re.MULTILINE), (
            f"{name} must be declared with `?=` so a different workstation can override it"
        )
        assert not re.search(rf"^{name}\s*:=", text, re.MULTILINE), (
            f"{name} is `:=`, which ignores the environment and the command line"
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


def test_no_certificate_verification_is_bypassed():
    """**The binary may widen which issuers it trusts. It may never stop checking.**

    `AppConfig.devTrustAnchor` lets a development build add one CA to the platform roots so
    the emulator can reach Caddy's locally-issued certificate over real TLS — `00` §7.3 puts
    the emulator on `10.0.2.2`, and `config.dart` refuses `http://`.

    **That mechanism makes a bypass reachable for the first time**, which is why this test
    exists now and did not before. One line — `badCertificateCallback = (_, __, ___) => true`
    — turns "trust one more root" into "trust anything", and it is the line somebody reaches
    for at 11pm when a certificate is wrong. It would pass every Dart test in the repository,
    because the failure it causes is invisible until a real network is hostile.

    The names below are the complete set of ways `dart:io` and Dio can be told to stop
    verifying. Anything that appears here is a defect, in `lib/`, in any build type.
    """
    forbidden = (
        "badCertificateCallback",
        "onBadCertificate",
        "allowLegacyUnsafeRenegotiation",
        "setTrustedCertificates(",  # the file-path form: unreadable on a device, and a
        # certificate read from disk is state outside the build
    )
    sources = dart_files()
    assert sources, "no Dart sources found — this test would pass vacuously"

    offenders = [
        f"{path.relative_to(MOBILE)}:{number}: {line.strip()}"
        for path in sources
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        # Comments are how this file documents the prohibition; only code counts.
        if not line.lstrip().startswith(("//", "///", "*"))
        and any(name in line for name in forbidden)
    ]
    assert not offenders, (
        "certificate verification is being bypassed or weakened: "
        f"{offenders}. Widening trust is `SecurityContext(withTrustedRoots: true)` plus "
        "`setTrustedCertificatesBytes`; disabling it is none of those."
    )


def test_the_development_trust_anchor_cannot_be_a_default():
    """A trust anchor compiled into `lib/` would be a P-9 violation and a permanent one.

    `devTrustAnchor` must arrive through `--dart-define`, exactly as the base URL does. A
    `defaultValue:` on that `String.fromEnvironment`, or a PEM literal anywhere in `lib/`,
    would mean every shipped APK trusts a certificate authority whose private key lives on a
    developer's laptop — and `02A` §9.3 assumes that APK is downloadable and decompiled.
    """
    config = LIB / "app" / "config.dart"
    assert config.exists(), "config.dart is missing — this test would pass vacuously"
    source = config.read_text(encoding="utf-8")

    assert "String.fromEnvironment(devTrustAnchorVariable)" in source, (
        "the development CA must be read from the build environment"
    )
    anchor_read = source.split("String.fromEnvironment(devTrustAnchorVariable)")[1][:80]
    assert "defaultValue" not in anchor_read, (
        "the development CA has a default; an unconfigured build would trust it"
    )

    # **Both markers, not one.** `config.dart` names `-----BEGIN CERTIFICATE-----` as the
    # string `_parseDevTrustAnchor` looks for when it validates a supplied CA — that is a
    # validation constant, not key material, and the first draft of this test flagged it.
    # A real PEM carries its END marker too; requiring the pair distinguishes a certificate
    # from a mention of one.
    literals = [
        f"{path.relative_to(MOBILE)}"
        for path in dart_files()
        if "BEGIN CERTIFICATE-----" in (source := path.read_text(encoding="utf-8"))
        and "END CERTIFICATE-----" in source
    ]
    assert not literals, f"a certificate is compiled into the binary (P-9): {literals}"


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
        # **Four spaces, not two.** A path/git *source* is nested under a package key:
        #     evil:
        #       path: ../evil
        # A top-level `  path: ^1.9.0` is the hosted pub.dev package *named* `path`, which
        # task 3 legitimately depends on. The first version of this check flagged it, and a
        # test that fails on a correct dependency gets deleted rather than heeded.
        if re.match(r"^\s{4,}(git|path):\s*\S", line) and "sdk: flutter" not in line
    ]
    assert not offenders, f"non-reproducible dependency source: {offenders}"


#: The `package:sqlite3` build-hook sources that provide an encryption codec, mapped to the
#: `PRAGMA` each one answers and upstream SQLite does not. The pairing is the point: a probe
#: that does not match the selected source fails closed on a *correct* build.
CIPHER_SOURCES: dict[str, str] = {
    "sqlite3mc": "PRAGMA cipher;",
    "sqlcipher": "PRAGMA cipher_version;",
}


def hook_source() -> str | None:
    """The value of `hooks: user_defines: sqlite3: source:` in `mobile/pubspec.yaml`.

    Hand-parsed rather than loaded with a YAML library: this suite imports nothing outside
    the standard library, and `pyyaml` is not a dependency of the backend image — adding one
    to read four lines would be a worse trade than tracking indentation. The nesting is a
    fixed chain of three keys, so this understands exactly that and returns `None` for
    anything else, which the callers treat as absence rather than guessing at intent.
    """
    text = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    chain = ("hooks:", "user_defines:", "sqlite3:")
    depth = 0
    indent = -1

    for raw in text.splitlines():
        # Comments are where this block explains itself; only the mapping counts. A commented
        # -out `source:` must read as absent, which is the whole point of the check.
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        column = len(raw) - len(raw.lstrip())

        # Dedent to or past the key we last matched means that block closed without the key
        # we were looking for. Returning here stops a `source:` under some *other* package's
        # user-defines from being read as this one's.
        if depth and column <= indent:
            return None

        if depth == len(chain):
            match = re.match(r"\s*source:\s*(\S+)", raw)
            if match:
                return match.group(1)
            continue

        if raw.strip() == chain[depth]:
            depth += 1
            indent = column

    return None


def test_the_build_hook_selects_an_encrypting_sqlite():
    """**Encryption at rest is four lines of YAML, and nothing else supplies it.**

    `package:sqlite3` 3.x picks its native library through a build hook and defaults to
    upstream SQLite, which has no codec. Against that library `PRAGMA key` is an unrecognised
    pragma: it does not fail, it is *ignored*, and the outbox is written in cleartext. That
    is not hypothetical — it is what M8 and M9 shipped. The APK carried `libsqlite3.so`
    alongside 14.5 MB of `libsqlcipher.so` that no code path could open, because `sqlite3`
    3.x removed `open.overrideFor`. Every one of 314 tests passed throughout.

    **This test exists because that defect was invisible for a milestone.** Deleting the
    `hooks:` block is a four-line edit that looks like tidying and silently downgrades
    FR-SYN-016 and NFR-SEC-008 from enforced to aspirational. `connection.dart` refuses to
    open an unencrypted database at runtime, but runtime is a device; this is the half that
    runs in `make verify`, which is the only authority (N-12).

    Either cipher source satisfies the requirement — neither FR-SYN-016 nor NFR-SEC-008 names
    a product — so this asserts the *property*, not the choice. Which one is selected is a
    design decision recorded against §5.6, and changing it is a decision, not a regression.
    """
    source = hook_source()

    assert source is not None, (
        "mobile/pubspec.yaml declares no `hooks: user_defines: sqlite3: source:`. Without it "
        "`package:sqlite3` bundles upstream SQLite, `PRAGMA key` is silently ignored, and "
        "the outbox is written in cleartext (FR-SYN-016, NFR-SEC-008)."
    )
    assert source in CIPHER_SOURCES, (
        f"the build hook selects `source: {source}`, which has no encryption codec. "
        f"FR-SYN-016 requires one of {sorted(CIPHER_SOURCES)}."
    )


def test_the_cipher_guard_is_unconditional_and_matches_the_hook():
    """**The runtime half: the guard must fire in release builds, and probe the right thing.**

    Drift's documentation suggests `assert(_debugCheckHasCipher(db))`. Asserts are stripped
    from release builds, so that check protects the developer and not the salesman — the one
    person whose device holds three days of unsent deliveries (§8.3). A guard that cannot fire
    in the build that ships is decoration.

    **The probe is cipher-specific and the two files must agree.** SQLite3MultipleCiphers
    answers `PRAGMA cipher`; SQLCipher answers `PRAGMA cipher_version`; upstream SQLite
    answers neither. Pairing the wrong probe with the right library fails closed on a correct
    build — the app refuses to start, the message blames the pubspec, and the search begins in
    the wrong file. That is a cheap mistake to make during a `source:` change and an expensive
    one to diagnose, so it is asserted here rather than left to a device.
    """
    source = hook_source()
    assert source in CIPHER_SOURCES, "no cipher source selected — see the test above"
    probe = CIPHER_SOURCES[source]

    connection = LIB / "data" / "db" / "connection.dart"
    assert connection.exists(), "connection.dart is missing — this test would pass vacuously"

    # Comments in that file discuss both probes by name, and a prohibition documented in a
    # comment must not read as a violation. Only code counts, exactly as the certificate
    # contract above decided.
    code = [
        line
        for line in connection.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith(("//", "///", "*"))
    ]

    # **Asserted before the probe's presence, because it is the likelier mistake.** Changing
    # `source:` without changing the probe leaves both files individually plausible, so the
    # diagnosis has to name the pair. `PRAGMA cipher;` is not a prefix match for
    # `PRAGMA cipher_version;` — the semicolon is what keeps the two distinguishable.
    code_text = "\n".join(code)
    mismatched = [
        other
        for name, other in CIPHER_SOURCES.items()
        if name != source and other in code_text
    ]
    assert not mismatched, (
        f"connection.dart probes {mismatched} but pubspec.yaml selects `source: {source}`, "
        f"which answers `{probe}`. The guard would reject a correctly configured build, and "
        "the message it prints would send the reader to the wrong file."
    )

    matching = [index for index, line in enumerate(code) if probe in line]
    assert matching, (
        f"connection.dart never probes for cipher support. `source: {source}` requires "
        f"`{probe}`; without it a build that quietly lost its codec would open a plaintext "
        "database and report success."
    )

    for index in matching:
        line = code[index]
        assert "assert" not in line, (
            f"the cipher check is inside an assert: {line.strip()!r}. Asserts are removed "
            "from release builds, so this would ship a cleartext outbox to a field device."
        )
        # The guard is a refusal, not an observation. Scoped to the statement that follows the
        # probe rather than the whole file, so a `throw` elsewhere cannot satisfy it.
        assert "throw" in "\n".join(code[index : index + 8]), (
            "the cipher probe does not refuse: a check whose failure branch does not throw "
            "leaves the database open and unencrypted (FR-SYN-016, NFR-SEC-008)."
        )
