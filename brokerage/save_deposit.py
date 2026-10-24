"""Write a simulated deposit: python -m brokerage.save_deposit REFERENCE AMOUNT."""

import argparse
from decimal import Decimal

from brokerage.ledger import DuplicateReferenceError, JournalEntry, Posting, Side
from brokerage.repository import save_entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Save a simulated Alex deposit")
    parser.add_argument("reference")
    parser.add_argument("amount", type=Decimal)
    args = parser.parse_args()

    entry = JournalEntry(args.reference, (
        Posting("bank_cash", Side.DEBIT, args.amount),
        Posting("customer_alex_cash_liability", Side.CREDIT, args.amount),
    ))
    try:
        result = save_entry(entry)
    except DuplicateReferenceError as error:
        parser.exit(1, f"Rejected: {error}\n")

    if result.created:
        print(f"Saved {entry.reference} as journal entry {result.entry_id}: USD {args.amount:.2f}")
    else:
        print(f"Already recorded: {entry.reference} (entry {result.entry_id}); no new postings")


if __name__ == "__main__":
    main()
