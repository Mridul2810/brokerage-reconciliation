# Brokerage Ledger & Reconciliation Engine

A portfolio project exploring financial correctness and failure recovery in a
simulated brokerage. Simulation only; no real funds or brokerage connection.

## Current milestone

Balanced USD journal entries, derived asset and liability balances, and a
PostgreSQL-backed journal with reference-based retry handling. Identical retries
return the existing entry; conflicting contents are rejected. Posting order is
significant when comparing retries. An in-memory implementation is also included.

PostgreSQL checks balance and posting count at transaction commit and blocks
journal updates, deletes, and truncation. These guards do not yet seal an entry
against additional balanced postings or restrict changes to account definitions.
Database administrator privileges can bypass guards; application roles are planned.
Trades, settlement, reconciliation, and an HTTP API are not implemented yet.

## Run locally

Requires Python 3.12 and Docker Desktop with Compose. From this directory:

```sh
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Replace the password placeholder in `.env` with a local development password.
Keep `.env` out of Git. Start the database:

```sh
docker compose up -d
docker compose ps
```

Wait for `healthy`. On a fresh database, apply each migration once, in order:

```sh
docker compose exec -T db psql -U brokerage -d brokerage -v ON_ERROR_STOP=1 < sql/001_accounts.sql
docker compose exec -T db psql -U brokerage -d brokerage -v ON_ERROR_STOP=1 < sql/002_journal.sql
docker compose exec -T db psql -U brokerage -d brokerage -v ON_ERROR_STOP=1 < sql/003_journal_guards.sql
```

Create the demo accounts, then run the Python commands:

```sh
docker compose exec db psql -U brokerage -d brokerage -c "INSERT INTO accounts (code, account_type) VALUES ('bank_cash', 'asset'), ('customer_alex_cash_liability', 'liability');"
./.venv/bin/python -m brokerage.check_db
./.venv/bin/python -m brokerage.save_deposit demo-deposit-001 50.00
```

Repeating the deposit command is an identical retry. Changing its amount while
keeping its reference raises a conflict. The default database is `brokerage` on
localhost port 5433. `POSTGRES_DB` can select a different database.

## Tests

```sh
./.venv/bin/python -m unittest discover -s tests -v
```

By default database tests are skipped. To enable them, first create the separate
database and apply the same migrations to it (once):

```sh
docker compose exec db psql -U brokerage -d postgres -c "CREATE DATABASE brokerage_test;"
docker compose exec -T db psql -U brokerage -d brokerage_test -v ON_ERROR_STOP=1 < sql/001_accounts.sql
docker compose exec -T db psql -U brokerage -d brokerage_test -v ON_ERROR_STOP=1 < sql/002_journal.sql
docker compose exec -T db psql -U brokerage -d brokerage_test -v ON_ERROR_STOP=1 < sql/003_journal_guards.sql
RUN_DB_TESTS=1 ./.venv/bin/python -m unittest discover -s tests -v
```

Tests seed their own accounts, use unique references, and retain test records.
They cover sequential retries, conflicts, partial-write rollback, and two concurrent
identical requests. The concurrent test coordinates worker starts; it does not
guarantee a particular database interleaving or prove all concurrency behavior.

The GitHub Actions workflow provisions a fresh PostgreSQL test database, applies
the migrations, and runs the full suite on pushes and pull requests.

## Accounting model

A customer deposit debits the brokerage's bank cash asset and credits its liability
to that customer. Debits increase assets; credits increase liabilities. Debit and
credit do not universally mean subtract and add.

Every journal entry must have at least two positive postings, and its total debits
must equal its total credits. Balanced entries can still contain business mistakes:
balance alone does not prove that an amount or customer is correct.

For this milestone, USD postings accept at most two decimal places. Future trade
calculations will need an explicit precision and rounding policy.
