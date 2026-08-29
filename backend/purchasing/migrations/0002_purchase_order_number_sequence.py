"""The purchase-order reference sequence (`04` T-30, D-PUR-8).

**A reference, not a statutory series.** `po_number` is drawn with `nextval` — lock-free,
gaps permitted — exactly as `payment_number_seq` serves `payment`
(`receivables/migrations/0002`), and deliberately **not** as `number_series` serves `invoice`,
where gaplessness is a legal requirement and is worth a row lock per document.

A purchase order abandoned in draft consumes a number. That is acceptable and was the
explicit basis of D-PUR-8: the number is allocated at *creation*, because a draft is already
a business document that support and audit need to be able to name.

**Migrated before the table that uses it.** `purchase_order.po_number` is `NOT NULL` from its
first row, so the service that allocates it must have a sequence to read.

`IF NOT EXISTS` and no schema qualification: the sequence is created in whatever schema the
connection is routed to, which preserves the schema-per-tenant path (ADR-0007).
"""

from django.db import migrations

FORWARD = """
CREATE SEQUENCE IF NOT EXISTS purchase_order_number_seq
    AS BIGINT
    START WITH 1
    INCREMENT BY 1
    NO MAXVALUE
    NO CYCLE;
"""

REVERSE = """
DROP SEQUENCE IF EXISTS purchase_order_number_seq;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('purchasing', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
