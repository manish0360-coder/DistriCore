"""**The production stack must be wrong loudly, or not at all** (`00` §10.1, §14, FD-13).

`config/settings/prod.py` already refuses to start on five unsafe settings. The gaps M11.1
found were the ones *outside* Django, where nothing asserted anything:

1. **Caddy had no domain.** `docker/Caddyfile` is parameterised `{$DISTRICORE_DOMAIN:…}`
   and `compose.dev.yml` sets it, noting that *"production supplies the real domain"*.
   `compose.prod.yml` never did. Unset, Caddy fell back to `localhost`, chose its internal
   issuer and served a certificate no browser trusts — for a domain that had been bought
   and pointed at the host. **Nothing failed**; TLS was simply wrong.
2. **Nothing ran the nightly backup.** `ops/backup.sh` has existed since P0 and is invoked
   by hand in three runbooks. FD-16 requires it *nightly*; `00` §13.1 alerts when none has
   completed in 26 hours; `/healthz` reports the stamp's age. A fresh host had no backups,
   `/healthz` said `backup.ok: false` for ever, and B-1 could not begin.
3. **`ops/backup.sh` loaded the prod overlay it does not need**, which coupled the backup to
   every variable that overlay interpolates. The moment `DISTRICORE_DOMAIN` became required,
   a missing certificate name would have stopped the backups — the B-3 defect exactly: a
   compose file loaded for no reason, taking the script down with it.

Read from the mounted repository, because that is where a deployment gets quietly
misconfigured — the same reasoning `test_restore_rehearsal` uses for a fabricated PASS.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.adversarial

ROOT = Path(__file__).resolve().parents[3]

PROD_COMPOSE = ROOT / "docker" / "compose.prod.yml"
CADDYFILE = ROOT / "docker" / "Caddyfile"
ENV_EXAMPLE = ROOT / ".env.example"
BACKUP = ROOT / "ops" / "backup.sh"
TIMER = ROOT / "ops" / "districore-backup.timer"
SERVICE = ROOT / "ops" / "districore-backup.service"
DEPLOY = ROOT / "docs" / "runbooks" / "deploy.md"
RUNBOOKS = ROOT / "docs" / "runbooks" / "README.md"
MAKEFILE = ROOT / "Makefile"
BOOTSTRAP = (
    ROOT / "backend" / "identity" / "management" / "commands" / "bootstrap_owner.py"
)

#: Read from outside `backend/`; they arrive by bind-mount (`docker/compose.dev.yml`).
REQUIRED_PATHS = (
    "docker/compose.prod.yml",
    "docker/Caddyfile",
    ".env.example",
    "ops/backup.sh",
    "ops/districore-backup.timer",
    "ops/districore-backup.service",
    "docs/runbooks/deploy.md",
    "docs/runbooks/README.md",
    "docs/runbooks/first-owner.md",
    "Makefile",
    "backend/identity/management/commands/bootstrap_owner.py",
)

#: Operator commands an administrator runs on the **production** host. `exec` attaches to a
#: running container, so neither overlay belongs in them — see `DCBASE` in the Makefile.
OPERATOR_TARGETS = ("owner", "superuser", "logs")
#: And the two that shell out to `ops/*.sh`, which require the backup environment.
REHEARSAL_TARGETS = ("pitr-rehearsal", "restore-rehearsal")


def test_every_path_this_suite_reads_is_visible_from_inside_the_container():
    """Fail on the plumbing *as* plumbing, before any contract is evaluated."""
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    assert not missing, (
        f"not visible at {ROOT}: {missing}. These arrive by bind-mount — add them to the "
        "`app` service volumes in `docker/compose.dev.yml`."
    )


# ------------------------------------------------------------ the certificate identity
def test_production_gives_caddy_a_domain_and_refuses_to_start_without_one():
    """**The gap that would have shipped an untrusted certificate.**

    `:?` rather than a default, for the reason `POSTGRES_PASSWORD` carries one: the value
    cannot be guessed, and a wrong guess is worse than a refusal. A default here is what
    produced `localhost` in the first place.
    """
    compose = PROD_COMPOSE.read_text(encoding="utf-8")
    caddy = re.search(r"\n  caddy:\n(?P<body>(?:    .*\n|\n)*)", compose)
    assert caddy, "the `caddy` service is gone from the production overlay"

    body = caddy.group("body")
    assert "DISTRICORE_DOMAIN" in body, (
        "the production Caddy has no `DISTRICORE_DOMAIN`. The Caddyfile falls back to "
        "`localhost` and serves an internally-issued certificate for whatever domain you "
        "bought — wrong, and silent."
    )
    assert re.search(r"DISTRICORE_DOMAIN:\s*\$\{DISTRICORE_DOMAIN:\?", body), (
        "`DISTRICORE_DOMAIN` has a default or is passed through unchecked. Production must "
        "refuse to start without it, the way `POSTGRES_PASSWORD` does."
    )


def test_the_caddyfile_still_reads_the_variable_production_supplies():
    """Anti-vacuity: the contract above is worth nothing if the Caddyfile stopped using it."""
    assert "$DISTRICORE_DOMAIN" in CADDYFILE.read_text(encoding="utf-8"), (
        "the Caddyfile no longer reads `DISTRICORE_DOMAIN`, so supplying it proves nothing"
    )


def test_the_domain_is_documented_where_an_operator_will_look():
    """`00` §9.1: *every variable the application reads appears* in `.env.example`.

    A required variable absent from the example file is a deploy that fails at the one
    moment nobody wants to be reading source — and it was absent.
    """
    example = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert re.search(r"^DISTRICORE_DOMAIN=", example, re.MULTILINE), (
        "`DISTRICORE_DOMAIN` is not in `.env.example`, so the operator has nowhere "
        "documented to set the one variable production refuses to start without"
    )
    assert "DISTRICORE_ALLOWED_HOSTS" in example and "DISTRICORE_CSRF_TRUSTED_ORIGINS" in example


# --------------------------------------------------------------- the nightly backup
def test_the_nightly_backup_is_actually_scheduled():
    """FD-16 says **nightly**; nothing ran it.

    `00` §13.1's third alert and `/healthz`'s `backup` check both read a stamp that only
    `ops/backup.sh` writes. Without a scheduler they describe a producer that never runs —
    *"the most under-monitored failure in small systems"*, monitored and unproduced.
    """
    timer = TIMER.read_text(encoding="utf-8")
    assert "OnCalendar=" in timer, "the backup timer has no schedule"
    assert "districore-backup.service" in timer, "the timer does not name its service"
    assert "Persistent=true" in timer, (
        "a host that was off at the scheduled time must back up when it returns, rather "
        "than skipping a night silently"
    )

    service = SERVICE.read_text(encoding="utf-8")
    assert "ops/backup.sh" in service, "the backup unit does not run `ops/backup.sh`"
    assert "Type=oneshot" in service
    assert "EnvironmentFile=" in service, (
        "the unit supplies no environment, so S-07's passphrase would be absent and the "
        "dump would be written in clear (B-2)"
    )


def test_the_deploy_runbook_installs_the_timer_and_the_monitor():
    """A unit file nobody installs is a unit file that does not run (B-4)."""
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert "districore-backup.timer" in deploy, "the runbook never installs the backup timer"
    assert "systemctl enable" in deploy, "the runbook never enables it"
    assert "/healthz" in deploy and re.search(r"A-08|uptime monitor", deploy), (
        "the runbook does not point the uptime monitor at `/healthz`, so nothing turns "
        "three of `00` §13.1's four alerts into an email"
    )
    assert "DISTRICORE_DOMAIN" in deploy, "the runbook does not tell the operator to set it"


def test_the_backup_does_not_depend_on_the_production_overlay():
    """**The B-3 defect, prevented rather than repeated.**

    `backup.sh` only needs `db`, which the base compose file defines; `exec` attaches to a
    running container and never consults the overlay's `ports: []`. Loading the overlay made
    the backup depend on every variable it interpolates — so once `DISTRICORE_DOMAIN` became
    required, a missing certificate name would have silently stopped the nightly dump.
    """
    source = BACKUP.read_text(encoding="utf-8")

    # **Comments stripped first**, the lesson `test_mobile_boundary` records: this file
    # *explains* why it no longer loads the overlay, and a plain substring search read that
    # explanation as the thing it forbids. A contract that cannot tell code from prose holds
    # "nobody wrote the word" — satisfied by deleting the comment.
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))

    assert "compose.prod.yml" not in code, (
        "`ops/backup.sh` loads the production overlay again. It does not need it, and doing "
        "so couples the backup to variables that have nothing to do with taking one."
    )
    assert "--env-file .env" in code, (
        "the compose call lost its explicit env file — the original B-3 failure"
    )
    assert "compose.yml" in code, "the backup no longer names a compose file at all"


def test_the_comment_stripper_actually_strips():
    """Anti-vacuity for the contract above, and it is not hypothetical.

    The first run of that test failed on `backup.sh`'s own explanation of why the overlay is
    gone. If this helper ever stopped removing comments, the contract would start passing
    for the wrong reason — or failing for one.
    """
    stripped = "\n".join(
        line
        for line in "# compose.prod.yml\ndocker compose -f docker/compose.yml\n".splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "compose.prod.yml" not in stripped
    assert "docker/compose.yml" in stripped


# ─────────────────────────────────── M11.5: the documented path must be executable
#
# M11.1 found a backup script nothing scheduled. M11.3 found an A-05 nothing provisioned.
# This is the same shape a third time: mechanisms that are correct and that the documented
# procedure could not actually invoke on a fresh host.


def _recipe(target: str) -> str:
    """A Make target's recipe — the tab-indented lines and their continuations."""
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(target)}:.*?\n((?:\t.*\n|\n)*)", text, re.MULTILINE)
    assert match, f"Make target `{target}` is gone"
    return match.group(1)


def test_the_deploy_runbook_bootstraps_an_owner_before_the_rehearsals():
    """**A fresh database has no users, and nothing said so.**

    Before M11.5 `deploy.md` never created one. The smoke test asks the operator to sign in
    and `ops/restore-pitr.sh` reports `max(audit_log.occurred_at)` as its evidence — so with
    no owner there is nobody to sign in as, no audit row to recover, and **NFR-AVA-001
    cannot be measured at all**.
    """
    deploy = DEPLOY.read_text(encoding="utf-8")
    # **The command, not the prose.** The first draft searched for `make owner`, which the
    # step's own explanatory sentence satisfies — so a mutation that moved the actual
    # command after the rehearsals passed. `PHONE=` is the invocation and nothing else.
    assert "make owner PHONE=" in deploy, "the deploy runbook never bootstraps an owner"
    assert "first-owner.md" in deploy, "it does not point at the runbook that explains this"

    owner_at = deploy.find("make owner PHONE=")
    rehearse_at = deploy.find("Rehearse both recoveries")
    assert owner_at < rehearse_at, (
        "the owner is bootstrapped after the rehearsals. The PITR rehearsal recovers "
        "`audit_log` rows that only a login produces."
    )
    assert "changepassword" in deploy, (
        "no recovery path for an owner created without a usable password — the exact "
        "outcome a blank prompt produces, and Django's own command is the fix"
    )


def test_the_deploy_runbook_says_the_password_is_required_when_creating_the_owner():
    """The defect that produced a locked-out owner in development, documented.

    A blank password reaches `UserManager._create` with `password=None`, which calls
    `set_unusable_password()`. Correct for retailers, who authenticate by OTP (`04` T-01);
    for an owner it is an account that holds the role, is audited, and can never sign in.
    """
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert "set_unusable_password" in deploy, (
        "the runbook does not warn that a blank password produces an unusable account"
    )


def test_the_bootstrap_prompt_no_longer_reads_as_optional_on_first_boot():
    """Wording only, and it is the whole defect.

    The prompt is issued *before* the service runs, so it cannot know whether the user
    exists — it must describe both cases. It read "leave blank if the user exists", which is
    sound for recovery and misleading on first boot, the path every new installation takes.
    """
    source = BOOTSTRAP.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    prompt = re.search(r'getpass\.getpass\(\s*(?:"|\n\s*")(.*?)"\s*\)', code, re.S)
    assert prompt, "the interactive password prompt is gone"
    text = prompt.group(1)
    assert "REQUIRED" in text, (
        f"the prompt does not say a password is required for a new user: {text!r}"
    )
    assert not re.search(r"^Password \(leave blank if the user exists", text), (
        "the misleading wording is back"
    )


@pytest.mark.parametrize("target", OPERATOR_TARGETS)
def test_operator_targets_load_neither_compose_overlay(target: str):
    """**The M11.2 ruling, applied to the Makefile.**

    `ops/backup.sh` records it: *"the prod overlay is not loaded, deliberately … loading it
    made this script depend on every variable the overlay interpolates, including
    `DISTRICORE_DOMAIN`"* — the B-3 defect. `exec` attaches to a running container and the
    project name is fixed by `name: districore`, so an overlay adds nothing.

    `$(DC)` would load the **dev** overlay on the production host; `$(DCPROD)` would couple
    an operator command to a certificate name and break the same command in development,
    where `DISTRICORE_DOMAIN` is empty and `:?` fires. `$(DCBASE)` is neither.
    """
    recipe = _recipe(target)
    assert "$(DCBASE)" in recipe, f"`make {target}` does not use the base compose file"
    for wrong in ("$(DC)", "$(DCPROD)", "compose.dev.yml", "compose.prod.yml"):
        assert wrong not in recipe, (
            f"`make {target}` loads `{wrong}`. An operator runs this on the production "
            "host; neither overlay belongs in a command that only execs."
        )


def test_the_base_compose_variable_really_loads_only_the_base_file():
    """Anti-vacuity: `DCBASE` could be defined as anything."""
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^DCBASE\s*:=\s*(.+)$", text, re.MULTILINE)
    assert match, "`DCBASE` is no longer defined"
    definition = match.group(1)
    assert "-f docker/compose.yml" in definition
    assert "--env-file .env" in definition
    assert "compose.dev.yml" not in definition and "compose.prod.yml" not in definition, (
        f"`DCBASE` loads an overlay: {definition}"
    )


@pytest.mark.parametrize("target", REHEARSAL_TARGETS)
def test_rehearsal_targets_supply_the_backup_environment(target: str):
    """The documented recovery command exited before it began.

    `ops/restore-pitr.sh` and `ops/restore.sh` require `DISTRICORE_BACKUP_PASSPHRASE` and
    `DISTRICORE_BACKUP_REMOTE` and refuse without them. The systemd units get those from
    `EnvironmentFile=`; a manual `make` invocation had no equivalent — so
    `restore-from-backup.md`'s `make pitr-rehearsal` died immediately on a production host.

    `.env` relative to the repository root is the same file the units name absolutely: they
    set `WorkingDirectory=/opt/districore`, so `/opt/districore/.env` **is** this `.env`.
    """
    recipe = _recipe(target)
    assert ". ./.env" in recipe, f"`make {target}` does not source the environment"
    assert "set -a" in recipe, (
        f"`make {target}` sources `.env` without exporting it, so the child script sees "
        "nothing"
    )

    text = MAKEFILE.read_text(encoding="utf-8")
    assert re.search(rf"^{re.escape(target)}: \.env", text, re.MULTILINE), (
        f"`{target}` does not require `.env`, so a missing file fails inside the script "
        "rather than at the one line that explains how to create it"
    )


@pytest.mark.parametrize("target", REHEARSAL_TARGETS)
def test_sourcing_the_environment_did_not_weaken_the_scripts_own_guards(target: str):
    """Fail-closed stays in the script, by name. Sourcing supplies; it does not excuse."""
    script = "restore-pitr.sh" if target == "pitr-rehearsal" else "restore.sh"
    source = (ROOT / "ops" / script).read_text(encoding="utf-8")
    assert re.search(r'\$\{DISTRICORE_BACKUP_PASSPHRASE:\?', source), (
        f"`ops/{script}` no longer refuses without the passphrase"
    )
    assert "set -euo pipefail" in source


def test_the_first_owner_runbook_is_reachable_from_the_index():
    """A runbook nobody can find is a runbook nobody runs (B-4).

    It existed, complete and correct, and was absent from the index — which is why the
    locked-out-owner case was diagnosed from source rather than from the document written
    for it.
    """
    assert "first-owner" in RUNBOOKS.read_text(encoding="utf-8"), (
        "`first-owner.md` is not listed in `docs/runbooks/README.md`"
    )
