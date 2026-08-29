"""The supplier-payment reference sequence (`04`, D5 S4.3).

**A reference, not a statutory series** — `nextval`, lock-free, gaps permitted, on exactly
the terms `purchase_order_number_seq` records in `0002`, `goods_receipt_number_seq` in
`0004` and `payment_number_seq` in `receivables/0002`.

Gaps are expected here for one reason beyond the usual: a submission that loses the
`uq_supplier_payment_submission` race has already drawn a number before its INSERT is
refused. Consuming a reference to prevent a duplicate payment is the right trade.

**Migrated before the table that uses it.** `supplier_payment.payment_number` is `NOT NULL`
from its first row, so the service that allocates it must have a sequence to read.

`IF NOT EXISTS` and no schema qualification: the sequence is created in whatever schema the
connection is routed to, which preserves the schema-per-tenant path (ADR-0007).
"""

from django.db import migrations

FORWARD = """
CREATE SEQUENCE IF NOT EXISTS supplier_payment_number_seq
    AS BIGINT
    START WITH 1
    INCREMENT BY 1
    NO MAXVALUE
    NO CYCLE;
"""

REVERSE = """
DROP SEQUENCE IF EXISTS supplier_payment_number_seq;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('purchasing', '0005_goods_receipt'),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
