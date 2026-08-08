"""The receipt-number sequence (M6-2, D-4).

**Django's autodetector does not generate bare sequences**, so this migration cannot come
from ``makemigrations``. It is hand-written for the same reason ``ledger/0002`` and
``billing/0002`` are: some database objects have no model representation.

Why a sequence rather than deriving the number from the primary key, as M3 does for
``order_number``:

M3 writes the row, reads the assigned key, then **updates** the row with the formatted
number. ``sales_order`` carries no immutability trigger, so that second statement is
permitted. ``payment`` does (migration 0003), and its permitted set is exactly four
reversal columns — an ``UPDATE`` writing ``payment_number`` would be refused and every
collection would fail.

Reading ``nextval`` *before* the insert means the row is written **once**, so the trigger
is never engaged and the number is immutable from the instant the row exists.

**Gaps are expected and correct here.** A sequence is non-transactional: a rolled-back
collection consumes a value permanently. That property disqualified sequences for invoice
numbers (M5-4 — a gap in a statutory series is a question from a tax authority) and is
exactly right for a receipt reference, which D-4 already declared non-gapless.

No schema name appears (N-09, E-05): this applies cleanly to any schema, which is what
preserves the schema-per-tenant path (ADR-0007).
"""

from django.db import migrations

FORWARD = """
CREATE SEQUENCE IF NOT EXISTS payment_number_seq
    AS BIGINT
    START WITH 1
    INCREMENT BY 1
    NO MAXVALUE
    NO CYCLE;
"""

REVERSE = """
DROP SEQUENCE IF EXISTS payment_number_seq;
"""


class Migration(migrations.Migration):
    dependencies = [("receivables", "0001_initial")]

    operations = [migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE)]
