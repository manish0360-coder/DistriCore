"""Normalise phone numbers already stored verbatim by ``UserManager._create``.

Data migration, kept separate from schema migrations (MIG-3). It writes no schema change:
`identity_user.phone` is already `varchar(20) UNIQUE`, and this only corrects the values
inside it.

**Why it is needed.** Every read path normalises (`authenticate_password`, `request_otp`,
`verify_otp`); the write path did not. Any user created through `createsuperuser` or the
manager before this migration may hold a non-canonical number and be unable to log in with
any spelling of it.

**Why the rule is copied rather than imported.** A migration must keep doing what the rule
meant on the day it ran. Importing `identity.phone.normalise_phone` would let a later change
to the canonical form silently rewrite history — the ordinary Django prohibition on
importing app code into migrations, and the reason `0002_seed_roles` inlines its data too.
The copy below is frozen at the 2026-08-08 definition.

**Idempotent.** Normalisation is idempotent, so a row already canonical is left untouched
and re-running the migration is a no-op.
"""

from django.db import migrations


def _normalise(phone: str) -> str:
    """Frozen copy of `identity.phone.normalise_phone` as at 2026-08-08.

    Returns the input unchanged when it cannot be normalised, so a malformed legacy row
    is preserved for a human rather than destroyed by a migration.
    """
    cleaned = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+").strip()
    if not cleaned:
        return phone
    digits = cleaned.lstrip("+")
    if len(digits) == 10:
        digits = f"91{digits}"
    return f"+{digits}"


def normalise(apps, schema_editor):
    User = apps.get_model("identity", "User")

    rows = list(User.objects.all().values_list("pk", "phone"))
    if not rows:
        return

    # Every row is mapped, including those already canonical. Because normalisation is
    # idempotent, a collision between a row being changed and a row being left alone shows
    # up in the same group — so one pass over all rows finds every conflict.
    targets: dict[str, list[tuple[int, str]]] = {}
    for pk, phone in rows:
        targets.setdefault(_normalise(phone), []).append((pk, phone))

    collisions = {
        target: holders for target, holders in targets.items() if len(holders) > 1
    }
    if collisions:
        # Refusing is the only safe answer. Picking a winner would silently orphan a real
        # person's account and their audit trail; `phone` is UNIQUE and is the login
        # identity (04 T-01), so the merge is a business decision, not a migration's.
        detail = "; ".join(
            f"{target} <- " + ", ".join(f"user {pk} ({raw!r})" for pk, raw in holders)
            for target, holders in sorted(collisions.items())
        )
        raise RuntimeError(
            "Cannot normalise identity_user.phone: two or more users would collide on the "
            "same canonical number. Resolve them by hand, then re-run the migration. "
            f"Collisions: {detail}"
        )

    for target, holders in targets.items():
        pk, raw = holders[0]
        if raw != target:
            User.objects.filter(pk=pk).update(phone=target)


def unnormalise(apps, schema_editor):
    """Deliberately a no-op.

    The original spelling is not recorded anywhere, so a reverse cannot restore it — and a
    reverse that guessed would put the database back into the state this migration exists
    to remove. Reversing the *schema* is unnecessary; nothing here changed it.
    """


class Migration(migrations.Migration):
    dependencies = [("identity", "0003_user_customer_user_ix_app_user_customer")]

    operations = [migrations.RunPython(normalise, unnormalise)]
