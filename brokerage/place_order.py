"""Create a simulated whole-share buy limit order."""

import argparse
from decimal import Decimal, InvalidOperation

from brokerage.orders import create_buy_order


def main() -> None:
    parser = argparse.ArgumentParser(description="Place a simulated buy limit order")
    parser.add_argument("reference")
    parser.add_argument("available_account")
    parser.add_argument("symbol")
    parser.add_argument("quantity", type=int)
    parser.add_argument("limit_price")
    args = parser.parse_args()

    try:
        result = create_buy_order(
            args.reference, args.available_account, args.symbol,
            args.quantity, Decimal(args.limit_price),
        )
    except InvalidOperation:
        parser.exit(1, "Rejected: limit price must be a decimal number\n")
    except (ValueError, TypeError) as error:
        parser.exit(1, f"Rejected: {error}\n")

    action = "Order created" if result.created else "Already recorded"
    print(f"{action}: {result.reference}; status={result.status}")


if __name__ == "__main__":
    main()
