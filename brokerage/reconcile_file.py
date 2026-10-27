"""Compare a full-account clearing snapshot with current internal executions."""

import argparse
from pathlib import Path

from brokerage.clearing import load_internal_trades, read_clearing_csv
from brokerage.reconciliation import reconcile
from brokerage.reports import save_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile a simulated full-account clearing CSV")
    parser.add_argument("file", type=Path)
    parser.add_argument("--account", required=True)
    parser.add_argument("--save", action="store_true", help="Save compared records and breaks as a report")
    args = parser.parse_args()
    try:
        clearing = read_clearing_csv(args.file, args.account)
        internal = load_internal_trades(args.account)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    breaks = reconcile(internal, clearing)
    print(f"Scope: {args.account}; all executions, current internal snapshot")
    print(f"Internal records: {len(internal)}; clearing records: {len(clearing)}")
    if args.save:
        run_id = save_report(args.account, args.file.name, internal, clearing)
        print(f"Saved reconciliation run: {run_id}")
    if not breaks:
        print("MATCH: no reconciliation breaks")
        return
    for item in breaks:
        print(f"{item.kind}: {item.reference} | {item.field} | internal={item.internal} | clearing={item.clearing}")
    print(f"BREAKS: {len(breaks)}; no financial records changed")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
