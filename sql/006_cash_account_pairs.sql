BEGIN;

CREATE TABLE cash_account_pairs (
    available_account_id BIGINT PRIMARY KEY REFERENCES accounts(account_id),
    reserved_account_id BIGINT NOT NULL UNIQUE REFERENCES accounts(account_id),
    CHECK (available_account_id <> reserved_account_id)
);

COMMIT;
