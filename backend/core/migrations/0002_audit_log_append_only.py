"""Database-level enforcement of audit immutability (N-04, I-12).

Python guards can be bypassed by raw SQL, a management command, or a future
developer using ``.update()`` without knowing the rule. A trigger cannot: the
database refuses even if the code asks.

No schema name appears anywhere in this migration (N-09, E-05) — it applies cleanly
to any schema, which is what preserves the schema-per-tenant path (ADR-007).
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION districore_audit_log_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'audit_log is append-only: % is not permitted (N-04, I-12)', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION districore_audit_log_append_only();

CREATE TRIGGER audit_log_no_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION districore_audit_log_append_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;
DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log;
DROP FUNCTION IF EXISTS districore_audit_log_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE)]
