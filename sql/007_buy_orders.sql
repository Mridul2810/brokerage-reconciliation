BEGIN;

CREATE TABLE buy_orders (
    reference TEXT PRIMARY KEY CHECK (length(trim(reference)) > 0),
    available_account_id BIGINT NOT NULL REFERENCES cash_account_pairs(available_account_id),
    symbol TEXT NOT NULL CHECK (symbol ~ '^[A-Z][A-Z0-9.]{0,9}$'),
    quantity BIGINT NOT NULL CHECK (quantity > 0),
    limit_price_cents BIGINT NOT NULL CHECK (limit_price_cents > 0),
    reservation_entry_id BIGINT NOT NULL UNIQUE REFERENCES journal_entries(entry_id),
    status TEXT NOT NULL DEFAULT 'reserved' CHECK (status = 'reserved'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMIT;
