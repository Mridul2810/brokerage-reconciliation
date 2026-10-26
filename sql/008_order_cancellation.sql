BEGIN;

ALTER TABLE buy_orders DROP CONSTRAINT buy_orders_status_check;
ALTER TABLE buy_orders
ADD COLUMN cancellation_entry_id BIGINT UNIQUE REFERENCES journal_entries(entry_id),
ADD CONSTRAINT buy_orders_status_check CHECK (status IN ('reserved', 'cancelled')),
ADD CONSTRAINT buy_orders_cancellation_check CHECK (
    (status = 'reserved' AND cancellation_entry_id IS NULL)
    OR (status = 'cancelled' AND cancellation_entry_id IS NOT NULL)
);

COMMIT;
