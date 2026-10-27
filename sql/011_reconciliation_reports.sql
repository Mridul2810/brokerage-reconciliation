BEGIN;

CREATE TABLE reconciliation_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_code TEXT NOT NULL,
    clearing_source TEXT NOT NULL,
    clearing_records_sha256 TEXT NOT NULL CHECK (length(clearing_records_sha256) = 64),
    internal_records JSONB NOT NULL CHECK (jsonb_typeof(internal_records) = 'array'),
    clearing_records JSONB NOT NULL CHECK (jsonb_typeof(clearing_records) = 'array'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reconciliation_breaks (
    break_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES reconciliation_runs(run_id),
    reference TEXT NOT NULL,
    kind TEXT NOT NULL,
    field TEXT NOT NULL,
    internal_value TEXT NOT NULL,
    clearing_value TEXT NOT NULL
);

CREATE INDEX reconciliation_breaks_run_idx ON reconciliation_breaks(run_id);

CREATE TRIGGER reconciliation_runs_no_changes
BEFORE UPDATE OR DELETE OR TRUNCATE ON reconciliation_runs
FOR EACH STATEMENT EXECUTE FUNCTION reject_journal_change();

CREATE TRIGGER reconciliation_breaks_no_changes
BEFORE UPDATE OR DELETE OR TRUNCATE ON reconciliation_breaks
FOR EACH STATEMENT EXECUTE FUNCTION reject_journal_change();

COMMIT;
