"""**B-3 — the restore rehearsal must be able to fail** (`00` §14, §19.2).

`00` §19.2's M10 → M11 gate is *"Restore rehearsed and recorded (B-3); security review
complete"*, and B-1 says why it exists:

> *"A backup that has never been restored does not count as a backup."*

The first real rehearsal, 2026-09-07, failed on `POSTGRES_PASSWORD is missing a value` before
PostgreSQL was touched — **and the target printed a `PASS` row anyway and exited 0.** Two
defects, and the second is the dangerous one: a gate that manufactures its own evidence is
worse than no gate, because the record it writes is believed.

**Both were in the tooling, not the product.** These contracts hold the tooling.

`Makefile` and `ops/` are read from the mounted repository, because that is where a rehearsal
gets neutered — the same reasoning `test_mobile_boundary` uses for `|| true`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.adversarial

ROOT = Path(__file__).resolve().parents[3]

#: Read from outside `backend/`; they arrive by bind-mount (`docker/compose.dev.yml`).
REQUIRED_PATHS = ("Makefile", "ops/restore.sh", "ops/backup.sh", "docker/compose.yml")

#: The live databases. A rehearsal that reaches either is not a rehearsal.
LIVE_DATABASES = ("districore", "districore_prod")


def test_every_path_this_suite_reads_is_visible_from_inside_the_container():
    """Fail on the plumbing *as* plumbing, before any contract is evaluated."""
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    assert not missing, (
        f"not visible at {ROOT}: {missing}. These arrive by bind-mount — add them to the "
        "`app` service volumes in `docker/compose.dev.yml`."
    )


def _rehearsal_recipe() -> str:
    """The `restore-rehearsal` recipe, tab-indented lines only."""
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(
        r"^restore-rehearsal:[^\n]*\n(?P<body>(?:\t[^\n]*\n|\n(?=\t))*)", makefile, re.MULTILINE
    )
    assert match, "the `restore-rehearsal` target is gone from the Makefile"
    return match.group("body")


# --------------------------------------------------- the fabricated-evidence defect
def test_the_rehearsal_cannot_report_pass_after_a_failed_restore():
    """**The defect that made a failed rehearsal look like a passed one.**

    The recipe chained its steps with `;`, so `./ops/restore.sh` failing did not stop the
    lines after it — and `make` only inspects the exit status of the *last* command in a
    logical line, which was an `echo`. A restore that died on a missing environment variable
    printed `| ... | PASS | ... |` and returned 0.

    Two properties, and both are needed. The outcome must be **derived** from the restore's
    exit status rather than assumed, and the recipe must **end in a check** that propagates
    it, or `make` reports success whatever was printed.
    """
    recipe = _rehearsal_recipe()

    assert "PASS" in recipe, "the recipe no longer offers a row to record — B-3 needs one"
    assert not re.search(r"\|\s*PASS\s*\|", recipe), (
        "the recipe prints a literal `| PASS |` row. The outcome must come from the restore's "
        "exit status, not from the template — that is how a failed rehearsal was recorded as "
        "a passed one on 2026-09-07."
    )
    assert "outcome=FAIL" in recipe, (
        "there is no failure branch: the recipe cannot describe a rehearsal that failed"
    )
    # Scoped to the `printf` statement, not to the recipe. `$$outcome` also appears in the
    # progress echo and in the final check, so a whole-recipe search stays true even when the
    # row itself has stopped carrying the verdict — a contract that could not fail.
    printf_statement = re.search(r"printf\s.*?;", recipe, re.DOTALL)
    assert printf_statement, "the recipe no longer prints a row to record"
    assert "$$outcome" in printf_statement.group(0), (
        "the derived outcome is never passed to `printf`, so the row's verdict column is "
        "filled by the format string rather than by what happened"
    )
    assert re.search(r'test\s+"?\$\$outcome"?\s*=\s*PASS', recipe), (
        "the recipe does not end in a check on the outcome, so `make` exits 0 even when the "
        "restore failed"
    )


def test_the_rehearsal_refuses_the_live_database():
    """`ops/restore.sh` defaults to a scratch database; the target refuses the live names.

    This is the one mistake in the procedure that cannot be undone, so it is guarded before
    anything is decrypted — and the guard exits non-zero rather than warning.
    """
    recipe = _rehearsal_recipe()

    for database in LIVE_DATABASES:
        assert database in recipe, f"`{database}` is no longer refused as a restore target"
    assert re.search(r"REFUSED[^\n]*live database", recipe), "the refusal message is gone"
    assert "exit 2" in recipe, "the guard does not exit non-zero"

    restore = (ROOT / "ops" / "restore.sh").read_text(encoding="utf-8")
    assert "districore_restore_test" in restore, (
        "restore.sh no longer defaults to a scratch database, so an omitted argument would "
        "restore over whatever the default became"
    )


# --------------------------------------------------- the environment-propagation defect
def test_every_compose_call_in_ops_passes_an_explicit_env_file():
    """**The failure the first rehearsal actually hit.**

    `docker compose -f docker/compose.yml ...` sets the **project directory** to `docker/`,
    so compose's automatic `.env` discovery looks for `docker/.env` — which does not exist.
    `.env` is at the repository root. `compose.yml` declares

        POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}

    with no default, so interpolation fails and the command dies before PostgreSQL is
    reached. Every Makefile invocation carries `--env-file .env` through `$(DC)`; the two
    scripts in `ops/` were the only compose callers that did not.
    """
    offenders = []
    for script in sorted((ROOT / "ops").glob("*.sh")):
        source = script.read_text(encoding="utf-8")
        for line in source.splitlines():
            if "docker compose" not in line or line.strip().startswith("#"):
                continue
            if "--env-file" not in line and "COMPOSE_ENV" not in line:
                offenders.append(f"{script.name}: {line.strip()[:80]}")
    assert not offenders, (
        f"these compose calls rely on automatic `.env` discovery, which looks in `docker/` "
        f"and finds nothing: {offenders}"
    )


def test_the_compose_password_really_has_no_default():
    """Anti-vacuity for the contract above, and the reason it matters.

    If `POSTGRES_PASSWORD` ever gained a default, a missing `--env-file` would stop failing
    loudly and start silently connecting with the wrong credential — which is worse. This
    asserts the strict form is still what makes the omission detectable.
    """
    compose = (ROOT / "docker" / "compose.yml").read_text(encoding="utf-8")
    assert re.search(r"POSTGRES_PASSWORD:\s*\$\{POSTGRES_PASSWORD:\?", compose), (
        "POSTGRES_PASSWORD is no longer a required variable; a missing env file would now "
        "fail somewhere less obvious than at interpolation"
    )


def test_the_restore_script_checks_its_prerequisites_before_decrypting():
    """B-4: *"written to be followed under stress by someone who did not write it."*

    A wrong working directory must fail as a wrong working directory — not as a compose
    interpolation error three steps later, and not after a passphrase has been spent.
    """
    restore = (ROOT / "ops" / "restore.sh").read_text(encoding="utf-8")

    prerequisites = restore.index("docker/compose.yml .env")
    decrypt = restore.index("gpg --batch")
    assert prerequisites < decrypt, (
        "the prerequisite check runs after decryption; a wrong directory would be discovered "
        "only once the archive had already been decrypted"
    )
    assert "Run this from the repository root" in restore, "the diagnosis names no remedy"


#: The row the **failed** 2026-09-07 rehearsal printed before the fabricated-PASS defect was
#: fixed. It was never observed to succeed, so it must never appear in the log.
FABRICATED_ROW = ("2026-09-07T11:40:09Z", "districore-20260907T112633Z.dump.gpg")


def test_every_rehearsal_log_row_records_an_observed_run():
    """**Every row must look like something a person watched.** B-3, `00` §14.1.

    This contract replaces an earlier "the log holds no data row" assertion, which was only
    ever correct *until a real rehearsal wrote one* — its own docstring said so. The first
    verified rehearsal ran on 2026-09-07 and is now recorded, so the useful invariant moved
    from *emptiness* to *well-formedness*.

    **Be honest about the limit.** No test can know whether a well-formed row was observed;
    that is what the operator's name is for. What this can hold is that a row cannot be a
    half-pasted template — the `make restore-rehearsal` output ships a literal `<your name>`
    placeholder, and an unattributed or malformed row is the shape a fabricated one takes.
    The specific row the failed rehearsal printed is refused by name.
    """
    runbook = (ROOT / "docs" / "runbooks" / "restore-from-backup.md").read_text(encoding="utf-8")
    log = runbook[runbook.index("## Rehearsal log") :]

    rows = [
        line
        for line in log.splitlines()
        if line.startswith("|") and not re.match(r"^\|[\s|:-]*\|$", line) and "Date" not in line
    ]

    for row in rows:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        assert len(cells) == 5, (
            f"row has {len(cells)} cells, not Date/Archive/Duration/Outcome/By: {row}"
        )
        date, archive, duration, outcome, operator = cells
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", date), (
            f"`{date}` is not the UTC stamp `make restore-rehearsal` prints: {row}"
        )
        assert re.fullmatch(r"districore-\d{8}T\d{6}Z\.dump(\.gpg)?", archive), (
            f"`{archive}` is not an archive `ops/backup.sh` produces: {row}"
        )
        assert re.fullmatch(r"\d+s", duration), (
            f"B-3 asks for a duration; `{duration}` is not one: {row}"
        )
        assert outcome in {"PASS", "FAIL"}, f"`{outcome}` is neither PASS nor FAIL: {row}"
        assert operator and operator != "<your name>", (
            "the row is unattributed — that is the `make restore-rehearsal` placeholder, "
            f"pasted without anyone claiming the run: {row}"
        )

    for row in rows:
        assert not all(part in row for part in FABRICATED_ROW), (
            f"this is the row the FAILED 2026-09-07 rehearsal printed: {row}. It died on "
            "POSTGRES_PASSWORD before PostgreSQL was reached and must never be recorded."
        )


def test_a_rehearsal_archive_cannot_be_committed():
    """**The artefact the rehearsal itself creates** (NFR-SEC-007, B-2).

    The procedure writes a full encrypted database dump into the working tree. `.gitignore`
    carried `/backups/` and `*.dump` — and the archive is `.backups/…dump.gpg`, matched by
    neither: wrong directory, and `*.dump` does not match `*.dump.gpg`. A whole customer
    database sat one `git add -A` from source control.

    **Encryption is not a reason to relax this.** NFR-SEC-007 is about what is committed, and
    S-07's passphrase lives in a password manager that a clone does not carry — but neither
    does a repository stay private for ever.
    """
    rules = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert rules, ".gitignore is empty — this check would be vacuous"

    for pattern in ("*.dump", "*.dump.gpg", ".backups/"):
        assert pattern in rules, f"`{pattern}` is not ignored; a rehearsal archive is committable"
