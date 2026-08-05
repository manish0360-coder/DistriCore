"""Seed the working set of reason codes (04 T-08).

Data migration, separate from schema (MIG-3). Idempotent, so it is safe to re-apply.

``is_system`` marks the codes referenced by name in code; they cannot be deactivated.
The owner adds their own without a developer (D-04, NFR-CFG-001) — "leakage", "rat
damage", "sample" and whatever else the business actually says.
"""

from django.db import migrations

SEED = [
    # code, name, direction, restockable, system
    ("OPENING", "Opening stock", "IN", True, True),
    ("SALES_RETURN", "Sales return", "IN", True, True),
    ("PURCHASE_IN", "Goods received", "IN", True, True),
    ("COUNT_ADJ", "Physical count adjustment", "BOTH", True, True),
    ("DAMAGE", "Damaged goods", "OUT", False, False),
    ("EXPIRY", "Expired goods", "OUT", False, False),
    ("SAMPLE", "Free sample", "OUT", False, False),
    ("THEFT", "Theft or loss", "OUT", False, False),
]


def seed(apps, schema_editor):
    ReasonCode = apps.get_model("inventory", "ReasonCode")
    for code, name, direction, restockable, system in SEED:
        ReasonCode.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "direction": direction,
                "is_restockable": restockable,
                "is_system": system,
            },
        )


def unseed(apps, schema_editor):
    ReasonCode = apps.get_model("inventory", "ReasonCode")
    ReasonCode.objects.filter(code__in=[c for c, *_ in SEED]).delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
