"""Database-level enforcement of financial document immutability (M5-3, N-04, E-02).

An issued invoice is the legal record of a sale. If it can be edited, no historical
financial claim the system makes is provable — and "we do not edit invoices" is a
convention until the database enforces it.

Three tables take a blanket refusal: ``invoice_line``, ``credit_note`` and
``credit_note_line``. Nothing about them may ever change.

``invoice`` is the exception, and the exception is narrow and explicit:

* **status ISSUED → CANCELLED**, with a reason (04 T-17, D-4). Cancellation is a status
  transition with a compensating ledger entry, never a value edit.
* **``pdf_media_id`` NULL → set, once** (D-5). The PDF is rendered on first request and
  cached; a rendering that was handed to a retailer must never change, so replacing an
  existing one is refused.

Every other column is compared as JSON, so a column added by a future migration is
immutable by default rather than mutable by omission. That default is the safe one.
"""

from django.db import migrations

FORWARD = """
-- ---------------------------------------------------------------- blanket refusal
CREATE OR REPLACE FUNCTION districore_document_immutable()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        '% is immutable once issued: % is not permitted. Correct it with a credit note (M5-3, N-04).',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER invoice_line_immutable
    BEFORE UPDATE OR DELETE ON invoice_line
    FOR EACH ROW EXECUTE FUNCTION districore_document_immutable();

CREATE TRIGGER credit_note_immutable
    BEFORE UPDATE OR DELETE ON credit_note
    FOR EACH ROW EXECUTE FUNCTION districore_document_immutable();

CREATE TRIGGER credit_note_line_immutable
    BEFORE UPDATE OR DELETE ON credit_note_line
    FOR EACH ROW EXECUTE FUNCTION districore_document_immutable();

-- ---------------------------------------------------------------- invoice
CREATE OR REPLACE FUNCTION districore_invoice_immutable()
RETURNS TRIGGER AS $$
DECLARE
    mutable  CONSTANT text[] := ARRAY['status', 'cancelled_reason', 'cancelled_at',
                                      'cancelled_by_id', 'pdf_media_id'];
    old_body jsonb;
    new_body jsonb;
    key      text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'invoice is never deleted (M5-3, N-04). Cancel it or credit it.'
            USING ERRCODE = 'restrict_violation';
    END IF;

    -- No financial column may move. Comparing whole rows minus the permitted keys means
    -- a column added later is immutable by default.
    old_body := to_jsonb(OLD);
    new_body := to_jsonb(NEW);
    FOREACH key IN ARRAY mutable LOOP
        old_body := old_body - key;
        new_body := new_body - key;
    END LOOP;
    IF old_body IS DISTINCT FROM new_body THEN
        RAISE EXCEPTION
            'invoice % is immutable once issued. Correct it with a credit note (M5-3, N-04).',
            OLD.invoice_number
            USING ERRCODE = 'restrict_violation';
    END IF;

    -- D-5: the PDF is written once and never replaced.
    IF OLD.pdf_media_id IS NOT NULL
       AND NEW.pdf_media_id IS DISTINCT FROM OLD.pdf_media_id THEN
        RAISE EXCEPTION
            'invoice % already has a rendered PDF; it is never regenerated (D-5).',
            OLD.invoice_number
            USING ERRCODE = 'restrict_violation';
    END IF;

    -- The one permitted lifecycle change.
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        IF NOT (OLD.status = 'ISSUED' AND NEW.status = 'CANCELLED') THEN
            RAISE EXCEPTION
                'invoice % cannot go from % to %.', OLD.invoice_number, OLD.status, NEW.status
                USING ERRCODE = 'restrict_violation';
        END IF;
        IF NEW.cancelled_reason IS NULL OR NEW.cancelled_reason = '' THEN
            RAISE EXCEPTION
                'invoice % cannot be cancelled without a reason.', OLD.invoice_number
                USING ERRCODE = 'restrict_violation';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER invoice_immutable
    BEFORE UPDATE OR DELETE ON invoice
    FOR EACH ROW EXECUTE FUNCTION districore_invoice_immutable();
"""

REVERSE = """
DROP TRIGGER IF EXISTS invoice_immutable ON invoice;
DROP TRIGGER IF EXISTS invoice_line_immutable ON invoice_line;
DROP TRIGGER IF EXISTS credit_note_immutable ON credit_note;
DROP TRIGGER IF EXISTS credit_note_line_immutable ON credit_note_line;
DROP FUNCTION IF EXISTS districore_invoice_immutable();
DROP FUNCTION IF EXISTS districore_document_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]

    operations = [migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE)]
