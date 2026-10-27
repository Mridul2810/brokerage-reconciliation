BEGIN;

CREATE TABLE investigation_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE CHECK (length(trim(reference)) > 0),
    break_id BIGINT NOT NULL REFERENCES reconciliation_breaks(break_id),
    status TEXT NOT NULL CHECK (status IN ('open', 'investigating', 'resolved')),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    note TEXT NOT NULL CHECK (length(trim(note)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX investigation_events_break_idx ON investigation_events(break_id, event_id);

CREATE TRIGGER investigation_events_no_changes
BEFORE UPDATE OR DELETE OR TRUNCATE ON investigation_events
FOR EACH STATEMENT EXECUTE FUNCTION reject_journal_change();

COMMIT;
