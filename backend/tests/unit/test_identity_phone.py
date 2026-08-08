"""**The write path must store what the read path looks for** (identity/phone.py).

The defect these tests exist for: `authenticate_password` normalised its input and
`UserManager._create` did not, so a superuser created as `7903324153` was stored verbatim,
the lookup asked for `+917903324153`, found nothing, and reported "Incorrect phone number
or password" — true of the query, and misleading about the cause.

`check_password` was never reached. `if user is None or not user.check_password(...)`
short-circuits, which is why the password verified in a shell and failed in a browser.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

from core.exceptions import InvalidCredentials
from identity.models import User
from identity.phone import normalise_phone
from identity.services import authenticate_password

pytestmark = pytest.mark.django_db

#: The three spellings one person uses for one number. They must all be one user.
SPELLINGS = ["7903324153", "917903324153", "+917903324153"]
CANONICAL = "+917903324153"
PASSWORD = "Manish.0360"


# ------------------------------------------------------------------------- the write path
def test_the_manager_stores_the_canonical_form(seeded_roles):
    """The one-line fix, asserted at the point it was missing."""
    user = User.objects.create_user(phone="7903324153", password=PASSWORD, full_name="Mack")
    assert user.phone == CANONICAL
    user.refresh_from_db()
    assert user.phone == CANONICAL


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_create_superuser_stores_the_canonical_form(seeded_roles, spelling):
    """`createsuperuser` reaches `_create` through `create_superuser`."""
    user = User.objects.create_superuser(
        phone=spelling, password=PASSWORD, full_name="Mack"
    )
    assert user.phone == CANONICAL


def test_the_createsuperuser_command_stores_the_canonical_form(seeded_roles, monkeypatch):
    """The management command itself, not just the manager beneath it.

    This is the path that produced the reported defect, so it is the path asserted —
    a test of the manager alone would not have caught a command that bypassed it.
    """
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", PASSWORD)
    call_command(
        "createsuperuser", interactive=False, phone="7903324153", full_name="Mack", verbosity=0
    )
    assert User.objects.filter(phone=CANONICAL).exists()
    assert not User.objects.filter(phone="7903324153").exists()


def test_an_empty_phone_still_raises_value_error(seeded_roles):
    """Unchanged behaviour. The guard sits above normalisation deliberately.

    `createsuperuser` relies on this contract, and `normalise_phone` raises a different
    exception type.
    """
    with pytest.raises(ValueError):
        User.objects.create_user(phone="", password=PASSWORD, full_name="Mack")


# -------------------------------------------------------------------------- the read path
@pytest.fixture
def mack(seeded_roles):
    """Created through the manager, exactly as `createsuperuser` would.

    No role is granted: `authenticate_password` does not consult roles, and adding one
    here would test the webadmin view's separate check by accident.
    """
    return User.objects.create_superuser(
        phone="7903324153", password=PASSWORD, full_name="Mack"
    )


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_login_succeeds_for_every_spelling_of_one_number(mack, spelling):
    """One number, one user — whichever way the owner types it at six in the morning."""
    assert authenticate_password(phone=spelling, password=PASSWORD).pk == mack.pk


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_a_wrong_password_still_fails_for_every_spelling(mack, spelling):
    """The fix must not turn a normalisation miss into a way past the password."""
    with pytest.raises(InvalidCredentials):
        authenticate_password(phone=spelling, password="wrong")


# ------------------------------------------------------------------- reader/writer agree
@pytest.mark.parametrize("spelling", SPELLINGS)
def test_what_the_manager_writes_is_what_normalise_returns(seeded_roles, spelling):
    """The property the defect violated, stated directly.

    Not "the manager normalises" — *the manager and every lookup produce the same string*.
    A second implementation that merely also normalised could drift; this asserts identity.
    """
    user = User.objects.create_user(phone=spelling, password=PASSWORD, full_name="Mack")
    assert user.phone == normalise_phone(spelling)


def test_normalisation_is_idempotent():
    """What makes the 0004 migration safe to re-run, and its collision check complete."""
    for spelling in SPELLINGS:
        once = normalise_phone(spelling)
        assert normalise_phone(once) == once


def test_three_spellings_cannot_become_three_users(seeded_roles):
    """The unique constraint now bites where it always should have.

    Before the fix these were three rows. `phone` is the login identity (04 T-01), so
    three rows meant three accounts for one person — and only one of them reachable.
    """
    User.objects.create_user(phone=SPELLINGS[0], password=PASSWORD, full_name="Mack")
    for spelling in SPELLINGS[1:]:
        # Each attempt gets its own savepoint: an IntegrityError poisons the transaction,
        # and without one the second iteration would fail for the wrong reason.
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create_user(phone=spelling, password=PASSWORD, full_name="Impostor")
