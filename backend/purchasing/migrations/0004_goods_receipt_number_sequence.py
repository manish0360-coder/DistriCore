"""The goods-receipt reference sequence (`04` T-32).

**A reference, not a statutory series** — `nextval`, lock-free, gaps permitted, on exactly the
terms `purchase_order_number_seq` records in `0002` and `payment_number_seq` in
`receivables/migrations/0002`. Nothing statutory is numbered here, so nothing is worth a row
lock per document.

**Migrated before the table that uses it.** `goods_receipt.grn_number` is `NOT NULL` from its
first row, so the service that allocates it must have a sequence to read.

`IF NOT EXISTS` and no schema qualification: the sequence is created in whatever schema the
connection is routed to, which preserves the schema-per-tenant path (ADR-0007).
"""

from django.db import migrations

FORWARD = """
CREATE SEQUENCE IF NOT EXISTS goods_receipt_number_seq
    AS BIGINT
    START WITH 1
    INCREMENT BY 1
    NO MAXVALUE
    NO CYCLE;
"""

REVERSE = """
DROP SEQUENCE IF EXISTS goods_receipt_number_seq;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('purchasing', '0003_purchase_order'),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
