"""Run with: python3 -m brokerage.demo"""

from decimal import Decimal

from brokerage.ledger import (
    AccountType, DuplicateReferenceError, JournalEntry, Ledger, Posting, Side,
    account_balance,
)


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
print("Balanced. Now submit the entry to an in-memory ledger.")

book = Ledger()
first_result = book.post(deposit)
retry_result = book.post(deposit)

print(f"First submission accepted as new: {first_result}")
print(f"Retry accepted as new: {retry_result}")
print(f"Stored journal entries: {len(book.entries)}")

conflicting_deposit = JournalEntry(
    reference="deposit-001",
    postings=(
        Posting("bank_cash", Side.DEBIT, Decimal("2000.00")),
        Posting("customer_alex_cash_liability", Side.CREDIT, Decimal("2000.00")),
    ),
)

try:
    book.post(conflicting_deposit)
except DuplicateReferenceError as error:
    print(f"Conflicting retry rejected: {error}")

alex_balance = account_balance(
    book.entries, "customer_alex_cash_liability", AccountType.LIABILITY,
)
print(f"Alex's cash balance: USD {alex_balance:.2f}")
print("In-memory demonstration only: entries disappear when this process exits.")
