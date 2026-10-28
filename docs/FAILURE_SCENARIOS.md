# Failure scenarios and what they demonstrate

Run the repeatable scenario with:

```sh
./.venv/bin/python -m brokerage.portfolio_demo
```

Run the complete suite, including actual PostgreSQL transactions, with:

```sh
RUN_DB_TESTS=1 ./.venv/bin/python -m unittest discover -s tests -v
```

| Scenario | Expected outcome | Evidence |
|---|---|---|
| Retry a successful deposit | Existing entry returned; no extra postings | Demo and database retry test |
| Reuse a deposit reference with a changed amount | Conflict rejected; original unchanged | Demo and conflict test |
| Fail account lookup after inserting a journal and its first posting | Entire transaction rolls back | Demo and partial-write rollback test |
| Withdraw more than available cash | Reject without a new journal entry | Demo and insufficient-funds test |
| Two withdrawals compete for the same cash | Exactly one succeeds when both cannot be funded | Concurrent withdrawal test |
| A reservation and withdrawal compete | Both use the same available-account lock | Mixed concurrent spending test |
| Retry settlement concurrently | One settlement posting set and one cash payment | Concurrent settlement test |
| Append balanced postings to an old entry | Database trigger rejects the append | Committed-entry test |
| Fill above a limit price | Reject; order stays reserved | Execution limit test |
| Retry cancellation | No second cash release | Cancellation retry test |
| Clearing file has a wrong quantity | Preserve both values as a field mismatch | Reconciliation tests and demo |
| Different trades offset to identical aggregate totals | Per-trade mismatches still detected | Equal-aggregate reconciliation test |
| Clearing file repeats a reference | Report duplicate; do not overwrite copies | CSV and reconciliation tests |
| Live settlement changes after a saved report | Saved evidence keeps its original state | Snapshot-preservation test |

## Five-minute explanation

“I built this to understand brokerage operations and failure handling. Here is a
customer's cash, split into available and reserved balances. A full fill moves the
trade cost to a clearing payable, and settlement clears that payable and reduces
bank cash. Shares move from pending to settled.

“The hard part is coordinating business state and accounting records. Those changes
share one PostgreSQL transaction. Retries compare original contents, and customer
account locks serialize competing spending decisions.

“This clearing input deliberately says three shares where our execution says two.
The reconciliation run preserves both inputs. An investigation adds a history of
operator decisions; a separate matching run supplies evidence for resolution.

“The demo and test suite exercise these scenarios. This is a synthetic local
simulation, with whole-share buys and manual settlement—not a real broker.”

## Limits of the evidence

The rollback demonstration is a controlled application exception after a partial
write, not a process-kill or power-loss experiment. Concurrent tests coordinate
worker starts but do not exhaust all schedules. There is no throughput benchmark,
real-market integration, production authentication, or external settlement transfer.
Resolution notes cite later reports as text; that link is not machine-enforced.

## Troubleshooting

- `command not found: docker`: launch Docker Desktop and check the CLI path.
- Connection refused or HTTP 503: check `docker compose ps` and local port 5433.
- Missing password: configure the ignored `.env` file from `.env.example`.
- `relation already exists`: do not rerun a manual migration; inspect schema state.
- Changed applied migration hash: restore the original migration; add a new one.
- HTTP 404 for account summary: use a configured available-cash account, not bank cash.
- `dquote>` in Terminal: press Control-C, then paste the complete command.
- Reconciliation exit code 1: inspect reported breaks; this is expected for faulty input.

Never reset a database to hide an unexplained error. Keep the failed inputs and
diagnostic output, fix the cause, and rerun the relevant checks.
