"""``manage.py bootstrap_owner`` — FR-IAM-014's break-glass procedure.

**A third delivery surface, obeying the same rule as the other two.** `api` and `webadmin`
parse and delegate; so does this. Every rule — the refusal predicate, the FIRST_BOOT /
RECOVERY classification, the grant, the audit row — lives in ``identity.services`` (N-01).
Nothing here touches a model.

ADR-0003 sanctions this path explicitly: *"emergency data fixes go through service functions
or a documented `psql` runbook, both of which are the correct paths anyway."* This is the
first of those two, made repeatable — and it replaces a raw ``INSERT`` into ``user_role``
that wrote no audit row at all.

Usage::

    manage.py bootstrap_owner --phone 7903324153 --full-name "Mack"
    manage.py bootstrap_owner --phone 7903324153 --reason "laptop lost, owner locked out"

The password is never a command-line argument: it would land in shell history and in
``ps``. It comes from ``DISTRICORE_OWNER_PASSWORD`` or an interactive prompt, and is needed
only when the user does not already exist.
"""

from __future__ import annotations

import getpass
import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.exceptions import DomainError
from identity.services import BOOTSTRAP_FIRST_BOOT, bootstrap_owner

# S105: the name of an environment variable, not a password. The value never appears in
# source, in shell history or in `ps` — which is the whole reason it is read from the
# environment rather than taken as an argument.
PASSWORD_ENV = "DISTRICORE_OWNER_PASSWORD"  # noqa: S105


class Command(BaseCommand):
    help = (
        "Grant OWNER to the first user, or recover owner access when none is active. "
        "Refuses while any active owner exists. Every use is audited as OWNER_BOOTSTRAP."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--phone", required=True, help="Any spelling; it is normalised.")
        parser.add_argument(
            "--full-name", default="", help="Required only when creating a new user."
        )
        parser.add_argument(
            "--reason",
            default="",
            help="Optional. Recorded in the audit row; never required, so a lockout is "
            "never prolonged by a missing text field.",
        )
        parser.add_argument(
            "--noinput",
            action="store_true",
            help=f"Never prompt. The password then comes from ${PASSWORD_ENV}.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        password = os.environ.get(PASSWORD_ENV) or None
        if password is None and not options["noinput"]:
            # Only asked for when one is actually needed; an existing user keeps theirs.
            # **Wording only, and it is load-bearing (M11.5).** This read "leave blank if
            # the user exists", which is sound advice for recovery and actively misleading
            # on first boot — the more common path, and the one a new installation always
            # takes. The prompt is issued *before* the service is called, so it cannot know
            # which case it is in; it must therefore describe both.
            #
            # A blank on first boot reaches `UserManager._create` with `password=None`,
            # which takes the `set_unusable_password()` branch. That branch is correct —
            # retailers authenticate by OTP and a placeholder hash would be a lie in the
            # data (`04` T-01) — but for a new *owner* it produces an account that holds
            # OWNER, is audited, and can never sign in. The only symptom is "Incorrect
            # phone number or password", which is true and tells the operator nothing.
            #
            # Nothing below this line changed: not the manager, the service, the hashing,
            # the models, the permissions or the command's semantics.
            password = (
                getpass.getpass(
                    "Password — REQUIRED for a new user, leave blank only if this "
                    "number already has one: "
                )
                or None
            )

        try:
            result = bootstrap_owner(
                phone=options["phone"],
                full_name=options["full_name"],
                password=password,
                reason=options["reason"],
            )
        except DomainError as exc:
            # A domain refusal is an expected outcome, not a traceback. CommandError
            # gives the operator one readable line and a non-zero exit status.
            raise CommandError(exc.detail) from exc

        mode = "first boot" if result.mode == BOOTSTRAP_FIRST_BOOT else "recovery"
        self.stdout.write(
            self.style.SUCCESS(
                f"OWNER granted to {result.user.full_name} <{result.user.phone}> "
                f"({mode}). Audited as OWNER_BOOTSTRAP."
            )
        )
