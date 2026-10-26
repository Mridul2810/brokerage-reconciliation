"""Cancel a simulated buy order and release its reserved cash."""

import argparse

from brokerage.orders import cancel_buy_order


def main() -> None:
    parser = argparse.ArgumentParser(description="Cancel an unexecuted buy order")
    parser.add_argument("reference")
    args = parser.parse_args()
    try:
        result = cancel_buy_order(args.reference)
    except ValueError as error:
        parser.exit(1, f"Rejected: {error}\n")

    action = "Order cancelled; cash released" if result.created else "Already cancelled; no new postings"
    print(f"{action}: {result.reference}")


if __name__ == "__main__":
    main()
