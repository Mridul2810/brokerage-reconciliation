BEGIN;

CREATE TABLE journal_entries (
    entry_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE CHECK (length(trim(reference)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE postings (
    posting_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entry_id BIGINT NOT NULL REFERENCES journal_entries(entry_id),
    account_id BIGINT NOT NULL REFERENCES accounts(account_id),
    side TEXT NOT NULL CHECK (side IN ('debit', 'credit')),
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0)
);

CREATE INDEX postings_entry_id_idx ON postings(entry_id);
CREATE INDEX postings_account_id_idx ON postings(account_id);

COMMIT;
