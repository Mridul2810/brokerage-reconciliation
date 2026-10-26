-- Demo data, not a schema migration. Run once against the demo database.
BEGIN;

INSERT INTO accounts (code, account_type)
VALUES ('customer_alex_reserved_cash', 'liability');

INSERT INTO cash_account_pairs (available_account_id, reserved_account_id)
VALUES (
    (SELECT account_id FROM accounts WHERE code = 'customer_alex_cash_liability'),
    (SELECT account_id FROM accounts WHERE code = 'customer_alex_reserved_cash')
);

COMMIT;
