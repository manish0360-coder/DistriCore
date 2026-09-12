"""**NFR-AVA-001 is an arithmetic claim spread across four files** (`02` §21.6, `00` §14).

> *"RPO ≤ 15 minutes; RTO ≤ 4 hours (DR-5)."*

Fifteen minutes is not delivered by a setting. It is delivered by a chain — PostgreSQL
closing a WAL segment within `archive_timeout`, the host encrypting and shipping it within
one timer period, and a base backup to replay it into — and the requirement holds only while
those numbers still add up to less than 900 seconds. They live in `docker/compose.yml`,
`ops/districore-wal-ship.timer` and `.env.example`, which is three places and one fact.

So these contracts are not "is WAL archiving configured". They are:

1. **Does the arithmetic still close?** Raising `archive_timeout` to an hour is a one-line
   change that silently converts a met requirement into an unmet one, and nothing else in
   the repository would notice.
2. **Can success be reported for a backup that is not offsite?** That was C-5: `backup.sh`
   warned about a missing passphrase and stamped success anyway, so `/healthz` reported a
   healthy backup for an unencrypted, host-only dump.
3. **Can the recovery chain be pruned from both ends?** WAL retention belongs to whichever
   schedule knows where the oldest retained base backup starts. Two schedules pruning by
   their own clocks is how a recovery discovers, months later, that the archive begins after
   the base.

Read from the mounted repository, because that is where a recovery posture gets quietly
dismantled — the same reasoning `test_deployment_readiness` and `test_restore_rehearsal` use.
Never `git ls-files`: the backend image contains no git (`M10_Security_Review`
§NFR-SEC-007).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.adversarial

ROOT = Path(__file__).resolve().parents[3]

COMPOSE = ROOT / "docker" / "compose.yml"
WAL_TIMER = ROOT / "ops" / "districore-wal-ship.timer"
WAL_SERVICE = ROOT / "ops" / "districore-wal-ship.service"
BASE_TIMER = ROOT / "ops" / "districore-basebackup.timer"
BASE_SERVICE = ROOT / "ops" / "districore-basebackup.service"
SHIP = ROOT / "ops" / "ship-wal.sh"
BASEBACKUP = ROOT / "ops" / "basebackup.sh"
BACKUP = ROOT / "ops" / "backup.sh"
PITR = ROOT / "ops" / "restore-pitr.sh"
ENV_EXAMPLE = ROOT / ".env.example"
SETTINGS = ROOT / "backend" / "config" / "settings"
HEALTH = ROOT / "backend" / "core" / "health.py"
REPORT = ROOT / "docs" / "M11.2_Recovery_Report.md"
RESTORE_RUNBOOK = ROOT / "docs" / "runbooks" / "restore-from-backup.md"
DEPLOY = ROOT / "docs" / "runbooks" / "deploy.md"
MAKEFILE = ROOT / "Makefile"

#: Read from outside `backend/`; they arrive by bind-mount (`docker/compose.dev.yml`).
REQUIRED_PATHS = (
    "docker/compose.yml",
    "ops/districore-wal-ship.timer",
    "ops/districore-wal-ship.service",
    "ops/districore-basebackup.timer",
    "ops/districore-basebackup.service",
    "ops/ship-wal.sh",
    "ops/basebackup.sh",
    "ops/backup.sh",
    "ops/restore-pitr.sh",
    ".env.example",
    "docs/M11.2_Recovery_Report.md",
    "docs/runbooks/restore-from-backup.md",
    "docs/runbooks/deploy.md",
    "Makefile",
)

#: `02` §21.6, in seconds. The requirement, not a preference.
RPO_TARGET_SECONDS = 900

#: Allowance for uploading one 16 MB segment. Deliberately generous: the contract should
#: fail when the *design* stops closing, not when a network is slow.
UPLOAD_ALLOWANCE_SECONDS = 60


def test_every_path_this_suite_reads_is_visible_from_inside_the_container():
    """Fail on the plumbing *as* plumbing, before any contract is evaluated."""
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    assert not missing, (
        f"not visible at {ROOT}: {missing}. These arrive by bind-mount — add them to the "
        "`app` service volumes in `docker/compose.dev.yml`."
    )


def _strip_comments(source: str, marker: str = "#") -> str:
    """Comment lines removed, for the reason `test_deployment_readiness` records.

    Every file in this milestone *explains* the failure it prevents, and a plain substring
    search reads that explanation as the thing it forbids. A contract that cannot tell code
    from prose holds "nobody wrote the word", which is satisfied by deleting the comment.
    """
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith(marker)
    )


def test_the_comment_stripper_actually_strips():
    """Anti-vacuity for every contract below that uses it."""
    stripped = _strip_comments("# rclone delete everything\nrclone copy a b\n")
    assert "delete" not in stripped
    assert "rclone copy a b" in stripped


# ------------------------------------------------------- 1. the arithmetic must still close
def _archive_timeout() -> int:
    match = re.search(r"archive_timeout=(\d+)", COMPOSE.read_text(encoding="utf-8"))
    assert match, "`archive_timeout` is gone from the db service — WAL may never be archived"
    return int(match.group(1))


def _wal_ship_period_seconds() -> int:
    timer = WAL_TIMER.read_text(encoding="utf-8")
    match = re.search(r"OnUnitActiveSec=(\d+)(min|sec|s|m)\b", timer)
    assert match, "the WAL shipping timer has no `OnUnitActiveSec` — it would run once and stop"
    value = int(match.group(1))
    return value * 60 if match.group(2) in {"min", "m"} else value


def test_the_rpo_budget_still_adds_up_to_less_than_the_requirement():
    """**The contract this whole suite exists for.**

    `archive_timeout` bounds how long a committed row waits for its segment to close; the
    timer period bounds how long that segment then waits to be shipped. Their sum, plus an
    upload, is the worst-case offsite lag — which is what RPO means.

    Neither number is meaningful alone, and either can be changed in one line by someone
    reasonably trying to reduce write amplification or network chatter. Without this test the
    requirement would go from met to unmet with nothing failing.
    """
    archive_timeout = _archive_timeout()
    period = _wal_ship_period_seconds()
    worst_case = archive_timeout + period + UPLOAD_ALLOWANCE_SECONDS

    assert worst_case <= RPO_TARGET_SECONDS, (
        f"worst-case offsite lag is {worst_case}s (archive_timeout {archive_timeout}s + "
        f"shipping period {period}s + {UPLOAD_ALLOWANCE_SECONDS}s upload) against "
        f"NFR-AVA-001's {RPO_TARGET_SECONDS}s. `02` §21.6 is not a preference — lower one "
        "of the two, or the requirement is no longer met."
    )


def test_the_requirement_is_stated_where_the_endpoint_can_report_it():
    """`/healthz` must measure against the requirement, not an invisible threshold.

    A health check whose threshold nobody can find is a health check nobody can argue with.
    """
    defaults = (SETTINGS / "base.py").read_text(encoding="utf-8")
    match = re.search(r'RPO_TARGET_SECONDS\s*=\s*env\.int\([^)]*default=(\d+)', defaults)
    assert match, "`RPO_TARGET_SECONDS` is no longer read from settings"
    assert int(match.group(1)) == RPO_TARGET_SECONDS, (
        f"the RPO target default is {match.group(1)}s, not NFR-AVA-001's "
        f"{RPO_TARGET_SECONDS}s. Changing this changes what `/healthz` claims compliance "
        "with, which is not an engineering decision to make in a settings file."
    )
    assert "rpo_target_seconds" in HEALTH.read_text(encoding="utf-8"), (
        "`/healthz` no longer reports the target it is measuring the lag against"
    )


# ------------------------------------------------- 2. the archiver must never block the server
def test_postgres_archives_continuously_to_the_separate_volume():
    """FD-16's continuous layer: *"WAL archiving — continuous — separate local volume."*"""
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "archive_mode=on" in compose, "archiving is off — there is no continuous layer"
    assert "wal_level=replica" in compose, (
        "`wal_level` is unpinned; a future `minimal` would break archiving silently"
    )
    assert re.search(r"^\s+wal_archive:\s*$", compose, re.MULTILINE), (
        "the `wal_archive` volume is gone. FD-16 says a *separate* local volume — a chain "
        "kept inside `db_data` is a second copy in the same place"
    )
    assert "wal_archive:/srv/wal_archive" in compose, "the archive volume is not mounted into db"


def test_the_archive_command_cannot_block_on_the_network_or_a_missing_tool():
    """**Why encryption and transport are not in `archive_command`.**

    It runs inside the PostgreSQL server's shell. A `gpg` or `rclone` there would be a
    missing binary in this image, and a network upload would let an unreachable A-05 stall
    WAL recycling until `pg_wal` fills and writes stop. The split is the same one
    `ops/backup.sh` uses: PostgreSQL writes locally, the host encrypts and ships.
    """
    match = re.search(r"archive_command=(?P<cmd>.*)", COMPOSE.read_text(encoding="utf-8"))
    assert match, "`archive_command` is gone while `archive_mode` may still be on"
    command = match.group("cmd")

    for forbidden in ("rclone", "gpg", "curl", "ssh", "aws"):
        assert forbidden not in command, (
            f"`archive_command` runs `{forbidden}`. It executes inside the database server: "
            "a slow or failing network call there stalls WAL recycling and eventually stops "
            "PostgreSQL accepting writes."
        )
    assert "/srv/wal_archive/" in command, "the archive command does not write to the volume"
    assert "test -f" in command, (
        "re-archiving an already-archived segment must succeed. A bare `cp` recipe fails "
        "there and PostgreSQL retries the same segment for ever."
    )
    assert ".part" in command, (
        "segments must be copied to a temporary name and renamed, so that a file under its "
        "final name is always complete — the shipper treats 'present' as 'shippable'"
    )


def test_the_archive_directory_is_created_and_owned_before_postgres_starts():
    """Anti-vacuity, and it is the failure I could not test without Docker.

    A fresh named volume mounted at a path the image does not define is created root-owned,
    while `archive_command` runs as the `postgres` server user. Without this wrapper every
    segment fails with EACCES, `pg_wal` grows without bound, and the first symptom is a full
    disk. Deleting the wrapper would leave every other contract here passing.
    """
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "mkdir -p /srv/wal_archive" in compose, (
        "nothing creates the archive directory before PostgreSQL starts"
    )
    assert "chown postgres:postgres /srv/wal_archive" in compose, (
        "the archive directory is not given to the `postgres` user, so `archive_command` "
        "cannot write to it"
    )
    assert "exec docker-entrypoint.sh" in compose, (
        "the wrapper no longer hands over to the image's entrypoint, so first-init, the "
        "password setup and the gosu drop to `postgres` would all be skipped"
    )


# --------------------------------------------------- 3. nothing may report an unproven success
STAMP_WRITERS = {
    "ops/backup.sh": BACKUP,
    "ops/ship-wal.sh": SHIP,
    "ops/basebackup.sh": BASEBACKUP,
}


@pytest.mark.parametrize("name", sorted(STAMP_WRITERS))
def test_every_backup_script_refuses_to_run_without_encryption_and_a_remote(name: str):
    """**C-5, as a contract instead of a warning.**

    `backup.sh` used to print *"WARNING: no passphrase set"* to stderr and then write the
    success stamp regardless, so `/healthz` reported a healthy backup for a dump lying in
    clear on the machine it was taken from — B-2 and B-7 both violated, invisibly.

    `:?` rather than a conditional, for the reason `POSTGRES_PASSWORD` carries one: an
    absent value cannot be guessed, and a wrong guess is worse than a refusal.
    """
    code = _strip_comments(STAMP_WRITERS[name].read_text(encoding="utf-8"))
    for variable in ("DISTRICORE_BACKUP_PASSPHRASE", "DISTRICORE_BACKUP_REMOTE"):
        assert re.search(rf'"\$\{{{variable}:\?', code), (
            f"{name} does not fail closed on {variable}. Unencrypted data must not leave "
            "the host (B-2) and a backup that never leaves it does not survive losing it "
            "(B-7) — a warning is not a control."
        )


@pytest.mark.parametrize("name", sorted(STAMP_WRITERS))
def test_no_script_writes_its_success_stamp_before_proving_the_remote_has_the_data(name: str):
    """Ordering, because *when* the stamp is written is the whole of its meaning.

    `rclone` exiting zero is not the claim. The claim is that the artefact can be retrieved
    from A-05, so each script lists the remote back and checks the name it just uploaded —
    and the stamp must come after that, not before.
    """
    code = _strip_comments(STAMP_WRITERS[name].read_text(encoding="utf-8"))

    # `\b` matters: the first draft of this contract used a plain substring search, and a
    # mutation that renamed the call to `rclone lsf_DISABLED` passed it. A contract that
    # accepts a prefix of the thing it requires is checking spelling, not behaviour.
    verify = re.search(r"\brclone lsf\b", code)
    verify_at = verify.start() if verify else -1
    stamp_at = code.find("cat > '$STAMP'")
    assert verify_at != -1, (
        f"{name} never lists the remote back. An upload that exited zero is not proof the "
        "data is retrievable, which is the only thing the stamp is allowed to mean."
    )
    assert stamp_at != -1, f"{name} no longer writes a success stamp through the container"
    assert verify_at < stamp_at, (
        f"{name} writes its success stamp before verifying the remote. That is the C-5 "
        "shape exactly: a green `/healthz` for data that may not be offsite."
    )


@pytest.mark.parametrize("name", sorted(STAMP_WRITERS))
def test_the_success_stamp_is_written_where_healthz_can_actually_read_it(name: str):
    """The disconnection that made every other guarantee here unobservable.

    `/healthz` runs in the `app` container and reads these stamps from the `backup_data`
    volume. The scripts run on the host and wrote the same *paths* on the host's own
    filesystem — so the endpoint could never see a stamp, `backup.ok` was false on a
    correctly backed-up host, and the §13.1 alert would have been permanent noise. A monitor
    that cannot go green is a monitor that gets muted.
    """
    code = _strip_comments(STAMP_WRITERS[name].read_text(encoding="utf-8"))
    assert re.search(r"exec -T app sh -c .*cat > '\$STAMP'", code), (
        f"{name} does not write its stamp inside the app container. A host path at the same "
        "location is a different filesystem, and `/healthz` reads the volume."
    )


def test_the_nightly_backup_no_longer_ships_media_in_clear_from_a_host_path():
    """Two faults in one line, and `set -e` made the second one fatal every night.

    `rclone sync /srv/media <remote>/media` named a path inside the `app` container, which
    does not exist on the host — so with a remote configured the run died there, after the
    dump had shipped and before any stamp. And a sync ships proof-of-delivery photographs to
    A-05 **unencrypted**, which B-2 forbids.
    """
    code = _strip_comments(BACKUP.read_text(encoding="utf-8"))
    assert "rclone sync /srv/media" not in code, (
        "media is synced from a host path that does not exist, and in clear (B-2)"
    )
    media = re.search(r"exec -T app tar -C /srv -cf - media.*?rclone rcat", code, re.DOTALL)
    assert media, (
        "media is no longer read out of the `media_data` volume and piped through gpg. "
        "Whatever replaced it must still encrypt before leaving the host (B-2)."
    )


# ---------------------------------------------- 4. the chain may be pruned from one end only
def test_wal_retention_belongs_to_the_base_backup_and_nowhere_else():
    """**The pruning rule that silently destroys recoverability if it is split.**

    A WAL segment stops being needed only when no retained base backup needs it.
    `ops/basebackup.sh` is the only schedule that knows where the oldest retained chain
    starts, so it owns remote WAL retention. If the five-minute shipper also pruned, the two
    clocks would disagree and a recovery would discover — months later, during an outage —
    that the archive begins after the base backup it must be replayed into.
    """
    ship = _strip_comments(SHIP.read_text(encoding="utf-8"))
    assert not re.search(r"rclone\s+(delete|deletefile|purge)", ship), (
        "`ops/ship-wal.sh` deletes from the remote. Remote WAL retention is "
        "`ops/basebackup.sh`'s, derived from the oldest base backup it keeps."
    )

    base = _strip_comments(BASEBACKUP.read_text(encoding="utf-8"))
    assert "--min-age" in base and "REMOTE_WAL" in base, (
        "`ops/basebackup.sh` no longer prunes WAL against its own retention, so the archive "
        "grows without bound or is pruned by something that does not know where the chain "
        "starts"
    )
    assert "-X fetch" in base, (
        "the base backup no longer embeds the WAL it needs to reach consistency, which is "
        "what makes pruning everything older than it safe"
    )


def test_the_local_archive_is_only_pruned_after_the_remote_is_verified():
    """Deleting an unshipped segment breaks the chain permanently and silently."""
    code = _strip_comments(SHIP.read_text(encoding="utf-8"))
    verify_at = code.find("missing=")
    prune_at = code.find("-delete")
    assert verify_at != -1 and prune_at != -1, (
        "`ops/ship-wal.sh` no longer both verifies the remote and prunes locally"
    )
    assert verify_at < prune_at, (
        "local segments are pruned before the remote is proven to hold them. A segment that "
        "exists in neither place is a hole in the recovery chain."
    )


# --------------------------------------------------- 5. the rehearsal must prove the chain
def test_the_pitr_rehearsal_recovers_from_the_offsite_copy_and_waits_for_real_recovery():
    """`restore-rehearsal` cannot discharge NFR-AVA-001, and this must not become it.

    Two correctness points that are easy to get wrong and impossible to notice:
    `pg_isready` succeeds *during* replay because hot standby accepts connections, so a
    query answered then reports an earlier recovery point than the one achieved. And a
    rehearsal that reads the local archive proves nothing about A-05, which is the copy that
    exists after the host is gone.
    """
    code = _strip_comments(PITR.read_text(encoding="utf-8"))
    assert "pg_is_in_recovery" in code, (
        "the rehearsal does not wait for recovery to finish. `pg_isready` is true during "
        "replay, so the evidence would understate what was recovered."
    )
    assert "recovery_target_time" in code and "restore_command" in code, (
        "the rehearsal does not configure point-in-time recovery, so it is a base restore "
        "with extra steps"
    )
    assert "rclone cat" in code, (
        "the rehearsal no longer reads the offsite archive. Recovering from the local volume "
        "proves nothing about the case NFR-AVA-001 exists for."
    )
    assert "mktemp -d" in code, (
        "the scratch cluster location is not generated. The one mistake in this procedure "
        "that cannot be undone is recovering over production."
    )
    assert "max(occurred_at) FROM audit_log" in code, (
        "the rehearsal reports no achieved recovery point. Row counts prove a restore "
        "happened; RPO is about how much was kept."
    )


def test_the_pitr_rehearsal_is_a_make_target_and_the_runbook_records_its_result():
    """`00` §5: an operation you must reconstruct the arguments for is not routine.

    B-3's log was empty for exactly this reason until `make restore-rehearsal` existed.
    """
    assert "pitr-rehearsal:" in MAKEFILE.read_text(encoding="utf-8"), (
        "there is no `make pitr-rehearsal`, so the only evidence for NFR-AVA-001 is a "
        "script somebody has to remember"
    )
    runbook = RESTORE_RUNBOOK.read_text(encoding="utf-8")
    assert "PITR rehearsal log" in runbook, (
        "the restore runbook has nowhere to record a PITR rehearsal, so NFR-AVA-002 "
        "(*'an untested backup does not satisfy this requirement'*) stays unmet for the "
        "continuous layer"
    )


# -------------------------------------------------------- 6. traceability and operability
def test_nfr_ava_001_is_traced_and_not_claimed_from_configuration():
    """`02` says NFR-AVA-001 is verified by rehearsal. Configuration is not evidence.

    Before M11.2 neither NFR-AVA-001 nor NFR-AVA-002 appeared anywhere in `backend/` or in
    any verification report — the requirement had no traceability at all. A report that
    recorded PASS because the settings look right would be worse than that silence.
    """
    report = REPORT.read_text(encoding="utf-8")
    assert "NFR-AVA-001" in report and "NFR-AVA-002" in report, (
        "the recovery report does not name the requirements it is evidence for"
    )
    assert "NOT MEASURED" in report, (
        "the report claims a verdict it has not measured. Until a PITR rehearsal has run "
        "against a real host, the honest verdict for NFR-AVA-001 is NOT MEASURED — the six "
        "verdict states exist so that 'not attempted' and 'attempted and passed' cannot be "
        "confused (M10.6a)."
    )
    assert not re.search(r"NFR-AVA-001[^\n]*\bPASS\b", report), (
        "NFR-AVA-001 is recorded as PASS. It is verified by rehearsal on a provisioned "
        "host (A-03/A-05), and neither exists yet."
    )


def test_the_deploy_runbook_installs_both_new_timers():
    """A unit file nobody installs is a unit file that does not run (B-4).

    This is the M11.1 finding repeated: `ops/backup.sh` existed from P0 and nothing ever
    scheduled it, so a fresh host had no backups at all.
    """
    deploy = DEPLOY.read_text(encoding="utf-8")
    for unit in ("districore-wal-ship.timer", "districore-basebackup.timer"):
        assert unit in deploy, f"the runbook never installs {unit}"
    assert "recovery_ready" in deploy, (
        "the runbook does not tell the operator what to confirm after installing them. "
        "`/healthz` reports one boolean for exactly this moment."
    )


def test_healthz_separates_local_backup_success_from_verified_offsite_readiness():
    """The distinction the endpoint exists to make.

    One `backup: ok` field cannot say whether last night's dump exists on this host or
    whether the business can be recovered to five minutes ago. Reporting the first while
    implying the second is what made C-5 dangerous rather than untidy.
    """
    health = HEALTH.read_text(encoding="utf-8")
    for check in ("_check_backup", "_check_wal_archive", "_check_wal_offsite", "_check_basebackup"):
        assert f"def {check}(" in health, f"`{check}` is gone — a failure mode is unreported"
    assert '"recovery_ready"' in health, (
        "`/healthz` no longer reports a single readiness boolean, so A-08 would need a "
        "fifth alert channel — `00` §13.1 permits four"
    )
    assert "pg_stat_archiver" in health, (
        "nothing asks PostgreSQL whether it is still archiving. A shipper stamp cannot "
        "detect a stalled archiver: 'everything local is offsite' is true of an archive "
        "that stopped growing an hour ago."
    )


def test_every_variable_the_application_reads_is_documented():
    """`00` §9.1: *"Every variable the application reads appears here"* — as a contract.

    M11.2 adds eight. Hand-listing them would police one instance of the defect;
    deriving the list from the settings modules retires the class. `DISTRICORE_DB_CONN_MAX_AGE`
    was already missing when this was written, which is how a general contract earns its
    keep over a specific one.
    """
    read_pattern = r'env\.\w+\(\s*"(DISTRICORE_[A-Z0-9_]+)"'
    read_by_app: set[str] = set()
    for module in sorted(SETTINGS.glob("*.py")):
        read_by_app |= set(re.findall(read_pattern, module.read_text(encoding="utf-8")))
    assert read_by_app, "no settings variables found — this contract would be vacuous"

    example = ENV_EXAMPLE.read_text(encoding="utf-8")
    documented = set(re.findall(r"^(DISTRICORE_[A-Z0-9_]+)=", example, re.MULTILINE))
    undocumented = sorted(read_by_app - documented)
    assert not undocumented, (
        f"read by the application and absent from `.env.example`: {undocumented}. An "
        "operator has nowhere documented to set them, which is a deploy that fails at the "
        "one moment nobody wants to be reading source."
    )
