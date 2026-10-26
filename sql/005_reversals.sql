BEGIN;

CREATE TABLE journal_reversals (
    original_entry_id BIGINT PRIMARY KEY REFERENCES journal_entries(entry_id),
    reversal_entry_id BIGINT NOT NULL UNIQUE REFERENCES journal_entries(entry_id),
    CHECK (original_entry_id <> reversal_entry_id)
);

CREATE TRIGGER reversals_no_changes
BEFORE UPDATE OR DELETE OR TRUNCATE ON journal_reversals
FOR EACH STATEMENT EXECUTE FUNCTION reject_journal_change();

COMMIT;
