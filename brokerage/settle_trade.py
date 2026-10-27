"""Manually settle a simulated execution."""

import argparse

from brokerage.settlement import settle_execution


def main() -> None:
    parser = argparse.ArgumentParser(description="Settle a simulated trade execution")
    parser.add_argument("execution_reference")
    args = parser.parse_args()
    try:
        result = settle_execution(args.execution_reference)
    except ValueError as error:
        parser.exit(1, f"Rejected: {error}\n")
    action = "Trade settled" if result.created else "Already settled; no new postings"
    print(f"{action}: {args.execution_reference}")


if __name__ == "__main__":
    main()
