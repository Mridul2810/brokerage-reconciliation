BEGIN;

ALTER TABLE trade_executions DROP CONSTRAINT trade_executions_settlement_status_check;
ALTER TABLE trade_executions
ADD COLUMN settlement_entry_id BIGINT UNIQUE REFERENCES journal_entries(entry_id),
ADD COLUMN settled_at TIMESTAMPTZ,
ADD CONSTRAINT trade_executions_settlement_status_check
    CHECK (settlement_status IN ('pending', 'settled')),
ADD CONSTRAINT trade_executions_settlement_details_check CHECK (
    (settlement_status = 'pending' AND settlement_entry_id IS NULL AND settled_at IS NULL)
    OR (settlement_status = 'settled' AND settlement_entry_id IS NOT NULL AND settled_at IS NOT NULL)
);

COMMIT;
