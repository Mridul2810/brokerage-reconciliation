"""Submit a simulated cash withdrawal from the command line."""

import argparse
from decimal import Decimal, InvalidOperation

from brokerage.withdrawals import withdraw


def main() -> None:
    parser = argparse.ArgumentParser(description="Withdraw simulated customer cash")
    parser.add_argument("reference")
    parser.add_argument("customer", help="Customer liability account code")
    parser.add_argument("amount", help="Positive USD amount, for example 80.00")
    args = parser.parse_args()

    try:
        amount = Decimal(args.amount)
        result = withdraw(args.reference, args.customer, amount)
    except InvalidOperation:
        parser.exit(1, "Rejected: amount must be a decimal number\n")
    except ValueError as error:
        parser.exit(1, f"Rejected: {error}\n")

    if result.created:
        print(f"Withdrawal saved: {args.reference} (entry {result.entry_id}), USD {amount:.2f}")
    else:
        print(f"Already recorded: {args.reference} (entry {result.entry_id}); no new postings")


if __name__ == "__main__":
    main()
