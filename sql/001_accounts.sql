BEGIN;

CREATE TABLE accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code TEXT NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]*$'),
    account_type TEXT NOT NULL CHECK (account_type IN ('asset', 'liability')),
    currency TEXT NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMIT;
