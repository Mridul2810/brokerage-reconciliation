"""Append an investigation note and operator-declared status."""

import argparse

from brokerage.investigations import record_event


def main() -> None:
    parser = argparse.ArgumentParser(description="Append a reconciliation investigation event")
    parser.add_argument("reference", help="Unique reference for this note/retry")
    parser.add_argument("break_id", type=int)
    parser.add_argument("--status", required=True, choices=("open", "investigating", "resolved"))
    parser.add_argument("--actor", required=True)
    parser.add_argument("--note", required=True)
    args = parser.parse_args()
    try:
        result = record_event(args.reference, args.break_id, args.status, args.actor, args.note)
    except ValueError as error:
        parser.exit(1, f"Rejected: {error}\n")
    action = "Investigation event saved" if result.created else "Already recorded; no new event"
    print(f"{action}: {result.event_id}")


if __name__ == "__main__":
    main()
