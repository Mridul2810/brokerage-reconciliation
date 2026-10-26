BEGIN;

-- Existing entries become sealed when this migration commits.
ALTER TABLE journal_entries
ADD COLUMN created_xid XID8 NOT NULL DEFAULT pg_current_xact_id();

CREATE FUNCTION stamp_journal_transaction() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    -- Ignore caller-supplied values: the database owns this field.
    NEW.created_xid := pg_current_xact_id();
    RETURN NEW;
END;
$$;

CREATE TRIGGER journal_transaction_stamp
BEFORE INSERT ON journal_entries
FOR EACH ROW EXECUTE FUNCTION stamp_journal_transaction();

CREATE FUNCTION reject_late_posting() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    entry_transaction XID8;
BEGIN
    SELECT created_xid INTO entry_transaction
    FROM journal_entries WHERE entry_id = NEW.entry_id;

    IF entry_transaction IS DISTINCT FROM pg_current_xact_id() THEN
        RAISE EXCEPTION 'Postings require a journal entry created in the same transaction'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER postings_same_transaction
BEFORE INSERT ON postings
FOR EACH ROW EXECUTE FUNCTION reject_late_posting();

COMMIT;
