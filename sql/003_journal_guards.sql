BEGIN;

-- Refuse to install guards over an already-invalid journal.
DO $$
BEGIN
    IF EXISTS (
        SELECT j.entry_id
        FROM journal_entries j
        LEFT JOIN postings p ON p.entry_id = j.entry_id
        GROUP BY j.entry_id
        HAVING COUNT(p.posting_id) < 2
            OR COALESCE(SUM(CASE WHEN p.side = 'debit'
                THEN p.amount_cents::NUMERIC ELSE -p.amount_cents::NUMERIC END), 0) <> 0
    ) THEN
        RAISE EXCEPTION 'Existing journal contains incomplete or unbalanced entries';
    END IF;
END;
$$;

CREATE FUNCTION check_journal_balance() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    posting_count BIGINT;
    net_cents NUMERIC;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(
        CASE WHEN side = 'debit'
            THEN amount_cents::NUMERIC ELSE -amount_cents::NUMERIC END
    ), 0)
    INTO posting_count, net_cents
    FROM postings
    WHERE entry_id = NEW.entry_id;

    IF posting_count < 2 OR net_cents <> 0 THEN
        RAISE EXCEPTION 'Entry % needs at least two balanced postings', NEW.entry_id
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER journal_entry_balance
AFTER INSERT ON journal_entries
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION check_journal_balance();

CREATE CONSTRAINT TRIGGER posting_balance
AFTER INSERT ON postings
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION check_journal_balance();

CREATE FUNCTION reject_journal_change() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Journal records cannot be edited or removed; use a correcting entry'
        USING ERRCODE = '23514';
END;
$$;

CREATE TRIGGER journal_no_changes
BEFORE UPDATE OR DELETE OR TRUNCATE ON journal_entries
FOR EACH STATEMENT EXECUTE FUNCTION reject_journal_change();

CREATE TRIGGER postings_no_changes
BEFORE UPDATE OR DELETE OR TRUNCATE ON postings
FOR EACH STATEMENT EXECUTE FUNCTION reject_journal_change();

COMMIT;
