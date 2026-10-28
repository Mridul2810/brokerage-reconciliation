# Reproduce the portfolio demo

## Current walkthrough database

If you already followed the guided build through migration 012, do not reapply
the migrations. With Docker running and `.env` configured:

```sh
./.venv/bin/python -m brokerage.portfolio_demo
```

The script creates its own `portfolio_demo_cash` and `portfolio_demo_reserved`
accounts. It leaves Alex's accounts untouched, while using the shared bank asset
and clearing payable. It verifies:

1. A $1,000 deposit retries without duplication; conflicting contents are rejected.
2. A $2,000 withdrawal is rejected.
3. A missing-account failure rolls back the journal entry and first posting.
4. Two shares reserved at $50 execute at $48 and settle once.
5. Available cash ends at $904, reserved cash at $0, and settled AAPL shares at 2.
6. An independently specified synthetic quantity of 3 produces one break.
7. A matching synthetic quantity of 2 produces a clean report.
8. Investigation events document the discrepancy and clean report reference.

Run it again: financial references are reused safely. Each invocation intentionally
creates two new evidence reports and their own investigation events. Do not modify
this dedicated demo account between runs; the scenario checks exact end balances.

Start the server:

```sh
./.venv/bin/python -m uvicorn brokerage.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`, enter `portfolio_demo_cash`, and load the account.
Select a faulty run to show 2 versus 3 shares and its investigation timeline; then
select its matching run. Open the preserved snapshots to show both inputs.

## Fresh checkout

For an existing guided-development setup with `brokerage_test` initialized, one
command performs the fresh-database and repeated-demo verification plus all tests:

```sh
./.venv/bin/python -m brokerage.verify_setup
```

It creates a uniquely named verification database, retains it for inspection,
and leaves existing databases intact. It requires the local database user to have
CREATE DATABASE privileges. Each invocation creates another verification database.
It prints `VERIFICATION PASSED` only after every subprocess succeeds. The full
test suite still uses the separately initialized `brokerage_test` database.

```sh
git clone https://github.com/Mridul2810/brokerage-reconciliation.git
cd brokerage-reconciliation
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Choose a local password in `.env`, then:

```sh
docker compose up -d
docker compose ps
```

Wait for healthy. On a fresh database:

```sh
./.venv/bin/python -m brokerage.migrate
./.venv/bin/python -m brokerage.portfolio_demo
```

The migration runner tracks source hashes and skips already-applied files. It
stops if an applied migration changes or the database was initialized manually.
It never resets data. Do not delete existing data to test setup.

To verify fresh setup alongside the existing walkthrough database, create an
additional database once:

```sh
docker compose exec db psql -U brokerage -d postgres -c "CREATE DATABASE brokerage_freshcheck;"
./.venv/bin/python -m brokerage.migrate --database brokerage_freshcheck
./.venv/bin/python -m brokerage.migrate --database brokerage_freshcheck
POSTGRES_DB=brokerage_freshcheck ./.venv/bin/python -m brokerage.portfolio_demo
```

The first migration run applies the schema; the second reports no changes.
If that named database already exists, inspect it rather than recreating it.

## Interview walkthrough (about five minutes)

- Explain the accounting entries and why bank cash moves at settlement.
- Show exact balances and settled shares in the dashboard.
- Show the deliberately wrong clearing quantity and preserved evidence.
- Show the investigation history and separate matching comparison.
- Open retry, rollback, and competing-withdrawal tests to explain their assertions.
- State current limits: local-only, full buy fills, manual settlement, no real funds.

Unexpected SQL or connection errors should be investigated, not described as
successful failure injection. The demo prints PASS only after its checks succeed.
