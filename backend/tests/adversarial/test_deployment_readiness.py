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

#: Read from outside `backend/`; they arrive by bind-mount (`docker/compose.dev.yml`).
REQUIRED_PATHS = (
    "docker/compose.prod.yml",
    "docker/Caddyfile",
    ".env.example",
    "ops/backup.sh",
    "ops/districore-backup.timer",
    "ops/districore-backup.service",
    "docs/runbooks/deploy.md",
)


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
