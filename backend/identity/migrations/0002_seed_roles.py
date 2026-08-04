"""Seed the four system roles (04 T-02).

Data migration, kept separate from schema migrations (MIG-3): different failure modes,
different recovery. Idempotent, so it is safe on an existing database.

The roles are seeded rather than hardcoded as an enum-only concept because Edition 2
adds roles without a migration (EP-B). ``is_system`` marks the four the code depends on.
"""

from django.db import migrations

SYSTEM_ROLES = [
    ("OWNER", "Owner", "Full authority over the business and its data."),
    ("SALESMAN", "Salesman", "Field sales: visits, customers, collections."),
    ("DELIVERY", "Delivery", "Delivery execution. Held alongside SALESMAN by one person."),
    ("RETAILER", "Retailer", "External shopkeeper. Own records only."),
]


def seed(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    for code, name, description in SYSTEM_ROLES:
        Role.objects.update_or_create(
            code=code,
            defaults={"name": name, "description": description, "is_system": True},
        )


def unseed(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    # Only remove roles nobody holds — never orphan a user's authorisation.
    Role.objects.filter(
        code__in=[c for c, _, _ in SYSTEM_ROLES], user_roles__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("identity", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
