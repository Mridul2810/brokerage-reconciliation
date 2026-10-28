# Verified behavior

Verified locally on October 28, 2026, using Python 3.12 and PostgreSQL 17:

- A separate fresh database accepted all 12 numbered migrations.
- Repeating the migration runner applied zero additional migrations.
- The portfolio demo completed twice, including conflict rejection,
  insufficient-funds rejection, partial-write rollback, trade settlement, and
  reconciliation evidence with investigation events.
- The full suite completed with **77 tests passing and no skips**.
- A database integration test verified that rerunning the portfolio demo preserves
  financial journal-entry count and the customer's cash and positions.

Command used:

```sh
./.venv/bin/python -m brokerage.verify_setup
```

The dashboard had also been checked in the browser for account loading, exact
cash balances, settled shares, matching-report selection, investigation history,
and unknown-account errors with stale balances cleared.

This records observed results, not a throughput benchmark or proof of production
readiness. GitHub Actions must independently pass for the pushed commit; its
status is available in the repository's Actions tab.
