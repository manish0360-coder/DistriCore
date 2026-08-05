"""Database-level enforcement of stock ledger immutability (M2-4, BR-004, N-03).

Python guards can be bypassed by raw SQL, a management command, or a future developer
calling ``.update()`` without knowing the rule. A trigger cannot: the database refuses
even if the code asks.

This mirrors ``core/0002`` for ``audit_log``, deliberately. Both tables are the
foundation of a derived figure the business acts on; both are worthless if editable.

**Escape hatch.** If a movement is ever genuinely wrong the answer is a compensating
movement, never an edit. If a true emergency demands otherwise, ``ALTER TABLE ... DISABLE
TRIGGER`` requires table ownership and is a runbook step with written justification — see
docs/runbooks/incident-response.md. It is not a code path.

No schema name appears anywhere (N-09, E-05): this applies cleanly to any schema, which
is what preserves the schema-per-tenant path (ADR-0007).
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION districore_stock_movement_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'stock_movement is append-only: % is not permitted. Post a compensating movement instead (M2-4, BR-004).', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER stock_movement_no_update
    BEFORE UPDATE ON stock_movement
    FOR EACH ROW EXECUTE FUNCTION districore_stock_movement_append_only();

CREATE TRIGGER stock_movement_no_delete
    BEFORE DELETE ON stock_movement
    FOR EACH ROW EXECUTE FUNCTION districore_stock_movement_append_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS stock_movement_no_update ON stock_movement;
DROP TRIGGER IF EXISTS stock_movement_no_delete ON stock_movement;
DROP FUNCTION IF EXISTS districore_stock_movement_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("inventory", "0004_seed_default_location")]

    operations = [migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE)]
