"""Reserve simulated customer cash from the command line."""

import argparse
from decimal import Decimal, InvalidOperation

from brokerage.reservations import reserve_cash


def main() -> None:
    parser = argparse.ArgumentParser(description="Reserve simulated cash for a future order")
    parser.add_argument("reference")
    parser.add_argument("available_account")
    parser.add_argument("amount")
    args = parser.parse_args()

    try:
        amount = Decimal(args.amount)
        result = reserve_cash(args.reference, args.available_account, amount)
    except InvalidOperation:
        parser.exit(1, "Rejected: amount must be a decimal number\n")
    except ValueError as error:
        parser.exit(1, f"Rejected: {error}\n")

    if result.created:
        print(f"Cash reserved: {args.reference} (entry {result.entry_id}), USD {amount:.2f}")
    else:
        print(f"Already recorded: {args.reference} (entry {result.entry_id}); no new postings")


if __name__ == "__main__":
    main()
