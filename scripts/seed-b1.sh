#!/usr/bin/env bash
# **B1 — FR-SYN-010 acceptance seed.** Test-support only; never imported by the application.
#
# `02` FR-SYN-010: *"Full sync of a typical daily volume MUST complete within 2 minutes of
# reconnection at the DR-8 envelope."* `02` NFR-PER-004 names the method: *"Timed sync at
# representative volume."* This script builds the volume; `mobile-device-sync-latency` times it.
#
# **What "typical daily volume" resolves to, and how much of it is derived.** DR-8 (`01` NFR-4)
# gives <=10,000 order lines/day across <=50 synchronising devices — about **200 per device**,
# which is also `05` §13's batch cap, so a typical device-day is one push batch. **That
# arithmetic is a derivation, not a frozen number**, and `01` §16.3 **CF-4** still lists the
# DR-8 envelope itself as an outstanding confirmation whose consequence is *"test targets
# remain provisional"*. Nothing here promotes 200 into a requirement.
#
# **Why `VISIT_CREATE` and not `DELIVERY_COMPLETE`.** Both are frozen mobile actions. A visit
# needs only a customer the actor can see (`backend/field/services.py::record_visit`); a
# delivery completion needs a real assigned delivery in the right state, which means seeding
# orders and dispatch as well. The customers seeded here therefore do double duty: they make
# every queued operation **server-acceptable** and they are the bulk of the pull payload. Rows
# that are rejected on purpose would measure the wrong thing.
#
# **This is not a Django management command, deliberately.** A seed that ships inside
# `backend/` is production code that creates users; it would need its own tests, its own
# authorisation story and a reason to exist on a customer's server. Test-support belongs here.
#
# Usage:
#   scripts/seed-b1.sh [customer_count]     # default 500
#
# Prints the credentials and counts the device build and the run report need.
set -euo pipefail
cd "$(dirname "$0")/.."

CUSTOMERS="${1:-500}"

COMPOSE=(docker compose -f docker/compose.yml -f docker/compose.dev.yml --env-file .env)

# Fixed, so a re-run is idempotent and the report can name the identity it measured.
B1_PHONE="+919876500001"
B1_PASSWORD="b1-acceptance-only"

echo "==> seeding B1 volume: 1 salesman, 1 zone, ${CUSTOMERS} customers"

# **No `-w` and no `PYTHONPATH`, deliberately.** The Makefile states the rule at line 6 —
# *"manage.py lives in backend/ -> that is the cwd for Django commands"* — and the image sets
# `WORKDIR /app/backend` to match, so `python manage.py` works with no override at all. This
# was first written with `-w /app -e PYTHONPATH=/app/backend`, which is the `$(TOOLS)`
# environment: correct for **pytest**, which needs the repo root to resolve `backend/tests/...`,
# and wrong for a Django command, which then cannot find `/app/manage.py`.
#
# `-T` is the one addition over `$(DC) exec app python manage.py shell`: there is no TTY, and
# the script feeds the program on stdin.
#
# `backend/tests/__init__.py` exists, so `tests.factories` imports from that cwd unaided, and
# `factory-boy` is installed because `compose.dev.yml` runs the dev image
# (`uv sync --frozen --extra dev`).
"${COMPOSE[@]}" exec -T app python manage.py shell <<PY
from django.contrib.auth import get_user_model
from django.db import transaction

from customers.models import Customer, Zone
from identity.models import Role

# **The factories, not hand-built rows.** They go through the manager the production write
# path uses — the whole point of TD-30 — so a user seeded here is a user the login endpoint
# will actually accept. Hand-rolling \`User.objects.create\` is how TD-30 hid two defects.
from tests.factories import CustomerFactory, UserFactory, ZoneFactory

User = get_user_model()
COUNT = ${CUSTOMERS}

with transaction.atomic():
    user = User.objects.filter(phone="${B1_PHONE}").first()
    if user is None:
        user = UserFactory(phone="${B1_PHONE}", full_name="B1 Acceptance Salesman")
    user.set_password("${B1_PASSWORD}")
    user.is_active = True
    user.save()

    salesman = Role.objects.get_or_create(code="SALESMAN", defaults={"name": "Salesman"})[0]
    user.roles.add(salesman)

    # \`visible_customers\` scopes a SALESMAN to \`zone__assigned_user=actor\`
    # (\`backend/customers/selectors.py\`), so the zone assignment is what makes both the pull
    # and every queued visit legal. Without it the pull is empty and every operation is
    # REJECTED as out of scope — which would still "complete", and would measure nothing.
    zone = Zone.objects.filter(name="B1 Acceptance Zone").first()
    if zone is None:
        zone = ZoneFactory(name="B1 Acceptance Zone")
    zone.assigned_user = user
    zone.is_active = True
    zone.save()

    existing = Customer.objects.filter(zone=zone).count()
    for index in range(existing, COUNT):
        CustomerFactory(zone=zone, code=f"B1-{index:05d}")

print("SEED:b1 user_id=%s phone=%s" % (user.pk, user.phone))
print("SEED:b1 roles=%s" % sorted(r.code for r in user.roles.all()))
print("SEED:b1 zone_id=%s customers=%s" % (zone.pk, Customer.objects.filter(zone=zone).count()))
PY

cat <<EOF

==> seeded.

    phone     ${B1_PHONE}
    password  ${B1_PASSWORD}

    These are acceptance-test credentials on a local dev stack. They are not secrets and
    must never exist on a deployed server.

    Next:  make mobile-device-sync-latency
EOF
