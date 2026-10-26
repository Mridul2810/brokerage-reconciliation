"""Record a simulated full execution at a supplied price."""

import argparse
from decimal import Decimal, InvalidOperation

from brokerage.executions import execute_buy_order


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a full buy-order fill")
    parser.add_argument("execution_reference")
    parser.add_argument("order_reference")
    parser.add_argument("price")
    args = parser.parse_args()
    try:
        result = execute_buy_order(args.execution_reference, args.order_reference, Decimal(args.price))
    except InvalidOperation:
        parser.exit(1, "Rejected: price must be a decimal number\n")
    except (ValueError, TypeError) as error:
        parser.exit(1, f"Rejected: {error}\n")
    action = "Execution recorded; shares pending settlement" if result.created else "Already recorded; no new postings"
    print(f"{action}: {result.reference}")


if __name__ == "__main__":
    main()
