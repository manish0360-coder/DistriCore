"""Seed the single stock location (M2-1).

Version 1 operates exactly one location. The column exists on every movement so that
multi-warehouse (Edition 2, EP-A) is a feature rather than a re-architecture — adding it
after a year of movements would re-key the largest table in the system (E-06: High).

Data migration, separate from schema (MIG-3). Idempotent.
"""

from django.db import migrations


def seed(apps, schema_editor):
    StockLocation = apps.get_model("inventory", "StockLocation")
    StockLocation.objects.update_or_create(
        code="MAIN",
        defaults={"name": "Main Warehouse", "is_default": True, "is_active": True},
    )


def unseed(apps, schema_editor):
    StockLocation = apps.get_model("inventory", "StockLocation")
    # Never orphan movements: only remove the location if nothing references it.
    StockLocation.objects.filter(code="MAIN", movements__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0003_stocklocation_stocklot_stockmovement_and_more")]

    operations = [migrations.RunPython(seed, unseed)]
