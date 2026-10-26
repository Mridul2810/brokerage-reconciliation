BEGIN;

ALTER TABLE buy_orders DROP CONSTRAINT buy_orders_status_check;
ALTER TABLE buy_orders DROP CONSTRAINT buy_orders_cancellation_check;
ALTER TABLE buy_orders
ADD CONSTRAINT buy_orders_status_check CHECK (status IN ('reserved', 'cancelled', 'executed')),
ADD CONSTRAINT buy_orders_cancellation_check CHECK (
    (status IN ('reserved', 'executed') AND cancellation_entry_id IS NULL)
    OR (status = 'cancelled' AND cancellation_entry_id IS NOT NULL)
);

INSERT INTO accounts (code, account_type)
VALUES ('clearing_trade_payable', 'liability');

CREATE TABLE trade_executions (
    reference TEXT PRIMARY KEY CHECK (length(trim(reference)) > 0),
    order_reference TEXT NOT NULL UNIQUE REFERENCES buy_orders(reference),
    quantity BIGINT NOT NULL CHECK (quantity > 0),
    price_cents BIGINT NOT NULL CHECK (price_cents > 0),
    cash_entry_id BIGINT NOT NULL UNIQUE REFERENCES journal_entries(entry_id),
    settlement_status TEXT NOT NULL DEFAULT 'pending' CHECK (settlement_status = 'pending'),
    executed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMIT;
