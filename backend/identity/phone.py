"""The canonical form of a phone number — defined **once** (N-07's argument, applied to
an identity key rather than to money).

`04` T-01 makes the phone number the login identity. There is no username and no email, so
this string *is* the primary human-facing key, and two spellings of one number are two
users. `core.fields.to_money` exists for exactly this reason on the money side: a canonical
representation that is fixed at the point a value enters the domain, not patched where it
is read.

**This module exists because that discipline was applied on read and not on write.**
``authenticate_password`` normalised its input; ``UserManager._create`` stored whatever it
was given. A superuser created as ``7903324153`` could therefore never log in — the lookup
asked for ``+917903324153`` and found nothing, and the failure was reported as
"Incorrect phone number or password", which was true of the query and misleading about the
cause.

It lives here, below both, so the reader and the writer import the same function rather
than the manager reaching up into the service layer.
"""

from __future__ import annotations

from core.exceptions import ValidationFailed


def normalise_phone(phone: str) -> str:
    """Collapse the ways a person types an Indian mobile number into one form.

    Without this, '+919876543210', '919876543210' and '9876543210' are three different
    users. Validation of the result belongs to the serialiser.

    Idempotent: ``normalise_phone(normalise_phone(x)) == normalise_phone(x)``, which is
    what makes the 0004 data migration safe to re-run and its collision check complete.
    """
    cleaned = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+").strip()
    if not cleaned:
        raise ValidationFailed(
            "A phone number is required.",
            errors=[{"field": "phone", "code": "REQUIRED", "message": "Phone number is required."}],
        )
    digits = cleaned.lstrip("+")
    if len(digits) == 10:
        digits = f"91{digits}"
    return f"+{digits}"
