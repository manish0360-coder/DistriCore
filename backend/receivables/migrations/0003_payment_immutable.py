"""Database-level enforcement of payment immutability (M6-3, M6-4, N-04).

A payment is money that changed hands. If the row can be edited, no historical balance
the system reports is provable — the same argument that made ``stock_movement``,
``audit_log``, ``customer_ledger_entry`` and ``invoice`` append-only before it.

``payment`` is **mutable in exactly four columns**, and this trigger is the authority on
which. It mirrors ``billing/0002``'s invoice trigger deliberately: compare
``to_jsonb(OLD)`` minus the permitted keys against the same for ``NEW``, so **a column
added by a future migration is immutable by default rather than mutable by omission.**
That default is the safe one.

Three rules beyond "nothing else may change":

* **DELETE is refused unconditionally.** A payment is reversed, never removed — reversal
  appends a compensating ledger entry and leaves both facts on the statement.
* **A reversal cannot be undone.** ``is_reversed`` moves false → true and never back.
  Un-reversing would silently re-credit a customer with no compensating entry.
* **A reversal without a reason is refused**, matching ``ck_payment_reversed`` and the
  service. Three layers agree because a reason is what makes the act auditable.

**Escape hatch.** ``ALTER TABLE … DISABLE TRIGGER`` requires table ownership and is a
runbook step with written justification — see docs/runbooks/incident-response.md. It is
not a code path.

No schema name appears (N-09, E-05).
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION districore_payment_immutable()
RETURNS TRIGGER AS $$
DECLARE
    mutable  CONSTANT text[] := ARRAY['is_reversed', 'reversed_reason',
                                      'reversed_at', 'reversed_by_id'];
    old_body jsonb;
    new_body jsonb;
    key      text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'payment % is never deleted. Reverse it instead (M6-3).', OLD.payment_number
            USING ERRCODE = 'restrict_violation';
    END IF;

    -- No column outside the reversal set may move. Comparing whole rows minus the
    -- permitted keys means a column added later is immutable by default.
    old_body := to_jsonb(OLD);
    new_body := to_jsonb(NEW);
    FOREACH key IN ARRAY mutable LOOP
        old_body := old_body - key;
        new_body := new_body - key;
    END LOOP;
    IF old_body IS DISTINCT FROM new_body THEN
        RAISE EXCEPTION
            'payment % is immutable once recorded. Reverse it instead (M6-3, M6-4).',
            OLD.payment_number
            USING ERRCODE = 'restrict_violation';
    END IF;

    -- A reversal is one-way. Un-reversing would re-credit the customer with no
    -- compensating ledger entry behind it.
    IF OLD.is_reversed AND NOT NEW.is_reversed THEN
        RAISE EXCEPTION
            'payment % has been reversed; that cannot be undone. Record a new payment.',
            OLD.payment_number
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF NEW.is_reversed AND (NEW.reversed_reason IS NULL OR NEW.reversed_reason = '') THEN
        RAISE EXCEPTION
            'payment % cannot be reversed without a reason.', OLD.payment_number
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER payment_immutable
    BEFORE UPDATE OR DELETE ON payment
    FOR EACH ROW EXECUTE FUNCTION districore_payment_immutable();
"""

REVERSE = """
DROP TRIGGER IF EXISTS payment_immutable ON payment;
DROP FUNCTION IF EXISTS districore_payment_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("receivables", "0002_payment_number_sequence")]

    operations = [migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE)]
