"""Database-level enforcement of ledger immutability (M5-3, BR-005, N-03).

Python guards can be bypassed by raw SQL, a management command, or a future developer
calling ``.update()`` without knowing the rule. A trigger cannot: the database refuses
even if the code asks.

This mirrors ``core/0002`` for ``audit_log`` and ``inventory/0005`` for
``stock_movement``, deliberately. All three are the foundation of a derived figure the
business acts on, and all three are worthless if editable. A balance computed from an
editable ledger proves nothing.

**Escape hatch.** If an entry is ever genuinely wrong the answer is a compensating
entry, never an edit. ``ALTER TABLE ... DISABLE TRIGGER`` requires table ownership and is
a runbook step with written justification — see docs/runbooks/incident-response.md. It is
not a code path.

No schema name appears anywhere (N-09, E-05): this applies cleanly to any schema, which
is what preserves the schema-per-tenant path (ADR-0007).
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION districore_ledger_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'customer_ledger_entry is append-only: % is not permitted. Post a compensating entry instead (M5-3, BR-005).', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER customer_ledger_entry_no_update
    BEFORE UPDATE ON customer_ledger_entry
    FOR EACH ROW EXECUTE FUNCTION districore_ledger_append_only();

CREATE TRIGGER customer_ledger_entry_no_delete
    BEFORE DELETE ON customer_ledger_entry
    FOR EACH ROW EXECUTE FUNCTION districore_ledger_append_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS customer_ledger_entry_no_update ON customer_ledger_entry;
DROP TRIGGER IF EXISTS customer_ledger_entry_no_delete ON customer_ledger_entry;
DROP FUNCTION IF EXISTS districore_ledger_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("ledger", "0001_initial")]

    operations = [migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE)]
