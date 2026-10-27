# Brokerage Ledger & Reconciliation Engine

A portfolio project exploring financial correctness and failure recovery in a
simulated brokerage. Simulation only; no real funds or brokerage connection.

## Current milestone

Balanced USD journal entries, derived asset and liability balances, and a
PostgreSQL-backed journal with reference-based retry handling. Identical retries
return the existing entry; conflicting contents are rejected. Posting order is
significant when comparing retries. An in-memory implementation is also included.

PostgreSQL checks balance and posting count at transaction commit and blocks
journal updates, deletes, and truncation. Migration 004 restricts new postings to
the transaction creating their journal entry, sealing entries at commit.
Account definitions are not yet protected against changes.
Cash reservations move a liability from an available account to its configured
reserved account, leaving bank cash unchanged. Reservations and withdrawals lock
the same available account before checking funds. Direct withdrawals from a
configured reserved account are rejected. Account-pair administration is currently
trusted. Whole-share buy limit orders can be created atomically with cash
reservations. Identical order retries compare customer, symbol, quantity, and price.
Reserved orders can be cancelled atomically with a release of their own reservation.
Repeated cancellation does not release cash twice. Generic reversals of order
reservation or cancellation entries are rejected by the correction service.
Simulated full buy fills enforce the limit price, release unused reserved cash,
record pending shares, and move trade cost into a clearing payable. Bank cash
does not move until manual settlement. Settlement clears the trade payable,
reduces bank cash, and moves shares from pending to settled atomically. Identical
and concurrent settlement retries do not pay twice. There is no settlement-date
calendar, external funds transfer, or bank-liquidity authorization in this simulation.
Share positions are derived from execution records, not a custody ledger. Partial fills,
fractional quantities, and fees are not yet supported. Direct SQL can still bypass
order lifecycle rules; application-role restrictions remain future work.
Full-entry reversals preserve original postings and link a new opposite entry to
the original. They are administrative corrections, not customer withdrawals:
they may produce a negative balance and require an operational review in a real
system. Partial reversals and reversing a reversal are not supported.
Database administrator privileges can bypass guards; application roles are planned.
Reconciliation compares execution records with a validated clearing CSV and reports
missing records, duplicates, and field mismatches. A local read-only HTTP API
exposes balances and preserved report evidence, including investigation history.

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
docker compose exec -T db psql -U brokerage -d brokerage -v ON_ERROR_STOP=1 < sql/004_seal_entries.sql
docker compose exec -T db psql -U brokerage -d brokerage -v ON_ERROR_STOP=1 < sql/005_reversals.sql
docker compose exec -T db psql -U brokerage -d brokerage -v ON_ERROR_STOP=1 < sql/006_cash_account_pairs.sql
docker compose exec -T db psql -U brokerage -d brokerage -v ON_ERROR_STOP=1 < sql/007_buy_orders.sql
docker compose exec -T db psql -U brokerage -d brokerage -v ON_ERROR_STOP=1 < sql/008_order_cancellation.sql
docker compose exec -T db psql -U brokerage -d brokerage -v ON_ERROR_STOP=1 < sql/009_trade_execution.sql
docker compose exec -T db psql -U brokerage -d brokerage -v ON_ERROR_STOP=1 < sql/010_trade_settlement.sql
docker compose exec -T db psql -U brokerage -d brokerage -v ON_ERROR_STOP=1 < sql/011_reconciliation_reports.sql
docker compose exec -T db psql -U brokerage -d brokerage -v ON_ERROR_STOP=1 < sql/012_investigations.sql
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
docker compose exec -T db psql -U brokerage -d brokerage_test -v ON_ERROR_STOP=1 < sql/004_seal_entries.sql
docker compose exec -T db psql -U brokerage -d brokerage_test -v ON_ERROR_STOP=1 < sql/005_reversals.sql
docker compose exec -T db psql -U brokerage -d brokerage_test -v ON_ERROR_STOP=1 < sql/006_cash_account_pairs.sql
docker compose exec -T db psql -U brokerage -d brokerage_test -v ON_ERROR_STOP=1 < sql/007_buy_orders.sql
docker compose exec -T db psql -U brokerage -d brokerage_test -v ON_ERROR_STOP=1 < sql/008_order_cancellation.sql
docker compose exec -T db psql -U brokerage -d brokerage_test -v ON_ERROR_STOP=1 < sql/009_trade_execution.sql
docker compose exec -T db psql -U brokerage -d brokerage_test -v ON_ERROR_STOP=1 < sql/010_trade_settlement.sql
docker compose exec -T db psql -U brokerage -d brokerage_test -v ON_ERROR_STOP=1 < sql/011_reconciliation_reports.sql
docker compose exec -T db psql -U brokerage -d brokerage_test -v ON_ERROR_STOP=1 < sql/012_investigations.sql
RUN_DB_TESTS=1 ./.venv/bin/python -m unittest discover -s tests -v
```

Tests seed their own accounts, use unique references, and retain test records.
They cover sequential retries, conflicts, partial-write rollback, and two concurrent
identical requests. The concurrent test coordinates worker starts; it does not
guarantee a particular database interleaving or prove all concurrency behavior.

The GitHub Actions workflow provisions a fresh PostgreSQL test database, applies
the migrations, and runs the full suite on pushes and pull requests.

## Local API

```sh
./.venv/bin/python -m uvicorn brokerage.api:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/docs` for interactive documentation. Endpoints:

Open `http://127.0.0.1:8000/` for the local operations dashboard. It reads live
available/reserved cash, pending/settled share positions, recent account-scoped
reports, saved comparisons, and investigation timelines. Select an account and
use View evidence to inspect a run. An operator-resolved break remains visible as
original break evidence; only a comparison with zero original breaks says MATCH.
Balance summaries use a single repeatable-read transaction. Reports are historical
evidence; account balances are live reads, not balances at the report's creation.
The dashboard is plain HTML/CSS/JavaScript served by FastAPI; no Node build is needed.

- `GET /health`: process liveness, not database readiness.
- `GET /accounts/{account_code}/balance`: USD balance as decimal text.
- `GET /accounts/{account_code}/summary`: paired cash balances and share positions.
- `GET /reconciliation/runs?account=...`: latest 50 runs and current investigation counts.
- `GET /reconciliation/runs/{run_id}`: compared snapshots, breaks, and event history.

Unknown resources return 404, invalid report IDs return 422, and database
connection failures return 503 without exposing connection details. HTTP tests
use mocked repository calls; database integration tests separately exercise the
real report reader. The API has no authentication and is intended only for local
development; do not expose it publicly. Stop the server with Control-C.

## Reconciliation demo

After reproducing the guided demo's settled `execution-demo-001` (2 AAPL at
$48 for Alex), run:

```sh
./.venv/bin/python -m brokerage.reconcile_file samples/clearing_match.csv --account customer_alex_cash_liability
./.venv/bin/python -m brokerage.reconcile_file samples/clearing_wrong_quantity.csv --account customer_alex_cash_liability
```

The first matches; the second reports quantity 2 internally versus 3 externally.
These are hand-authored synthetic fixtures, not real clearing records or exports
copied from the internal database. Extra demo executions will produce extra breaks.

The file must contain a complete snapshot of all executions for the named account,
using the same observation point as the current internal state. The internal read
uses a repeatable-read transaction. Historical cutoffs, timestamped external
snapshots and raw input-file persistence are pending.
Pause trading/settlement during this initial demo. A status difference is reported
as a mismatch; the tool does not automatically infer that it is a settlement delay.

Exit codes: 0 means no breaks, 1 means breaks found, and 2 means invalid command
input or CSV input. Unexpected database errors still surface as exceptions.
Reconciliation never repairs ledger balances automatically. Add `--save` to persist
a run's compared record snapshots and breaks. The SHA-256 fingerprints the parsed
clearing records, not the original file bytes; record order and duplicates are
preserved. Report creation time is not a historical trade cutoff. Reports and
break rows reject updates/deletions, but privileged SQL can bypass those protections
or append evidence; application-role restrictions remain future work. Repeated
`--save` commands intentionally create separate runs.

Investigation events append notes and statuses to a break. New breaks start open;
operators move them to investigating, then resolved, and can reopen them by
returning to investigating. Same-status events add further notes. Event references
support identical retries and reject changed contents. Resolution is an operator
declaration, not proof of a corrected external file or a financial repair. Actor
names are supplied by the caller and are not authenticated identities. Original
breaks and prior events are preserved; direct privileged SQL remains outside the
application's workflow guarantees.

## Accounting model

A customer deposit debits the brokerage's bank cash asset and credits its liability
to that customer. Debits increase assets; credits increase liabilities. Debit and
credit do not universally mean subtract and add.

Every journal entry must have at least two positive postings, and its total debits
must equal its total credits. Balanced entries can still contain business mistakes:
balance alone does not prove that an amount or customer is correct.

For this milestone, USD postings accept at most two decimal places. Future trade
calculations will need an explicit precision and rounding policy.
