# Brokerage Ledger & Reconciliation Engine

A portfolio project exploring financial correctness and failure recovery in a
simulated brokerage. Simulation only; no real funds or brokerage connection.

## Current milestone

An immutable in-memory model of balanced USD journal entries, plus validation
tests. Entries are not persisted. References are labels, not yet idempotency keys.
Database constraints, duplicate protection, trades, settlement, and reconciliation
are planned, not implemented.

## Run locally

Requires Python 3.12 or later. No external packages are required for this milestone.
Run these commands from this directory:

```sh
python3 -m brokerage.demo
python3 -m unittest discover -s tests -v
```

## Accounting model

A customer deposit debits the brokerage's bank cash asset and credits its liability
to that customer. Debits increase assets; credits increase liabilities. Debit and
credit do not universally mean subtract and add.

Every journal entry must have at least two positive postings, and its total debits
must equal its total credits. Balanced entries can still contain business mistakes:
balance alone does not prove that an amount or customer is correct.

For this milestone, USD postings accept at most two decimal places. Future trade
calculations will need an explicit precision and rounding policy.
