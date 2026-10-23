"""Run with: python3 -m brokerage.demo"""

from decimal import Decimal

from brokerage.ledger import JournalEntry, Posting, Side


deposit = JournalEntry(
    reference="deposit-001",
    postings=(
        Posting("bank_cash", Side.DEBIT, Decimal("1000.00")),
        Posting("customer_alex_cash_liability", Side.CREDIT, Decimal("1000.00")),
    ),
)

print(f"Validated journal entry: {deposit.reference}")
for posting in deposit.postings:
    print(f"{posting.side.value:6}  {posting.account:32}  USD {posting.amount:.2f}")
print("Balanced. This example validates an entry; it does not save it yet.")
